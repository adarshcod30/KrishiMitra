"""FAO-56 root-zone water balance -> 8-day crop water deficit.

For every pixel and 8-day composite we estimate the **root-zone soil-water
deficit** (depletion Dr, in mm below field capacity) and the **crop water
demand** (ETc):

* **ETc = Kc x ET0** — demand flux, with Kc from the satellite-detected stage.
* **Root-zone wetness** is read directly from the satellite: an *absolute*
  (not cohort-relative) proxy blends SAR **VV** backscatter (all-weather soil
  moisture) with optical **NDWI** (canopy water). Depletion Dr = (1 - wetness) x TAW.
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
from scipy.ndimage import uniform_filter1d

from ..config import Config
from .phenology_stage import _crop_param_maps

# Absolute SAR VV -> soil-wetness calibration (dB). Dry bare soil ~ -15 dB,
# saturated ~ -8 dB for C-band VV at moderate incidence. Tune per sensor/AOI.
_VV_DRY_DB = -15.0
_VV_WET_DB = -8.0


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


def _effective_rain(p_mm: np.ndarray) -> np.ndarray:
    p = np.clip(p_mm, 0, None)
    return np.clip(np.where(p < 250, p * (125 - 0.2 * p) / 125.0, 125 + 0.1 * p), 0, p)


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

    # --- absolute root-zone wetness from satellite (SAR VV + optical NDWI) ---
    vv = indices["vv"]
    ndwi = indices["ndwi"]
    vv_wet = np.clip((vv - _VV_DRY_DB) / (_VV_WET_DB - _VV_DRY_DB), 0, 1)
    ndwi_wet = np.clip(ndwi / 0.6, 0, 1)
    wetness = 0.55 * vv_wet + 0.45 * ndwi_wet
    wetness = uniform_filter1d(wetness, size=3, axis=0, mode="nearest")   # soil lag

    depletion = (1.0 - wetness) * taw[None]
    depletion = np.clip(depletion, 0.0, taw[None]).astype(np.float32)
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
    )
