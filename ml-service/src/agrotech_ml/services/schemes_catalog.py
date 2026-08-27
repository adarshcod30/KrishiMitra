"""Offline, verified catalogue of Government of India farmer schemes.

``data/schemes_catalog.json`` is a committed, human-verified snapshot of the
major currently-running central schemes (PM-KISAN, PMFBY, KCC, PM-KUSUM, Soil
Health Card, e-NAM, AIF, PMKSY-PDMC, SMAM, PKVY, PM-KMY, KCC-AH). Every entry
carries a ``source_url`` and ``verified_date``; amounts and rules were checked
against the cited official/press sources on that date. This module loads that
file and filters it by the fields of ``SchemeRecommendationRequest`` so the
API always has real schemes to show even when the live myScheme upstream is
down or unauthorised (its API key returns 401 without credentials).

The public entry point, :func:`recommend_from_catalog`, returns plain dicts
shaped like ``SchemeItem`` (id/title/description/eligibility/link/source) plus
a ``how_to_apply`` list of steps that the frontend renders when present.
Callers can pass the dicts straight to ``SchemeItem(**item)`` after dropping
keys their schema does not declare, or extend the schema additively.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ml-service/src/agrotech_ml/services/schemes_catalog.py -> ml-service/data/
DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "schemes_catalog.json"
)

_SUPPORTED_LANGS = ("en", "hi")

# (mtime, parsed payload) per path so serving never re-reads an unchanged file.
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load and cache the schemes catalogue JSON.

    Returns ``{"version": .., "verified_date": .., "schemes": [...]}``.
    Missing or unparseable files yield an empty catalogue rather than raising,
    because scheme recommendations must degrade, never 500.
    """
    catalog_path = path or DEFAULT_CATALOG_PATH
    key = str(catalog_path)
    try:
        mtime = catalog_path.stat().st_mtime
    except OSError:
        logger.warning("Schemes catalogue not found at %s", catalog_path)
        return {"version": 0, "verified_date": None, "schemes": []}

    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read schemes catalogue %s: %s", catalog_path, exc)
        return {"version": 0, "verified_date": None, "schemes": []}

    if not isinstance(payload.get("schemes"), list):
        payload["schemes"] = []
    with _cache_lock:
        _cache[key] = (mtime, payload)
    return payload


def catalog_schemes(path: Path | None = None) -> list[dict[str, Any]]:
    """All raw scheme entries, sorted by their ``priority`` field."""
    schemes = load_catalog(path)["schemes"]
    return sorted(schemes, key=lambda s: (s.get("priority", 999), s.get("id", "")))


def catalog_verified_date(path: Path | None = None) -> str | None:
    return load_catalog(path).get("verified_date")


def _lang(value: Any, language: str) -> str:
    """Pick the ``language`` variant of a bilingual field, falling back to en.

    Only en/hi are stored; every other language code gets English so the
    caller's translation layer (if configured) can take it from there.
    """
    if isinstance(value, dict):
        lang = language if language in _SUPPORTED_LANGS else "en"
        return str(value.get(lang) or value.get("en") or "")
    return str(value or "")


def _lang_list(value: Any, language: str) -> list[str]:
    if isinstance(value, dict):
        lang = language if language in _SUPPORTED_LANGS else "en"
        items = value.get(lang) or value.get("en") or []
    else:
        items = value or []
    return [str(item) for item in items if str(item).strip()]


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _state_matches(entry_states: Any, requested_state: str) -> bool:
    """True when the scheme applies in the farmer's state.

    ``states`` in the catalogue is either the string ``"all"`` or a list of
    state names. An empty/"India" request matches everything.
    """
    requested = _normalize(requested_state)
    if not requested or requested == "india":
        return True
    if entry_states in (None, "", "all"):
        return True
    if isinstance(entry_states, str):
        entry_states = [entry_states]
    for state in entry_states:
        normalized = _normalize(state)
        if normalized == "all" or requested in normalized or normalized in requested:
            return True
    return False


def _eligible(
    entry: dict[str, Any],
    *,
    farmer_type: str,
    land_size_acres: float,
    annual_income_lakh: float,
    state: str,
) -> bool:
    eligibility = entry.get("eligibility") or {}

    farmer_types = eligibility.get("farmer_types")
    if farmer_types and farmer_type and farmer_type not in farmer_types:
        return False

    max_land = eligibility.get("max_land_acres")
    if max_land is not None and land_size_acres > float(max_land):
        return False

    max_income = eligibility.get("max_annual_income_lakh")
    if max_income is not None and annual_income_lakh > float(max_income):
        return False

    return _state_matches(eligibility.get("states"), state)


def _to_scheme_item(entry: dict[str, Any], language: str) -> dict[str, Any]:
    eligibility = entry.get("eligibility") or {}
    how_to_apply = entry.get("how_to_apply") or {}
    link = str(
        how_to_apply.get("official_url") or entry.get("source_url") or ""
    )
    source_url = str(entry.get("source_url") or link)
    verified = entry.get("verified_date")
    source_note = f"Source: {source_url}"
    if verified:
        source_note += f" (verified {verified})"
    return {
        "id": str(entry.get("id", "")),
        "title": _lang(entry.get("name"), language),
        "description": _lang(entry.get("what_you_get"), language),
        "eligibility": _lang(eligibility.get("notes"), language),
        "link": link,
        "how_to_apply": _lang_list(how_to_apply.get("steps"), language),
        "source": source_note,
    }


def recommend_from_catalog(
    *,
    farmer_type: str = "small",
    land_size_acres: float = 2.0,
    annual_income_lakh: float = 2.0,
    state: str = "India",
    language: str = "en",
    limit: int = 8,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Filter the committed catalogue by the farmer's profile.

    Mirrors the fields of ``SchemeRecommendationRequest``. Always returns the
    eligible schemes in priority order (PM-KISAN, PMFBY, KCC first); never
    raises and never returns fabricated entries.
    """
    items: list[dict[str, Any]] = []
    for entry in catalog_schemes(path):
        try:
            if not _eligible(
                entry,
                farmer_type=farmer_type,
                land_size_acres=float(land_size_acres),
                annual_income_lakh=float(annual_income_lakh),
                state=state or "India",
            ):
                continue
        except (TypeError, ValueError):
            # A malformed entry must never take down recommendations.
            logger.warning("Skipping malformed scheme entry: %r", entry.get("id"))
            continue
        items.append(_to_scheme_item(entry, language))
        if len(items) >= max(1, int(limit)):
            break
    return items


__all__ = [
    "DEFAULT_CATALOG_PATH",
    "catalog_schemes",
    "catalog_verified_date",
    "load_catalog",
    "recommend_from_catalog",
]
