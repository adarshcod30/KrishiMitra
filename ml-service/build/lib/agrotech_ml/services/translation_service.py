from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import httpx

from agrotech_ml.models.schemas import LanguageCode
from agrotech_ml.core.settings import AppSettings
from agrotech_ml.db.storage import cache_translation, get_cached_translation


SARVAM_LANGUAGE_CODES: dict[LanguageCode, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "bn": "bn-IN",
    "te": "te-IN",
    "ta": "ta-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "pa": "pa-IN",
    "or": "od-IN",
}


def is_translation_enabled(settings: AppSettings) -> bool:
    if not settings.sarvam_api_key:
        return False
    return _sarvam_available(
        settings.sarvam_api_key,
        settings.sarvam_api_url,
        settings.sarvam_model,
    )


def _provider_name(settings: AppSettings) -> str:
    return settings.sarvam_model if settings.sarvam_api_key else "local"


def _normalize_text(text: str) -> str:
    return text.strip()


def _translate_with_sarvam(
    settings: AppSettings,
    *,
    text: str,
    target_language: LanguageCode,
    source_language: LanguageCode | str = "en",
) -> str:
    payload = {
        "input": text,
        "source_language_code": "auto"
        if source_language == "auto"
        else SARVAM_LANGUAGE_CODES.get(source_language, "en-IN"),
        "target_language_code": SARVAM_LANGUAGE_CODES[target_language],
        "speaker_gender": "Male",
        "mode": "modern-colloquial",
        "model": settings.sarvam_model,
    }
    if target_language != "en":
        payload["output_script"] = "fully-native"

    with httpx.Client(timeout=25) as client:
        response = client.post(
            settings.sarvam_api_url,
            headers={
                "api-subscription-key": settings.sarvam_api_key or "",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    translated = data.get("translated_text")
    if not isinstance(translated, str) or not translated.strip():
        return text
    return translated.strip()


@lru_cache(maxsize=4)
def _sarvam_available(api_key: str, api_url: str, model: str) -> bool:
    payload = {
        "input": "Hello",
        "source_language_code": "en-IN",
        "target_language_code": "hi-IN",
        "speaker_gender": "Male",
        "model": model,
    }

    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                api_url,
                headers={
                    "api-subscription-key": api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
    except Exception:
        return False

    return True


def translate_text(
    settings: AppSettings,
    text: str,
    target_language: LanguageCode,
    *,
    source_language: LanguageCode | str = "en",
) -> str:
    cleaned = _normalize_text(text)
    if not cleaned or target_language == "en":
        return cleaned

    provider = _provider_name(settings)
    cached = get_cached_translation(
        settings,
        source_text=cleaned,
        source_language=str(source_language),
        target_language=target_language,
        provider=provider,
    )
    if cached:
        return cached

    translated = cleaned
    translation_succeeded = False
    if settings.sarvam_api_key:
        try:
            translated = _translate_with_sarvam(
                settings,
                text=cleaned,
                target_language=target_language,
                source_language=source_language,
            )
            translation_succeeded = True
        except Exception:
            translated = cleaned

    if translation_succeeded or not settings.sarvam_api_key:
        cache_translation(
            settings,
            source_text=cleaned,
            source_language=str(source_language),
            target_language=target_language,
            translated_text=translated,
            provider=provider,
        )
    return translated


def translate_many(
    settings: AppSettings,
    texts: Iterable[str],
    target_language: LanguageCode,
    *,
    source_language: LanguageCode | str = "en",
) -> list[str]:
    return [
        translate_text(
            settings,
            text,
            target_language,
            source_language=source_language,
        )
        for text in texts
    ]
