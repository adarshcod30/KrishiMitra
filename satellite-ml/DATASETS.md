# Datasets — where to get real data

The pipeline runs on **simulated** data by default, so you need nothing to
demo it. To run on a **real pilot command area**, pull the layers below and set
`data.source: gee` (easiest) or load your own GeoTIFFs into a `DataCube`.

Everything here is **free / open** unless noted. Nothing in this repo requires a
paid dataset.

---

## 1. Optical satellite data (vegetation vigour, NDVI/EVI/NDWI, phenology)

| Source | Resolution | Access | Notes |
|---|---|---|---|
| **Sentinel-2 L2A** | 10–20 m | Google Earth Engine `COPERNICUS/S2_SR_HARMONIZED`; [Copernicus Browser](https://browser.dataspace.copernicus.eu/) | **Recommended.** Already wired in `gee_ingest.py`. |
| **Landsat 8/9 L2** | 30 m | GEE `LANDSAT/LC08/C02/T1_L2`; [USGS EarthExplorer](https://earthexplorer.usgs.gov/) | Longer archive, coarser. |
| **MODIS MOD13Q1 NDVI** | 250 m | GEE `MODIS/061/MOD13Q1` | 16-day NDVI, great for multi-year VCI baselines. |
| **ISRO LISS-III / LISS-IV / AWiFS** | 5.8–56 m | [Bhoonidhi](https://bhoonidhi.nrsc.gov.in/) / [Bhuvan](https://bhuvan.nrsc.gov.in/) | India-specific; free with NRSC login. LISS-IV = high-res crop mapping. |

## 2. Microwave SAR data (all-weather, soil moisture, crop structure)

| Source | Resolution | Access | Notes |
|---|---|---|---|
| **Sentinel-1 GRD (VV/VH)** | 10 m | GEE `COPERNICUS/S1_GRD`; Copernicus | **Recommended.** Wired in `gee_ingest.py`. |
| **ISRO EOS-04 / RISAT-1A** | 6–25 m | [Bhoonidhi](https://bhoonidhi.nrsc.gov.in/) | Indian C-band SAR. |
| **NISAR (L/S-band)** | ~10 m | ISRO/NASA portals (post-launch) | Upcoming; the pipeline's VV/VH slots accept dual-pol SAR directly. |

## 3. Ancillary & meteorological data (ET0, rainfall, soil, canal command)

| Source | Access | Notes |
|---|---|---|
| **ERA5-Land daily** (ET0 proxy, precip) | GEE `ECMWF/ERA5_LAND/DAILY_AGGR` | Wired in `gee_ingest.py`. |
| **IMD gridded rainfall / temperature** | [IMD Pune](https://www.imdpune.gov.in/) | India, 0.25°. |
| **CHIRPS rainfall** | GEE `UCSB-CHG/CHIRPS/DAILY` | 5 km daily precipitation. |
| **FAO-56 crop coefficients (Kc)** | [FAO Irrigation & Drainage Paper 56](https://www.fao.org/3/x0490e/x0490e00.htm) | Already encoded per crop in `config/pilot_area.yaml`. |
| **Soil (FC, WP, texture)** | [SoilGrids](https://soilgrids.org/) · [NBSS&LUP](https://www.nbsslup.in/) | For per-pixel water-holding capacity. |
| **Canal command boundaries** | State irrigation dept / [WRIS](https://indiawris.gov.in/) | Defines the AOI and rotation units. |

## 4. Ground-truth crop labels (for training & validation)

Field points are the one thing satellites can't give you. Options:

| Source | What it gives | Access |
|---|---|---|
| **Your own field survey / GPS points** | crop + location + date | best quality; even 100–200 points/crop is enough |
| **FASAL / CCE crop-cutting data (India)** | crop yield & type points | via [DES / Agriculture Statistics](https://desagri.gov.in/) |
| **Kaggle — "Crop Recommendation Dataset"** | soil/climate → crop (tabular) | for the *agronomic* model, not pixel labels |
| **Kaggle — "EuroSAT" / "So2Sat"** | labelled Sentinel-2 patches | pretraining / transfer for the CNN path |
| **Radiant MLHub — agricultural datasets** | labelled S1/S2 crop tiles (incl. some India/Africa) | [mlhub.earth](https://mlhub.earth/) |
| **ESA WorldCereal** | global crop-type reference | [esa-worldcereal.org](https://esa-worldcereal.org/) |

For the tabular soil→crop advisory in the **main app** (`ml-service/`), the
included `Crop_dataset.csv` mirrors the popular Kaggle *Crop Recommendation*
schema (N, P, K, temperature, humidity, pH, rainfall → crop).

---

## Fastest path to a real run

1. `pip install earthengine-api geemap && earthengine authenticate`
2. In `config/pilot_area.yaml`: set `data.source: gee` and `pilot.aoi_bbox`
   to your command area.
3. (Optional) provide ground-truth points as an EE `FeatureCollection` and wire
   them into `sample_ground_truth`. Without labels you still get NDVI/SAR
   indices, phenology, stress and the FAO-56 advisory — only supervised
   crop-type classification needs labels.
4. `python -m krishimitra_rs.pipeline --source gee`

**Data-readiness note:** Sentinel-1/2, Landsat and MODIS are open and
cloud-hosted (GEE), so a real pilot needs only an Earth Engine account and a few
ground-truth points — well within a 30-hour hackathon.
