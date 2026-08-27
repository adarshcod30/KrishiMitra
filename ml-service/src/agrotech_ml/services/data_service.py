from __future__ import annotations

import asyncio
import csv
import html
import json
import io
import logging
import re
import threading
import time
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, TypeVar
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx

from agrotech_ml.core.i18n import LANGUAGE_LABELS, localize_crop_name, tr
from agrotech_ml.models.schemas import (
    DashboardSummary,
    FarmerSearchResult,
    InvestorOpportunity,
    KnowledgeArticle,
    LanguageCode,
    LocationSearchItem,
    MarketPriceItem,
    NewsItem,
    RentalTool,
    SchemeItem,
    SchemeRecommendationRequest,
    SchemeResponse,
    SearchResultItem,
    UserProfile,
    UserProfileCreate,
    WeatherDay,
    WeatherResponse,
)
from agrotech_ml.core.settings import AppSettings
from agrotech_ml.db.storage import (
    add_farm,
    dashboard_summary as storage_dashboard_summary,
    get_user,
    list_advisories,
    list_farms,
    list_uploads,
    search_users as storage_search_users,
    upsert_user,
)
from agrotech_ml.services.fallback_catalog import FALLBACK_AVAILABILITY, RENTAL_TOOL_CATALOG
from agrotech_ml.services.translation_service import is_translation_enabled, translate_text


logger = logging.getLogger(__name__)

T = TypeVar("T")

# The dashboard fans out to several third-party services. Each probe gets a
# short leash of its own so the aggregate stays well under a few seconds even
# when every upstream is down.
DASHBOARD_PROBE_TIMEOUT_SECONDS = 2.5

# api.data.gov.in silently black-holes requests that do not look like a browser
# (the connection is accepted and then never answered), which is what turned
# GET /market/prices into a guaranteed read-timeout -> HTTP 500.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

MARKET_SAMPLE_PATH = Path(__file__).resolve().parents[3] / "data" / "market_prices_sample.csv"
MARKET_ROW_LIMIT = 2000

# Mandi prices are published once a day, so re-fetching 100 KB of CSV on every
# request only buys latency and upstream throttling.
MARKET_CACHE_TTL_SECONDS = 300
_market_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
_market_cache_lock = threading.Lock()

# The eNAM logistics page is a slow scrape whose table no longer exists. Give it
# a short leash and remember the outcome (including "no rows") so a dead
# upstream costs one bounded request rather than one per caller.
RENTAL_SCRAPE_TIMEOUT_SECONDS = 5.0
RENTAL_CACHE_TTL_SECONDS = 600
_rental_cache: dict[str, tuple[float, str | None]] = {}
_rental_cache_lock = threading.Lock()

TAG_RE = re.compile(r"<[^>]+>")
DATA_GOV_URL_RE = re.compile(r'field_datafile_url:"([^"]+)"')
ENAM_LOGISTICS_ROW_RE = re.compile(
    r'<td[^>]*><b>(?P<name>[^<]+)</b></td>\s*<td><a href="(?P<url>[^"]+)"[^>]*>.*?</a><br ?/?>\s*(?P<description>.*?)</td>',
    flags=re.IGNORECASE | re.DOTALL,
)


def _clean_html_snippet(snippet: str) -> str:
    return html.unescape(TAG_RE.sub("", snippet)).strip()


STATE_MAPPING = {
    "up": "uttar pradesh",
    "mp": "madhya pradesh",
    "ap": "andhra pradesh",
    "hp": "himachal pradesh",
    "jk": "jammu and kashmir",
    "wb": "west bengal",
    "tn": "tamil nadu",
    "kl": "kerala",
    "ka": "karnataka",
    "mh": "maharashtra",
    "gj": "gujarat",
    "rj": "rajasthan",
    "pb": "punjab",
    "hr": "haryana",
    "uk": "uttarakhand",
    "br": "bihar",
    "jh": "jharkhand",
    "ct": "chhattisgarh",
    "od": "odisha",
    "as": "assam",
    "ts": "telangana",
}


def _normalize_state(state: str) -> str:
    if not state:
        return ""
    s = state.strip().lower()
    return STATE_MAPPING.get(s, s)


def _strip_markdown(text: str) -> str:
    cleaned = re.sub(r"[#*_`>\-]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return html.unescape(cleaned).strip()


def _translate_value(settings: AppSettings, value: str, language: LanguageCode) -> str:
    if language == "en" or not value:
        return value
    return translate_text(settings, value, language)


def _official_browser_headers(referer: str, api_key: str | None = None) -> dict[str, str]:
    """Browser-like headers for the public MyScheme endpoints.

    The API key is supplied from settings (AGROTECH_MYSCHEME_API_KEY) and is
    omitted entirely when unset, so no credential is ever embedded in source.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Origin": "https://www.myscheme.gov.in",
        "Referer": referer,
    }
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _safe_first(values: list[str | None]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _get_timeout(settings: AppSettings, override: float | None = None) -> float:
    if override is not None:
        return max(0.5, float(override))
    return float(settings.request_timeout_seconds)


def _with_default_headers(headers: dict[str, str] | None) -> dict[str, str]:
    merged = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    if headers:
        merged.update(headers)
    return merged


async def _http_get_text(
    url: str,
    *,
    settings: AppSettings,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float | None = None,
) -> str:
    async with httpx.AsyncClient(
        timeout=_get_timeout(settings, timeout), follow_redirects=True
    ) as client:
        response = await client.get(url, headers=_with_default_headers(headers), params=params)
        response.raise_for_status()
        return response.text


def _http_get_text_sync(
    url: str,
    *,
    settings: AppSettings,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float | None = None,
) -> str:
    with httpx.Client(timeout=_get_timeout(settings, timeout), follow_redirects=True) as client:
        response = client.get(url, headers=_with_default_headers(headers), params=params)
        response.raise_for_status()
        return response.text


def _http_get_json_sync(
    url: str,
    *,
    settings: AppSettings,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float | None = None,
) -> dict:
    with httpx.Client(timeout=_get_timeout(settings, timeout), follow_redirects=True) as client:
        response = client.get(url, headers=_with_default_headers(headers), params=params)
        response.raise_for_status()
        return response.json()


async def _probe(
    factory: Callable[[], T],
    *,
    fallback: T,
    label: str,
    timeout: float = DASHBOARD_PROBE_TIMEOUT_SECONDS,
) -> T:
    """Run a blocking probe off the event loop, bounded by ``timeout``.

    Any failure (timeout, HTTP error, parse error) degrades to ``fallback``
    rather than propagating: a dashboard is not worth a 500.
    """
    try:
        return await asyncio.wait_for(asyncio.to_thread(factory), timeout=timeout)
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("Dashboard probe %s timed out after %.1fs", label, timeout)
    except Exception as exc:  # noqa: BLE001 - degraded dashboards beat broken ones
        logger.warning("Dashboard probe %s failed: %s", label, exc)
    return fallback


def _extract_data_gov_csv_url(page_html: str) -> str:
    match = DATA_GOV_URL_RE.search(page_html)
    if not match:
        raise RuntimeError("Unable to locate the live market CSV URL from data.gov.in")

    encoded = match.group(1)
    decoded = encoded.replace(r"\u002F", "/")
    decoded = html.unescape(decoded)
    return _sanitize_data_gov_url(decoded)


def _sanitize_data_gov_url(url: str) -> str:
    """Repair the resource URL data.gov.in embeds in its catalogue page.

    The published value ends in a percent-encoded CRLF (``limit=all%0D%0A``),
    which the resource API rejects with a validation error, and it carries no
    ``format`` parameter so the API answers XML instead of CSV. Both are
    normalised here; the api-key and resource id are preserved as published.
    """
    parts = urlsplit(url.strip())
    query = dict(parse_qsl(parts.query, keep_blank_values=True))

    limit = (query.get("limit") or "").strip()
    if not limit.isdigit():
        limit = str(MARKET_ROW_LIMIT)
    query["limit"] = limit
    query["offset"] = (query.get("offset") or "0").strip() or "0"
    query["format"] = "csv"

    cleaned = {key.strip(): str(value).strip() for key, value in query.items()}
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(cleaned), ""))


def _cached_market_rows(key: str) -> list[dict[str, str]] | None:
    with _market_cache_lock:
        entry = _market_cache.get(key)
    if entry is None:
        return None
    stored_at, rows = entry
    if time.monotonic() - stored_at > MARKET_CACHE_TTL_SECONDS:
        return None
    return rows


def _store_market_rows(key: str, rows: list[dict[str, str]]) -> None:
    with _market_cache_lock:
        _market_cache[key] = (time.monotonic(), rows)


def clear_market_cache() -> None:
    with _market_cache_lock:
        _market_cache.clear()


def _load_market_rows(
    settings: AppSettings,
    *,
    timeout: float | None = None,
) -> list[dict[str, str]]:
    cache_key = settings.data_gov_market_catalog_url
    cached = _cached_market_rows(cache_key)
    if cached is not None:
        return cached

    catalog_page = _http_get_text_sync(
        settings.data_gov_market_catalog_url, settings=settings, timeout=timeout
    )
    csv_url = _extract_data_gov_csv_url(catalog_page)
    csv_payload = _http_get_text_sync(csv_url, settings=settings, timeout=timeout)
    if not csv_payload.lstrip().startswith("State,"):
        raise RuntimeError("data.gov.in did not return the expected market CSV payload")

    rows = list(csv.DictReader(io.StringIO(csv_payload)))
    if rows:
        _store_market_rows(cache_key, rows)
    return rows


def _load_market_sample_rows() -> list[dict[str, str]]:
    """Committed offline snapshot, reshaped like the live data.gov.in CSV."""
    if not MARKET_SAMPLE_PATH.is_file():
        return []

    rows: list[dict[str, str]] = []
    with MARKET_SAMPLE_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                arrival = datetime.strptime((row.get("date") or "").strip(), "%Y-%m-%d").date()
            except ValueError:
                continue
            rows.append(
                {
                    "State": (row.get("state") or "").strip(),
                    "District": "",
                    "Market": (row.get("mandi") or "").strip(),
                    "Commodity": (row.get("crop") or "").strip(),
                    "Arrival_Date": arrival.strftime("%d/%m/%Y"),
                    "Modal_x0020_Price": (row.get("modal_price_inr_quintal") or "").strip(),
                }
            )
    return rows


def _market_item_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        row.get("State", "").strip(),
        row.get("Market", "").strip(),
        row.get("Commodity", "").strip(),
    )


def _market_trend(current_price: float, previous_price: float | None) -> str:
    if previous_price is None:
        return "stable"
    delta = current_price - previous_price
    if abs(delta) <= 1:
        return "stable"
    return "up" if delta > 0 else "down"


def market_prices(
    settings: AppSettings,
    language: LanguageCode,
    *,
    crop: str | None = None,
    state: str | None = None,
    timeout: float | None = None,
) -> tuple[list[MarketPriceItem], bool]:
    """Return ``(items, live)`` and never raise.

    ``live`` is True only when the data.gov.in feed answered. Otherwise the
    committed ``data/market_prices_sample.csv`` snapshot is served, so the
    endpoint is always a 200 with usable content.
    """
    try:
        rows = _load_market_rows(settings, timeout=timeout)
        items = _build_market_items(settings, rows, language, crop=crop, state=state)
        if items:
            return items, True
        logger.warning("data.gov.in returned no usable market rows; using offline snapshot")
    except Exception as exc:  # noqa: BLE001 - upstream flakiness must not 500
        logger.warning("Live market price fetch failed (%s); using offline snapshot", exc)

    sample = _build_market_items(
        settings, _load_market_sample_rows(), language, crop=crop, state=state
    )
    return sample, False


def localize_market_prices(
    settings: AppSettings,
    language: LanguageCode,
    *,
    crop: str | None = None,
    state: str | None = None,
    timeout: float | None = None,
) -> list[MarketPriceItem]:
    items, _live = market_prices(
        settings, language, crop=crop, state=state, timeout=timeout
    )
    return items


def _build_market_items(
    settings: AppSettings,
    rows: list[dict[str, str]],
    language: LanguageCode,
    *,
    crop: str | None = None,
    state: str | None = None,
) -> list[MarketPriceItem]:
    if not rows:
        return []

    crop_filter = crop.strip().lower() if crop else None
    state_filter = state.strip().lower() if state else None

    parsed_rows: list[tuple[date, dict[str, str]]] = []
    for row in rows:
        try:
            arrival_date = datetime.strptime(row.get("Arrival_Date", ""), "%d/%m/%Y").date()
            modal_price = float(row.get("Modal_x0020_Price", "0") or 0)
        except ValueError:
            continue

        if modal_price <= 0:
            continue
        if crop_filter and crop_filter not in row.get("Commodity", "").lower():
            continue
        if state_filter and state_filter not in row.get("State", "").lower():
            continue
        parsed_rows.append((arrival_date, row))

    if not parsed_rows:
        return []

    latest_date = max(item[0] for item in parsed_rows)
    latest_rows = [row for arrival_date, row in parsed_rows if arrival_date == latest_date]

    previous_prices: dict[tuple[str, str, str], tuple[date, float]] = {}
    for arrival_date, row in parsed_rows:
        if arrival_date >= latest_date:
            continue
        key = _market_item_key(row)
        try:
            modal_price = float(row.get("Modal_x0020_Price", "0") or 0)
        except ValueError:
            continue

        existing = previous_prices.get(key)
        if existing is None or arrival_date > existing[0]:
            previous_prices[key] = (arrival_date, modal_price)

    items: list[MarketPriceItem] = []
    for row in latest_rows[:80]:
        current_price = float(row.get("Modal_x0020_Price", "0") or 0)
        key = _market_item_key(row)
        previous_price = previous_prices.get(key, (None, None))[1]
        items.append(
            MarketPriceItem(
                crop=localize_crop_name(row.get("Commodity", ""), language),
                mandi=_translate_value(settings, row.get("Market", ""), language),
                state=_translate_value(settings, row.get("State", ""), language),
                modal_price_inr_quintal=current_price,
                trend=_market_trend(current_price, previous_price),
                arrival_date=latest_date,
                source_url=settings.data_gov_market_catalog_url,
            )
        )

    items.sort(key=lambda item: (item.state, item.crop, item.mandi))
    return items[:40]


def _myscheme_search(
    settings: AppSettings,
    *,
    keyword: str,
    size: int = 8,
    timeout: float | None = None,
) -> list[dict]:
    base_url = f"{settings.myscheme_api_url}/search/v6/schemes"
    try:
        payload = _http_get_json_sync(
            base_url,
            settings=settings,
            headers=_official_browser_headers(
                "https://www.myscheme.gov.in/search", settings.myscheme_api_key
            ),
            params={"lang": "en", "keyword": keyword, "from": "0", "size": str(size)},
            timeout=timeout,
        )
        return payload.get("data", {}).get("hits", {}).get("items", [])
    except Exception:
        return []


def _myscheme_scheme_details(settings: AppSettings, slug: str) -> dict:
    base_url = f"{settings.myscheme_api_url}/schemes/v6/public/schemes"
    payload = _http_get_json_sync(
        base_url,
        settings=settings,
        headers=_official_browser_headers(
            f"https://www.myscheme.gov.in/schemes/{slug}", settings.myscheme_api_key
        ),
        params={"slug": slug, "lang": "en"},
    )
    return payload.get("data", {})


def _myscheme_scheme_link(slug: str, details: dict) -> str:
    en_content = details.get("en", {})
    references = en_content.get("schemeContent", {}).get("references", [])
    if references:
        link = references[0].get("url")
        if isinstance(link, str) and link.strip():
            return link.strip()

    application_process = en_content.get("applicationProcess", [])
    for item in application_process:
        link = item.get("url")
        if isinstance(link, str) and link.strip():
            return link.strip()

    return f"https://www.myscheme.gov.in/schemes/{slug}"


def _myscheme_description(details: dict) -> str:
    en_content = details.get("en", {})
    scheme_content = en_content.get("schemeContent", {})
    return _safe_first(
        [
            scheme_content.get("briefDescription"),
            _strip_markdown(scheme_content.get("benefits_md", "")),
            _strip_markdown(scheme_content.get("detailedDescription_md", "")),
        ]
    )


def _myscheme_eligibility(details: dict) -> str:
    en_content = details.get("en", {})
    eligibility = en_content.get("eligibilityCriteria", {})
    return _safe_first(
        [
            _strip_markdown(eligibility.get("eligibilityDescription_md", "")),
            _strip_markdown(json.dumps(eligibility.get("eligibilityDescription", []), ensure_ascii=False)),
        ]
    )


def _upstream_scheme_items(
    settings: AppSettings, payload: SchemeRecommendationRequest
) -> list[SchemeItem]:
    """Live MyScheme recommendations. Empty when the API key is unset or dead.

    The public MyScheme endpoints answer 401 without an x-api-key, so when no
    key is configured we skip the round-trips entirely instead of burning a
    request per keyword just to collect failures.
    """
    if not settings.myscheme_api_key:
        return []

    keywords = ["farmer agriculture scheme"]
    if payload.farmer_type in {"small", "marginal"}:
        keywords.append("farmer subsidy insurance credit")
    if payload.annual_income_lakh <= 3:
        keywords.append("income support farmer")
    if payload.land_size_acres >= 5:
        keywords.append("farm mechanization irrigation")
    if payload.state and payload.state.lower() != "india":
        keywords.append(f"farmer scheme {payload.state}")

    seen_slugs: set[str] = set()
    items: list[SchemeItem] = []
    for keyword in keywords:
        for hit in _myscheme_search(settings, keyword=keyword, size=12):
            fields = hit.get("fields") or {}
            slug = fields.get("slug")
            if not slug or slug in seen_slugs:
                continue

            states = fields.get("beneficiaryState") or []
            if isinstance(states, str):
                states = [states]

            if payload.state and payload.state.lower() != "india":
                normalized_state = _normalize_state(payload.state)
                # Fuzzy match: state match if either name contains the other or it's "all"
                if states and isinstance(states, list):
                    matched = False
                    for s in states:
                        s_low = str(s or "").lower()
                        if s_low == "all" or normalized_state in s_low or s_low in normalized_state:
                            matched = True
                            break
                    if not matched:
                        continue

            try:
                details = _myscheme_scheme_details(settings, slug)
            except Exception:
                continue

            description = _myscheme_description(details)
            eligibility = _myscheme_eligibility(details)
            if not description:
                description = str(fields.get("briefDescription") or "")
            if not eligibility:
                eligibility = "Check the official scheme page for the latest eligibility conditions."

            title = str(fields.get("schemeName") or slug)
            source = "myScheme"
            items.append(
                SchemeItem(
                    id=str(hit.get("id") or slug),
                    title=_translate_value(settings, title, payload.language),
                    description=_translate_value(settings, description, payload.language),
                    eligibility=_translate_value(settings, eligibility, payload.language),
                    link=_myscheme_scheme_link(slug, details),
                    source=source,
                )
            )
            seen_slugs.add(slug)
            if len(items) >= 6:
                return items
    return items


SCHEMES_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "schemes_catalog.json"


def _catalog_text(value: object, language: LanguageCode) -> str:
    """Pick the language variant from a ``{"en": ..., "hi": ...}`` block.

    The committed catalogue carries native English and Hindi text; other
    languages fall back to English (the caller may translate further).
    """
    if isinstance(value, dict):
        for candidate in (language, "en"):
            text = value.get(candidate)
            if isinstance(text, str) and text.strip():
                return text.strip()
            if isinstance(text, list):
                joined = " ".join(str(part).strip() for part in text if str(part).strip())
                if joined:
                    return joined
        return ""
    return str(value or "").strip()


def _builtin_catalog_scheme_rows(
    settings: AppSettings, payload: SchemeRecommendationRequest
) -> list[dict]:
    """Insurance reader for ``data/schemes_catalog.json``.

    Only used when :mod:`agrotech_ml.services.schemes_catalog` (the primary
    owner of the catalogue logic) cannot be imported or fails. Applies the
    same eligibility filters the request describes and returns
    ``SchemeItem``-shaped dicts.
    """
    with SCHEMES_CATALOG_PATH.open(encoding="utf-8") as handle:
        catalog = json.load(handle)

    verified_date = str(catalog.get("verified_date") or "").strip()
    language = payload.language
    needs_translation = language not in {"en", "hi"}
    normalized_state = _normalize_state(payload.state) if payload.state else ""

    rows: list[dict] = []
    for entry in sorted(
        catalog.get("schemes", []), key=lambda item: item.get("priority", 999)
    ):
        eligibility = entry.get("eligibility") or {}

        farmer_types = eligibility.get("farmer_types") or []
        if farmer_types and payload.farmer_type not in farmer_types:
            continue
        max_land = eligibility.get("max_land_acres")
        if max_land is not None and payload.land_size_acres > float(max_land):
            continue
        max_income = eligibility.get("max_annual_income_lakh")
        if max_income is not None and payload.annual_income_lakh > float(max_income):
            continue
        states = eligibility.get("states")
        if (
            normalized_state
            and normalized_state != "india"
            and isinstance(states, list)
            and states
        ):
            state_match = any(
                _normalize_state(str(s)) in {normalized_state, "all"}
                or normalized_state in _normalize_state(str(s))
                for s in states
            )
            if not state_match:
                continue

        title = _catalog_text(entry.get("name"), language)
        description = _catalog_text(entry.get("what_you_get"), language)
        eligibility_text = _catalog_text((eligibility.get("notes") or {}), language)
        if needs_translation:
            title = _translate_value(settings, title, language)
            description = _translate_value(settings, description, language)
            eligibility_text = _translate_value(settings, eligibility_text, language)

        source_label = "Official catalogue"
        if verified_date:
            source_label = f"Official catalogue (verified {verified_date})"

        rows.append(
            {
                "id": str(entry.get("id") or ""),
                "title": title,
                "description": description,
                "eligibility": eligibility_text
                or "Check the official scheme page for the latest eligibility conditions.",
                "link": str(entry.get("source_url") or "https://www.myscheme.gov.in/"),
                "source": source_label,
            }
        )
    return rows


def _catalog_scheme_items(
    settings: AppSettings, payload: SchemeRecommendationRequest
) -> list[SchemeItem]:
    """Recommendations from the committed offline catalogue.

    Delegates to :mod:`agrotech_ml.services.schemes_catalog`, which owns the
    verified ``data/schemes_catalog.json`` content and its request filtering.
    If that module is unavailable or errors, a minimal built-in reader for the
    same committed JSON keeps the endpoint from ever going silently empty.
    Never raises: schemes are a flagship social feature, and a catalogue bug
    must degrade to fewer results, not a 500.
    """
    rows: list[dict] | None = None
    try:
        from agrotech_ml.services.schemes_catalog import recommend_from_catalog

        rows = recommend_from_catalog(
            farmer_type=payload.farmer_type,
            land_size_acres=payload.land_size_acres,
            annual_income_lakh=payload.annual_income_lakh,
            state=payload.state,
            language=payload.language,
            limit=MAX_SCHEME_RESULTS,
        )
    except Exception as exc:  # noqa: BLE001 - fall through to the built-in reader
        logger.warning("schemes_catalog module unavailable (%s); using built-in reader", exc)

    if rows is None:
        try:
            rows = _builtin_catalog_scheme_rows(settings, payload)
        except Exception as exc:  # noqa: BLE001 - degrade, never break the endpoint
            logger.error("Offline scheme catalogue unavailable: %s", exc)
            return []

    # The catalogue stores native en/hi text; any other language goes through
    # the translation layer (a no-op when translation is not configured).
    translate = payload.language not in {"en", "hi"}

    items: list[SchemeItem] = []
    for row in rows:
        try:
            item = SchemeItem.model_validate(row)
        except Exception as exc:  # noqa: BLE001 - skip malformed rows, keep the rest
            logger.warning("Skipping malformed catalogue scheme row: %s", exc)
            continue
        if translate:
            item.title = _translate_value(settings, item.title, payload.language)
            item.description = _translate_value(settings, item.description, payload.language)
            item.eligibility = _translate_value(settings, item.eligibility, payload.language)
            item.how_to_apply = [
                _translate_value(settings, step, payload.language)
                for step in item.how_to_apply
            ]
        items.append(item)
    return items


MAX_SCHEME_RESULTS = 12

_SCHEME_SOURCE_NOTES = {
    "myscheme_live": "Live matches from the official myScheme portal.",
    "official_catalog": (
        "Shown from the official scheme catalogue maintained with this app "
        "and verified against government sources. Confirm the latest rules "
        "on each scheme's official page."
    ),
    "myscheme_live+official_catalog": (
        "Live myScheme matches, topped up from the verified official scheme "
        "catalogue maintained with this app."
    ),
}


def recommend_schemes(
    settings: AppSettings, payload: SchemeRecommendationRequest
) -> SchemeResponse:
    """Scheme recommendations that are never silently empty.

    Order of preference: live MyScheme results (only possible when an API key
    is configured), merged with — or replaced by — the committed offline
    catalogue filtered by the farmer's profile. The response carries a
    ``source`` label and human ``note`` so the UI can say where the
    recommendations came from.
    """
    upstream = _upstream_scheme_items(settings, payload)
    catalog = _catalog_scheme_items(settings, payload)

    seen_titles = {item.title.strip().lower() for item in upstream}
    seen_ids = {item.id for item in upstream}
    merged = list(upstream)
    for item in catalog:
        if item.id in seen_ids or item.title.strip().lower() in seen_titles:
            continue
        merged.append(item)
        seen_ids.add(item.id)
        seen_titles.add(item.title.strip().lower())
        if len(merged) >= MAX_SCHEME_RESULTS:
            break

    if upstream and len(merged) > len(upstream):
        source = "myscheme_live+official_catalog"
    elif upstream:
        source = "myscheme_live"
    elif merged:
        source = "official_catalog"
    else:
        # Catalogue filtering can legitimately produce nothing only for very
        # unusual inputs; say so honestly instead of blaming the farmer.
        source = "official_catalog"

    note = _SCHEME_SOURCE_NOTES[source]
    return SchemeResponse(
        schemes=merged,
        source=source,
        note=_translate_value(settings, note, payload.language),
    )


def rental_tools(
    settings: AppSettings,
    language: LanguageCode,
    *,
    location: str | None = None,
    timeout: float | None = None,
) -> tuple[list[RentalTool], bool]:
    """Return ``(tools, live)`` and never raise.

    The eNAM logistics page no longer renders the provider table this scraper
    was written against (zero ``<td>`` elements today), so the live path
    reliably yields nothing. When that happens the committed catalogue is
    served instead of an empty list.
    """
    try:
        scraped = _scrape_enam_rental_tools(
            settings, language, location=location, timeout=timeout
        )
        if scraped:
            return scraped, True
        logger.info("eNAM logistics page matched no providers; using offline catalogue")
    except Exception as exc:  # noqa: BLE001 - upstream flakiness must not 500
        logger.warning("eNAM logistics fetch failed (%s); using offline catalogue", exc)

    return _fallback_rental_tools(settings, language, location=location), False


def localize_rental_tools(
    settings: AppSettings,
    language: LanguageCode,
    *,
    location: str | None = None,
    timeout: float | None = None,
) -> list[RentalTool]:
    tools, _live = rental_tools(settings, language, location=location, timeout=timeout)
    return tools


def _fallback_rental_tools(
    settings: AppSettings,
    language: LanguageCode,
    *,
    location: str | None = None,
) -> list[RentalTool]:
    location_filter = location.strip().lower() if location else None
    results: list[RentalTool] = []
    for entry in RENTAL_TOOL_CATALOG:
        coverage = str(entry["location"])
        name = str(entry["name"])
        if location_filter:
            haystack = f"{coverage} {name} {entry['provider']}".lower()
            if location_filter not in haystack and "pan-india" not in coverage.lower():
                continue
        results.append(
            RentalTool(
                name=_translate_value(settings, name, language),
                hourly_rate_inr=entry["hourly_rate_inr"],  # type: ignore[arg-type]
                provider=_translate_value(settings, str(entry["provider"]), language),
                location=_translate_value(settings, coverage, language),
                availability=_translate_value(settings, FALLBACK_AVAILABILITY, language),
                service_type=_translate_value(settings, str(entry["service_type"]), language),
                source_url=str(entry["source_url"]),
            )
        )
    return results


def _enam_page(settings: AppSettings, timeout: float | None) -> str | None:
    """Fetch the eNAM page through a short-TTL cache. ``None`` means unreachable."""
    key = settings.enam_logistics_url
    with _rental_cache_lock:
        entry = _rental_cache.get(key)
    if entry is not None and time.monotonic() - entry[0] <= RENTAL_CACHE_TTL_SECONDS:
        return entry[1]

    budget = min(
        RENTAL_SCRAPE_TIMEOUT_SECONDS,
        float(timeout) if timeout is not None else float(settings.request_timeout_seconds),
    )
    try:
        page: str | None = _http_get_text_sync(key, settings=settings, timeout=budget)
    except Exception as exc:  # noqa: BLE001 - cached as a negative result
        logger.warning("eNAM logistics fetch failed (%s); caching offline fallback", exc)
        page = None

    with _rental_cache_lock:
        _rental_cache[key] = (time.monotonic(), page)
    return page


def clear_rental_cache() -> None:
    with _rental_cache_lock:
        _rental_cache.clear()


def _scrape_enam_rental_tools(
    settings: AppSettings,
    language: LanguageCode,
    *,
    location: str | None = None,
    timeout: float | None = None,
) -> list[RentalTool]:
    page = _enam_page(settings, timeout)
    if page is None:
        return []
    location_filter = location.lower() if location else None
    results: list[RentalTool] = []
    for match in ENAM_LOGISTICS_ROW_RE.finditer(page):
        name = _clean_html_snippet(match.group("name"))
        url = match.group("url").strip()
        description = _clean_html_snippet(match.group("description"))
        coverage = "Pan-India"
        if location_filter and location_filter not in description.lower() and location_filter not in name.lower():
            continue
        if "presence in" in description.lower():
            coverage = description.split("presence in", 1)[1].split(".", 1)[0].strip().title()
        elif "all states" in description.lower() or "across the country" in description.lower():
            coverage = "Pan-India"

        availability = "Contact the provider directly for live booking and rate confirmation."
        results.append(
            RentalTool(
                name=_translate_value(settings, name, language),
                hourly_rate_inr=None,
                provider=_translate_value(settings, name, language),
                location=_translate_value(settings, coverage, language),
                availability=_translate_value(settings, availability, language),
                service_type=_translate_value(settings, "Logistics and transport", language),
                source_url=url,
            )
        )
    return results


def localize_investor_opportunities(
    settings: AppSettings,
    language: LanguageCode,
    *,
    timeout: float | None = None,
) -> list[InvestorOpportunity]:
    opportunities: list[InvestorOpportunity] = []
    for hit in _myscheme_search(
        settings,
        keyword="agribusiness entrepreneurship financing farmer producer organization",
        size=6,
        timeout=timeout,
    ):
        fields = hit.get("fields") or {}
        slug = fields.get("slug")
        title = str(fields.get("schemeName") or "")
        summary = str(fields.get("briefDescription") or "")
        if not title or not slug:
            continue

        provider = fields.get("nodalMinistryName")
        if not isinstance(provider, str):
            provider = None
        tags = fields.get("tags") or []
        focus_area = tags[0] if tags else "Agriculture finance"
        opportunities.append(
            InvestorOpportunity(
                title=_translate_value(settings, title, language),
                expected_irr_percent=None,
                minimum_ticket_inr=None,
                tenure_months=None,
                focus_area=_translate_value(settings, str(focus_area), language),
                provider=_translate_value(settings, provider, language) if provider else "myScheme",
                summary=_translate_value(settings, summary, language),
                source_url=f"https://www.myscheme.gov.in/schemes/{slug}",
            )
        )
    return opportunities


def _knowledge_category(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    if "soil" in text or "ph" in text or "nutrient" in text:
        return "soil"
    if "market" in text or "price" in text or "mandi" in text:
        return "market"
    if "pest" in text or "disease" in text or "spray" in text:
        return "treatment"
    if "horticulture" in text or "fruit" in text or "vegetable" in text:
        return "horticulture"
    return "production"


_KNOWLEDGE_CATEGORIES = {"production", "treatment", "horticulture", "soil", "market"}


def _local_knowledge_articles(
    settings: AppSettings,
    language: LanguageCode,
    *,
    query: str | None = None,
) -> list[KnowledgeArticle]:
    """Articles from the committed local library. Empty only when it fails.

    Delegates to :mod:`agrotech_ml.services.knowledge_catalog`, which owns the
    curated ``data/knowledge_library.json`` content (native en/hi). Rows
    arrive ``KnowledgeArticle``-shaped; other languages are translated here
    (a no-op when translation is not configured).
    """
    try:
        from agrotech_ml.services.knowledge_catalog import (
            knowledge_articles,
            search_articles,
        )

        if query and query.strip():
            rows = search_articles(query, language=language, limit=12)
        else:
            rows = knowledge_articles(language)
    except Exception as exc:  # noqa: BLE001 - the web fallback below still runs
        logger.warning("Local knowledge library unavailable: %s", exc)
        return []

    translate = language not in {"en", "hi"}
    articles: list[KnowledgeArticle] = []
    for row in rows:
        try:
            data = dict(row)
            if data.get("category") not in _KNOWLEDGE_CATEGORIES:
                data["category"] = _knowledge_category(
                    str(data.get("title") or ""), str(data.get("summary") or "")
                )
            article = KnowledgeArticle.model_validate(data)
        except Exception as exc:  # noqa: BLE001 - skip malformed rows, keep the rest
            logger.warning("Skipping malformed knowledge article: %s", exc)
            continue
        if translate:
            article.title = _translate_value(settings, article.title, language)
            article.summary = _translate_value(settings, article.summary, language)
            article.body_points = [
                _translate_value(settings, point, language)
                for point in article.body_points
            ]
        articles.append(article)
    return articles


async def localize_knowledge_library(
    settings: AppSettings,
    language: LanguageCode,
    *,
    query: str | None = None,
) -> list[KnowledgeArticle]:
    """Knowledge library backed by committed local content.

    The curated local library is the primary source, so the page works with
    zero external dependencies. When a Brave Search API key is configured and
    the farmer typed a query, a few live web results are appended as optional
    enrichment. The legacy web-search flow remains only as a last resort when
    the local library cannot be loaded at all.
    """
    articles = _local_knowledge_articles(settings, language, query=query)

    enrichment_limit = 4
    if articles and query and settings.brave_search_api_key:
        try:
            results = await search_knowledge(
                settings, query=query, language=language, limit=enrichment_limit
            )
            for i, res in enumerate(results):
                articles.append(
                    KnowledgeArticle(
                        id=f"web-{i}",
                        category=_knowledge_category(res.title, res.summary),
                        title=res.title,
                        summary=res.summary,
                        url=res.url,
                        source=res.source,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - enrichment is strictly optional
            logger.info("Knowledge enrichment search failed: %s", exc)

    if articles:
        return articles

    # Last resort: the old live-search behaviour, so the page still renders
    # something when the local library is missing or unreadable.
    search_query = query or "soil health irrigation pest management agriculture India"
    results = await search_knowledge(settings, query=search_query, language=language, limit=12)
    return [
        KnowledgeArticle(
            id=f"kb-{i}",
            category=_knowledge_category(res.title, res.summary),
            title=res.title,
            summary=res.summary,
            url=res.url,
            source=res.source,
        )
        for i, res in enumerate(results)
    ]


async def fetch_weather(
    settings: AppSettings,
    *,
    latitude: float,
    longitude: float,
    language: LanguageCode = "en",
    days: int = 7,
) -> WeatherResponse:
    query = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean",
        "current": "temperature_2m,wind_speed_10m",
        "timezone": "auto",
        "forecast_days": days,
    }

    async with httpx.AsyncClient(timeout=_get_timeout(settings)) as client:
        response = await client.get("https://api.open-meteo.com/v1/forecast", params=query)
        response.raise_for_status()
        payload = response.json()

    daily_payload = payload.get("daily", {})
    dates = daily_payload.get("time", [])
    min_temps = daily_payload.get("temperature_2m_min", [])
    max_temps = daily_payload.get("temperature_2m_max", [])
    rains = daily_payload.get("precipitation_sum", [])
    humidity = daily_payload.get("relative_humidity_2m_mean", [])

    daily: list[WeatherDay] = []
    for idx, day_str in enumerate(dates):
        daily.append(
            WeatherDay(
                date=date.fromisoformat(day_str),
                min_temp=float(min_temps[idx]),
                max_temp=float(max_temps[idx]),
                rain_mm=float(rains[idx]),
                humidity=float(humidity[idx]),
            )
        )

    soil_hint = "Loamy balance likely" if (abs(latitude) + abs(longitude)) % 2 > 1 else "Clay loam tendency"
    localized_hint = soil_hint if language == "en" else _translate_value(settings, soil_hint, language)

    return WeatherResponse(
        latitude=latitude,
        longitude=longitude,
        current_temp=float(payload.get("current", {}).get("temperature_2m", 0.0)),
        current_wind_kph=float(payload.get("current", {}).get("wind_speed_10m", 0.0)),
        daily=daily,
        soil_hint=localized_hint,
    )


async def search_locations(query: str) -> list[LocationSearchItem]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": 6, "language": "en", "format": "json"},
        )
        response.raise_for_status()
        payload = response.json()

    results = payload.get("results") or []
    return [
        LocationSearchItem(
            name=item.get("name", ""),
            admin1=item.get("admin1"),
            admin2=item.get("admin2"),
            country=item.get("country", ""),
            latitude=float(item.get("latitude", 0)),
            longitude=float(item.get("longitude", 0)),
        )
        for item in results
    ]


async def search_knowledge(
    settings: AppSettings,
    *,
    query: str,
    language: LanguageCode,
    limit: int = 6,
) -> list[SearchResultItem]:
    if not query.strip():
        return []

    if settings.brave_search_api_key:
        try:
            async with httpx.AsyncClient(timeout=_get_timeout(settings)) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": f"{query} agriculture India farming", "count": limit},
                    headers={"X-Subscription-Token": settings.brave_search_api_key},
                )
                response.raise_for_status()
                payload = response.json()
            results = payload.get("web", {}).get("results", [])
            return [
                SearchResultItem(
                    title=_translate_value(settings, item.get("title", ""), language),
                    summary=_translate_value(settings, item.get("description", ""), language),
                    url=item.get("url", ""),
                    source=item.get("profile", {}).get("name", "Brave Search"),
                    published_at=None,
                )
                for item in results[:limit]
            ]
        except Exception:
            pass

    async with httpx.AsyncClient(timeout=_get_timeout(settings)) as client:
        response = await client.get(
            "https://en.wikipedia.org/w/rest.php/v1/search/title",
            params={"q": query, "limit": limit},
            headers={"User-Agent": "AgroTech/1.0 (contact: support@agrotech.local)"},
        )
        response.raise_for_status()
        payload = response.json()

    results = payload.get("pages", [])
    localized_results: list[SearchResultItem] = []
    for item in results:
        title = item.get("title", "")
        summary = _clean_html_snippet(item.get("description") or item.get("excerpt") or "")
        key = item.get("key", title.replace(" ", "_"))
        localized_results.append(
            SearchResultItem(
                title=_translate_value(settings, title, language),
                summary=_translate_value(settings, summary, language),
                url=f"https://en.wikipedia.org/wiki/{quote(key)}",
                source="Wikipedia",
                published_at=None,
            )
        )
    return localized_results


# ---------------------------------------------------------------------------
# Evergreen news fallback
#
# When the live Google News RSS feed is unreachable (or answers with nothing),
# the farmer should still see useful, real destinations instead of an error.
# Every link below was verified reachable (HTTP 200) and its page title checked
# on 2026-08-27; each entry points at a permanent official government portal,
# not at a dated article, so the content cannot go stale the way a cached
# headline would. Rows are served with ``is_fallback=True`` so the UI can label
# them clearly as standing resources rather than today's news.
# ---------------------------------------------------------------------------
EVERGREEN_AGRI_NEWS: list[dict[str, str]] = [
    {
        "title": "Government press releases on agriculture (PIB)",
        "summary": (
            "Official announcements from the Government of India, including "
            "the Ministry of Agriculture and Farmers Welfare: new schemes, "
            "MSP decisions and crop advisories, published daily."
        ),
        "url": "https://pib.gov.in/allRel.aspx",
        "source": "Press Information Bureau",
    },
    {
        "title": "Department of Agriculture and Farmers Welfare portal",
        "summary": (
            "Central portal for farmer schemes, seasonal guidelines and "
            "programme updates from the Ministry of Agriculture and Farmers "
            "Welfare, Government of India."
        ),
        "url": "https://agriwelfare.gov.in/",
        "source": "Ministry of Agriculture & Farmers Welfare",
    },
    {
        "title": "Kisan Call Centre: free expert advice on 1800-180-1551",
        "summary": (
            "Call the toll-free Kisan Call Centre number 1800-180-1551 to "
            "speak with an agricultural expert in your own language, any day "
            "from 6 AM to 10 PM."
        ),
        "url": "https://dackkms.gov.in/",
        "source": "Kisan Call Centre (Govt. of India)",
    },
    {
        "title": "Weather and agromet advisories from IMD",
        "summary": (
            "District-level forecasts, rainfall warnings and crop-weather "
            "advisories from the India Meteorological Department."
        ),
        "url": "https://mausam.imd.gov.in/",
        "source": "India Meteorological Department",
    },
    {
        "title": "PM-KISAN: check your instalment status",
        "summary": (
            "Rs 6,000 per year income support for landholding farmer "
            "families. Register or check your payment status on the official "
            "PM-KISAN portal."
        ),
        "url": "https://pmkisan.gov.in/",
        "source": "PM-KISAN Portal",
    },
    {
        "title": "Live mandi prices on Agmarknet",
        "summary": (
            "Daily wholesale prices and arrivals for crops across APMC "
            "mandis in India, published by the Directorate of Marketing and "
            "Inspection."
        ),
        "url": "https://agmarknet.gov.in/",
        "source": "Agmarknet",
    },
    {
        "title": "Sell produce online through eNAM",
        "summary": (
            "The National Agriculture Market (eNAM) connects APMC mandis "
            "online so farmers can get competitive bids for their produce."
        ),
        "url": "https://enam.gov.in/",
        "source": "eNAM",
    },
    {
        "title": "Get your Soil Health Card",
        "summary": (
            "Free soil testing and fertilizer recommendations for your field "
            "under the Soil Health Card scheme. Find your nearest soil "
            "testing lab on the portal."
        ),
        "url": "https://soilhealth.dac.gov.in/",
        "source": "Soil Health Card Portal",
    },
]


def _evergreen_news(settings: AppSettings, language: LanguageCode, limit: int) -> list[NewsItem]:
    items: list[NewsItem] = []
    for entry in EVERGREEN_AGRI_NEWS[: max(1, limit)]:
        items.append(
            NewsItem(
                title=_translate_value(settings, entry["title"], language),
                summary=_translate_value(settings, entry["summary"], language),
                url=entry["url"],
                source=entry["source"],
                published_at=None,
                is_fallback=True,
            )
        )
    return items


async def fetch_news_feed(
    settings: AppSettings,
    *,
    query: str = "agriculture India farming",
    language: LanguageCode,
    limit: int = 6,
) -> list[NewsItem]:
    """Live agri headlines, falling back to committed evergreen resources.

    Never returns an empty list and never raises for upstream failures: when
    the Google News RSS feed is down or yields nothing, the verified
    ``EVERGREEN_AGRI_NEWS`` entries are served with ``is_fallback=True``.
    """
    rss_url = (
        "https://news.google.com/rss/search"
        f"?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    headlines: list[NewsItem] = []
    try:
        async with httpx.AsyncClient(timeout=_get_timeout(settings)) as client:
            response = await client.get(rss_url)
            response.raise_for_status()
            raw_xml = response.text

        root = ElementTree.fromstring(raw_xml)
        items = root.findall("./channel/item")[:limit]
        for item in items:
            title = item.findtext("title", default="")
            link = item.findtext("link", default="")
            source = item.findtext("source", default="Google News")
            published_at_raw = item.findtext("pubDate")
            published_at = parsedate_to_datetime(published_at_raw) if published_at_raw else None
            summary = title.rsplit(" - ", 1)[0] if " - " in title else title
            headlines.append(
                NewsItem(
                    title=_translate_value(settings, title, language),
                    summary=_translate_value(settings, summary, language),
                    url=link,
                    source=source,
                    published_at=published_at,
                )
            )
    except Exception as exc:  # noqa: BLE001 - a dead news feed must not 502
        logger.warning("Live news feed failed (%s); serving evergreen fallback", exc)

    if headlines:
        return headlines
    return _evergreen_news(settings, language, limit)


def _scheme_facet_probe(settings: AppSettings, timeout: float) -> bool:
    return bool(
        _http_get_json_sync(
            f"{settings.myscheme_api_url}/search/v6/schemes/facets",
            settings=settings,
            headers=_official_browser_headers(
                "https://www.myscheme.gov.in/search", settings.myscheme_api_key
            ),
            params={"lang": "en"},
            timeout=timeout,
        )
    )


async def summary(settings: AppSettings) -> DashboardSummary:
    """Dashboard counters, assembled from concurrent, timeout-bounded probes.

    Previously this ran four blocking third-party requests back to back on the
    request thread (~42 s worst case). Each probe now has its own short timeout
    and they all run at once, so the endpoint stays responsive and degrades to
    offline snapshots instead of hanging.
    """
    timeout = min(DASHBOARD_PROBE_TIMEOUT_SECONDS, float(settings.request_timeout_seconds))

    tools_result, investor_result, market_result, scheme_live, translation_live = (
        await asyncio.gather(
            _probe(
                lambda: rental_tools(settings, "en", timeout=timeout),
                fallback=([], False),
                label="rental_tools",
                timeout=timeout,
            ),
            _probe(
                lambda: localize_investor_opportunities(settings, "en", timeout=timeout),
                fallback=[],
                label="investor_opportunities",
                timeout=timeout,
            ),
            _probe(
                lambda: market_prices(settings, "en", timeout=timeout),
                fallback=([], False),
                label="market_prices",
                timeout=timeout,
            ),
            _probe(
                lambda: _scheme_facet_probe(settings, timeout),
                fallback=False,
                label="scheme_facets",
                timeout=timeout,
            ),
            _probe(
                lambda: is_translation_enabled(settings),
                fallback=False,
                label="translation",
                timeout=timeout,
            ),
        )
    )

    tools, _tools_live = tools_result
    market_items, live_market_enabled = market_result

    # Counting the offline catalogue keeps the tile populated when eNAM is down.
    listed_tools = len(tools) or len(RENTAL_TOOL_CATALOG)

    # Keep the DB round-trip off the event loop too: it is a local SQLite
    # COUNT in development but a network call against managed Postgres in production.
    return await asyncio.to_thread(
        storage_dashboard_summary,
        settings,
        listed_tools=listed_tools,
        investor_deals=len(investor_result),
        available_languages=len(LANGUAGE_LABELS),
        translation_enabled=bool(translation_live),
        live_search_enabled=True,
        live_market_enabled=bool(live_market_enabled and market_items),
        live_scheme_enabled=bool(scheme_live),
        write_auth_enabled=bool(settings.jwt_secret and settings.admin_username),
        audit_logging_enabled=settings.enable_audit_logging,
    )


def localized_note(language: str) -> str:
    return tr(language, "irrigation_note")


# ---------------------------------------------------------------------------
# Farmer directory search
#
# The storage layer matches an unanchored LIKE '%q%' across farmer_id, name,
# mobile, district and state. On mobile numbers that is a bulk-PII sieve: the
# two-character query "99" returns every farmer whose number contains "99".
# The rules below re-filter the candidate rows so a mobile number only ever
# matches on an exact value or a genuine dialling prefix.
# ---------------------------------------------------------------------------

MIN_SEARCH_QUERY_LENGTH = 3
MAX_SEARCH_RESULTS = 20
MIN_MOBILE_PREFIX_DIGITS = 4
_NON_DIGITS_RE = re.compile(r"\D")


def _mobile_matches(mobile: str, query: str) -> bool:
    normalized_mobile = _NON_DIGITS_RE.sub("", mobile or "")
    normalized_query = _NON_DIGITS_RE.sub("", query)
    if not normalized_mobile or not normalized_query:
        return False
    if normalized_mobile == normalized_query:
        return True
    # Prefix search is only useful (and only safe) with enough leading digits.
    if len(normalized_query) < MIN_MOBILE_PREFIX_DIGITS:
        return False
    return normalized_mobile.startswith(normalized_query)


def _identity_matches(result: FarmerSearchResult, needle: str) -> bool:
    fields = (result.farmer_id, result.name, result.district, result.state)
    return any(needle in (value or "").lower() for value in fields)


def search_farmers(
    settings: AppSettings,
    query: str,
    *,
    limit: int = 8,
) -> list[FarmerSearchResult]:
    """Search the farmer directory with PII-safe matching rules.

    Raises ``ValueError`` when the query is too short to be a lookup rather
    than an enumeration attempt.
    """
    needle = (query or "").strip()
    if len(needle) < MIN_SEARCH_QUERY_LENGTH:
        raise ValueError(
            f"Search query must be at least {MIN_SEARCH_QUERY_LENGTH} characters."
        )

    capped_limit = max(1, min(int(limit), MAX_SEARCH_RESULTS))
    # Over-fetch a little because rows that only matched a mid-number substring
    # are dropped below; cap the over-fetch so this stays a bounded query.
    candidates = storage_search_users(settings, needle, limit=min(capped_limit * 5, 100))

    lowered = needle.lower()
    filtered = [
        candidate
        for candidate in candidates
        if _identity_matches(candidate, lowered) or _mobile_matches(candidate.mobile, needle)
    ]
    return filtered[:capped_limit]


__all__ = [
    "add_farm",
    "fetch_news_feed",
    "fetch_weather",
    "get_user",
    "list_advisories",
    "list_farms",
    "list_uploads",
    "localize_investor_opportunities",
    "localize_knowledge_library",
    "localize_market_prices",
    "localize_rental_tools",
    "localized_note",
    "market_prices",
    "recommend_schemes",
    "rental_tools",
    "search_farmers",
    "search_knowledge",
    "search_locations",
    "summary",
    "upsert_user",
    "MAX_SEARCH_RESULTS",
    "MIN_SEARCH_QUERY_LENGTH",
    "UserProfile",
    "UserProfileCreate",
]
