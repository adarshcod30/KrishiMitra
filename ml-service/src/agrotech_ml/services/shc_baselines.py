"""District soil-nutrient baselines from the Soil Health Card portal.

data/shc_district_baselines.csv.gz aggregates block-level sample counts from
the official SHC nutrient dashboard (cycles 2023-24 + 2024-25) into per-district
class percentages: N/P/K/OC Low-Medium-High, pH Acidic-Neutral-Alkaline, EC
salinity and S/Fe/Zn/Cu/Mn/B deficiency. See scripts/fetch_shc_baselines.py.

Two uses: pre-filling the Soil Check form for a farmer who has no lab report
("typical for your district"), and turning their own numbers into a comparison
("your nitrogen is low - so is 62% of your district's").
"""
from __future__ import annotations

import csv
import gzip
import logging
import re
from functools import lru_cache
from typing import Any

from agrotech_ml.datafiles import data_file

logger = logging.getLogger(__name__)

DATASET = "shc_district_baselines.csv.gz"
SOURCE_NOTE = (
    "Soil Health Card nutrient dashboard, Dept. of Agriculture "
    "(cycles 2023-24 and 2024-25)"
)

# Representative mid-class values for pre-filling the form, expressed on the
# form's own input scales. A district whose nitrogen tests mostly "Low" gets a
# LOW starting value - the point is to reflect the district's typical soil,
# which the farmer then adjusts if they know better.
_PREFILL = {
    "n": {"low": 35.0, "medium": 75.0, "high": 120.0},
    "p": {"low": 8.0, "medium": 18.0, "high": 35.0},
    "k": {"low": 35.0, "medium": 70.0, "high": 130.0},
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower())


@lru_cache(maxsize=1)
def _load() -> dict[tuple[str, str], dict[str, Any]]:
    path = data_file(DATASET)
    if not path.is_file():
        logger.warning("SHC baselines missing at %s", path)
        return {}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            parsed: dict[str, Any] = {"state": row["state"], "district": row["district"]}
            for key, value in row.items():
                if key in ("state", "district"):
                    continue
                try:
                    parsed[key] = float(value) if value not in ("", None) else None
                except ValueError:
                    parsed[key] = None
            out[(_norm(row["state"]), _norm(row["district"]))] = parsed
    logger.info("loaded SHC baselines for %d districts", len(out))
    return out


def is_available() -> bool:
    return bool(_load())


# A nutrient class share computed from a handful of tests is noise, not a
# baseline. Districts routinely have thousands of P samples but only dozens of
# N samples in recent cycles, so each nutrient is gated on ITS OWN count.
MIN_NUTRIENT_SAMPLES = 100


def _dominant(row: dict[str, Any], stem: str) -> tuple[str, float] | None:
    if (row.get(f"{stem}_samples") or 0) < MIN_NUTRIENT_SAMPLES:
        return None
    classes = {c: row.get(f"{stem}_{c}_pct") for c in ("low", "medium", "high")}
    classes = {c: v for c, v in classes.items() if v is not None}
    if not classes:
        return None
    cls = max(classes, key=classes.get)
    return cls, classes[cls]


def baseline_for(state: str, district: str) -> dict[str, Any] | None:
    """District baseline summary, or None when the district is absent."""
    row = _load().get((_norm(state), _norm(district)))
    if not row or not row.get("samples_n"):
        return None

    summary: dict[str, Any] = {
        "district": row["district"],
        "state": row["state"],
        "samples": int(row["samples_n"]),
        "source": SOURCE_NOTE,
        "nutrients": {},
    }
    if summary["samples"] < MIN_NUTRIENT_SAMPLES:
        return None
    for stem, label in (("n", "Nitrogen"), ("p", "Phosphorus"),
                        ("k", "Potassium"), ("oc", "Organic Carbon")):
        dom = _dominant(row, stem)
        if dom:
            summary["nutrients"][label] = {
                "dominant_class": dom[0],
                "share_pct": dom[1],
                "low_pct": row.get(f"{stem}_low_pct"),
                "medium_pct": row.get(f"{stem}_medium_pct"),
                "high_pct": row.get(f"{stem}_high_pct"),
            }
    ph = {c: row.get(f"ph_{c}_pct") for c in ("acidic", "neutral", "alkaline")}
    ph = {c: v for c, v in ph.items() if v is not None}
    if (row.get("ph_samples") or 0) < MIN_NUTRIENT_SAMPLES:
        ph = {}
    if ph:
        cls = max(ph, key=ph.get)
        summary["ph"] = {"dominant_class": cls, "share_pct": ph[cls], **ph}
    deficiencies = {
        m.upper(): row.get(f"{m}_deficient_pct")
        for m in ("s", "fe", "zn", "cu", "mn", "b")
        if (row.get(f"{m}_deficient_pct") or 0) >= 30.0
    }
    if deficiencies:
        summary["widespread_deficiencies"] = deficiencies

    # Form pre-fill: mid-class values for the dominant class of each nutrient.
    prefill: dict[str, float] = {}
    for stem, field in (("n", "N"), ("p", "P"), ("k", "K")):
        dom = _dominant(row, stem)
        if dom:
            prefill[field] = _PREFILL[stem][dom[0]]
    if "ph" in summary:
        prefill["ph"] = {"acidic": 5.8, "neutral": 7.0, "alkaline": 8.2}[
            summary["ph"]["dominant_class"]
        ]
    summary["prefill"] = prefill
    return summary


__all__ = ["baseline_for", "is_available", "SOURCE_NOTE"]
