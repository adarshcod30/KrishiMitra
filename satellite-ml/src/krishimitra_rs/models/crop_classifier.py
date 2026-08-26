"""Crop-type classification from multi-temporal optical + SAR features.

Trains Random Forest and XGBoost on a small labelled sample (mimicking field
survey points), evaluates on a **field-disjoint** validation set, and predicts a
seasonal crop map for the whole command area with a per-pixel confidence layer.

The multi-model design mirrors the problem statement's "RF / XGBoost for
tabular multi-temporal feature classification" — the better of the two on the
held-out fields becomes the deployed classifier.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import cohen_kappa_score

from ..config import Config
from ..features.build import FeatureStack

try:
    from xgboost import XGBClassifier
    _HAS_XGB = True
except Exception:  # pragma: no cover
    _HAS_XGB = False


@dataclass
class GroundTruth:
    train_idx: np.ndarray          # flat pixel indices for training
    val_idx: np.ndarray            # flat pixel indices for validation (disjoint fields)
    y_train: np.ndarray            # crop codes
    y_val: np.ndarray


@dataclass
class ClassificationResult:
    crop_map: np.ndarray                    # (H, W) predicted crop codes
    confidence: np.ndarray                  # (H, W) max class probability
    metrics: dict                           # per-model {oa, kappa, per_class, confusion}
    best_model: str
    models: dict = field(default_factory=dict)
    feature_importance: list[tuple[str, float]] = field(default_factory=list)
    ground_truth: GroundTruth | None = None
    classes_: np.ndarray | None = None      # ordered crop codes
    val_pred: np.ndarray | None = None      # predictions on val_idx (best model)


# --------------------------------------------------------------------------- #
# Ground-truth sampling with field-disjoint train/val split
# --------------------------------------------------------------------------- #
def sample_ground_truth(cube, fs: FeatureStack, cfg: Config, rng=None) -> GroundTruth:
    if rng is None:
        rng = np.random.default_rng(cfg.seed + 7)
    labels = cube.labels.reshape(-1)
    field_id = cube.extra.get("field_id")
    field_flat = field_id.reshape(-1) if field_id is not None else np.arange(labels.size)

    ppc = int(cfg.ground_truth["points_per_class"])
    train_frac = float(cfg.ground_truth["train_fraction"])

    # Assign each field to train or val ONCE, so no field straddles the split.
    uniq_fields = np.unique(field_flat)
    rng.shuffle(uniq_fields)
    n_train_fields = int(round(len(uniq_fields) * train_frac))
    train_fields = set(uniq_fields[:n_train_fields].tolist())

    tr_idx, va_idx = [], []
    for code in cfg.crop_codes:
        pix = np.where(labels == code)[0]
        if pix.size == 0:
            continue
        rng.shuffle(pix)
        is_train = np.array([field_flat[p] in train_fields for p in pix])
        tr = pix[is_train][:ppc]
        va = pix[~is_train][: max(ppc // 3, 30)]
        tr_idx.append(tr)
        va_idx.append(va)
    train_idx = np.concatenate(tr_idx)
    val_idx = np.concatenate(va_idx)
    return GroundTruth(
        train_idx=train_idx,
        val_idx=val_idx,
        y_train=labels[train_idx],
        y_val=labels[val_idx],
    )


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def _evaluate(y_true, y_pred, classes, code_to_name) -> dict:
    oa = float((y_true == y_pred).mean())
    kappa = float(cohen_kappa_score(y_true, y_pred, labels=classes))
    # confusion matrix and per-class producer/user accuracy
    K = len(classes)
    cm = np.zeros((K, K), dtype=int)
    ci = {c: i for i, c in enumerate(classes)}
    for t, p in zip(y_true, y_pred):
        cm[ci[t], ci[p]] += 1
    per_class = {}
    for i, c in enumerate(classes):
        tp = cm[i, i]
        prod = tp / cm[i, :].sum() if cm[i, :].sum() else 0.0   # producer's acc (recall)
        user = tp / cm[:, i].sum() if cm[:, i].sum() else 0.0   # user's acc (precision)
        f1 = 2 * prod * user / (prod + user) if (prod + user) else 0.0
        per_class[code_to_name.get(int(c), str(c))] = {
            "producer_acc": round(prod, 4), "user_acc": round(user, 4),
            "f1": round(f1, 4), "support": int(cm[i, :].sum()),
        }
    return {
        "overall_accuracy": round(oa, 4),
        "kappa": round(kappa, 4),
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
        "classes": [code_to_name.get(int(c), str(c)) for c in classes],
    }


# --------------------------------------------------------------------------- #
# Training / prediction
# --------------------------------------------------------------------------- #
def classify_crops(cube, fs: FeatureStack, cfg: Config, gt: GroundTruth | None = None) -> ClassificationResult:
    rng = np.random.default_rng(cfg.seed + 7)
    if gt is None:
        gt = sample_ground_truth(cube, fs, cfg, rng)

    X = fs.X
    code_to_name = cfg.code_to_name
    classes = np.array(sorted(np.unique(gt.y_train)))
    Xtr, Xva = X[gt.train_idx], X[gt.val_idx]

    models: dict = {}
    metrics: dict = {}

    # --- Random Forest ---
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=None, min_samples_leaf=2,
        max_features="sqrt", n_jobs=-1, class_weight="balanced_subsample",
        random_state=cfg.seed,
    )
    rf.fit(Xtr, gt.y_train)
    metrics["random_forest"] = _evaluate(gt.y_val, rf.predict(Xva), classes, code_to_name)
    models["random_forest"] = rf

    # --- XGBoost ---
    if _HAS_XGB:
        code2i = {c: i for i, c in enumerate(classes)}
        i2code = {i: c for c, i in code2i.items()}
        ytr_i = np.array([code2i[c] for c in gt.y_train])
        xgb = XGBClassifier(
            n_estimators=400, max_depth=6, learning_rate=0.08,
            subsample=0.85, colsample_bytree=0.7, tree_method="hist",
            objective="multi:softprob", num_class=len(classes),
            eval_metric="mlogloss", n_jobs=-1, random_state=cfg.seed,
        )
        xgb.fit(Xtr, ytr_i)
        yva_pred = np.array([i2code[i] for i in xgb.predict(Xva)])
        metrics["xgboost"] = _evaluate(gt.y_val, yva_pred, classes, code_to_name)
        models["xgboost"] = (xgb, i2code, code2i)

    # --- pick the better model on held-out fields ---
    best = max(metrics, key=lambda m: metrics[m]["overall_accuracy"])

    # --- predict the full command-area map ---
    if best == "xgboost":
        xgb, i2code, _ = models["xgboost"]
        proba = xgb.predict_proba(X)
        pred_i = proba.argmax(1)
        crop_flat = np.array([i2code[i] for i in pred_i])
        conf_flat = proba.max(1)
        imp_model = xgb
    else:
        proba = rf.predict_proba(X)
        crop_flat = rf.classes_[proba.argmax(1)]
        conf_flat = proba.max(1)
        imp_model = rf

    crop_map = crop_flat.reshape(fs.shape)
    confidence = conf_flat.reshape(fs.shape)

    importances = getattr(imp_model, "feature_importances_", None)
    feat_imp: list[tuple[str, float]] = []
    if importances is not None:
        order = np.argsort(importances)[::-1][:25]
        feat_imp = [(fs.names[i], float(importances[i])) for i in order]

    # best-model predictions on val (for the validation report / viz)
    if best == "xgboost":
        val_pred = np.array([i2code[i] for i in models["xgboost"][0].predict(Xva)])
    else:
        val_pred = rf.predict(Xva)

    return ClassificationResult(
        crop_map=crop_map, confidence=confidence, metrics=metrics,
        best_model=best, models=models, feature_importance=feat_imp,
        ground_truth=gt, classes_=classes, val_pred=val_pred,
    )
