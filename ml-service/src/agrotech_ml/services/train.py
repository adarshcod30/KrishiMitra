import csv
import json
import logging
from pathlib import Path

from agrotech_ml.datafiles import data_file
from typing import Any

import joblib

from agrotech_ml.core.settings import AppSettings, get_settings
from agrotech_ml.services.training import train_models

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Disease model: trained from the curated, committed symptom dataset.
#
# data/disease_symptoms.csv is the source of truth (multiple labelled symptom
# descriptions per disease, plus treatment AND prevention text sourced from
# public agricultural extension material - see the CSV's own source column).
# The tiny sample file is only a last-resort fallback so a bare checkout still
# trains. The artifact payload carries a per-disease "library" (title,
# treatment, prevention, severity, source) so serving never needs the CSV.
# ---------------------------------------------------------------------------

DISEASE_CSV_FILENAME = "disease_symptoms.csv"
DISEASE_CSV_FALLBACK_FILENAME = "disease_symptoms_sample.csv"

_SEVERITIES = {"low", "moderate", "high"}

# Column aliases tolerated when reading the CSV, so the dataset file can
# evolve without breaking training. First match wins.
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "symptoms": ("symptoms", "symptom_text", "symptom", "symptoms_text"),
    "label": ("label", "disease_id", "disease_key", "id"),
    "title": ("title", "disease_name", "disease", "name"),
    "crop": ("crop", "crops", "host_crop"),
    "treatment": ("treatment", "advice", "treatment_text", "remedy"),
    "prevention": ("prevention", "preventive_actions", "prevention_text"),
    "severity": ("severity", "risk"),
    "source": ("source", "reference", "source_url", "citation"),
}


def disease_csv_path(settings: AppSettings) -> Path:
    """Prefer the curated dataset; fall back to the tiny committed sample."""
    data_dir = settings.data_path.parent
    curated = data_dir / DISEASE_CSV_FILENAME
    if curated.is_file():
        return curated
    return data_dir / DISEASE_CSV_FALLBACK_FILENAME


def _pick(row: dict[str, str], field: str) -> str:
    for alias in _COLUMN_ALIASES[field]:
        value = (row.get(alias) or "").strip()
        if value:
            return value
    return ""


def _split_list(value: str) -> list[str]:
    for separator in ("|", ";"):
        if separator in value:
            return [part.strip() for part in value.split(separator) if part.strip()]
    return [value.strip()] if value.strip() else []


def load_disease_rows(settings: AppSettings) -> list[dict[str, Any]]:
    """Read and normalise the disease symptom dataset.

    Returns rows shaped ``{symptoms, label, title, crop, treatment,
    prevention (list), severity, source}``. Rows without symptoms or a label
    are skipped.
    """
    path = disease_csv_path(settings)
    if not path.is_file():
        raise FileNotFoundError(
            f"Disease symptom dataset not found: {path}. "
            f"Commit data/{DISEASE_CSV_FILENAME} to train the disease model."
        )

    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = {
                (key or "").strip().lower(): (value or "").strip()
                for key, value in raw.items()
            }
            symptoms = _pick(row, "symptoms")
            label = _pick(row, "label") or _pick(row, "title")
            if not symptoms or not label:
                continue

            severity = _pick(row, "severity").lower()
            if severity not in _SEVERITIES:
                severity = "moderate"

            rows.append(
                {
                    "symptoms": symptoms,
                    "label": label.lower().replace(" ", "_"),
                    "title": _pick(row, "title") or label.replace("_", " ").title(),
                    "crop": _pick(row, "crop"),
                    "treatment": _pick(row, "treatment"),
                    "prevention": _split_list(_pick(row, "prevention")),
                    "severity": severity,
                    "source": _pick(row, "source"),
                    # Native-language text from the Kaggle Indian corpus. When
                    # present these are served verbatim, which is how a Hindi or
                    # Marathi speaker gets real advice rather than the built-in
                    # transliterator's Hinglish.
                    "translations": {
                        lang: {
                            "title": (row.get(f"disease_{lang}") or "").strip(),
                            "treatment": (row.get(f"treatment_{lang}") or "").strip(),
                        }
                        for lang in ("hi", "mr")
                    },
                }
            )
    if not rows:
        raise ValueError(f"Disease symptom dataset {path} contained no usable rows.")
    return rows


def _build_disease_library(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """One metadata record per disease label, taken from its richest row."""
    library: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = row["label"]
        entry = library.get(label)
        candidate = {
            "title": row["title"],
            "treatment": row["treatment"],
            "prevention": row["prevention"],
            "severity": row["severity"],
            "source": row["source"],
            "translations": row.get("translations") or {},
        }
        if entry is None:
            library[label] = candidate
            continue
        # Fill any blanks from later rows of the same disease.
        if not entry.get("treatment") and candidate["treatment"]:
            entry["treatment"] = candidate["treatment"]
        if not entry.get("prevention") and candidate["prevention"]:
            entry["prevention"] = candidate["prevention"]
        if not entry.get("source") and candidate["source"]:
            entry["source"] = candidate["source"]
        for lang, text in (candidate.get("translations") or {}).items():
            current = entry.setdefault("translations", {}).setdefault(
                lang, {"title": "", "treatment": ""}
            )
            for field in ("title", "treatment"):
                if not current.get(field) and text.get(field):
                    current[field] = text[field]
    return library


def train_disease_model(settings: AppSettings) -> dict[str, Any]:
    """Train the symptom-text classifier from the committed CSV and dump it.

    Overwrites ``settings.disease_model_path`` with a payload that also carries
    the per-disease treatment/prevention library, and returns that payload.
    Cheap by design (TF-IDF + logistic regression on a few hundred rows), so
    it can also run lazily in serving when only a legacy artifact is present.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    rows = load_disease_rows(settings)
    csv_path = disease_csv_path(settings)

    texts: list[str] = []
    labels: list[str] = []
    label_counts: dict[str, int] = {}
    for row in rows:
        label_counts[row["label"]] = label_counts.get(row["label"], 0) + 1

    # Light augmentation for under-represented labels only: the curated CSV
    # normally has several phrasings per disease already.
    paraphrases = ("in field condition", "during humid weather", "in early crop stage")
    for row in rows:
        text = f"{row['crop']} {row['symptoms']}".strip()
        texts.append(text)
        labels.append(row["label"])
        if label_counts[row["label"]] < 3:
            for suffix in paraphrases:
                texts.append(f"{text} {suffix}")
                labels.append(row["label"])

    model = Pipeline(
        steps=[
            (
                "vectorizer",
                TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True),
            ),
            (
                "classifier",
                # A higher C sharpens the probability spread: with the old
                # near-uniform outputs, "confidence" was stuck at the 1/n_classes
                # floor and distinct symptom texts collapsed onto one disease.
                LogisticRegression(max_iter=2400, C=8.0, random_state=settings.random_state),
            ),
        ]
    )
    model.fit(texts, labels)

    payload: dict[str, Any] = {
        "pipeline": model,
        "labels": sorted(set(labels)),
        "library": _build_disease_library(rows),
        "dataset": csv_path.name,
        "dataset_rows": len(rows),
        "trained_from_csv": True,
    }
    joblib.dump(payload, settings.disease_model_path)
    logger.info(
        "Disease model trained from %s (%d rows, %d diseases)",
        csv_path.name,
        len(rows),
        len(payload["library"]),
    )
    return payload


def main() -> None:
    settings = get_settings()
    metadata = train_models(settings)

    # train_models() writes a legacy toy disease artifact via the auxiliary
    # trainer; immediately replace it with the model built from the curated
    # symptom dataset so serving always has treatment + prevention content.
    disease_payload = train_disease_model(settings)

    summary = {
        "best_model": metadata.best_model,
        "dataset_rows": metadata.dataset_rows,
        "trained_at": metadata.trained_at.isoformat(),
        "auxiliary_models": metadata.auxiliary_models,
        "disease_dataset": disease_payload["dataset"],
        "disease_rows": disease_payload["dataset_rows"],
        "disease_labels": len(disease_payload["library"]),
        "leaf_classes": _train_leaf_model_if_possible(settings),
        "top_models": [
            {
                "model": score.model_name,
                "macro_f1": round(score.macro_f1, 4),
                "accuracy": round(score.accuracy, 4),
            }
            for score in metadata.model_scores[:3]
        ],
    }

    print(json.dumps(summary, indent=2))



def _train_leaf_model_if_possible(settings: AppSettings) -> int:
    """Rebuild the leaf-photo classifier from the committed feature CSV.

    Runs as part of the normal training pass so a deploy build produces the
    model without needing the multi-gigabyte image corpora, which are
    downloaded once, used to extract features, and deleted. Returns the number
    of classes, or 0 when the feature file is absent.
    """
    features_csv = data_file("leaf_features.csv")
    if not features_csv.is_file():
        return 0
    try:
        import csv as _csv

        import joblib
        import numpy as np
        from sklearn.ensemble import ExtraTreesClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        with features_csv.open(encoding="utf-8") as fh:
            rows = list(_csv.reader(fh))
        header, body = rows[0], rows[1:]
        labels = np.array([f"{r[0]}|{r[1]}" for r in body])
        matrix = np.array([[float(v) for v in r[2:]] for r in body], dtype=np.float32)

        model = Pipeline([
            ("scale", StandardScaler()),
            ("clf", ExtraTreesClassifier(
                n_estimators=120, min_samples_leaf=5, max_depth=24,
                max_features="sqrt", class_weight="balanced",
                n_jobs=-1, random_state=42)),
        ])
        model.fit(matrix, labels)
        joblib.dump(
            {
                "pipeline": model,
                "classes": sorted(set(labels.tolist())),
                "feature_names": header[2:],
                "n_images": len(labels),
            },
            Path(settings.artifacts_dir) / "leaf_model.joblib",
        )
        return len(set(labels.tolist()))
    except Exception as exc:  # never fail the whole training run for this
        logger.warning("leaf model not rebuilt: %s", exc)
        return 0

if __name__ == "__main__":
    main()
