from __future__ import annotations

import csv
import html
import json
import io
import re
from collections import defaultdict
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlencode
from xml.etree import ElementTree

import httpx

from agrotech_ml.core.i18n import localize_crop_name, tr
from agrotech_ml.models.schemas import (
    DashboardSummary,
    InvestorOpportunity,
    KnowledgeArticle,
    LanguageCode,
    LocationSearchItem,
    MarketPriceItem,
    NewsItem,
    RentalTool,
    SchemeItem,
    SchemeRecommendationRequest,
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
    upsert_user,
)
from agrotech_ml.services.translation_service import is_translation_enabled, translate_text


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


def _official_browser_headers(referer: str) -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Origin": "https://www.myscheme.gov.in",
        "Referer": referer,
        "x-api-key": "tYTy5eEhlu9rFjyxuCr7ra7ACp4dv1RH8gWuHTDc",
    }


def _safe_first(values: list[str | None]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _get_timeout(settings: AppSettings) -> float:
    return float(settings.request_timeout_seconds)


async def _http_get_text(
    url: str,
    *,
    settings: AppSettings,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> str:
    async with httpx.AsyncClient(timeout=_get_timeout(settings), follow_redirects=True) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.text


def _http_get_text_sync(
    url: str,
    *,
    settings: AppSettings,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> str:
    with httpx.Client(timeout=_get_timeout(settings), follow_redirects=True) as client:
        response = client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.text


def _http_get_json_sync(
    url: str,
    *,
    settings: AppSettings,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> dict:
    with httpx.Client(timeout=_get_timeout(settings), follow_redirects=True) as client:
        response = client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


def _extract_data_gov_csv_url(page_html: str) -> str:
    match = DATA_GOV_URL_RE.search(page_html)
    if not match:
        raise RuntimeError("Unable to locate the live market CSV URL from data.gov.in")

    encoded = match.group(1)
    decoded = encoded.replace(r"\u002F", "/")
    decoded = html.unescape(decoded)
    return decoded


def _load_market_rows(settings: AppSettings) -> list[dict[str, str]]:
    catalog_page = _http_get_text_sync(settings.data_gov_market_catalog_url, settings=settings)
    csv_url = _extract_data_gov_csv_url(catalog_page)
    csv_payload = _http_get_text_sync(csv_url, settings=settings)
    return list(csv.DictReader(io.StringIO(csv_payload)))


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


def localize_market_prices(
    settings: AppSettings,
    language: LanguageCode,
    *,
    crop: str | None = None,
    state: str | None = None,
) -> list[MarketPriceItem]:
    rows = _load_market_rows(settings)
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
) -> list[dict]:
    base_url = f"{settings.myscheme_api_url}/search/v6/schemes"
    try:
        payload = _http_get_json_sync(
            base_url,
            settings=settings,
            headers=_official_browser_headers("https://www.myscheme.gov.in/search"),
            params={"lang": "en", "keyword": keyword, "from": "0", "size": str(size)},
        )
        return payload.get("data", {}).get("hits", {}).get("items", [])
    except Exception:
        return []


def _myscheme_scheme_details(settings: AppSettings, slug: str) -> dict:
    base_url = f"{settings.myscheme_api_url}/schemes/v6/public/schemes"
    payload = _http_get_json_sync(
        base_url,
        settings=settings,
        headers=_official_browser_headers(f"https://www.myscheme.gov.in/schemes/{slug}"),
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


def recommend_schemes(settings: AppSettings, payload: SchemeRecommendationRequest) -> list[SchemeItem]:
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


def localize_rental_tools(
    settings: AppSettings,
    language: LanguageCode,
    *,
    location: str | None = None,
) -> list[RentalTool]:
    page = _http_get_text_sync(settings.enam_logistics_url, settings=settings)
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
) -> list[InvestorOpportunity]:
    opportunities: list[InvestorOpportunity] = []
    for hit in _myscheme_search(settings, keyword="agribusiness entrepreneurship financing farmer producer organization", size=6):
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


async def localize_knowledge_library(
    settings: AppSettings,
    language: LanguageCode,
    *,
    query: str | None = None,
) -> list[KnowledgeArticle]:
    search_query = query or "soil health irrigation pest management agriculture India"
    results = await search_knowledge(settings, query=search_query, language=language, limit=12)
    
    articles = []
    for i, res in enumerate(results):
        articles.append(KnowledgeArticle(
            id=f"kb-{i}",
            category=_knowledge_category(res.title, res.summary),
            title=res.title,
            summary=res.summary,
            url=res.url,
            source=res.source
        ))
    return articles


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


async def fetch_news_feed(
    settings: AppSettings,
    *,
    query: str = "agriculture India farming",
    language: LanguageCode,
    limit: int = 6,
) -> list[NewsItem]:
    rss_url = (
        "https://news.google.com/rss/search"
        f"?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    async with httpx.AsyncClient(timeout=_get_timeout(settings)) as client:
        response = await client.get(rss_url)
        response.raise_for_status()
        raw_xml = response.text

    root = ElementTree.fromstring(raw_xml)
    items = root.findall("./channel/item")[:limit]
    headlines: list[NewsItem] = []
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
    return headlines


def summary(settings: AppSettings) -> DashboardSummary:
    try:
        listed_tools = len(localize_rental_tools(settings, "en"))
    except Exception:
        listed_tools = 0

    try:
        investor_deals = len(localize_investor_opportunities(settings, "en"))
    except Exception:
        investor_deals = 0

    live_market_enabled = False
    try:
        live_market_enabled = bool(localize_market_prices(settings, "en"))
    except Exception:
        live_market_enabled = False

    live_scheme_enabled = False
    try:
        live_scheme_enabled = bool(
            _http_get_json_sync(
                f"{settings.myscheme_api_url}/search/v6/schemes/facets",
                settings=settings,
                headers=_official_browser_headers("https://www.myscheme.gov.in/search"),
                params={"lang": "en"},
            )
        )
    except Exception:
        live_scheme_enabled = False

    return storage_dashboard_summary(
        settings,
        listed_tools=listed_tools,
        investor_deals=investor_deals,
        available_languages=2,
        translation_enabled=is_translation_enabled(settings),
        live_search_enabled=True,
        live_market_enabled=live_market_enabled,
        live_scheme_enabled=live_scheme_enabled,
        write_auth_enabled=bool(settings.jwt_secret and settings.admin_username),
        audit_logging_enabled=settings.enable_audit_logging,
    )


def localized_note(language: str) -> str:
    return tr(language, "irrigation_note")


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
    "recommend_schemes",
    "search_knowledge",
    "search_locations",
    "summary",
    "upsert_user",
    "UserProfile",
    "UserProfileCreate",
]
