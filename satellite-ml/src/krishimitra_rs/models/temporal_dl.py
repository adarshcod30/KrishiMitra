"""Optional deep temporal models: LSTM and Temporal-CNN for crop classification.

These operate directly on the raw multi-temporal index sequence per pixel
``(T, C)`` — ``C`` indices (NDVI, EVI, NDWI, VV, VH, ...) over ``T`` composites —
learning temporal-spectral dynamics end-to-end, as the problem statement's
"LSTM / Temporal-CNN for time-series dynamics" suggests. They are **optional**:
the RF/XGBoost path in :mod:`crop_classifier` is the default and needs no GPU.

Install the extra to use them::  pip install torch

Everything here is import-safe without torch; :data:`TORCH_AVAILABLE` tells the
caller whether the DL path can run.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Config
from ..features.indices import ALL_INDEX_NAMES

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    TORCH_AVAILABLE = False


@dataclass
class TemporalResult:
    crop_map: np.ndarray
    confidence: np.ndarray
    overall_accuracy: float
    kappa: float
    arch: str


def build_sequences(fs, cube) -> np.ndarray:
    """Assemble the ``(N, T, C)`` sequence tensor from the index stacks."""
    T = cube.T
    N = cube.H * cube.W
    C = len(ALL_INDEX_NAMES)
    seq = np.zeros((N, T, C), dtype=np.float32)
    for c, name in enumerate(ALL_INDEX_NAMES):
        stack = fs.indices[name]                 # (T, H, W)
        seq[:, :, c] = stack.reshape(T, N).T
    # standardise per channel (helps optimisation)
    mu = seq.mean((0, 1), keepdims=True)
    sd = seq.std((0, 1), keepdims=True) + 1e-6
    return (seq - mu) / sd


if TORCH_AVAILABLE:

    class _LSTM(nn.Module):
        def __init__(self, c_in, n_cls, hidden=64):
            super().__init__()
            self.lstm = nn.LSTM(c_in, hidden, num_layers=1, batch_first=True, bidirectional=True)
            self.head = nn.Sequential(nn.Linear(2 * hidden, 64), nn.ReLU(),
                                      nn.Dropout(0.3), nn.Linear(64, n_cls))

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1])

    class _TempCNN(nn.Module):
        """1-D temporal CNN (Pelletier et al., 2019 style)."""

        def __init__(self, c_in, n_cls):
            super().__init__()
            def block(i, o):
                return nn.Sequential(nn.Conv1d(i, o, 3, padding=1), nn.BatchNorm1d(o),
                                     nn.ReLU(), nn.Dropout(0.2))
            self.body = nn.Sequential(block(c_in, 64), block(64, 64), block(64, 64))
            self.head = nn.Sequential(nn.AdaptiveAvgPool1d(1), nn.Flatten(),
                                      nn.Linear(64, n_cls))

        def forward(self, x):                     # x: (B, T, C) -> (B, C, T)
            return self.head(self.body(x.transpose(1, 2)))


def train_temporal_model(cube, fs, cfg: Config, gt, arch: str = "lstm",
                         epochs: int = 25, batch: int = 256) -> TemporalResult:
    """Train an LSTM or Temporal-CNN on the field-disjoint ground truth."""
    if not TORCH_AVAILABLE:
        raise ImportError("Deep temporal models require torch:  pip install torch")
    from sklearn.metrics import cohen_kappa_score

    seq = build_sequences(fs, cube)
    classes = np.array(sorted(np.unique(gt.y_train)))
    c2i = {c: i for i, c in enumerate(classes)}
    i2c = {i: c for c, i in c2i.items()}

    Xtr = torch.tensor(seq[gt.train_idx])
    ytr = torch.tensor(np.array([c2i[c] for c in gt.y_train]), dtype=torch.long)
    Xva = torch.tensor(seq[gt.val_idx])

    device = "cuda" if torch.cuda.is_available() else "cpu"
    C = seq.shape[2]
    model = (_LSTM(C, len(classes)) if arch == "lstm" else _TempCNN(C, len(classes))).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    lossf = nn.CrossEntropyLoss()
    loader = DataLoader(TensorDataset(Xtr, ytr), batch_size=batch, shuffle=True)

    model.train()
    for _ in range(epochs):
        for xb, yb in loader:
            opt.zero_grad()
            loss = lossf(model(xb.to(device)), yb.to(device))
            loss.backward()
            opt.step()

    model.eval()
    with torch.no_grad():
        proba_all = torch.softmax(model(torch.tensor(seq).to(device)), 1).cpu().numpy()
    pred_i = proba_all.argmax(1)
    crop_flat = np.array([i2c[i] for i in pred_i])
    conf_flat = proba_all.max(1)

    yva_pred = crop_flat[gt.val_idx]
    oa = float((yva_pred == gt.y_val).mean())
    kappa = float(cohen_kappa_score(gt.y_val, yva_pred, labels=classes))
    return TemporalResult(
        crop_map=crop_flat.reshape(fs.shape),
        confidence=conf_flat.reshape(fs.shape),
        overall_accuracy=round(oa, 4), kappa=round(kappa, 4), arch=arch,
    )
