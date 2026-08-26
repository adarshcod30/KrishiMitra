"""GLCM-style texture features (per-pixel, windowed).

The problem statement asks for GLCM texture. A full per-pixel gray-level
co-occurrence matrix over a moving window is expensive in pure Python, so we
compute the two most-discriminating GLCM statistics — **contrast** and
**homogeneity** — plus **dissimilarity** directly from the co-occurrence
*difference* image, which is mathematically equivalent and needs only fast
box-filters:

    contrast(w)      = mean over window of (q - q_shift)^2
    dissimilarity(w) = mean over window of |q - q_shift|
    homogeneity(w)   = mean over window of 1 / (1 + (q - q_shift)^2)

where ``q`` is the gray-quantised band and ``q_shift`` is ``q`` displaced by the
GLCM offset (averaged over 4 directions for rotation invariance). Local
variance (a first-order texture) is added for good measure. If scikit-image is
installed, set ``method="skimage"`` for the classical windowed GLCM.

Texture is computed once, on the peak-greenness NDVI composite and on a
mid-season VH image — the two layers where field structure is most legible.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter

TEXTURE_STATS = ("contrast", "dissimilarity", "homogeneity", "variance")


def _quantize(img: np.ndarray, levels: int = 16) -> np.ndarray:
    finite = np.isfinite(img)
    lo, hi = np.percentile(img[finite], [2, 98]) if finite.any() else (0.0, 1.0)
    if hi - lo < 1e-6:
        hi = lo + 1e-6
    q = np.clip((img - lo) / (hi - lo), 0, 1) * (levels - 1)
    return np.nan_to_num(q).astype(np.float32)


def _glcm_diff_texture(img: np.ndarray, window: int = 5, levels: int = 16) -> dict[str, np.ndarray]:
    """Fast difference-based GLCM texture, averaged over 4 offsets."""
    q = _quantize(img, levels)
    offsets = [(0, 1), (1, 0), (1, 1), (1, -1)]
    contrast = np.zeros_like(q)
    dissim = np.zeros_like(q)
    homog = np.zeros_like(q)
    for dy, dx in offsets:
        shifted = np.roll(np.roll(q, dy, axis=0), dx, axis=1)
        diff = q - shifted
        contrast += uniform_filter(diff * diff, size=window, mode="nearest")
        dissim += uniform_filter(np.abs(diff), size=window, mode="nearest")
        homog += uniform_filter(1.0 / (1.0 + diff * diff), size=window, mode="nearest")
    n = len(offsets)
    mean = uniform_filter(q, size=window, mode="nearest")
    var = uniform_filter(q * q, size=window, mode="nearest") - mean * mean
    return {
        "contrast": (contrast / n).astype(np.float32),
        "dissimilarity": (dissim / n).astype(np.float32),
        "homogeneity": (homog / n).astype(np.float32),
        "variance": np.clip(var, 0, None).astype(np.float32),
    }


def _glcm_skimage(img: np.ndarray, window: int = 5, levels: int = 16) -> dict[str, np.ndarray]:
    from skimage.feature import graycomatrix, graycoprops  # type: ignore

    q = _quantize(img, levels).astype(np.uint8)
    H, W = q.shape
    pad = window // 2
    qp = np.pad(q, pad, mode="reflect")
    out = {k: np.zeros((H, W), np.float32) for k in ("contrast", "dissimilarity", "homogeneity")}
    for i in range(H):
        for j in range(W):
            patch = qp[i:i + window, j:j + window]
            g = graycomatrix(patch, [1], [0, np.pi / 2], levels=levels, symmetric=True, normed=True)
            for k in ("contrast", "dissimilarity", "homogeneity"):
                out[k][i, j] = graycoprops(g, k).mean()
    mean = uniform_filter(q.astype(np.float32), size=window, mode="nearest")
    out["variance"] = np.clip(
        uniform_filter(q.astype(np.float32) ** 2, size=window, mode="nearest") - mean ** 2, 0, None
    ).astype(np.float32)
    return out


def texture_features(
    image: np.ndarray, window: int = 5, levels: int = 16, method: str = "fast"
) -> dict[str, np.ndarray]:
    """Per-pixel texture stats for a single 2-D ``image``.

    method="fast" (default, no deps) uses the difference-GLCM; "skimage" uses
    the classical windowed GLCM (slower, requires scikit-image).
    """
    if method == "skimage":
        try:
            return _glcm_skimage(image, window, levels)
        except Exception:  # pragma: no cover - fall back gracefully
            pass
    return _glcm_diff_texture(image, window, levels)
