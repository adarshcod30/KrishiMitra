"""Assemble the per-pixel feature table consumed by the crop classifier.

A pixel's feature vector concatenates four complementary views, which is what
lets moderate-resolution multi-temporal data separate crops that look identical
on any single date:

* **Multi-temporal signature** — every index at every 8-day composite
  (the raw temporal-spectral profile).
* **Temporal summary stats** — mean / std / max / min / amplitude per index.
* **Phenology metrics** — SOS, POS, EOS, LGP, green-up & senescence rates, AUC.
* **Texture** — GLCM contrast/homogeneity/… on peak-NDVI and mid-season VH.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..data.ard import DataCube
from .indices import ALL_INDEX_NAMES, compute_indices
from .phenology import PHENOLOGY_NAMES, phenology_metrics
from .texture import TEXTURE_STATS, texture_features


@dataclass
class FeatureStack:
    X: np.ndarray                    # (N, F) per-pixel features, N = H*W
    names: list[str]                 # length F
    shape: tuple[int, int]           # (H, W)
    indices: dict[str, np.ndarray]   # reused by the moisture-stress module
    pheno: dict[str, np.ndarray]     # reused by growth-stage detection
    meta: dict = field(default_factory=dict)

    @property
    def n_features(self) -> int:
        return self.X.shape[1]

    def as_maps(self, values: np.ndarray) -> np.ndarray:
        """Reshape a length-N vector back to an (H, W) map."""
        return values.reshape(self.shape)


def build_feature_stack(cube: DataCube, texture_method: str = "fast") -> FeatureStack:
    idx = compute_indices(cube, gapfill=True)
    ndvi = idx["ndvi"]
    pheno = phenology_metrics(ndvi)

    H, W = cube.H, cube.W
    N = H * W
    T = cube.T

    peak_ndvi = ndvi.max(axis=0)
    vh_mid = cube.sar["vh"][T // 2]
    tex_ndvi = texture_features(peak_ndvi, method=texture_method)
    tex_vh = texture_features(vh_mid, method=texture_method)

    cols: list[np.ndarray] = []
    names: list[str] = []

    # 1) multi-temporal signature
    for name in ALL_INDEX_NAMES:
        stack = idx[name]
        for t in range(T):
            cols.append(stack[t].reshape(N))
            names.append(f"{name}_t{t:02d}")

    # 2) temporal summary statistics
    for name in ALL_INDEX_NAMES:
        stack = idx[name]
        cols.extend([
            stack.mean(0).reshape(N), stack.std(0).reshape(N),
            stack.max(0).reshape(N), stack.min(0).reshape(N),
            (stack.max(0) - stack.min(0)).reshape(N),
        ])
        names.extend([f"{name}_mean", f"{name}_std", f"{name}_max",
                      f"{name}_min", f"{name}_amp"])

    # 3) phenology metrics
    for k in PHENOLOGY_NAMES:
        cols.append(pheno[k].reshape(N))
        names.append(f"pheno_{k}")

    # 4) texture
    for src, tex in (("ndvi", tex_ndvi), ("vh", tex_vh)):
        for k in TEXTURE_STATS:
            cols.append(tex[k].reshape(N))
            names.append(f"tex_{src}_{k}")

    X = np.nan_to_num(np.stack(cols, axis=1).astype(np.float32))
    return FeatureStack(X=X, names=names, shape=(H, W), indices=idx, pheno=pheno)
