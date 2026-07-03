"""Payload- och källrads-cache för Sankey Inbound."""
from __future__ import annotations

from datetime import date
import threading
import time
from typing import Any

from ..config import settings
from ..settings_service import clean_productivity_finance_company_code


_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 15 * 60 if settings.is_production else 0
_CACHE_MAX_ITEMS = 64
_CACHE: dict[tuple[Any, ...], tuple[float, dict]] = {}
SANKEY_INBOUND_PAYLOAD_SCHEMA = "client_filters_v8"

# Källrads-cache (oberoende av only_consumed). only_consumed är bara ett efterfilter
# i bygget – samma rader hämtas oavsett – så vi cachar de dyra hämtningarna separat
# med en kort, alltid påslagen TTL. Det gör att t.ex. "Visa endast förverkade"
# kan togglas utan att hämta om allt, även lokalt där payload-cachen har TTL 0.
_SOURCE_CACHE_LOCK = threading.Lock()
_SOURCE_CACHE_TTL_SECONDS = 120
_SOURCE_CACHE_MAX_ITEMS = 64
_SOURCE_CACHE: dict[tuple[Any, ...], tuple[float, tuple[dict, list, list]]] = {}


def _cache_key(
    *,
    business_id: int | None,
    period: str,
    selected_date: date,
    company_filter: str | None,
    only_consumed: bool,
    company_codes: list[str],
    tenant: str | None,
) -> tuple[Any, ...]:
    return (
        SANKEY_INBOUND_PAYLOAD_SCHEMA,
        business_id,
        str(period or "day").lower(),
        selected_date.isoformat(),
        clean_productivity_finance_company_code(company_filter) or "ALL",
        bool(only_consumed),
        tuple(sorted(clean_productivity_finance_company_code(code) for code in company_codes)),
        tenant or "",
    )


def get_cached_sankey_payload(key: tuple[Any, ...]) -> dict | None:
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if not cached:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _CACHE.pop(key, None)
            return None
        return payload


def set_cached_sankey_payload(key: tuple[Any, ...], payload: dict) -> None:
    now = time.time()
    with _CACHE_LOCK:
        _CACHE[key] = (now + _CACHE_TTL_SECONDS, payload)
        if len(_CACHE) <= _CACHE_MAX_ITEMS:
            return
        for stale_key, (expires_at, _payload) in sorted(_CACHE.items(), key=lambda item: item[1][0])[: len(_CACHE) - _CACHE_MAX_ITEMS]:
            _CACHE.pop(stale_key, None)


def _source_cache_key(
    *,
    business_id: int | None,
    period: str,
    selected_date: date,
    company_filter: str | None,
    company_codes: list[str],
    tenant: str | None,
) -> tuple[Any, ...]:
    # Medvetet utan only_consumed: samma rader hämtas oavsett filtret.
    return (
        SANKEY_INBOUND_PAYLOAD_SCHEMA,
        business_id,
        str(period or "day").lower(),
        selected_date.isoformat(),
        clean_productivity_finance_company_code(company_filter) or "ALL",
        tuple(sorted(clean_productivity_finance_company_code(code) for code in company_codes)),
        tenant or "",
    )


def _get_cached_sankey_sources(key: tuple[Any, ...]) -> tuple[dict, list, list] | None:
    now = time.time()
    with _SOURCE_CACHE_LOCK:
        cached = _SOURCE_CACHE.get(key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at <= now:
            _SOURCE_CACHE.pop(key, None)
            return None
        return value


def _set_cached_sankey_sources(key: tuple[Any, ...], value: tuple[dict, list, list]) -> None:
    now = time.time()
    with _SOURCE_CACHE_LOCK:
        _SOURCE_CACHE[key] = (now + _SOURCE_CACHE_TTL_SECONDS, value)
        if len(_SOURCE_CACHE) <= _SOURCE_CACHE_MAX_ITEMS:
            return
        for stale_key, (expires_at, _value) in sorted(_SOURCE_CACHE.items(), key=lambda item: item[1][0])[: len(_SOURCE_CACHE) - _SOURCE_CACHE_MAX_ITEMS]:
            _SOURCE_CACHE.pop(stale_key, None)
