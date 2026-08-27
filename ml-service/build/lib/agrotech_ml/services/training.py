from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from agrotech_ml.db.dataset import FEATURE_COLUMNS, TARGET_COLUMN, feature_ranges, load_dataset
from agrotech_ml.services.multi_models import train_auxiliary_models
from agrotech_ml.models.schemas import FeatureImportance, ModelMetadata, ModelScore, SkippedModel
from agrotech_ml.core.settings import AppSettings


def build_model_candidates(random_state: int) -> dict[str, Any]:
    candidates: dict[str, Any] = {
        # n_estimators is deliberately modest: on this 2,200-row dataset more
        # trees add zero accuracy but grow the pickle linearly (650 unbounded
        # extra-trees weighed 111 MB on disk / ~240 MB in RAM, which alone
        # ruled out 512 MB serving tiers). min_samples_leaf=2 halves node
        # count with no measurable accuracy cost.
        "Random Forest": RandomForestClassifier(
            n_estimators=150,
            min_samples_split=3,
            min_samples_leaf=2,
            random_state=random_state,
            n_jobs=-1,
        ),
        "Extra Trees": ExtraTreesClassifier(
            n_estimators=150,
            min_samples_leaf=2,
            random_state=random_state,
            n_jobs=-1,
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            learning_rate=0.06,
            max_iter=280,
            random_state=random_state,
        ),
        "Logistic Regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=6000),
        ),
        "SVC-RBF": make_pipeline(
            StandardScaler(),
            SVC(kernel="rbf", C=12.0, gamma="scale", probability=True),
        ),
    }

    try:
        from xgboost import XGBClassifier

        candidates["XGBoost"] = XGBClassifier(
            objective="multi:softprob",
            n_estimators=520,
            learning_rate=0.055,
            max_depth=8,
            subsample=0.9,
            colsample_bytree=0.88,
            reg_lambda=1.1,
            random_state=random_state,
            n_jobs=-1,
            tree_method="hist",
            eval_metric="mlogloss",
        )
    except Exception:
        pass

    try:
        from lightgbm import LGBMClassifier

        candidates["LightGBM"] = LGBMClassifier(
            n_estimators=540,
            learning_rate=0.05,
            num_leaves=64,
            random_state=random_state,
        )
    except Exception:
        pass

    try:
        from catboost import CatBoostClassifier

        candidates["CatBoost"] = CatBoostClassifier(
            iterations=500,
            learning_rate=0.05,
            depth=8,
            random_seed=random_state,
            verbose=False,
        )
    except Exception:
        pass

    return candidates


def _predict_proba(model: Any, features: Any) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(features), dtype=float)

    if hasattr(model, "decision_function"):
        decision = np.asarray(model.decision_function(features), dtype=float)
        if decision.ndim == 1:
            decision = np.column_stack([-decision, decision])

        decision = decision - decision.max(axis=1, keepdims=True)
        exp_values = np.exp(decision)
        return exp_values / exp_values.sum(axis=1, keepdims=True)

    labels = np.asarray(model.predict(features))
    classes = np.asarray(model.classes_)
    matrix = np.zeros((labels.shape[0], classes.shape[0]), dtype=float)
    class_index = {label: idx for idx, label in enumerate(classes)}
    for row_idx, label in enumerate(labels):
        matrix[row_idx, class_index[label]] = 1.0
    return matrix


def _top_k_accuracy(y_true: Any, proba: np.ndarray, classes: np.ndarray, k: int = 3) -> float:
    class_lookup = {label: index for index, label in enumerate(classes)}
    true_indices = np.array([class_lookup[label] for label in y_true])

    top_indices = np.argsort(proba, axis=1)[:, -k:]
    hits = [true_index in ranked for true_index, ranked in zip(true_indices, top_indices, strict=False)]
    return float(np.mean(hits))


def _normalize_importance(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, a_min=0, a_max=None)
    denominator = float(clipped.sum())
    if math.isclose(denominator, 0.0):
        return np.full_like(clipped, 1 / len(clipped), dtype=float)
    return clipped / denominator


def _extract_feature_importance(model: Any, x_test: Any, y_test: Any) -> list[FeatureImportance]:
    estimator = model.steps[-1][1] if hasattr(model, "steps") else model

    raw_importance: np.ndarray
    if hasattr(estimator, "feature_importances_"):
        raw_importance = np.asarray(estimator.feature_importances_, dtype=float)
    elif hasattr(estimator, "coef_"):
        coefficients = np.asarray(estimator.coef_, dtype=float)
        raw_importance = np.mean(np.abs(coefficients), axis=0)
    else:
        permutation = permutation_importance(
            model,
            x_test,
            y_test,
            n_repeats=8,
            random_state=42,
            scoring="f1_macro",
            n_jobs=-1,
        )
        raw_importance = np.asarray(permutation.importances_mean, dtype=float)

    normalized = _normalize_importance(raw_importance)
    feature_importance = [
        FeatureImportance(feature=feature, importance=float(value))
        for feature, value in zip(FEATURE_COLUMNS, normalized, strict=False)
    ]
    return sorted(feature_importance, key=lambda item: item.importance, reverse=True)


def train_models(settings: AppSettings) -> ModelMetadata:
    dataframe = load_dataset(settings.data_path)
    features = dataframe[FEATURE_COLUMNS]
    labels = dataframe[TARGET_COLUMN]

    x_train, x_test, y_train, y_test = train_test_split(
        features,
        labels,
        test_size=settings.test_size,
        random_state=settings.random_state,
        stratify=labels,
    )

    candidates = build_model_candidates(settings.random_state)
    scores: list[ModelScore] = []
    skipped_models: list[SkippedModel] = []
    fitted_models: dict[str, Any] = {}

    for model_name, candidate in candidates.items():
        start = time.perf_counter()
        try:
            candidate.fit(x_train, y_train)
            elapsed = time.perf_counter() - start

            predictions = candidate.predict(x_test)
            probabilities = _predict_proba(candidate, x_test)
            classes = np.asarray(candidate.classes_)

            score = ModelScore(
                model_name=model_name,
                accuracy=float(accuracy_score(y_test, predictions)),
                macro_f1=float(f1_score(y_test, predictions, average="macro")),
                top3_accuracy=_top_k_accuracy(y_test, probabilities, classes, k=3),
                training_seconds=float(elapsed),
            )
            scores.append(score)
            fitted_models[model_name] = candidate
        except Exception as exc:  # pragma: no cover - best effort fallback
            skipped_models.append(SkippedModel(model_name=model_name, reason=str(exc)))

    if not scores:
        details = "; ".join(f"{item.model_name}: {item.reason}" for item in skipped_models)
        raise RuntimeError(f"All candidate models failed. {details}")

    scores.sort(key=lambda item: (item.macro_f1, item.accuracy, item.top3_accuracy), reverse=True)
    best_model_name = scores[0].model_name

    final_model = clone(candidates[best_model_name])
    final_model.fit(features, labels)

    artifact_payload = {
        "model": final_model,
        "best_model": best_model_name,
        "feature_columns": FEATURE_COLUMNS,
        "class_labels": sorted(labels.unique().tolist()),
        "feature_ranges": feature_ranges(dataframe),
    }
    joblib.dump(artifact_payload, settings.model_path)

    explainability = _extract_feature_importance(fitted_models[best_model_name], x_test, y_test)
    aux_artifacts = train_auxiliary_models(settings)

    metadata = ModelMetadata(
        trained_at=datetime.now(timezone.utc),
        dataset_rows=int(len(dataframe)),
        best_model=best_model_name,
        feature_columns=FEATURE_COLUMNS,
        model_scores=scores,
        feature_importance=explainability,
        skipped_models=skipped_models,
        auxiliary_models={
            "disease_model": aux_artifacts.disease_model,
            "fertilizer_model": aux_artifacts.fertilizer_model,
            "irrigation_model": aux_artifacts.irrigation_model,
        },
    )

    settings.metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    return metadata


def load_metadata(settings: AppSettings) -> ModelMetadata:
    if not settings.metadata_path.exists():
        raise FileNotFoundError(f"Metadata not found at {settings.metadata_path}")
    return ModelMetadata.model_validate_json(settings.metadata_path.read_text(encoding="utf-8"))
