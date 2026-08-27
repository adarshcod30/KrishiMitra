"""What actually grows well in a farmer's district, from government APY data.

Built from the Directorate of Economics & Statistics Area/Production/Yield
returns (2017-18 to 2022-23, 736 districts, 62 crops). See
scripts/build_apy_dataset.py and scripts/build_crop_suitability.py.

This answers a different question from the soil model. The soil model asks
"what suits these N/P/K/pH numbers"; this asks "what do 5 years of district
returns say actually yields here". Together they are far stronger than either
alone: a crop that fits the soil AND is proven in the district is a real
recommendation, while one that fits the soil but nobody grows is a warning.

Season note: states differ in how they file the same crop. Uttar Pradesh
reports sugarcane under Kharif while Karnataka and Maharashtra file it as Whole
Year, so a strict season filter silently hides a district's main crop. Lookups
therefore fall back to all seasons when the requested one has no rows.
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

DATASET = "crop_suitability.csv.gz"
SOURCE_NOTE = (
    "Directorate of Economics & Statistics, Ministry of Agriculture "
    "(Area, Production & Yield returns, 2017-18 to 2022-23)"
)

_NUMERIC = ("score", "yield_median", "area_median_ha", "yield_pctile", "area_share", "reliability")


def normalize(name: str) -> str:
    """Fold district/state spelling variants to a comparable key."""
    return re.sub(r"[^a-z]", "", (name or "").lower())


@lru_cache(maxsize=1)
def _load() -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Index rows by (state key, district key); empty dict when absent."""
    path = data_file(DATASET)
    if not path.is_file():
        logger.warning("crop suitability dataset not found at %s", path)
        return {}

    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for column in _NUMERIC:
                try:
                    row[column] = float(row[column])
                except (TypeError, ValueError):
                    row[column] = None
            try:
                row["rank_in_district"] = int(row["rank_in_district"])
            except (TypeError, ValueError):
                row["rank_in_district"] = 999
            index.setdefault((normalize(row["state"]), normalize(row["district"])), []).append(row)
    logger.info("loaded crop suitability for %d districts", len(index))
    return index


def is_available() -> bool:
    return bool(_load())


def districts_for_state(state: str) -> list[str]:
    key = normalize(state)
    return sorted({
        rows[0]["district"] for (state_key, _), rows in _load().items() if state_key == key
    })


def recommend(
    state: str, district: str, season: str | None = None, limit: int = 6
) -> dict[str, Any]:
    """Top crops for a district, best first.

    Returns ``{"crops": [...], "season_used": str|None, "source": str}``; an
    empty crop list simply means this district is not in the returns, which the
    caller should present as "no local data" rather than as a failure.
    """
    rows = _load().get((normalize(state), normalize(district)), [])
    if not rows:
        return {"crops": [], "season_used": None, "source": SOURCE_NOTE, "matched": False}

    selected = [r for r in rows if season and r["season"].lower() == season.lower()]
    season_used = season if selected else None
    if not selected:
        # Fall back across seasons; see the module docstring on UP sugarcane.
        selected = rows

    best: dict[str, dict[str, Any]] = {}
    for row in sorted(selected, key=lambda r: -(r["score"] or 0)):
        # Keep each crop once, at its strongest season.
        best.setdefault(row["crop"], row)

    crops = [
        {
            "crop": row["crop"],
            "season": row["season"],
            "score": round(row["score"] or 0, 3),
            "median_yield": row["yield_median"],
            "yield_unit": row.get("yield_unit") or "t/ha",
            "area_ha": row["area_median_ha"],
            # Plain-language reason a farmer can weigh, not a model number.
            "why": _why(row),
        }
        for row in list(best.values())[:limit]
    ]
    return {"crops": crops, "season_used": season_used, "source": SOURCE_NOTE, "matched": True}


def _why(row: dict[str, Any]) -> str:
    parts: list[str] = []
    pctile = row.get("yield_pctile")
    if pctile is not None and pctile >= 0.75:
        parts.append("yields better here than in most districts that grow it")
    elif pctile is not None and pctile <= 0.25:
        parts.append("yields below average here compared with other districts")
    area = row.get("area_median_ha") or 0
    if area >= 10000:
        parts.append(f"widely grown locally ({area:,.0f} ha)")
    elif area >= 500:
        parts.append(f"grown locally on about {area:,.0f} ha")
    reliability = row.get("reliability")
    if reliability is not None and reliability >= 0.8:
        parts.append("harvested consistently every year")
    return "; ".join(parts).capitalize() or "Recorded in the district returns."


__all__ = ["recommend", "districts_for_state", "is_available", "SOURCE_NOTE"]
