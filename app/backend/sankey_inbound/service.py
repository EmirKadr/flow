"""Orkestrering av Sankey Inbound: cache-uppslag, hämtning, bygge och trace-token."""
from __future__ import annotations

from datetime import date
import logging
import time
from typing import Any

from ..settings_service import clean_productivity_finance_company_code
from . import build, fetch
from .cache import (
    _CACHE_TTL_SECONDS,
    _cache_key,
    _get_cached_sankey_sources,
    _set_cached_sankey_sources,
    _source_cache_key,
    get_cached_sankey_payload,
    set_cached_sankey_payload,
)
from .common import SANKEY_SOURCE_VIEWS, ProgressCallback, _emit_progress
from .rows import sankey_period_bounds
from .trace import compute_trace_counts, store_trace_rows


logger = logging.getLogger(__name__)


def _trace_filter_for_payload(payload: dict) -> dict[str, Any]:
    period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    company = clean_productivity_finance_company_code(filters.get("company")) or "ALL"
    return {
        "company": company,
        "start_date": period.get("start_date"),
        "end_date": period.get("end_date"),
        "only_consumed": bool(filters.get("only_consumed")),
    }


def _set_trace_metadata(payload: dict, trace_rows: list[dict[str, Any]], token: str) -> None:
    payload["trace_total"] = len(trace_rows)
    payload["trace_counts"] = compute_trace_counts(trace_rows)
    payload["trace_filter"] = _trace_filter_for_payload(payload)
    payload["trace_token"] = token


def _client_filter_payloads(payload: dict):
    client_filters = payload.get("client_filters")
    if not isinstance(client_filters, dict):
        return
    for key in ("all", "only_consumed"):
        variant = client_filters.get(key)
        if isinstance(variant, dict):
            yield variant
    views = client_filters.get("views")
    if isinstance(views, dict):
        for variant in views.values():
            if isinstance(variant, dict):
                yield variant


def _attach_trace_token(payload: dict) -> None:
    """Flytta trace_rows från payloaden till server-side cache; lämna token + antal kvar.

    Håller huvud-payloaden liten (kraschar aldrig fliken); frontend lazy-laddar raderna
    per nod/länk via /inbound/trace och exporterar via /inbound/trace.csv.
    """
    trace_rows = payload.pop("trace_rows", None) or []
    token_rows = trace_rows
    client_filters = payload.get("client_filters")
    all_variant = client_filters.get("all") if isinstance(client_filters, dict) else None
    if isinstance(all_variant, dict) and all_variant.get("trace_rows") is not None:
        token_rows = all_variant.get("trace_rows") or []
    token = store_trace_rows(token_rows)
    _set_trace_metadata(payload, trace_rows, token)
    for variant in _client_filter_payloads(payload) or ():
        variant_rows = variant.pop("trace_rows", None) or []
        _set_trace_metadata(variant, variant_rows, token)


def load_sankey_inbound_payload(
    *,
    finance_settings: dict,
    company_codes: list[str],
    period: str,
    selected_date: date,
    business_id: int | None = None,
    business_code: str | None = None,
    company_filter: str | None = None,
    only_consumed: bool = False,
    tenant: str | None = None,
    db: Any = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    period_start, period_end, period_label = sankey_period_bounds(period, selected_date)
    today = date.today()
    if period_end > today:
        period_end = today
    if period_start > period_end:
        period_start = period_end
    cache_key = _cache_key(
        business_id=business_id,
        period=period,
        selected_date=selected_date,
        company_filter=company_filter,
        only_consumed=only_consumed,
        company_codes=company_codes,
        tenant=tenant,
    )
    cached = get_cached_sankey_payload(cache_key)
    if cached:
        return {**cached, "cache": {"status": "hit", "ttl_seconds": _CACHE_TTL_SECONDS}}
    total_steps = len(SANKEY_SOURCE_VIEWS) + 1
    source_key = _source_cache_key(
        business_id=business_id,
        period=period,
        selected_date=selected_date,
        company_filter=company_filter,
        company_codes=company_codes,
        tenant=tenant,
    )
    cached_sources = _get_cached_sankey_sources(source_key)
    fetch_started = time.perf_counter()
    sources_cached = cached_sources is not None
    if cached_sources is not None:
        # Källraderna finns redan – bara efterfiltret (only_consumed) skiljer.
        # Hoppa över hämtningen och gå direkt till bygget.
        source_rows, source_status, warnings = cached_sources
        warnings = list(warnings)
    else:
        source_rows, source_status, warnings = fetch.fetch_sankey_inbound_sources(
            period_start=period_start,
            period_end=period_end,
            follow_until=today,
            company_codes=company_codes,
            company_filter=company_filter,
            tenant=tenant,
            business_code=business_code,
            db=db,
            progress_callback=progress_callback,
            total_steps=total_steps,
        )
        _set_cached_sankey_sources(source_key, (source_rows, source_status, list(warnings)))
    fetch_ms = round((time.perf_counter() - fetch_started) * 1000, 1)
    _emit_progress(
        progress_callback,
        step=total_steps,
        total=total_steps,
        key="build",
        label="Bygger flöde",
    )
    build_started = time.perf_counter()
    payload = build.build_sankey_inbound_payload(
        source_rows=source_rows,
        finance_settings=finance_settings,
        company_codes=company_codes,
        period_start=period_start,
        period_end=period_end,
        follow_until=today,
        period_type=str(period or "day").strip().lower(),
        period_label=period_label,
        company_filter=company_filter,
        only_consumed=only_consumed,
        source_status=source_status,
        warnings=warnings,
    )
    build_ms = round((time.perf_counter() - build_started) * 1000, 1)
    payload["period"]["type"] = str(period or "day").strip().lower()
    payload["period"]["label"] = period_label
    payload["date"] = selected_date.isoformat()
    payload["cache"] = {"status": "miss", "ttl_seconds": _CACHE_TTL_SECONDS}
    timing = {
        "fetch_ms": fetch_ms,
        "build_ms": build_ms,
        "total_ms": round(fetch_ms + build_ms, 1),
        "sources_cached": sources_cached,
        "rows_by_source": {key: len(rows or []) for key, rows in source_rows.items()},
        "sources": [
            {"key": item.get("key"), "view": item.get("view"), "segment": item.get("segment"), "rows": item.get("rows"), "ms": item.get("ms")}
            for item in source_status
            if isinstance(item, dict)
        ],
    }
    payload["timing"] = timing
    logger.info(
        "Sankey inbound klar: period=%s datum=%s bolag=%s only_consumed=%s fetch=%sms build=%sms total=%sms cache=%s rader=%s",
        period, selected_date.isoformat(), clean_productivity_finance_company_code(company_filter) or "ALLA",
        only_consumed, fetch_ms, build_ms, timing["total_ms"], sources_cached, timing["rows_by_source"],
    )
    _attach_trace_token(payload)
    set_cached_sankey_payload(cache_key, payload)
    return payload
