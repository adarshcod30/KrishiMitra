"""Translate the 8-day water deficit into an irrigation-status advisory.

The net root-zone deficit (as a fraction of readily-available water) is binned
into four operational actions the command-area manager can act on:

    None (0)        deficit < b0 % RAW      -> soil comfortable
    Monitor (1)     b0..b1 %                -> watch, no action yet
    Schedule (2)    b1..b2 %                -> plan irrigation in the next rotation
    Irrigate now (3)  > b2 %                -> readily-available water exhausted

Each pixel also carries the recommended **gross irrigation depth** (mm), and the
command area gets aggregate demand (area to irrigate, total water volume) — the
numbers a canal roster is actually built from.

Advice is muted on fallow ground and capped at "Monitor" inside the pre-harvest
ripening window (see :func:`ripening_mask`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import Config

ADVISORY_NAMES = {0: "None", 1: "Monitor", 2: "Schedule", 3: "Irrigate now"}

# Default width of the pre-harvest ripening window in which active irrigation
# advice is muted (overridable via config.advisory).
_RIPENING_DAYS = 15


def ripening_mask(cube, crop_map: np.ndarray, cfg: Config, shape: tuple) -> np.ndarray:
    """``(T, H, W)`` bool — pixels inside the final pre-harvest ripening window.

    Irrigating a crop that is a fortnight from harvest wastes water (and can
    lodge cereals), so active advice is capped at "Monitor" there.

    The window is anchored on the **crop's agronomic harvest date** (the crop
    map says *which* crop, the config says when that crop ripens), NOT on the
    pixel's own observed NDVI peak. A water-stressed pixel senesces early, so a
    peak-anchored rule declares exactly the driest fields "mature" and switches
    the advisory off precisely where irrigation is most needed.
    """
    T, H, W = shape
    days = int(cfg.advisory.get("stop_irrigation_days_before_harvest", _RIPENING_DAYS))
    mask = np.zeros((T, H, W), dtype=bool)
    for c in cfg.crops:
        if int(c["code"]) == 0:
            continue
        harvest = cfg.resolve_doy(c.get("phenology", {}).get("eos_doy"))
        if harvest is None:
            continue
        cm = crop_map == c["code"]
        if not cm.any():
            continue
        for t, d in enumerate(cube.dates):
            if (harvest - d).days <= days:
                mask[t] |= cm
    return mask


@dataclass
class AdvisoryResult:
    advisory_class: np.ndarray     # (T, H, W) int 0..3
    latest_class: np.ndarray       # (H, W) advisory at the headline (peak-demand) composite
    gross_mm: np.ndarray           # (T, H, W) recommended gross depth
    latest_gross_mm: np.ndarray    # (H, W)
    area_timeseries: dict          # class -> list over T of area fraction
    command_area_summary: dict     # headline-composite aggregate demand
    snapshot_index: int = 0        # composite index used for the headline map
    per_crop_demand: dict = field(default_factory=dict)


def generate_advisory(cube, wb, stage: np.ndarray, crop_map: np.ndarray, cfg: Config) -> AdvisoryResult:
    T, H, W = wb.depletion.shape
    bins = cfg.advisory["depletion_pct_bins"]         # [b0, b1, b2] % of RAW depleted
    min_mm = float(cfg.advisory["min_advisory_mm"])

    pct = 100.0 * wb.depletion_ratio                  # depletion as % of RAW
    adv = np.zeros((T, H, W), np.int8)
    adv = np.where(pct >= bins[0], 1, adv)            # Monitor
    adv = np.where(pct >= bins[1], 2, adv)            # Schedule
    adv = np.where(pct >= bins[2], 3, adv)            # Irrigate now (RAW exhausted)
    # suppress trivially small recommended depths and fallow
    adv = np.where(wb.ir_net < min_mm, 0, adv)
    adv[:, crop_map == 0] = 0
    # Phenology-aware: cap the advice at "Monitor" in the pre-harvest ripening
    # window (irrigating a crop days from harvest wastes water) and mute it on
    # bare/fallow ground. Active advice concentrates on the vegetative,
    # reproductive and grain-filling phases — including post-peak senescence,
    # which is still highly irrigation-responsive in cereals.
    adv = np.where(ripening_mask(cube, crop_map, cfg, adv.shape), np.minimum(adv, 1), adv)
    adv[stage < 0] = 0

    gross = np.where(adv >= 2, wb.ir_gross, 0.0).astype(np.float32)

    area_ts = {name: [] for name in ADVISORY_NAMES.values()}
    for t in range(T):
        for cls, name in ADVISORY_NAMES.items():
            area_ts[name].append(float((adv[t] == cls).mean()))

    # Headline snapshot = the composite that maximises action-area weighted by
    # crop water demand (ETc). This lands on peak in-season demand (flowering)
    # rather than establishment or harvest, when irrigation matters most.
    etc_series = np.asarray(wb.etc_area_series)
    etc_w = etc_series / max(etc_series.max(), 1e-6)
    score = [float((adv[t] >= 2).mean()) * float(etc_w[t]) for t in range(T)]
    snap = int(np.argmax(score))
    latest = adv[snap]
    latest_gross = gross[snap]
    px_area_ha = (cube.meta.get("pixel_size_m", 20) ** 2) / 1e4   # ha per pixel
    need_mask = latest >= 2                                        # schedule + irrigate now
    area_ha = float(need_mask.sum() * px_area_ha)
    # volume (m3) = depth(mm)->m * area(m2)
    px_area_m2 = cube.meta.get("pixel_size_m", 20) ** 2
    volume_m3 = float((latest_gross[need_mask].sum() / 1000.0) * px_area_m2)

    per_crop: dict = {}
    for c in cfg.crops:
        if c["code"] == 0:
            continue
        m = crop_map == c["code"]
        if not m.any():
            continue
        cm = m & need_mask
        per_crop[c["name"]] = {
            "area_to_irrigate_ha": round(float(cm.sum() * px_area_ha), 1),
            "mean_gross_mm": round(float(latest_gross[cm].mean()) if cm.any() else 0.0, 1),
        }

    summary = {
        "date": cube.dates[snap].isoformat(),
        "area_needing_irrigation_ha": round(area_ha, 1),
        "total_gross_volume_m3": round(volume_m3, 0),
        "total_gross_volume_ML": round(volume_m3 / 1000.0, 1),
        "pct_command_area_irrigate_now": round(float((latest == 3).mean()) * 100, 1),
        "pct_command_area_schedule": round(float((latest == 2).mean()) * 100, 1),
    }

    return AdvisoryResult(
        advisory_class=adv,
        latest_class=latest.astype(np.int8),
        gross_mm=gross,
        latest_gross_mm=latest_gross.astype(np.float32),
        area_timeseries=area_ts,
        command_area_summary=summary,
        snapshot_index=snap,
        per_crop_demand=per_crop,
    )
