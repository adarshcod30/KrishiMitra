"""Diagnose a crop disease from an uploaded leaf photograph.

Complements the text path in :mod:`agrotech_ml.services.inference`: a farmer who
cannot describe a symptom in words can photograph the leaf instead. Features
come from :mod:`agrotech_ml.services.leaf_features` (colour, texture, lesion
coverage) and feed a small ExtraTrees classifier, so no deep-learning runtime is
required on the serving instance.

Treatment text is deliberately NOT duplicated here - the predicted condition is
looked up in the same disease library the text diagnosis uses, so both paths
give a farmer identical advice, including the native Hindi and Marathi wording.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from agrotech_ml.core.settings import AppSettings

logger = logging.getLogger(__name__)

LEAF_MODEL_FILENAME = "leaf_model.joblib"
# Below this the photo is treated as unreadable rather than guessed at: a wrong
# confident diagnosis costs a farmer a spray they did not need.
MIN_CONFIDENCE = 0.35


def leaf_model_path(settings: AppSettings) -> Path:
    return Path(settings.artifacts_dir) / LEAF_MODEL_FILENAME


@lru_cache(maxsize=1)
def _load(path_str: str, mtime: float) -> dict[str, Any] | None:
    """Load and cache the model; the mtime key busts the cache after retraining."""
    import joblib

    try:
        return joblib.load(path_str)
    except Exception as exc:
        logger.warning("leaf model unavailable at %s (%s)", path_str, exc)
        return None


def load_leaf_model(settings: AppSettings) -> dict[str, Any] | None:
    path = leaf_model_path(settings)
    if not path.is_file():
        return None
    return _load(str(path), path.stat().st_mtime)


def is_available(settings: AppSettings) -> bool:
    return load_leaf_model(settings) is not None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def predict(settings: AppSettings, image_bytes: bytes) -> dict[str, Any] | None:
    """Return ``{crop, condition, label, confidence, ranked}`` or ``None``.

    ``None`` means the model is missing or the image could not be read; the
    caller should fall back to the text path rather than inventing a result.
    """
    payload = load_leaf_model(settings)
    if payload is None:
        return None

    import io

    import numpy as np

    from agrotech_ml.services.leaf_features import extract_features

    try:
        features = extract_features(io.BytesIO(image_bytes)).reshape(1, -1)
    except Exception as exc:
        logger.info("leaf photo could not be read: %s", exc)
        return None

    pipeline = payload["pipeline"]
    probabilities = pipeline.predict_proba(features)[0]
    classes = list(pipeline.classes_)
    order = np.argsort(probabilities)[::-1]

    ranked = [
        {
            "crop": classes[i].split("|", 1)[0],
            "condition": classes[i].split("|", 1)[1],
            "probability": round(float(probabilities[i]), 4),
        }
        for i in order[:3]
    ]
    best = ranked[0]
    return {
        "crop": best["crop"],
        "condition": best["condition"],
        "label": slug(best["condition"]),
        "confidence": best["probability"],
        "confident": best["probability"] >= MIN_CONFIDENCE,
        "ranked": ranked,
        "model_accuracy": payload.get("accuracy"),
        "n_training_images": payload.get("n_images"),
    }


__all__ = ["predict", "is_available", "load_leaf_model", "leaf_model_path", "MIN_CONFIDENCE"]


def response_for(settings: AppSettings, prediction: dict[str, Any], language: str):
    """Build a DiseaseResponse directly from the disease library.

    Deliberately does NOT feed the predicted condition back through the text
    classifier: doing so re-classifies a label that is already known and picked
    the wrong disease (a healthy cotton leaf came back as leaf curl virus at
    0.94 confidence). The label from the photo model is looked up as-is.
    """
    from agrotech_ml.models.schemas import DiseaseResponse
    from agrotech_ml.services.inference import _load_disease_bundle

    condition = prediction["condition"]
    confidence = float(prediction["confidence"])

    if condition.strip().lower() == "healthy":
        healthy = {
            "en": ("Healthy", "No disease signs found in this photo. Keep monitoring the field weekly.",
                   ["Keep monitoring the crop weekly", "Remove weeds that host pests"]),
            "hi": ("स्वस्थ", "इस फ़ोटो में रोग के लक्षण नहीं मिले। खेत की हर हफ़्ते जाँच करते रहें।",
                   ["हर हफ़्ते फ़सल की जाँच करें", "कीट पालने वाले खरपतवार हटाएँ"]),
            "mr": ("निरोगी", "या फोटोत रोगाची लक्षणे आढळली नाहीत. शेताची दर आठवड्याला पाहणी करत रहा.",
                   ["दर आठवड्याला पिकाची पाहणी करा", "किडींना आश्रय देणारे तण काढा"]),
        }
        title, advice, actions = healthy.get(language, healthy["en"])
        return DiseaseResponse(
            disease=title, confidence=confidence, severity="low",
            advice=advice, preventive_actions=actions,
            treatment=advice, prevention=actions, source=None,
        )

    artifact = _load_disease_bundle(settings)
    library = (artifact or {}).get("library") or {}
    entry = library.get(slug(condition)) or {}
    native = (entry.get("translations") or {}).get(language) or {}

    treatment = str(native.get("treatment") or entry.get("treatment") or "").strip()
    title = str(native.get("title") or entry.get("title") or condition).strip()
    prevention = [str(item) for item in (entry.get("prevention") or [])]
    severity = str(entry.get("severity") or "moderate")
    if severity not in {"low", "moderate", "high"}:
        severity = "moderate"

    if not treatment:
        treatment = (
            "Show this photo to your nearest Krishi Vigyan Kendra before spraying."
        )

    return DiseaseResponse(
        disease=title, confidence=confidence, severity=severity,  # type: ignore[arg-type]
        advice=treatment, preventive_actions=prevention,
        treatment=treatment, prevention=prevention,
        source=str(entry.get("source") or "") or None,
    )
