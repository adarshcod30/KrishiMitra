"""Offline, source-cited farming knowledge library.

``data/knowledge_library.json`` is a committed set of bilingual (en/hi)
farming-practice articles - soil testing, drip vs flood, IPM, seed treatment,
crop rotation, mulching, composting, safe pesticide use, PM-KISAN enrolment,
post-harvest storage, intercropping, zero-till wheat, SRI rice, kitchen
gardens and more. Every article cites the public extension source it is based
on (``source_url``). This module serves the library and offers a naive
keyword search over it so the Knowledge tab has sound content even when live
web search (Brave/Wikipedia) is unavailable.

Article dicts returned here are shaped to slot into the API's
``KnowledgeArticle`` schema: ``{id, category, title, summary, url, source}``
plus ``body_points`` (a list of plain sentences the frontend may render as
bullets). ``category`` values are limited to the schema's literals:
production / treatment / horticulture / soil / market.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ml-service/src/agrotech_ml/services/knowledge_catalog.py -> ml-service/data/
DEFAULT_LIBRARY_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "knowledge_library.json"
)

_SUPPORTED_LANGS = ("en", "hi")
_VALID_CATEGORIES = {"production", "treatment", "horticulture", "soil", "market"}

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()

_TOKEN_RE = re.compile(r"[a-z0-9ऀ-ॿ]+")


def load_library(path: Path | None = None) -> dict[str, Any]:
    """Load and cache the knowledge library JSON (empty library on failure)."""
    library_path = path or DEFAULT_LIBRARY_PATH
    key = str(library_path)
    try:
        mtime = library_path.stat().st_mtime
    except OSError:
        logger.warning("Knowledge library not found at %s", library_path)
        return {"version": 0, "verified_date": None, "articles": []}

    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]

    try:
        payload = json.loads(library_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read knowledge library %s: %s", library_path, exc)
        return {"version": 0, "verified_date": None, "articles": []}

    if not isinstance(payload.get("articles"), list):
        payload["articles"] = []
    with _cache_lock:
        _cache[key] = (mtime, payload)
    return payload


def _lang(value: Any, language: str) -> str:
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


def _to_article(entry: dict[str, Any], language: str) -> dict[str, Any]:
    category = str(entry.get("category") or "production")
    if category not in _VALID_CATEGORIES:
        category = "production"
    return {
        "id": str(entry.get("id", "")),
        "category": category,
        "title": _lang(entry.get("title"), language),
        "summary": _lang(entry.get("summary"), language),
        "body_points": _lang_list(entry.get("body_points"), language),
        "url": str(entry.get("source_url") or "") or None,
        "source": str(entry.get("source_name") or "") or None,
    }


def knowledge_articles(
    language: str = "en", *, path: Path | None = None
) -> list[dict[str, Any]]:
    """The full library, localized, in priority order."""
    entries = load_library(path)["articles"]
    ordered = sorted(entries, key=lambda a: (a.get("priority", 999), a.get("id", "")))
    return [_to_article(entry, language) for entry in ordered]


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text or "").lower())


def _score(entry: dict[str, Any], query_tokens: list[str]) -> int:
    """Naive relevance: weighted token hits across both language variants."""
    if not query_tokens:
        return 0
    title = " ".join(
        _tokens(_lang(entry.get("title"), "en")) + _tokens(_lang(entry.get("title"), "hi"))
    )
    summary = " ".join(
        _tokens(_lang(entry.get("summary"), "en"))
        + _tokens(_lang(entry.get("summary"), "hi"))
    )
    body = " ".join(
        _tokens(" ".join(_lang_list(entry.get("body_points"), "en")))
        + _tokens(" ".join(_lang_list(entry.get("body_points"), "hi")))
    )
    score = 0
    for token in query_tokens:
        if token in title:
            score += 4
        if token in summary:
            score += 2
        if token in body:
            score += 1
    return score


def search_articles(
    query: str,
    *,
    language: str = "en",
    limit: int = 6,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Naive keyword search over the committed library.

    Matching articles come back most-relevant-first; a blank or unmatched
    query falls back to the top-priority articles so the caller never renders
    an empty Knowledge tab.
    """
    entries = load_library(path)["articles"]
    query_tokens = _tokens(query)
    limit = max(1, int(limit))

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for entry in entries:
        score = _score(entry, query_tokens)
        scored.append((score, entry.get("priority", 999), entry))

    matched = [item for item in scored if item[0] > 0]
    if matched:
        matched.sort(key=lambda item: (-item[0], item[1]))
        chosen = [entry for _, _, entry in matched[:limit]]
    else:
        ordered = sorted(scored, key=lambda item: item[1])
        chosen = [entry for _, _, entry in ordered[:limit]]

    return [_to_article(entry, language) for entry in chosen]


__all__ = [
    "DEFAULT_LIBRARY_PATH",
    "knowledge_articles",
    "load_library",
    "search_articles",
]
