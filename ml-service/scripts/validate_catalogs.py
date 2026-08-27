"""Validate the committed data catalogues (schemes, disease symptoms, knowledge).

Run from ml-service/ with just the standard library:

    python3 scripts/validate_catalogs.py

Asserts the invariants the serving code and the frontend rely on:
- schemes_catalog.json: 10+ schemes, bilingual name/what_you_get/notes/steps,
  structured eligibility, official apply URL, source_url and verified_date on
  every entry.
- disease_symptoms.csv: 60+ rows, 10 target crops covered, every disease label
  has severity plus a treatment, prevention and source on its richest row.
- knowledge_library.json: 15+ articles, bilingual title/summary/body_points,
  valid category literals, source citation on every article.

Exits non-zero on the first failed assertion, so it can run in CI.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

EXPECTED_CROPS = {
    "rice",
    "wheat",
    "cotton",
    "tomato",
    "potato",
    "chilli",
    "maize",
    "sugarcane",
    "mustard",
    "gram",
}
VALID_SEVERITIES = {"low", "moderate", "high"}
VALID_CATEGORIES = {"production", "treatment", "horticulture", "soil", "market"}
VALID_FARMER_TYPES = {"marginal", "small", "medium", "large"}


def _bilingual(value: object, context: str) -> None:
    assert isinstance(value, dict), f"{context}: expected en/hi dict, got {type(value)}"
    for lang in ("en", "hi"):
        text = value.get(lang)
        assert isinstance(text, (str, list)) and text, f"{context}: missing '{lang}'"


def validate_schemes() -> int:
    payload = json.loads((DATA_DIR / "schemes_catalog.json").read_text("utf-8"))
    schemes = payload["schemes"]
    assert 10 <= len(schemes) <= 20, f"expected 10-20 schemes, found {len(schemes)}"
    seen_ids: set[str] = set()
    for scheme in schemes:
        sid = scheme.get("id")
        assert sid and sid not in seen_ids, f"missing/duplicate scheme id: {sid!r}"
        seen_ids.add(sid)
        _bilingual(scheme.get("name"), f"{sid}.name")
        _bilingual(scheme.get("what_you_get"), f"{sid}.what_you_get")

        eligibility = scheme.get("eligibility")
        assert isinstance(eligibility, dict), f"{sid}: eligibility must be structured"
        farmer_types = eligibility.get("farmer_types")
        assert farmer_types and set(farmer_types) <= VALID_FARMER_TYPES, (
            f"{sid}: bad farmer_types {farmer_types!r}"
        )
        assert "max_land_acres" in eligibility, f"{sid}: max_land_acres key required"
        states = eligibility.get("states")
        assert states == "all" or isinstance(states, list), f"{sid}: bad states"
        _bilingual(eligibility.get("notes"), f"{sid}.eligibility.notes")

        how_to_apply = scheme.get("how_to_apply")
        assert isinstance(how_to_apply, dict), f"{sid}: how_to_apply required"
        _bilingual(how_to_apply.get("steps"), f"{sid}.how_to_apply.steps")
        official = how_to_apply.get("official_url", "")
        assert official.startswith("http"), f"{sid}: official_url missing"
        assert str(scheme.get("source_url", "")).startswith("http"), (
            f"{sid}: source_url missing"
        )
        assert scheme.get("verified_date"), f"{sid}: verified_date missing"
    return len(schemes)


def validate_diseases() -> tuple[int, int]:
    with (DATA_DIR / "disease_symptoms.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 60, f"expected 60+ disease rows, found {len(rows)}"

    crops = {row["crop"].strip().lower() for row in rows}
    missing = EXPECTED_CROPS - crops
    assert not missing, f"crops without disease rows: {sorted(missing)}"

    by_label: dict[str, list[dict]] = {}
    for i, row in enumerate(rows, start=2):
        assert row["crop"].strip(), f"line {i}: crop required"
        assert len(row["symptoms_text"].strip()) >= 15, f"line {i}: symptoms too short"
        assert row["label"].strip(), f"line {i}: label required"
        assert row["disease"].strip(), f"line {i}: disease name required"
        assert row["severity"].strip() in VALID_SEVERITIES, f"line {i}: bad severity"
        by_label.setdefault(row["label"].strip(), []).append(row)

    assert len(by_label) >= 35, f"expected 35+ diseases, found {len(by_label)}"
    for label, group in by_label.items():
        richest = group[0]
        assert richest["treatment"].strip(), f"{label}: first row needs treatment"
        assert richest["prevention"].strip(), f"{label}: first row needs prevention"
        assert richest["source"].strip(), f"{label}: first row needs source citation"
        assert len(group) >= 2, f"{label}: needs 2+ symptom phrasings"
    return len(rows), len(by_label)


def validate_knowledge() -> int:
    payload = json.loads((DATA_DIR / "knowledge_library.json").read_text("utf-8"))
    articles = payload["articles"]
    assert len(articles) >= 15, f"expected 15+ articles, found {len(articles)}"
    seen_ids: set[str] = set()
    for article in articles:
        aid = article.get("id")
        assert aid and aid not in seen_ids, f"missing/duplicate article id: {aid!r}"
        seen_ids.add(aid)
        assert article.get("category") in VALID_CATEGORIES, f"{aid}: bad category"
        _bilingual(article.get("title"), f"{aid}.title")
        _bilingual(article.get("summary"), f"{aid}.summary")
        body = article.get("body_points")
        _bilingual(body, f"{aid}.body_points")
        assert len(body["en"]) >= 4 and len(body["hi"]) >= 4, (
            f"{aid}: needs 4+ body points per language"
        )
        assert str(article.get("source_url", "")).startswith("http"), (
            f"{aid}: source_url missing"
        )
    return len(articles)


def main() -> None:
    n_schemes = validate_schemes()
    n_rows, n_diseases = validate_diseases()
    n_articles = validate_knowledge()
    print(
        f"OK: {n_schemes} schemes, {n_rows} disease rows across "
        f"{n_diseases} diseases, {n_articles} knowledge articles"
    )


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"CATALOG VALIDATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
