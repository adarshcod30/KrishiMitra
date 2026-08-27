"""Seasonal context for mandi prices, from two years of Agmarknet history.

The live feed shows one day, which cannot say whether a price is good. These
baselines (data/mandi_seasonality.csv.gz, built by build_mandi_seasonality.py
from CC0 Kaggle data) add "typical for this month" bands and a seasonal index
for Potato, Onion, Wheat, Tomato and Rice. Commodities outside that history get
no claim at all rather than an invented one.
"""
from __future__ import annotations

import csv
import gzip
import logging
from datetime import date
from functools import lru_cache
from typing import Any

from agrotech_ml.datafiles import data_file

logger = logging.getLogger(__name__)

DATASET = "mandi_seasonality.csv.gz"
SOURCE_NOTE = "Agmarknet daily mandi prices 2023-2025 (via Kaggle, CC0)"

MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


@lru_cache(maxsize=1)
def _load() -> dict[tuple[str, str, int], dict[str, Any]]:
    path = data_file(DATASET)
    if not path.is_file():
        logger.warning("mandi seasonality dataset missing at %s", path)
        return {}
    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                key = (row["commodity"].strip().lower(),
                       row["state"].strip().lower(),
                       int(row["month"]))
                index[key] = {
                    "median": float(row["median"]),
                    "p25": float(row["p25"]),
                    "p75": float(row["p75"]),
                    "seasonal_index": float(row["seasonal_index"] or 1.0),
                    "n_obs": int(row["n_obs"]),
                }
            except (KeyError, ValueError):
                continue
    return index


def _lookup(commodity: str, state: str | None, month: int) -> dict[str, Any] | None:
    data = _load()
    name = (commodity or "").strip().lower()
    # crop names arrive as "Potato" from filters but "Onion Red" etc. from feeds
    for candidate in (name, name.split("(")[0].strip(), name.split()[0] if name else ""):
        if state:
            hit = data.get((candidate, state.strip().lower(), month))
            if hit:
                return hit
        hit = data.get((candidate, "all", month))
        if hit:
            return hit
    return None


def context_for(commodity: str, state: str | None = None,
                current_price: float | None = None,
                month: int | None = None) -> dict[str, Any] | None:
    """Seasonal context for one price row, or None when we have no history."""
    month = month or date.today().month
    hit = _lookup(commodity, state, month)
    if hit is None:
        return None

    result: dict[str, Any] = {
        "typical_min": hit["p25"],
        "typical_max": hit["p75"],
        "typical_median": hit["median"],
        "month": MONTH_NAMES[month],
        "source": SOURCE_NOTE,
    }
    index = hit["seasonal_index"]
    if index >= 1.15:
        result["season_note"] = (
            f"{MONTH_NAMES[month]} is usually a HIGH-price month for this crop."
        )
    elif index <= 0.85:
        result["season_note"] = (
            f"{MONTH_NAMES[month]} is usually a LOW-price month for this crop."
        )
    if current_price and hit["p25"] and hit["p75"]:
        if current_price > hit["p75"]:
            result["price_note"] = "Above the typical band for this month - a good time to sell."
        elif current_price < hit["p25"]:
            result["price_note"] = "Below the typical band for this month."
        else:
            result["price_note"] = "Within the typical band for this month."
    return result


def is_available() -> bool:
    return bool(_load())


__all__ = ["context_for", "is_available", "SOURCE_NOTE"]
