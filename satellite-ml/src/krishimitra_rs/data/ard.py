"""Analysis-Ready-Data (ARD) container shared by the simulate and GEE paths.

A :class:`DataCube` holds one Rabi season for a command area:

* multi-temporal **optical** surface reflectance (red / nir / green / swir1),
* multi-temporal **SAR** backscatter (VV / VH, in dB),
* a per-timestep **cloud/invalid mask** for the optical stack,
* daily **meteorology** (reference ET0 and rainfall) for the water balance,
* optional **ground-truth labels** and latent **soil moisture** (simulation only,
  used to *validate* the derived stress layer).

Shapes: optical/SAR are ``(T, H, W)``; labels are ``(H, W)``; meteorology is
daily ``(D,)``. ``T`` = number of 8-day composites, ``D`` = number of days.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# Optical band keys carried through the pipeline (Sentinel-2 / LISS analogues).
OPTICAL_BANDS = ("red", "nir", "green", "swir1")
SAR_BANDS = ("vv", "vh")


@dataclass
class DataCube:
    dates: list[_dt.date]                      # composite centre dates, len T
    optical: dict[str, np.ndarray]             # band -> (T, H, W) reflectance [0,1]
    sar: dict[str, np.ndarray]                 # band -> (T, H, W) backscatter dB
    cloud_mask: np.ndarray                     # (T, H, W) bool: True = invalid optical
    met: dict[str, Any]                        # daily meteorology + soil params
    labels: np.ndarray | None = None           # (H, W) int crop code, or None
    soil_moisture: np.ndarray | None = None    # (T, H, W) volumetric, sim-only
    meta: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, np.ndarray] = field(default_factory=dict)  # aux truth arrays (sim)

    # ---- shape helpers ----------------------------------------------------
    @property
    def T(self) -> int:  # noqa: N802 (dimension name)
        return len(self.dates)

    @property
    def H(self) -> int:  # noqa: N802
        return self.optical["red"].shape[1]

    @property
    def W(self) -> int:  # noqa: N802
        return self.optical["red"].shape[2]

    @property
    def doys(self) -> np.ndarray:
        return np.array([d.timetuple().tm_yday for d in self.dates])

    def n_pixels(self) -> int:
        return self.H * self.W

    # ---- persistence ------------------------------------------------------
    def to_npz(self, path: str | Path) -> Path:
        return save_cube(self, path)


def composite_gapfill(stack: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Temporally gap-fill a cloud-masked ``(T, H, W)`` optical stack.

    Cloud-contaminated observations (``mask == True``) are the reality of kharif
    monsoon monitoring; before any index or phenology metric is computed the
    series must be made continuous. We linearly interpolate each pixel along
    time and extrapolate the ends by nearest-valid — the same idea as a
    smoothed temporal composite, done per pixel.
    """
    stack = stack.astype(np.float32).copy()
    T = stack.shape[0]
    flat = stack.reshape(T, -1)
    m = mask.reshape(T, -1)
    t = np.arange(T)
    for j in range(flat.shape[1]):
        valid = ~m[:, j]
        if valid.all():
            continue
        if valid.sum() == 0:
            flat[:, j] = np.nan
            continue
        flat[:, j] = np.interp(t, t[valid], flat[valid, j])
    return flat.reshape(stack.shape)


def save_cube(cube: DataCube, path: str | Path) -> Path:
    """Persist a cube to a compressed ``.npz`` (portable, no geospatial deps)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "dates": np.array([d.isoformat() for d in cube.dates]),
        "cloud_mask": cube.cloud_mask,
        "met_json": np.array(_json_dumps(cube.met)),
        "meta_json": np.array(_json_dumps(cube.meta)),
    }
    for b in OPTICAL_BANDS:
        payload[f"opt_{b}"] = cube.optical[b].astype(np.float32)
    for b in SAR_BANDS:
        payload[f"sar_{b}"] = cube.sar[b].astype(np.float32)
    if cube.labels is not None:
        payload["labels"] = cube.labels.astype(np.int16)
    if cube.soil_moisture is not None:
        payload["soil_moisture"] = cube.soil_moisture.astype(np.float32)
    for k, v in cube.extra.items():
        payload[f"extra_{k}"] = np.asarray(v)
    np.savez_compressed(path, **payload)
    return path


def load_cube(path: str | Path) -> DataCube:
    z = np.load(path, allow_pickle=False)
    dates = [_dt.date.fromisoformat(s) for s in z["dates"].tolist()]
    optical = {b: z[f"opt_{b}"] for b in OPTICAL_BANDS}
    sar = {b: z[f"sar_{b}"] for b in SAR_BANDS}
    extra = {k[len("extra_"):]: z[k] for k in z.files if k.startswith("extra_")}
    return DataCube(
        dates=dates,
        optical=optical,
        sar=sar,
        cloud_mask=z["cloud_mask"],
        met=_json_loads(str(z["met_json"])),
        labels=z["labels"] if "labels" in z else None,
        soil_moisture=z["soil_moisture"] if "soil_moisture" in z else None,
        meta=_json_loads(str(z["meta_json"])),
        extra=extra,
    )


# ---- tiny JSON helpers (kept local to avoid import churn) -----------------
def _json_dumps(obj: Any) -> str:
    import json

    def _default(o: Any) -> Any:
        if isinstance(o, (_dt.date, _dt.datetime)):
            return o.isoformat()
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        raise TypeError(f"not serialisable: {type(o)}")

    return json.dumps(obj, default=_default)


def _json_loads(s: str) -> dict[str, Any]:
    import json

    return json.loads(s)
