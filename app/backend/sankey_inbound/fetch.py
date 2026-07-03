"""Datahämtning för Sankey Inbound: API-klient, segment, snapshots och arkivcache."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import logging
import time
from typing import Any

from .. import local_archive_store
from ..business_scope import DEFAULT_BUSINESS_CODE
from ..config import settings
from ..data_fetch_service import (
    ARCHIVE_TO_LIVE,
    DataFetchConfigError,
    DataFetchPlanError,
    LIVE_ARCHIVE_PAIRS,
    _date_period_payload,
    _period_values_for_column,
    _preferred_date_column,
    load_catalog,
)
from ..external_data_client import (
    ExternalDataClient,
    ExternalDataClientError,
    data_source_base_url_for_tenant,
)
from ..productivity_service import (
    ProductivitySourceError,
    _read_csv,
    _read_csv_rows_with_headers,
    find_kpi_file,
)
from ..productivity_sync import productivity_snapshot_source_path, productivity_snapshot_status
from ..settings_service import clean_productivity_finance_company_code
from .common import (
    CURRENT_STATE_SOURCE_KEYS,
    DEGRADABLE_SOURCE_KEYS,
    PERIOD_ONLY_SOURCE_KEYS,
    PRODUCTIVITY_SNAPSHOT_REUSE_SOURCE_KEYS,
    ProgressCallback,
    REQUIRED_SOURCE_KEYS,
    SANKEY_SOURCE_VIEWS,
    SOURCE_LABELS,
    SankeyInboundError,
    _emit_progress,
)


logger = logging.getLogger(__name__)


def _api_client(tenant: str | None = None) -> ExternalDataClient:
    missing = [
        name
        for name in (
            "DATA_SOURCE_API_BASE_URL",
            "DATA_SOURCE_API_KEY",
            "DATA_SOURCE_API_CLIENT",
            "DATA_SOURCE_API_KEY_HEADER",
            "DATA_SOURCE_API_CLIENT_HEADER",
            "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE",
        )
        if not str(getattr(settings, name, "")).strip()
    ]
    if missing:
        raise SankeyInboundError(f"Saknar {', '.join(missing)} i servermiljon.", status_code=503)
    try:
        base_url = data_source_base_url_for_tenant(settings.DATA_SOURCE_API_BASE_URL, tenant)
    except ValueError as exc:
        raise SankeyInboundError(str(exc), status_code=503) from exc
    return ExternalDataClient(
        base_url=base_url,
        api_key=settings.DATA_SOURCE_API_KEY.strip() or None,
        api_client=settings.DATA_SOURCE_API_CLIENT.strip() or None,
        api_key_header=settings.DATA_SOURCE_API_KEY_HEADER.strip() or None,
        api_client_header=settings.DATA_SOURCE_API_CLIENT_HEADER.strip() or None,
        view_data_path_template=settings.DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE.strip(),
        timeout=settings.DATA_SOURCE_TIMEOUT_SECONDS,
        verify_ssl=settings.DATA_SOURCE_VERIFY_SSL,
        ca_bundle=settings.DATA_SOURCE_CA_BUNDLE.strip() or None,
        response_row_cap=int(getattr(settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 0) or 0),
    )


def _company_filter(company_filter: str | None, company_codes: list[str]) -> list[dict[str, Any]]:
    company = clean_productivity_finance_company_code(company_filter)
    if company and company != "ALL":
        return [{"id": "company", "operator": "EQ", "value": company}]
    codes = [clean_productivity_finance_company_code(code) for code in company_codes]
    codes = [code for code in codes if code]
    if len(codes) == 1:
        return [{"id": "company", "operator": "EQ", "value": codes[0]}]
    if len(codes) > 1:
        return [{"id": "company", "operator": "Terms", "value": codes}]
    return []


def _date_filter_for_view(view_id: str, period_start: date, period_end: date) -> dict[str, Any] | None:
    try:
        view = load_catalog().view(view_id)
    except (DataFetchConfigError, DataFetchPlanError):
        return None
    column = _preferred_date_column(view)
    if column is None:
        return None
    period = _date_period_payload("sankey", period_start, period_end)
    return {"id": column.id, "operator": "Between", "value": _period_values_for_column(period, column)}


def _segments_for_view(view_id: str, period_start: date, period_end: date, today: date) -> tuple[list[tuple[str, date, date]], list[dict]]:
    if view_id not in LIVE_ARCHIVE_PAIRS:
        return [(view_id, period_start, period_end)], []
    days, archive_id = LIVE_ARCHIVE_PAIRS[view_id]
    cutoff = today - timedelta(days=days)
    warnings = []
    if period_start >= cutoff:
        return [(view_id, period_start, period_end)], warnings
    warnings.append(
        {
            "code": "archive_retention_used",
            "view": view_id,
            "archive_view": archive_id,
            "message": f"{view_id} använder dblog-arkiv före {cutoff.isoformat()}.",
        }
    )
    if period_end < cutoff:
        return [(archive_id, period_start, period_end)], warnings
    return [
        (archive_id, period_start, cutoff - timedelta(days=1)),
        (view_id, cutoff, period_end),
    ], warnings


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _segment_kind(segment_view: str) -> str:
    return "arkiv" if segment_view in ARCHIVE_TO_LIVE else "live"


def _fetch_segment_rows(
    client: ExternalDataClient,
    *,
    segment_view: str,
    segment_start: date | None,
    segment_end: date | None,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> list[dict[str, Any]]:
    rows, _source = _fetch_segment_rows_with_source(
        client,
        segment_view=segment_view,
        segment_start=segment_start,
        segment_end=segment_end,
        company_codes=company_codes,
        company_filter=company_filter,
        tenant=tenant,
    )
    return rows


def _fetch_segment_rows_with_source(
    client: ExternalDataClient,
    *,
    segment_view: str,
    segment_start: date | None,
    segment_end: date | None,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    filters = _company_filter(company_filter, company_codes)
    if segment_start and segment_end:
        date_filter = _date_filter_for_view(segment_view, segment_start, segment_end)
        if date_filter:
            filters.append(date_filter)
    # Lokal arkiv-cache först för dblog-segment; None => fall tillbaka till API/dblog.
    if segment_view in ARCHIVE_TO_LIVE and local_archive_store.is_enabled():
        try:
            cached = local_archive_store.query_rows(tenant, segment_view, filters or None)
        except Exception:  # noqa: BLE001 – cache-fel får aldrig fälla Sankey
            logger.warning("Lokal arkiv-cache misslyckades för %s, faller tillbaka.", segment_view, exc_info=True)
            cached = None
        if cached is not None:
            return cached, "local_archive"
    return client.fetch_all(segment_view, filters=filters or None), "api"


def _query_local_archive_segment(
    *,
    archive_view: str,
    segment_start: date,
    segment_end: date,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> list[dict[str, Any]] | None:
    if not local_archive_store.is_enabled() or archive_view not in ARCHIVE_TO_LIVE:
        return None
    filters = _company_filter(company_filter, company_codes)
    date_filter = _date_filter_for_view(archive_view, segment_start, segment_end)
    if date_filter:
        filters.append(date_filter)
    try:
        return local_archive_store.query_rows(tenant, archive_view, filters or None)
    except Exception:  # noqa: BLE001 – cache-fel får aldrig fälla Sankey
        logger.warning("Lokal arkiv-cache misslyckades för %s, faller tillbaka.", archive_view, exc_info=True)
        return None


def _date_span(start: date, end: date) -> list[date]:
    if start > end:
        return []
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _fetch_productivity_snapshot_rows(
    *,
    key: str,
    view_id: str,
    period_start: date,
    period_end: date,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]] | None:
    if key not in PRODUCTIVITY_SNAPSHOT_REUSE_SOURCE_KEYS:
        return None
    days = _date_span(period_start, period_end)
    if not days:
        return None

    paths = []
    for day in days:
        status = productivity_snapshot_status(day)
        if not status.get("ready"):
            return None
        path = productivity_snapshot_source_path(day, key)
        if not path.is_file():
            return None
        paths.append((day, path))

    rows: list[dict[str, Any]] = []
    try:
        for _day, path in paths:
            _headers, day_rows = _read_csv_rows_with_headers(path, compressed=True)
            rows.extend(dict(row) for row in day_rows)
    except Exception:
        logger.warning("Could not reuse productivity snapshot rows for Sankey source %s.", key, exc_info=True)
        return None

    return (
        rows,
        [
            {
                "key": key,
                "view": view_id,
                "segment": "productivity_snapshot",
                "status": "productivity_snapshot",
                "rows": len(rows),
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "days": len(days),
            }
        ],
        [],
    )


def _source_failure_message(
    *,
    key: str,
    view: str,
    kind: str,
    start: date | None,
    end: date | None,
    company_filter: str | None,
    exc: Exception,
    archive_view: str | None = None,
    archive_exc: Exception | None = None,
) -> str:
    label = SOURCE_LABELS.get(key, key)
    span = f"{start.isoformat()}–{end.isoformat()}" if start and end else "hela perioden"
    company = clean_productivity_finance_company_code(company_filter) or "ALLA"
    detail = f"{label} ({key}) kunde inte hämtas — vy {view} [{kind}], period {span}, bolag {company}: {exc}"
    if archive_view is not None and archive_exc is not None:
        detail += f" · arkivet {archive_view} svarade också: {archive_exc}"
    return detail


def _degraded_source_warning(*, key: str, view: str, message: str) -> dict[str, Any]:
    return {
        "code": "degraded_source_segment_unavailable",
        "source": key,
        "view": view,
        "message": (
            f"{message}. Rapporten fortsätter med tillgängliga segment, "
            "men förverkade/plockade grenar kan vara underskattade."
        ),
    }


def _fetch_snapshot_rows(
    client: ExternalDataClient,
    *,
    key: str,
    view_id: str,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    """Hämtar en datumlös nulägeskälla (buffer/saldo/kpi).

    Sådana vyer kan inte datum-chunkas. Om svaret slår i radtaket delar vi per bolag
    så att vi inte tyst tappar rader (t.ex. buffertpall som kapas vid 50 000).
    """
    cap = int(getattr(settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 0) or 0)
    rows = _fetch_segment_rows(
        client, segment_view=view_id, segment_start=None, segment_end=None,
        company_codes=company_codes, company_filter=company_filter,
    )
    if not cap or len(rows) < cap:
        return rows, [{"key": key, "view": view_id, "segment": "snapshot", "status": "api", "rows": len(rows)}], []

    cleaned_filter = clean_productivity_finance_company_code(company_filter)
    if cleaned_filter and cleaned_filter != "ALL":
        codes = [cleaned_filter]
    else:
        codes = [c for c in (clean_productivity_finance_company_code(x) for x in company_codes) if c]
    statuses: list[dict] = []
    warnings: list[dict] = []
    if len(codes) > 1:
        combined: list[dict[str, Any]] = []
        for code in codes:
            part = _fetch_segment_rows(
                client, segment_view=view_id, segment_start=None, segment_end=None,
                company_codes=[code], company_filter=code,
            )
            statuses.append({"key": key, "view": view_id, "segment": f"snapshot:{code}", "status": "api", "rows": len(part)})
            combined.extend(part)
            if cap and len(part) >= cap:
                warnings.append({
                    "code": "snapshot_truncated", "source": key, "view": view_id, "company": code,
                    "message": f"{SOURCE_LABELS.get(key, key)} för {code} nådde fortfarande radtaket ({cap}) och kan vara ofullständig.",
                })
        warnings.insert(0, {
            "code": "snapshot_chunked_by_company", "source": key, "view": view_id,
            "message": f"{SOURCE_LABELS.get(key, key)} nådde radtaket ({cap}) – hämtade per bolag istället ({len(combined)} rader totalt).",
        })
        logger.warning("Sankey snapshot %s nådde radtaket %d – chunkade per bolag till %d rader.", key, cap, len(combined))
        return combined, statuses, warnings

    # Ett enda bolag som ändå slår i taket – inget mer att dela på.
    warnings.append({
        "code": "snapshot_truncated", "source": key, "view": view_id,
        "message": f"{SOURCE_LABELS.get(key, key)} nådde radtaket ({cap}) utan datum- eller bolagsaxel att dela på och kan vara ofullständig.",
    })
    logger.warning("Sankey snapshot %s nådde radtaket %d och kunde inte delas.", key, cap)
    return rows, [{"key": key, "view": view_id, "segment": "snapshot", "status": "api", "rows": len(rows), "truncated": True}], warnings


def _fetch_item_alias_rows(
    client: ExternalDataClient,
    *,
    view_id: str,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    """Hämta item_alias fullständigt trots datakällans radtak.

    item_alias är en nulägeskälla utan datumaxel i Sankey, men vyn har en timestamp-
    kolumn (utan tomma värden). Ett brett timestamp-Between låter ``fetch_all`` dela ner
    under radtaket – annars kapas svaret vid ~50k/bolag och faktorer tappas, vilket ger
    fel förpacknings-ladders. Ingen bolagschunkning behövs då.
    """
    filters = _company_filter(company_filter, company_codes)
    if local_archive_store.is_enabled():
        try:
            cached = local_archive_store.query_snapshot_rows(tenant, view_id, filters or None)
        except Exception:  # noqa: BLE001 - cache faults must not break Sankey
            logger.warning("Lokal snapshot-cache misslyckades för %s, faller tillbaka.", view_id, exc_info=True)
            cached = None
        if cached is not None:
            status = [{
                "key": "item_alias",
                "view": view_id,
                "segment": "snapshot",
                "status": "local_snapshot",
                "rows": len(cached),
            }]
            return cached, status, []
    date_filter = _date_filter_for_view(view_id, date(2000, 1, 1), date.today())
    if date_filter:
        filters.append(date_filter)
    rows = client.fetch_all(view_id, filters=filters or None)
    status = [{"key": "item_alias", "view": view_id, "segment": "timestamp-split", "status": "api", "rows": len(rows)}]
    return rows, status, []


def _fetch_view_rows(
    client: ExternalDataClient,
    *,
    key: str,
    view_id: str,
    period_start: date | None,
    period_end: date | None,
    company_codes: list[str],
    company_filter: str | None,
    today: date,
    tenant: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    rows: list[dict[str, Any]] = []
    statuses: list[dict] = []
    warnings: list[dict] = []
    company = clean_productivity_finance_company_code(company_filter) or "ALLA"
    if not (period_start and period_end):
        # Datumlös nulägeskälla – egen väg med bolagschunkning vid radtak.
        try:
            if key == "item_alias":
                # item_alias är för stor för bolagschunkning (>50k/bolag) – timestamp-split
                # istället så inga omräkningsfaktorer kapas bort.
                return _fetch_item_alias_rows(
                    client, view_id=view_id, company_codes=company_codes, company_filter=company_filter, tenant=tenant,
                )
            return _fetch_snapshot_rows(
                client, key=key, view_id=view_id, company_codes=company_codes, company_filter=company_filter,
            )
        except ExternalDataClientError as exc:
            message = _source_failure_message(
                key=key, view=view_id, kind="snapshot", start=None, end=None,
                company_filter=company_filter, exc=exc,
            )
            statuses.append({"key": key, "view": view_id, "segment": "snapshot", "status": "error", "rows": 0, "company": company, "message": message})
            logger.error("Sankey-källa misslyckades: %s", message)
            if key in REQUIRED_SOURCE_KEYS:
                raise SankeyInboundError(message, status_code=502, source_status=statuses) from exc
            warnings.append({"code": "optional_source_unavailable", "source": key, "view": view_id, "message": message})
            return rows, statuses, warnings
    if period_start and period_end:
        reused = _fetch_productivity_snapshot_rows(
            key=key,
            view_id=view_id,
            period_start=period_start,
            period_end=period_end,
        )
        if reused is not None:
            return reused
        segments, warnings = _segments_for_view(view_id, period_start, period_end, today)
    else:
        segments = [(view_id, None, None)]
    for segment_view, segment_start, segment_end in segments:
        kind = _segment_kind(segment_view)
        fetch_start = segment_start
        if (
            segment_view in LIVE_ARCHIVE_PAIRS
            and segment_start is not None
            and segment_end is not None
            and local_archive_store.is_enabled()
        ):
            archive_view = LIVE_ARCHIVE_PAIRS[segment_view][1]
            min_cached, max_cached = local_archive_store.covered_range(tenant, archive_view)
            if min_cached is not None and max_cached is not None and min_cached <= segment_start <= max_cached:
                cached_end = min(segment_end, max_cached)
                cached_rows = _query_local_archive_segment(
                    archive_view=archive_view,
                    segment_start=segment_start,
                    segment_end=cached_end,
                    company_codes=company_codes,
                    company_filter=company_filter,
                    tenant=tenant,
                )
                if cached_rows is not None:
                    rows.extend(cached_rows)
                    statuses.append({
                        "key": key,
                        "view": archive_view,
                        "live_view": segment_view,
                        "segment": "lokal_cache",
                        "status": "local_archive",
                        "rows": len(cached_rows),
                        "start": _iso(segment_start),
                        "end": _iso(cached_end),
                    })
                    fetch_start = cached_end + timedelta(days=1)
                    if fetch_start > segment_end:
                        continue
        try:
            segment_rows, segment_source = _fetch_segment_rows_with_source(
                client,
                segment_view=segment_view,
                segment_start=fetch_start,
                segment_end=segment_end,
                company_codes=company_codes,
                company_filter=company_filter,
                tenant=tenant,
            )
        except ExternalDataClientError as exc:
            archive_pair = LIVE_ARCHIVE_PAIRS.get(segment_view)
            # Live-vyn svarade inte (t.ex. kortare faktisk retention än konfigurerat,
            # eller 403 på äldre data) – prova dblog-arkivet innan vi ger upp.
            if archive_pair is not None:
                archive_view = archive_pair[1]
                logger.warning(
                    "Sankey-källa '%s': live-vy %s misslyckades (%s) för %s–%s bolag %s – provar arkiv %s.",
                    key, segment_view, exc, _iso(segment_start), _iso(segment_end), company, archive_view,
                )
                try:
                    segment_rows, segment_source = _fetch_segment_rows_with_source(
                        client,
                        segment_view=archive_view,
                        segment_start=fetch_start,
                        segment_end=segment_end,
                        company_codes=company_codes,
                        company_filter=company_filter,
                        tenant=tenant,
                    )
                except ExternalDataClientError as archive_exc:
                    message = _source_failure_message(
                        key=key, view=segment_view, kind=kind, start=fetch_start, end=segment_end,
                        company_filter=company_filter, exc=exc, archive_view=archive_view, archive_exc=archive_exc,
                    )
                    statuses.append({
                        "key": key, "view": segment_view, "archive_view": archive_view, "segment": kind,
                        "status": "error", "rows": 0, "start": _iso(fetch_start), "end": _iso(segment_end),
                        "company": company, "message": message,
                    })
                    logger.error("Sankey-källa misslyckades (även arkiv): %s", message)
                    if key in REQUIRED_SOURCE_KEYS:
                        if key in DEGRADABLE_SOURCE_KEYS:
                            warnings.append(_degraded_source_warning(key=key, view=segment_view, message=message))
                            continue
                        raise SankeyInboundError(message, status_code=502, source_status=statuses) from archive_exc
                    warnings.append({"code": "optional_source_unavailable", "source": key, "view": segment_view, "message": message})
                    continue
                fallback_message = (
                    f"{SOURCE_LABELS.get(key, key)}: live-vyn {segment_view} svarade '{exc}'. "
                    f"Hämtade {len(segment_rows)} rader från arkivet {archive_view} istället."
                )
                warnings.append({
                    "code": "archive_fallback_used", "source": key, "view": segment_view,
                    "archive_view": archive_view, "message": fallback_message,
                })
                statuses.append({
                    "key": key, "view": archive_view, "segment": "arkiv (fallback)", "status": segment_source,
                    "rows": len(segment_rows), "start": _iso(fetch_start), "end": _iso(segment_end),
                })
                logger.warning("Sankey-källa '%s': arkiv-fallback via %s lyckades (%d rader).", key, archive_view, len(segment_rows))
                rows.extend(segment_rows)
                continue
            # Ingen arkivpartner – misslyckas direkt, men med full kontext.
            message = _source_failure_message(
                key=key, view=segment_view, kind=kind, start=fetch_start, end=segment_end,
                company_filter=company_filter, exc=exc,
            )
            statuses.append({
                "key": key, "view": segment_view, "segment": kind, "status": "error", "rows": 0,
                "start": _iso(fetch_start), "end": _iso(segment_end), "company": company, "message": message,
            })
            logger.error("Sankey-källa misslyckades: %s", message)
            if key in REQUIRED_SOURCE_KEYS:
                if key in DEGRADABLE_SOURCE_KEYS:
                    warnings.append(_degraded_source_warning(key=key, view=segment_view, message=message))
                    continue
                raise SankeyInboundError(message, status_code=502, source_status=statuses) from exc
            warnings.append({"code": "optional_source_unavailable", "source": key, "view": segment_view, "message": message})
            continue
        rows.extend(segment_rows)
        statuses.append({
            "key": key, "view": segment_view, "segment": kind, "status": segment_source,
            "rows": len(segment_rows), "start": _iso(fetch_start), "end": _iso(segment_end),
        })
    return rows, statuses, warnings


def _load_kpi_fallback_rows(
    *,
    business_code: str | None,
    db: Any = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    """Läs KPI-mål från Produktivitetens coredata-fil.

    Sankey använder coredata som förstahandskälla eftersom v_ask_kpi_target inte
    är en tillgänglig API-källa i detta flöde. Det speglar Produktivitetens
    fallbackfil så processpoängen hålls gemensamma.
    """
    try:
        path = find_kpi_file(None, business_code or DEFAULT_BUSINESS_CODE, db=db)
        rows = [dict(row) for row in _read_csv(path)]
    except (ProductivitySourceError, OSError):
        return [], [], []
    if not rows:
        return [], [], []
    status = [
        {
            "key": "kpi",
            "view": SANKEY_SOURCE_VIEWS["kpi"],
            "status": "coredata_primary",
            "rows": len(rows),
        }
    ]
    warning = [
        {
            "code": "kpi_coredata_fallback",
            "source": "kpi",
            "message": f"{SOURCE_LABELS['kpi']} hämtades från Produktivitetens coredata-fil.",
        }
    ]
    return rows, status, warning


def fetch_sankey_inbound_sources(
    *,
    period_start: date,
    period_end: date | None = None,
    follow_until: date,
    company_codes: list[str],
    company_filter: str | None = None,
    tenant: str | None = None,
    business_code: str | None = None,
    db: Any = None,
    progress_callback: ProgressCallback | None = None,
    total_steps: int | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict], list[dict]]:
    try:
        load_catalog()
    except DataFetchConfigError as exc:
        raise SankeyInboundError(str(exc), status_code=503) from exc
    except DataFetchPlanError as exc:
        raise SankeyInboundError(str(exc), status_code=503) from exc
    all_rows: dict[str, list[dict[str, Any]]] = {}
    source_status: list[dict] = []
    warnings: list[dict] = []
    today = date.today()
    total = total_steps or (len(SANKEY_SOURCE_VIEWS) + 1)
    steps = {key: index for index, key in enumerate(SANKEY_SOURCE_VIEWS, start=1)}

    def _fetch_source(key: str, view_id: str) -> tuple[str, list[dict[str, Any]], list[dict], list[dict]]:
        is_current = key in CURRENT_STATE_SOURCE_KEYS
        _emit_progress(progress_callback, step=steps[key], total=total, key=key, label=f"Hämtar {SOURCE_LABELS.get(key, key)}")
        started = time.perf_counter()
        if key == "kpi":
            rows, statuses, source_warnings = _load_kpi_fallback_rows(business_code=business_code, db=db)
            if not statuses:
                statuses = [{"key": key, "view": view_id, "status": "coredata_missing", "rows": 0}]
                source_warnings = [
                    {
                        "code": "kpi_coredata_missing",
                        "source": "kpi",
                        "message": f"{SOURCE_LABELS['kpi']} saknas i Produktivitetens coredata-fil.",
                    }
                ]
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            for status in statuses:
                status.setdefault("ms", elapsed_ms)
            _emit_progress(progress_callback, step=steps[key], total=total, key=key, label=f"{SOURCE_LABELS.get(key, key)} klar", rows=len(rows), done=True, ms=elapsed_ms)
            return key, rows, statuses, source_warnings
        client = _api_client(tenant=tenant)
        source_period_end = period_end if key in PERIOD_ONLY_SOURCE_KEYS and period_end is not None else follow_until
        rows, statuses, source_warnings = _fetch_view_rows(
            client,
            key=key,
            view_id=view_id,
            period_start=None if is_current else period_start,
            period_end=None if is_current else source_period_end,
            company_codes=company_codes,
            company_filter=company_filter,
            today=today,
            tenant=tenant,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        for status in statuses:
            status.setdefault("ms", elapsed_ms)
        _emit_progress(progress_callback, step=steps[key], total=total, key=key, label=f"{SOURCE_LABELS.get(key, key)} klar", rows=len(rows), done=True, ms=elapsed_ms)
        return key, rows, statuses, source_warnings

    # Loggkällorna (receive/trans/pick) är oberoende och tunga – hämta dem parallellt.
    # Nulägeskällorna (buffer/kpi) körs sekventiellt eftersom kpi-fallbacken rör DB-sessionen.
    parallel_views = [(k, v) for k, v in SANKEY_SOURCE_VIEWS.items() if k not in CURRENT_STATE_SOURCE_KEYS]
    sequential_views = [(k, v) for k, v in SANKEY_SOURCE_VIEWS.items() if k in CURRENT_STATE_SOURCE_KEYS]
    results: dict[str, tuple[list[dict[str, Any]], list[dict], list[dict]]] = {}
    required_error: SankeyInboundError | None = None

    if parallel_views:
        with ThreadPoolExecutor(max_workers=min(4, len(parallel_views)), thread_name_prefix="sankey-fetch") as pool:
            futures = {pool.submit(_fetch_source, key, view_id): key for key, view_id in parallel_views}
            for future in as_completed(futures):
                try:
                    key, rows, statuses, source_warnings = future.result()
                    results[key] = (rows, statuses, source_warnings)
                except SankeyInboundError as exc:
                    required_error = required_error or exc
    if required_error is not None:
        raise required_error

    for key, view_id in sequential_views:
        _, rows, statuses, source_warnings = _fetch_source(key, view_id)
        results[key] = (rows, statuses, source_warnings)

    for key in SANKEY_SOURCE_VIEWS:
        rows, statuses, source_warnings = results[key]
        all_rows[key] = rows
        source_status.extend(statuses)
        warnings.extend(source_warnings)

    warnings.append(
        {
            "code": "pick_location_log_retention",
            "message": "Plockplatsloggen har begransad historik och saknar kvantitet; aldre saldo-FIFO markeras med lagre confidence.",
        }
    )
    return all_rows, source_status, warnings
