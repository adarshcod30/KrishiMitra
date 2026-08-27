#!/usr/bin/env python3
"""Build data/disease_symptoms.csv from the curated rows + the Kaggle corpus.

Two sources, deliberately merged rather than one replacing the other:

* ``data/disease_symptoms_curated.csv`` - hand-written rows carrying a real
  source URL and *prevention* advice, which the Kaggle set does not have.
* the Kaggle "Indian Crop Disease Dataset (Hindi and Marathi)" (CC BY 4.0) -
  2,231 farmer-phrased symptom questions over 11 Indian crops and 82 diseases,
  with remedies written natively in Hindi and Marathi. That native text is what
  lets the API answer a Hindi speaker without a machine-translation key.

Re-run after refreshing either source:
    python scripts/build_disease_dataset.py --kaggle <extracted_csv>
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
OUT = DATA / "disease_symptoms.csv"
CURATED = DATA / "disease_symptoms_curated.csv"

# The trainer expects these; hi/mr columns are additive and ignored by it.
FIELDS = [
    "crop", "symptoms_text", "disease", "label", "severity",
    "treatment", "prevention", "source",
    "crop_hi", "disease_hi", "symptoms_hi", "treatment_hi",
    "disease_mr", "symptoms_mr", "treatment_mr",
]

# Kaggle uses four severity words; the model only knows three buckets.
SEVERITY = {"mild": "low", "low": "low", "moderate": "moderate", "severe": "high"}

KAGGLE_SOURCE = (
    "Kaggle: ammar019/indian-crop-disease-dataset-hindi-and-marathi (CC BY 4.0)"
)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def norm(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none"} else text


def from_kaggle(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            disease = norm(raw.get("disease_name_en"))
            symptoms = norm(raw.get("question_en"))
            if not disease or not symptoms:
                continue
            rows.append({
                "crop": norm(raw.get("crop_name_en")).lower(),
                "symptoms_text": symptoms,
                "disease": disease,
                "label": slug(disease),
                "severity": SEVERITY.get(norm(raw.get("severity_level")).lower(), "moderate"),
                "treatment": norm(raw.get("remedy_en")),
                # The Kaggle set has no prevention column; `cause` is the closest
                # actionable text, so it seeds prevention rather than inventing any.
                "prevention": norm(raw.get("cause")),
                "source": KAGGLE_SOURCE,
                "crop_hi": norm(raw.get("crop_name_hi")),
                "disease_hi": norm(raw.get("disease_name_hi")),
                "symptoms_hi": norm(raw.get("question_hi")),
                "treatment_hi": norm(raw.get("remedy_hi")),
                "disease_mr": norm(raw.get("disease_name_mr")),
                "symptoms_mr": norm(raw.get("question_mr")),
                "treatment_mr": norm(raw.get("remedy_mr")),
            })
    return rows


def from_curated(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as fh:
        return [{**{k: "" for k in FIELDS}, **{k: norm(v) for k, v in row.items() if k in FIELDS}}
                for row in csv.DictReader(fh)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kaggle", type=Path, required=True)
    args = ap.parse_args()

    curated = from_curated(CURATED)
    kaggle = from_kaggle(args.kaggle)

    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    # Curated first so its prevention text and citation win any collision.
    for row in curated + kaggle:
        key = (row["label"], row["symptoms_text"].lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append({field: row.get(field, "") for field in FIELDS})

    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(merged)

    labels = {r["label"] for r in merged}
    print(f"curated={len(curated)} kaggle={len(kaggle)} merged={len(merged)}")
    print(f"diseases={len(labels)} crops={len({r['crop'] for r in merged})}")
    print(f"with Hindi remedy: {sum(1 for r in merged if r['treatment_hi'])}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
