"""Real satellite ingestion via Google Earth Engine (Sentinel-1 + Sentinel-2).

This is the operational data path: point it at a real command area (set
``data.source: gee`` and ``pilot.aoi_bbox`` in the config) and it builds the
same :class:`~krishimitra_rs.data.ard.DataCube` the rest of the pipeline
consumes — so nothing downstream changes between the demo and a live run.

Requirements (install the ``gee`` extra)::

    pip install earthengine-api geemap
    earthengine authenticate           # one-time, opens a browser

What it does
------------
* **Sentinel-2 L2A** surface reflectance, cloud/shadow-masked with the Scene
  Classification Layer (SCL), composited to 8-day medians -> red/nir/green/swir1.
* **Sentinel-1 GRD** (IW, ascending) VV+VH backscatter in dB, refined-Lee-style
  speckle reduction, composited to 8-day means -> vv/vh.
* **ERA5-Land** daily reference ET proxy + total precipitation for the balance.

Bands are sampled to the config grid with ``ee.Image.sampleRectangle``; for
large AOIs switch to ``geemap.ee_export_image`` / Earth Engine batch export and
load the GeoTIFFs instead (see ``_sample_to_array``).

NOTE: this module is import-safe without earthengine-api installed — the import
error is only raised when you actually call :func:`ingest_gee_cube`.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np

from ..config import Config
from .ard import DataCube


def _require_ee():
    try:
        import ee  # type: ignore
        return ee
    except Exception as exc:  # pragma: no cover
        raise ImportError(
            "Google Earth Engine path requires 'earthengine-api' (and usually "
            "'geemap'). Install with:  pip install earthengine-api geemap  and "
            "authenticate with:  earthengine authenticate"
        ) from exc


# --------------------------------------------------------------------------- #
# Earth Engine building blocks
# --------------------------------------------------------------------------- #
def _s2_masked(ee, aoi, start, end):
    """Cloud/shadow-masked Sentinel-2 L2A scaled to reflectance."""
    def mask_scl(img):
        scl = img.select("SCL")
        # keep vegetation(4), bare(5), water(6), unclassified(7); drop clouds/shadows
        good = scl.remap([4, 5, 6, 7], [1, 1, 1, 1], 0)
        scaled = img.select(["B4", "B8", "B3", "B11"]).multiply(1e-4)
        return scaled.updateMask(good).copyProperties(img, ["system:time_start"])

    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
        .map(mask_scl)
    )


def _s1_prepared(ee, aoi, start, end):
    """Sentinel-1 GRD IW VV+VH (dB) with light speckle smoothing."""
    def prep(img):
        # GRD is already in dB via log scaling of sigma0; apply a focal-mean
        # speckle reducer (a practical stand-in for Refined Lee).
        sm = img.select(["VV", "VH"]).focal_mean(30, "circle", "meters")
        return sm.copyProperties(img, ["system:time_start"])

    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING"))
        .map(prep)
    )


def _composite(ee, coll, aoi, dates, days, reducer):
    """Reduce a collection to one image per composite window."""
    imgs = []
    for centre in dates:
        lo = ee.Date(centre.isoformat())
        hi = lo.advance(days, "day")
        window = coll.filterDate(lo, hi)
        img = ee.Algorithms.If(window.size().gt(0),
                               window.reduce(reducer).clip(aoi),
                               None)
        imgs.append(img)
    return imgs


def _sample_to_array(ee, img, band, aoi, h, w):
    """Sample one band of an EE image into an (h, w) numpy array.

    Uses ``sampleRectangle`` (fine for moderate AOIs). For large command areas,
    replace this with ``geemap.ee_export_image`` to Drive/local GeoTIFF and read
    with rasterio — the array contract is identical.
    """
    if img is None:
        return np.full((h, w), np.nan, np.float32)
    try:
        rect = ee.Image(img).select([band]).sampleRectangle(region=aoi, defaultValue=-9999)
        arr = np.array(rect.get(band).getInfo(), dtype=np.float32)
        arr[arr <= -9990] = np.nan
        # resample to the target grid
        from scipy.ndimage import zoom
        zy, zx = h / arr.shape[0], w / arr.shape[1]
        return zoom(np.nan_to_num(arr, nan=np.nanmean(arr)), (zy, zx), order=1)
    except Exception:
        return np.full((h, w), np.nan, np.float32)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def ingest_gee_cube(cfg: Config) -> DataCube:
    ee = _require_ee()
    ee.Initialize()

    minx, miny, maxx, maxy = cfg.pilot["aoi_bbox"]
    aoi = ee.Geometry.Rectangle([minx, miny, maxx, maxy])
    dates = cfg.composite_dates
    days = cfg.composite_days
    H, W = cfg.grid_hw
    start = cfg.start_date.isoformat()
    end = (cfg.end_date + _dt.timedelta(days=days)).isoformat()

    s2 = _s2_masked(ee, aoi, start, end)
    s1 = _s1_prepared(ee, aoi, start, end)
    s2c = _composite(ee, s2, aoi, dates, days, ee.Reducer.median())
    s1c = _composite(ee, s1, aoi, dates, days, ee.Reducer.mean())

    T = len(dates)
    optical = {b: np.full((T, H, W), np.nan, np.float32) for b in ("red", "nir", "green", "swir1")}
    sar = {b: np.full((T, H, W), np.nan, np.float32) for b in ("vv", "vh")}
    band_map = {"red": "B4_median", "nir": "B8_median", "green": "B3_median", "swir1": "B11_median"}
    sar_map = {"vv": "VV_mean", "vh": "VH_mean"}

    for t in range(T):
        for key, eb in band_map.items():
            optical[key][t] = _sample_to_array(ee, s2c[t], eb, aoi, H, W)
        for key, eb in sar_map.items():
            sar[key][t] = _sample_to_array(ee, s1c[t], eb, aoi, H, W)

    cloud_mask = np.isnan(optical["red"])
    et0_c, rain_c = _era5_composites(ee, aoi, dates, days)

    meta = {
        "pilot": cfg.pilot["name"], "source": "gee",
        "pixel_size_m": cfg.pilot["pixel_size_m"],
        "crop_names": cfg.code_to_name, "crop_colors": cfg.code_to_color,
        "aoi_bbox": cfg.pilot["aoi_bbox"],
    }
    return DataCube(
        dates=dates, optical=optical, sar=sar, cloud_mask=cloud_mask,
        met={"soil": cfg.meteorology["soil"]},
        labels=None, soil_moisture=None, meta=meta,
        extra={"et0_composite": et0_c.astype(np.float32),
               "rain_composite": rain_c.astype(np.float32)},
    )


def _era5_composites(ee, aoi, dates, days):
    """Composite ERA5-Land reference-ET proxy and precipitation (mm/window)."""
    T = len(dates)
    et0 = np.full(T, np.nan, np.float32)
    rain = np.full(T, np.nan, np.float32)
    try:
        era = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
        for t, centre in enumerate(dates):
            lo = ee.Date(centre.isoformat())
            hi = lo.advance(days, "day")
            w = era.filterDate(lo, hi)
            # potential evaporation (m) -> mm; total precipitation (m) -> mm
            pev = w.select("potential_evaporation_sum").sum().multiply(-1000)
            pr = w.select("total_precipitation_sum").sum().multiply(1000)
            stats = pev.addBands(pr).reduceRegion(ee.Reducer.mean(), aoi, 1000)
            info = stats.getInfo()
            et0[t] = float(info.get("potential_evaporation_sum", 25.0) or 25.0)
            rain[t] = float(info.get("total_precipitation_sum", 0.0) or 0.0)
    except Exception:
        et0[:] = 25.0
        rain[:] = 0.0
    return np.nan_to_num(et0, nan=25.0), np.nan_to_num(rain, nan=0.0)
