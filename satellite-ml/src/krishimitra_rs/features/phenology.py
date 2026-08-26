"""Per-pixel phenological metrics from an NDVI time series.

These land-surface-phenology metrics (Start / Peak / End of Season, Length of
Growing Period, green-up & senescence rates, seasonal integral) are both
powerful crop-discriminators (wheat vs. sugarcane differ far more in *timing*
than in peak greenness) and the substrate for growth-stage detection used by
the irrigation advisory.

Method: amplitude-threshold on the smoothed NDVI trajectory. SOS/EOS are the
first/last crossings of ``base + frac * amplitude``; POS is the argmax.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter1d

PHENOLOGY_NAMES = (
    "ndvi_min", "ndvi_max", "ndvi_amp", "pos_t", "pos_val",
    "sos_t", "eos_t", "lgp", "greenup_rate", "senescence_rate", "auc",
)

# Growth-stage codes used by the stress detector and the irrigation advisory.
STAGE_NAMES = {-1: "fallow", 0: "sowing", 1: "vegetative", 2: "flowering", 3: "maturity"}


def _smooth_time(stack: np.ndarray, size: int = 3) -> np.ndarray:
    """Light temporal smoothing (Savitzky-Golay-like) before metric extraction."""
    return uniform_filter1d(stack, size=size, axis=0, mode="nearest")


def phenology_metrics(ndvi: np.ndarray, frac: float = 0.3) -> dict[str, np.ndarray]:
    """Compute phenology metric maps from an ``(T, H, W)`` NDVI stack."""
    T = ndvi.shape[0]
    s = _smooth_time(ndvi)

    base = s.min(axis=0)
    peak = s.max(axis=0)
    amp = np.clip(peak - base, 1e-3, None)
    thr = base + frac * amp
    above = s >= thr[None]

    pos_t = np.argmax(s, axis=0).astype(np.float32)
    pos_val = peak.astype(np.float32)

    # first / last time the series is above threshold
    sos_t = np.argmax(above, axis=0).astype(np.float32)
    eos_t = (T - 1 - np.argmax(above[::-1], axis=0)).astype(np.float32)
    # pixels that never rise (fallow) -> degenerate season
    never = ~above.any(axis=0)
    sos_t[never] = 0.0
    eos_t[never] = 0.0

    lgp = np.clip(eos_t - sos_t, 0, None)
    eos_val = np.take_along_axis(s, eos_t.astype(int)[None], axis=0)[0]

    greenup = (pos_val - base) / np.clip(pos_t - sos_t, 1, None)
    senescence = (pos_val - eos_val) / np.clip(eos_t - pos_t, 1, None)
    _trapz = getattr(np, "trapezoid", np.trapz)    # numpy>=2 renamed trapz
    auc = _trapz(s, axis=0).astype(np.float32)     # seasonal integral (biomass proxy)

    return {
        "ndvi_min": base.astype(np.float32),
        "ndvi_max": peak.astype(np.float32),
        "ndvi_amp": amp.astype(np.float32),
        "pos_t": pos_t,
        "pos_val": pos_val,
        "sos_t": sos_t,
        "eos_t": eos_t,
        "lgp": lgp.astype(np.float32),
        "greenup_rate": greenup.astype(np.float32),
        "senescence_rate": senescence.astype(np.float32),
        "auc": auc,
    }


def growth_stage_stack(
    ndvi: np.ndarray, pheno: dict[str, np.ndarray], min_amp: float = 0.12
) -> np.ndarray:
    """Assign each pixel a growth stage at each timestep from its phenology.

    Returns an ``(T, H, W)`` int array using :data:`STAGE_NAMES`:

    * ``-1`` fallow / no crop (seasonal NDVI amplitude below ``min_amp``)
    * ``0``  sowing / establishment  (t < SOS)
    * ``1``  vegetative / green-up    (SOS <= t < POS)
    * ``2``  flowering / reproductive (peak window around POS)
    * ``3``  maturity / senescence    (t beyond the peak window)

    The flowering window is +-1 composite (+-8 days) around peak greenness — the
    reproductive phase that is most sensitive to moisture stress.
    """
    T = ndvi.shape[0]
    H, W = ndvi.shape[1:]
    sos = pheno["sos_t"]
    pos = pheno["pos_t"]
    amp = pheno["ndvi_amp"]
    fallow = amp < min_amp

    t = np.arange(T)[:, None, None]
    stage = np.full((T, H, W), 0, dtype=np.int8)          # default: sowing
    stage = np.where(t >= sos[None], 1, stage)            # vegetative
    flowering = (t >= (pos[None] - 1)) & (t <= (pos[None] + 1))
    stage = np.where(flowering, 2, stage)                 # flowering
    stage = np.where(t > (pos[None] + 1), 3, stage)       # maturity
    stage[:, fallow] = -1
    return stage

