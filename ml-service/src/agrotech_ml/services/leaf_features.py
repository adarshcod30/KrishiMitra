"""Hand-crafted features for leaf-photo disease classification.

Why not a CNN? The serving instance has 512 MB of RAM and no GPU, and PyTorch
alone is a ~800 MB install. Classical colour + texture descriptors fed to a
scikit-learn classifier give a model measured in single-digit megabytes, reuse
the numpy/sklearn stack already present, and keep cold starts fast.

The same function runs at training time (over a downloaded image corpus) and at
inference time (over one uploaded photo), so the feature contract cannot drift
between them. Only the derived features are committed to the repository - the
image corpora themselves are downloaded, used, and deleted.

Feature groups, 68 values in total:
  * per-channel statistics for RGB, HSV and excess-green (mean, std, skew)
  * 3x3x3 quantised RGB colour histogram (27 bins) - lesion colour signature
  * 8-bin hue histogram - separates chlorosis, rust and necrosis
  * GLCM-style texture on the grey channel (contrast, dissimilarity,
    homogeneity, local variance) at two offsets - lesion roughness
  * lesion-coverage ratios: fraction of pixels that are brown, yellow or dark
"""
from __future__ import annotations

import numpy as np

# Every photo is resampled to this square before measurement so that features
# do not depend on the phone camera's resolution.
IMAGE_SIZE = 128

FEATURE_NAMES: list[str] = []
for _space in ("r", "g", "b", "h", "s", "v", "exg"):
    FEATURE_NAMES += [f"{_space}_mean", f"{_space}_std", f"{_space}_skew"]
FEATURE_NAMES += [f"rgbhist_{i:02d}" for i in range(27)]
FEATURE_NAMES += [f"huehist_{i}" for i in range(8)]
for _off in (1, 3):
    FEATURE_NAMES += [
        f"glcm{_off}_contrast", f"glcm{_off}_dissimilarity",
        f"glcm{_off}_homogeneity", f"glcm{_off}_variance",
    ]
FEATURE_NAMES += ["frac_brown", "frac_yellow", "frac_dark", "frac_green"]


def _stats(channel: np.ndarray) -> list[float]:
    mean = float(channel.mean())
    std = float(channel.std())
    # Third standardised moment: lesions make a channel's distribution skew.
    skew = float(((channel - mean) ** 3).mean() / (std**3 + 1e-6))
    return [mean, std, skew]


def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """Vectorised RGB->HSV for a float array in [0, 1]."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    diff = mx - mn + 1e-6
    hue = np.select(
        [mx == r, mx == g, mx == b],
        [(g - b) / diff % 6, (b - r) / diff + 2, (r - g) / diff + 4],
        default=0.0,
    ) / 6.0
    return np.stack([hue, diff / (mx + 1e-6), mx], axis=-1)


def _glcm_like(grey: np.ndarray, offset: int) -> list[float]:
    """Difference-based GLCM statistics, averaged over four directions.

    Equivalent to the contrast/dissimilarity/homogeneity a full co-occurrence
    matrix yields, but computed directly from shifted differences, which needs
    no scikit-image and is fast enough to run per request.
    """
    quant = np.floor(grey * 15).astype(np.int16)
    contrast = dissim = homog = 0.0
    shifts = ((0, offset), (offset, 0), (offset, offset), (offset, -offset))
    for dy, dx in shifts:
        diff = (quant - np.roll(np.roll(quant, dy, 0), dx, 1)).astype(np.float32)
        contrast += float((diff**2).mean())
        dissim += float(np.abs(diff).mean())
        homog += float((1.0 / (1.0 + diff**2)).mean())
    n = len(shifts)
    return [contrast / n, dissim / n, homog / n, float(grey.var())]


def extract_features(image) -> np.ndarray:
    """Return the feature vector for a PIL image (or anything PIL can open)."""
    from PIL import Image

    if not hasattr(image, "convert"):
        image = Image.open(image)
    rgb = np.asarray(
        image.convert("RGB").resize((IMAGE_SIZE, IMAGE_SIZE), Image.BILINEAR),
        dtype=np.float32,
    ) / 255.0

    hsv = _rgb_to_hsv(rgb)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # Excess green is the standard vegetation index for RGB cameras; it
    # separates leaf tissue from soil and shadow without any calibration.
    exg = np.clip(2 * g - r - b, -1, 1)
    grey = 0.299 * r + 0.587 * g + 0.114 * b

    values: list[float] = []
    for channel in (r, g, b, hsv[..., 0], hsv[..., 1], hsv[..., 2], exg):
        values += _stats(channel)

    bins = np.clip((rgb * 3).astype(np.int16), 0, 2)
    flat = bins[..., 0] * 9 + bins[..., 1] * 3 + bins[..., 2]
    hist = np.bincount(flat.ravel(), minlength=27).astype(np.float32)
    values += (hist / hist.sum()).tolist()

    hue_hist = np.histogram(hsv[..., 0], bins=8, range=(0.0, 1.0))[0].astype(np.float32)
    values += (hue_hist / max(hue_hist.sum(), 1)).tolist()

    for offset in (1, 3):
        values += _glcm_like(grey, offset)

    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    brown = (hue > 0.02) & (hue < 0.11) & (sat > 0.25) & (val < 0.65)
    yellow = (hue >= 0.11) & (hue < 0.19) & (sat > 0.3)
    dark = val < 0.22
    green = (hue >= 0.19) & (hue < 0.45) & (sat > 0.2)
    values += [float(m.mean()) for m in (brown, yellow, dark, green)]

    return np.nan_to_num(np.asarray(values, dtype=np.float32))


__all__ = ["extract_features", "FEATURE_NAMES", "IMAGE_SIZE"]
