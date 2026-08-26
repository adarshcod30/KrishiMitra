"""Growth-stage detection and stage-based Kc reconstruction.

``detect_growth_stage`` is a thin wrapper over the phenology feature (kept here
so advisory code has a single import surface). ``kc_from_detected_stage``
rebuilds an FAO-56 crop-coefficient time series *from the satellite-observed
phenology* rather than a fixed planting-date calendar — the whole point of a
remote-sensing advisory is that Kc follows the crop the sensor actually sees.
"""
from __future__ import annotations

import numpy as np

from ..config import Config
from ..features.phenology import growth_stage_stack, phenology_metrics  # noqa: F401


def detect_growth_stage(ndvi: np.ndarray, pheno: dict) -> np.ndarray:
    """(T, H, W) growth-stage codes from an NDVI stack + phenology metrics."""
    return growth_stage_stack(ndvi, pheno)


def _crop_param_maps(crop_map: np.ndarray, cfg: Config, keys: list[str]) -> dict[str, np.ndarray]:
    """Build (H, W) parameter maps (e.g. kc_ini) from the crop map + config."""
    out = {k: np.zeros(crop_map.shape, np.float32) for k in keys}
    for c in cfg.crops:
        m = crop_map == c["code"]
        if not m.any():
            continue
        for k in keys:
            out[k][m] = float(c["fao56"][k])
    return out


def kc_from_detected_stage(
    stage: np.ndarray, pheno: dict, crop_map: np.ndarray, cfg: Config
) -> np.ndarray:
    """Reconstruct an ``(T, H, W)`` Kc series from detected stage + phenology.

    * sowing      -> Kc_ini
    * vegetative  -> ramp Kc_ini -> Kc_mid across green-up (SOS..POS)
    * flowering   -> Kc_mid (peak canopy)
    * maturity    -> ramp Kc_mid -> Kc_end across senescence (POS..EOS)
    """
    T = stage.shape[0]
    p = _crop_param_maps(crop_map, cfg, ["kc_ini", "kc_mid", "kc_end"])
    ki, km, ke = p["kc_ini"], p["kc_mid"], p["kc_end"]
    sos, pos, eos = pheno["sos_t"], pheno["pos_t"], pheno["eos_t"]

    t = np.arange(T)[:, None, None]
    veg_frac = np.clip((t - sos[None]) / np.clip((pos - sos)[None], 1, None), 0, 1)
    sen_frac = np.clip((t - pos[None]) / np.clip((eos - pos)[None], 1, None), 0, 1)

    kc = np.empty((T, *stage.shape[1:]), np.float32)
    kc[:] = ki[None]                                             # sowing / default
    kc = np.where(stage == 1, ki[None] + (km - ki)[None] * veg_frac, kc)
    kc = np.where(stage == 2, km[None], kc)
    kc = np.where(stage == 3, km[None] + (ke - km)[None] * sen_frac, kc)
    kc = np.where(stage == -1, ki[None], kc)                    # fallow / bare
    return kc.astype(np.float32)
