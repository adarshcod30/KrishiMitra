"""Spectral (optical) and backscatter (SAR) index time series.

All indices are returned as ``(T, H, W)`` stacks. Optical indices are computed
on a temporally gap-filled reflectance stack (clouds interpolated away) so the
downstream phenology/classification never sees NaNs; SAR indices need no
gap-fill (all-weather).

Indices
-------
optical : NDVI (vigour), EVI (high-biomass, soil/atmosphere resistant),
          GNDVI (chlorophyll), NDWI/NDMI (canopy water — key for moisture stress)
sar     : RVI (radar vegetation index), CR = VH/VV cross-ratio (both from linear
          power), and VV/VH themselves passed through for temporal features.
"""
from __future__ import annotations

import numpy as np

from ..data.ard import DataCube, composite_gapfill

OPTICAL_INDEX_NAMES = ("ndvi", "evi", "gndvi", "ndwi")
SAR_INDEX_NAMES = ("vv", "vh", "cr", "rvi")
ALL_INDEX_NAMES = OPTICAL_INDEX_NAMES + SAR_INDEX_NAMES


def _safe_ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    return num / np.where(np.abs(den) < 1e-6, 1e-6, den)


def _db_to_linear(db: np.ndarray) -> np.ndarray:
    return np.power(10.0, db / 10.0)


def compute_indices(cube: DataCube, gapfill: bool = True) -> dict[str, np.ndarray]:
    """Return a dict of ``(T, H, W)`` index stacks keyed by :data:`ALL_INDEX_NAMES`."""
    red = cube.optical["red"].astype(np.float32)
    nir = cube.optical["nir"].astype(np.float32)
    green = cube.optical["green"].astype(np.float32)
    swir1 = cube.optical["swir1"].astype(np.float32)

    if gapfill:
        red = composite_gapfill(red, cube.cloud_mask)
        nir = composite_gapfill(nir, cube.cloud_mask)
        green = composite_gapfill(green, cube.cloud_mask)
        swir1 = composite_gapfill(swir1, cube.cloud_mask)

    ndvi = _safe_ratio(nir - red, nir + red)
    # EVI (Huete et al.): G=2.5, C1=6, C2=7.5, L=1 on reflectance.
    evi = 2.5 * _safe_ratio(nir - red, nir + 6.0 * red - 7.5 * green + 1.0)
    gndvi = _safe_ratio(nir - green, nir + green)
    # NDWI/NDMI (Gao) — canopy water content, drops early under moisture stress.
    ndwi = _safe_ratio(nir - swir1, nir + swir1)

    vv_db = cube.sar["vv"].astype(np.float32)
    vh_db = cube.sar["vh"].astype(np.float32)
    vv_lin = _db_to_linear(vv_db)
    vh_lin = _db_to_linear(vh_db)
    cr = _safe_ratio(vh_lin, vv_lin)                    # cross-ratio (linear)
    rvi = _safe_ratio(4.0 * vh_lin, vv_lin + vh_lin)    # radar vegetation index

    return {
        "ndvi": np.clip(ndvi, -1, 1).astype(np.float32),
        "evi": np.clip(evi, -1, 1).astype(np.float32),
        "gndvi": np.clip(gndvi, -1, 1).astype(np.float32),
        "ndwi": np.clip(ndwi, -1, 1).astype(np.float32),
        "vv": vv_db,
        "vh": vh_db,
        "cr": cr.astype(np.float32),
        "rvi": np.clip(rvi, 0, 2).astype(np.float32),
    }
