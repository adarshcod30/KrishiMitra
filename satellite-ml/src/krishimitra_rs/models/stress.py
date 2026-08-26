"""Phenology-aware moisture-stress detection from optical + SAR signals.

The detector fuses three physically-distinct stress signals and interprets them
*by growth stage* (the same depletion is tolerable at maturity but critical at
flowering):

* **VCI** — Vegetation Condition Index from NDVI. Classic VCI normalises a
  pixel against its multi-year min/max for that date; with a single season we
  use the operational surrogate of the **crop-and-date cohort** (how this pixel
  compares to healthy peers of the same crop on the same date). The multi-year
  formula is a drop-in replacement once an NDVI archive is available.
* **OWC** — optical canopy-water condition from NDWI/NDMI (water stress shows in
  canopy water before it shows in greenness).
* **SMI** — microwave Soil-Moisture Index from SAR VV backscatter (all-weather;
  the only signal available under monsoon cloud).

Fused condition -> stage-weighted stress score -> 4-class stress map
(None / Mild / Moderate / Severe), per 8-day composite.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import Config
from ..features.phenology import STAGE_NAMES

STRESS_CLASS_NAMES = {0: "None", 1: "Mild", 2: "Moderate", 3: "Severe"}


@dataclass
class StressResult:
    condition: np.ndarray          # (T, H, W) fused condition [0 bad .. 1 good]
    stress_class: np.ndarray       # (T, H, W) int 0..3
    vci: np.ndarray                # (T, H, W) vegetation condition index
    smi: np.ndarray                # (T, H, W) SAR soil-moisture index
    stage: np.ndarray              # (T, H, W) growth-stage codes
    season_peak_class: np.ndarray  # (H, W) worst stress class during crop period
    latest_class: np.ndarray       # (H, W) stress class at most recent composite
    area_timeseries: dict          # class -> list over T of area fraction
    validation: dict = field(default_factory=dict)


def _cohort_condition(stack, crop_map, codes, low=5, high=95) -> np.ndarray:
    """Normalise a value stack to [0,1] within each crop-and-date cohort.

    For every crop and every composite, map the cohort's ``low``/``high``
    percentiles to 0/1 — a pixel near its healthy peers' maximum scores ~1.
    """
    T = stack.shape[0]
    out = np.zeros_like(stack, dtype=np.float32)
    for code in codes:
        m = crop_map == code
        if not m.any():
            continue
        for t in range(T):
            vals = stack[t][m]
            lo, hi = np.percentile(vals, [low, high])
            if hi - lo < 1e-4:
                out[t][m] = 1.0
            else:
                out[t][m] = np.clip((stack[t][m] - lo) / (hi - lo), 0, 1)
    return out


def detect_moisture_stress(
    cube, fs, cfg: Config, stage: np.ndarray, crop_map: np.ndarray
) -> StressResult:
    idx = fs.indices
    codes = [c for c in cfg.crop_codes if c != 0]  # cohorts of actual crops

    vci = _cohort_condition(idx["ndvi"], crop_map, codes)
    owc = _cohort_condition(idx["ndwi"], crop_map, codes)     # optical water
    smi = _cohort_condition(idx["vv"], crop_map, codes)        # microwave soil moisture

    w = float(cfg.stress["optical_weight"])
    optical_cond = 0.5 * vci + 0.5 * owc
    condition = w * optical_cond + (1.0 - w) * smi              # fused (T,H,W)

    # --- stage-aware stress scoring ---
    sens = cfg.stress["stage_sensitivity"]
    stage_mult = np.ones_like(condition, dtype=np.float32)
    for code, name in STAGE_NAMES.items():
        if name == "fallow":
            stage_mult[stage == code] = 0.0
        else:
            stage_mult[stage == code] = float(sens.get(name, 1.0))

    stress_raw = 1.0 - condition
    stress_adj = np.clip(stress_raw * stage_mult, 0, 1)
    cond_adj = 1.0 - stress_adj

    # --- classify against VCI bins ---
    b = cfg.stress["vci_bins"]           # [severe, moderate, mild] cutoffs
    stress_class = np.zeros_like(cond_adj, dtype=np.int8)
    stress_class = np.where(cond_adj < b[2], 1, stress_class)   # Mild
    stress_class = np.where(cond_adj < b[1], 2, stress_class)   # Moderate
    stress_class = np.where(cond_adj < b[0], 3, stress_class)   # Severe
    stress_class[stage < 0] = 0                                 # fallow -> None

    # --- summaries ---
    crop_active = stage >= 1                                    # emerged crop only
    masked = np.where(crop_active, stress_class, 0)
    season_peak = masked.max(axis=0).astype(np.int8)
    latest = stress_class[-1].astype(np.int8)

    area_ts = {name: [] for name in STRESS_CLASS_NAMES.values()}
    total_px = cube.H * cube.W
    for t in range(cube.T):
        for cls, name in STRESS_CLASS_NAMES.items():
            area_ts[name].append(float((stress_class[t] == cls).mean()))
    _ = total_px

    # --- validation against latent truth (simulation only) ---
    validation: dict = {}
    if "true_ks" in cube.extra:
        true_ks = cube.extra["true_ks"]
        cm = crop_active
        if cm.any():
            r = np.corrcoef(condition[cm].ravel(), true_ks[cm].ravel())[0, 1]
            # true stress class from Ks using same bins
            true_cls = np.zeros_like(true_ks, dtype=np.int8)
            true_cls = np.where(true_ks < b[2], 1, true_cls)
            true_cls = np.where(true_ks < b[1], 2, true_cls)
            true_cls = np.where(true_ks < b[0], 3, true_cls)
            # agreement within +-1 stress class (ordinal tolerance)
            diff = np.abs(stress_class[cm].astype(int) - true_cls[cm].astype(int))
            validation = {
                "condition_vs_trueKs_corr": round(float(r), 3),
                "stress_class_exact_agree": round(float((diff == 0).mean()), 3),
                "stress_class_within1_agree": round(float((diff <= 1).mean()), 3),
            }

    return StressResult(
        condition=condition.astype(np.float32),
        stress_class=stress_class,
        vci=vci.astype(np.float32),
        smi=smi.astype(np.float32),
        stage=stage,
        season_peak_class=season_peak,
        latest_class=latest,
        area_timeseries=area_ts,
        validation=validation,
    )
