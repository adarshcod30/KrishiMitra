"""FAO-56 root-zone water balance -> 8-day crop water deficit.

For every pixel and 8-day composite we estimate the **root-zone soil-water
deficit** (depletion Dr, in mm below field capacity) and the **crop water
demand** (ETc):

* **ETc = Kc x ET0** — demand flux, with Kc from the satellite-detected stage.
* **Root-zone depletion** is *prognostic*: the FAO-56 single-bucket is
  integrated forward in time,

      Dr[t] = clip(Dr[t-1] + ETc[t] - Peff[t] - Irr[t], 0, TAW)

  so today's deficit is the accumulated history of demand minus supply, exactly
  as FAO-56 Ch. 8 prescribes — not a snapshot read off a single image.
* **Satellite assimilation.** The command area's irrigation deliveries are not
  observed, so they are *inferred* from the model-observation discrepancy: when
  the satellite says the root zone is wetter than the bucket predicts, water
  must have been applied. That inferred depth enters the balance as a one-sided
  source term (irrigation can only add water), and the analysed state is a
  model-dominant blend

      Dr = (1 - w) * Dr_model + w * Dr_obs      with w = 0.25

  i.e. the observation is a *weak nudge*, never the primary estimate.
* **Observation operator.** The wetness proxy blends SAR **VV** backscatter
  (all-weather surface soil moisture, speckle-filtered) with optical **NDWI**
  (canopy water). The NDWI term is weighted by **canopy cover** so bare or
  early-season ground — which is optically "dry" simply because there is no
  canopy — cannot be mistaken for a water-stressed crop. On bare soil the
  estimate falls back entirely on SAR.
* **Effective rainfall** (USDA-SCS) is tracked for the command-area balance.

Two quantities feed the advisory:
  - ``depletion``  (mm) and ``depletion_ratio`` (Dr / RAW) — the *state*, i.e.
    how close the crop is to water stress (ratio >= 1 => readily-available water
    exhausted);
  - ``ir_net`` (mm) — the net depth to refill the root zone to a comfortable
    level, and its gross equivalent after application efficiency.

Depletion is a stock (a depth), so it can legitimately exceed a single period's
ETc; it is reported against the RAW threshold rather than against the ET flux.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter, uniform_filter1d

from ..config import Config
from .phenology_stage import _crop_param_maps

# Absolute SAR VV -> soil-wetness calibration (dB). Dry bare soil ~ -15 dB,
# saturated ~ -8 dB for C-band VV at moderate incidence. Tune per sensor/AOI.
_VV_DRY_DB = -15.0
_VV_WET_DB = -8.0

# Absolute NDWI/NDMI -> canopy-water calibration for a *closed* canopy.
_NDWI_DRY = 0.05
_NDWI_WET = 0.45

# NDVI end-members used to turn NDVI into fractional canopy cover.
_NDVI_BARE = 0.15
_NDVI_FULL = 0.75

# Max weight the canopy-water (NDWI) term may take, reached at full cover.
# Below full cover it is scaled by fCover, so bare soil is read from SAR alone.
_NDWI_MAX_WEIGHT = 0.45

# Speckle/noise reduction on the wetness proxy: a (2*_SPECKLE_RADIUS+1)^2 boxcar
# (multi-look) in space plus a 3-composite boxcar in time (soil lags rainfall).
_SPECKLE_RADIUS = 2
_TIME_WINDOW = 3

# Data-assimilation gains (defaults; overridable from config.advisory).
_ASSIM_WEIGHT = 0.25        # weight of the observation in the analysis blend
_IRR_INFERENCE_GAIN = 0.5   # share of the model-obs discrepancy read as irrigation


@dataclass
class WaterBalanceResult:
    etc: np.ndarray             # (T, H, W) crop water demand, mm/composite
    peff: np.ndarray            # (T,) effective rainfall over command area, mm
    depletion: np.ndarray       # (T, H, W) root-zone depletion Dr, mm
    depletion_ratio: np.ndarray # (T, H, W) Dr / RAW (>=1 => stressed)
    ir_net: np.ndarray          # (T, H, W) net irrigation requirement, mm
    ir_gross: np.ndarray        # (T, H, W) gross (after efficiency), mm
    raw_map: np.ndarray         # (H, W) readily-available water, mm
    taw_map: np.ndarray         # (H, W) total available water, mm
    etc_area_series: list       # command-area mean ETc per composite
    depletion_area_series: list # command-area mean Dr per composite
    raw_area_mean: float        # command-area mean RAW (threshold line)
    irrigation_inferred: np.ndarray | None = None  # (T, H, W) assimilated irrigation, mm


def _effective_rain(p_mm: np.ndarray) -> np.ndarray:
    p = np.clip(p_mm, 0, None)
    return np.clip(np.where(p < 250, p * (125 - 0.2 * p) / 125.0, 125 + 0.1 * p), 0, p)


def canopy_cover(ndvi: np.ndarray) -> np.ndarray:
    """Fractional canopy cover from NDVI (linear between bare and full-cover)."""
    return np.clip((ndvi - _NDVI_BARE) / (_NDVI_FULL - _NDVI_BARE), 0.0, 1.0)


def observed_wetness(indices: dict) -> np.ndarray:
    """Absolute root-zone wetness proxy in [0, 1] from SAR VV + optical NDWI.

    The canopy-water (NDWI) term is weighted by fractional canopy cover, so a
    bare or barely-emerged pixel is read from SAR backscatter alone. Without
    that weighting, low vegetation is indistinguishable from dry soil and the
    advisory fires on early-season ground where the crop is not stressed.
    """
    vv = np.asarray(indices["vv"], dtype=np.float32)
    ndwi = np.asarray(indices["ndwi"], dtype=np.float32)
    ndvi = np.asarray(indices["ndvi"], dtype=np.float32)

    if _SPECKLE_RADIUS:                     # multi-look the SAR before calibrating
        k = 2 * _SPECKLE_RADIUS + 1
        vv = uniform_filter(vv, size=(1, k, k), mode="nearest")

    vv_wet = np.clip((vv - _VV_DRY_DB) / (_VV_WET_DB - _VV_DRY_DB), 0, 1)
    ndwi_wet = np.clip((ndwi - _NDWI_DRY) / (_NDWI_WET - _NDWI_DRY), 0, 1)

    w_canopy = _NDWI_MAX_WEIGHT * canopy_cover(ndvi)
    wetness = (1.0 - w_canopy) * vv_wet + w_canopy * ndwi_wet
    return uniform_filter1d(wetness, size=_TIME_WINDOW, axis=0, mode="nearest")


def water_balance(cube, kc: np.ndarray, indices: dict, crop_map: np.ndarray, cfg: Config) -> WaterBalanceResult:
    T, H, W = kc.shape
    soil = cfg.meteorology["soil"]
    taw_per_m = soil["total_available_water_mm_m"]

    p = _crop_param_maps(crop_map, cfg, ["root_depth_m", "depletion_p"])
    zr = np.clip(p["root_depth_m"], 0.2, None)
    dp = np.clip(p["depletion_p"], 0.2, 0.8)
    taw = taw_per_m * zr                                        # (H, W) mm
    raw = np.clip(dp * taw, 1e-3, None)

    # meteorology -> composites
    et0_c = np.asarray(cube.extra["et0_composite"]) if "et0_composite" in cube.extra else \
        np.full(T, cfg.meteorology["et0_mm_day_mean"] * cfg.composite_days)
    rain_c = np.asarray(cube.extra["rain_composite"]) if "rain_composite" in cube.extra else \
        np.zeros(T)
    peff = _effective_rain(rain_c)
    etc = kc * et0_c[:, None, None]

    # --- satellite observation of root-zone wetness -> observed depletion ----
    wetness = observed_wetness(indices)
    dr_obs = np.clip((1.0 - wetness) * taw[None], 0.0, taw[None])

    # --- prognostic FAO-56 bucket with weak satellite assimilation ----------
    w_obs = float(cfg.advisory.get("assimilation_weight", _ASSIM_WEIGHT))
    gain = float(cfg.advisory.get("irrigation_inference_gain", _IRR_INFERENCE_GAIN))

    depletion = np.zeros((T, H, W), np.float32)
    irr_inferred = np.zeros((T, H, W), np.float32)
    dr = dr_obs[0].copy()                       # warm start from the first image
    for t in range(T):
        # 1. forecast: yesterday's stock + demand - effective rainfall
        dr_forecast = dr + etc[t] - peff[t]
        # 2. infer the (unobserved) irrigation delivered: the satellite reads
        #    wetter than the bucket predicts => water was applied. One-sided:
        #    irrigation can only *add* water, never remove it.
        irr = np.clip(dr_forecast - dr_obs[t], 0.0, None) * gain
        dr_model = np.clip(dr_forecast - irr, 0.0, taw)
        # 3. analysis: model-dominant blend, observation as a weak nudge
        dr = np.clip((1.0 - w_obs) * dr_model + w_obs * dr_obs[t], 0.0, taw)
        depletion[t] = dr
        irr_inferred[t] = irr

    depletion_ratio = (depletion / raw[None]).astype(np.float32)

    # net irrigation to refill to a comfortable level (half of RAW below FC)
    ir_net = np.clip(depletion - 0.5 * raw[None], 0.0, None)
    ir_net[:, crop_map == 0] = 0.0
    eff = float(cfg.advisory["irrigation_efficiency"])
    ir_gross = ir_net / max(eff, 1e-3)

    crop_mask = crop_map != 0
    etc_series = [float(etc[t][crop_mask].mean()) if crop_mask.any() else 0.0 for t in range(T)]
    dep_series = [float(depletion[t][crop_mask].mean()) if crop_mask.any() else 0.0 for t in range(T)]
    raw_mean = float(raw[crop_mask].mean()) if crop_mask.any() else float(raw.mean())

    return WaterBalanceResult(
        etc=etc.astype(np.float32),
        peff=peff.astype(np.float32),
        depletion=depletion,
        depletion_ratio=depletion_ratio,
        ir_net=ir_net.astype(np.float32),
        ir_gross=ir_gross.astype(np.float32),
        raw_map=raw.astype(np.float32),
        taw_map=taw.astype(np.float32),
        etc_area_series=etc_series,
        depletion_area_series=dep_series,
        raw_area_mean=raw_mean,
        irrigation_inferred=irr_inferred,
    )
