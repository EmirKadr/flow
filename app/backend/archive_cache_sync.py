"""Fill and refresh the per-tenant local DuckDB archive cache.

Strategy (see wiki/local-archive-cache.md and local_archive_store.py):
- **Seed once** from the ``dblog_*`` archive view for the deep history window.
- **Top up daily** by capturing the days that have left / are leaving the live
  retention window straight from the *live* view (richer columns, and we never have
  to touch the flaky dblog views again during normal operation).
- The DuckDB ``_row_date`` range plus ``_archive_coverage`` per view is the
  watermark. Re-running is idempotent (chunks replace rows and mark coverage).

Local-dev only: the scheduler refuses to start in production and when
``ARCHIVE_CACHE_ENABLED`` is off.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from . import local_archive_store as store
from .config import settings
from .data_fetch_service import (
    ARCHIVE_TO_LIVE,
    PACKAGE_ALIAS_VIEW,
    _date_period_payload,
    _period_values_for_column,
    _preferred_date_column,
    load_catalog,
)
from .database import SessionLocal
from .external_data_client import ExternalDataClientError, clean_data_source_tenant
from .models import Business
from .workflow_data import _api_client

logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Europe/Berlin")

# Arkivvyer som Sankey och Produktivitet faktiskt använder (union). Bara dessa
# seedas/toppas – aggregat-/statistikvyer och oanvända loggar hoppas över.
SYNC_ARCHIVE_VIEWS: tuple[str, ...] = (
    "dblog_pick_log",
    "dblog_trans_log",
    "dblog_receive_log",
    "dblog_dispatch_pallet_log",
    "dblog_loading_log",
    "dblog_order_log",
)
SYNC_SNAPSHOT_VIEWS: tuple[str, ...] = (PACKAGE_ALIAS_VIEW,)
SYNC_CACHE_VIEWS: tuple[str, ...] = (*SYNC_ARCHIVE_VIEWS, *SYNC_SNAPSHOT_VIEWS)

_SYNC_LOCK = threading.Lock()
_SCHEDULER_STARTED = False


class ArchiveCacheSyncError(RuntimeError):
    pass


def _date_between_filter(view_id: str, start: date, end: date) -> list[dict] | None:
    try:
        view = load_catalog().view(view_id)
    except Exception:
        return None
    column = _preferred_date_column(view)
    if column is None:
        return None
    period = _date_period_payload("archive_cache", start, end)
    return [{"id": column.id, "operator": "Between", "value": _period_values_for_column(period, column)}]


def _fetch(tenant: str | None, view_id: str, start: date, end: date) -> list[dict]:
    if start > end:
        return []
    client = _api_client(tenant=tenant) if tenant else _api_client()
    filters = _date_between_filter(view_id, start, end)
    return client.fetch_all(view_id, filters=filters)


def _fetch_snapshot(tenant: str | None, view_id: str, today: date) -> list[dict]:
    client = _api_client(tenant=tenant) if tenant else _api_client()
    filters = _date_between_filter(view_id, date(2000, 1, 1), today)
    return client.fetch_all(view_id, filters=filters)


def _chunk_days() -> int:
    return max(1, int(getattr(settings, "ARCHIVE_CACHE_CHUNK_DAYS", 14) or 14))


def _empty_stop_days() -> int:
    raw = getattr(settings, "ARCHIVE_CACHE_EMPTY_STOP_DAYS", 300)
    if raw is None or raw == "":
        raw = 300
    return max(0, int(raw))


def _source_segments(
    archive_view_id: str, live_id: str, chunk_start: date, chunk_end: date, cutoff: date
) -> list[tuple[str, str, date, date]]:
    """Dela en chunk i (källa-etikett, vy, start, slut). dblog för datum < cutoff, live för >=."""
    if chunk_end < cutoff:
        return [("dblog", archive_view_id, chunk_start, chunk_end)]
    if chunk_start >= cutoff:
        return [("live", live_id, chunk_start, chunk_end)]
    return [
        ("dblog", archive_view_id, chunk_start, cutoff - timedelta(days=1)),
        ("live", live_id, cutoff, chunk_end),
    ]


ReportCallback = Callable[[str, date, date, int], None] | None


@dataclass
class FillChunkResult:
    written: int = 0
    fetched: int = 0


@dataclass
class FillRangeResult:
    written: int = 0
    empty_stopped: bool = False
    empty_days: int = 0


def _fill_range(
    tenant: str | None,
    archive_view_id: str,
    live_id: str,
    cutoff: date,
    start: date,
    end: date,
    *,
    descending: bool,
    report: ReportCallback = None,
) -> FillRangeResult:
    """Hämta+skriv [start, end] i bitar, en chunk i taget (bounded minne, återupptagningsbart).

    Varje chunk persisteras direkt, så ett avbrott tappar bara den pågående biten – nästa
    körning fortsätter från det som redan skrivits. ``descending`` styr riktningen så att det
    lagrade intervallet alltid växer sammanhängande (bakåt från min, framåt från max).
    ``report(source, seg_start, seg_end, rows)`` anropas efter varje skriven bit (progress).
    """
    if start > end:
        return FillRangeResult()
    chunk = _chunk_days()
    total = 0
    if descending:
        empty_stop_days = _empty_stop_days()
        empty_days = 0
        cursor_end = end
        while cursor_end >= start:
            cursor_start = max(start, cursor_end - timedelta(days=chunk - 1))
            result = _fill_one_chunk(tenant, archive_view_id, live_id, cutoff, cursor_start, cursor_end, report)
            total += result.written
            if result.fetched == 0:
                empty_days += (cursor_end - cursor_start).days + 1
            else:
                empty_days = 0
            if empty_stop_days and empty_days >= empty_stop_days:
                detail = (
                    f"empty stop efter {empty_days} dagar utan rader; "
                    f"{start.isoformat()}..{end.isoformat()} betraktas som tackt"
                )
                store.mark_covered_range(tenant, archive_view_id, start, end, detail=detail)
                store.record_sync(
                    tenant,
                    archive_view_id,
                    "empty_stop",
                    start=start,
                    end=end,
                    rows=0,
                    status="ok",
                    detail=detail,
                )
                logger.info(
                    "Archive cache empty stop: %s tenant=%s %s..%s efter %d tomma dagar.",
                    archive_view_id, tenant, start.isoformat(), end.isoformat(), empty_days,
                )
                return FillRangeResult(written=total, empty_stopped=True, empty_days=empty_days)
            cursor_end = cursor_start - timedelta(days=1)
    else:
        cursor_start = start
        while cursor_start <= end:
            cursor_end = min(end, cursor_start + timedelta(days=chunk - 1))
            total += _fill_one_chunk(
                tenant, archive_view_id, live_id, cutoff, cursor_start, cursor_end, report
            ).written
            cursor_start = cursor_end + timedelta(days=1)
    return FillRangeResult(written=total)


def _fill_one_chunk(
    tenant: str | None, archive_view_id: str, live_id: str, cutoff: date,
    chunk_start: date, chunk_end: date, report: ReportCallback = None,
) -> FillChunkResult:
    written_total = 0
    fetched_total = 0
    for source, seg_view, seg_start, seg_end in _source_segments(archive_view_id, live_id, chunk_start, chunk_end, cutoff):
        try:
            rows = _fetch(tenant, seg_view, seg_start, seg_end)
        except ExternalDataClientError as exc:
            store.record_sync(tenant, archive_view_id, source, start=seg_start, end=seg_end, rows=0, status="error", detail=str(exc))
            raise
        fetched = len(rows)
        fetched_total += fetched
        written = sum(store.append_rows_by_date(tenant, archive_view_id, rows).values())
        written_total += written
        if fetched == 0 or written > 0:
            store.mark_covered_range(
                tenant,
                archive_view_id,
                seg_start,
                seg_end,
                detail=f"{source} {seg_start.isoformat()}..{seg_end.isoformat()} rows={written}",
            )
        store.record_sync(tenant, archive_view_id, source, start=seg_start, end=seg_end, rows=written, status="ok")
        logger.info(
            "Archive cache %s %s tenant=%s %s..%s -> %d rader.",
            source, archive_view_id, tenant, seg_start.isoformat(), seg_end.isoformat(), written,
        )
        if report is not None:
            report(source, seg_start, seg_end, written)
    return FillChunkResult(written=written_total, fetched=fetched_total)


def missing_window(tenant: str | None, archive_view_id: str, today: date | None = None) -> tuple[date, date] | None:
    """Vilka hela dygn saknas mellan senaste ingestade dag och igår? None om inget/oseedad."""
    today = today or datetime.now(LOCAL_TZ).date()
    _min_d, max_d = store.covered_range(tenant, archive_view_id)
    if max_d is None:
        return None
    start = max_d + timedelta(days=1)
    end = today - timedelta(days=1)
    if start > end:
        return None
    return start, end


def view_coverage(tenant: str | None, archive_view_id: str, today: date | None = None) -> dict:
    days, live_id = ARCHIVE_TO_LIVE[archive_view_id]
    day = today or datetime.now(LOCAL_TZ).date()
    seed_days = max(1, int(getattr(settings, "ARCHIVE_CACHE_SEED_DAYS", 400) or 400))
    target_start = day - timedelta(days=seed_days)
    target_end = day - timedelta(days=1)
    ingested_min, ingested_max = store.ingested_range(tenant, archive_view_id)
    min_d, max_d = store.covered_range(tenant, archive_view_id)
    miss = missing_window(tenant, archive_view_id, today=day)
    fully_covered = store.is_window_covered(tenant, archive_view_id, target_start, target_end)
    backfill_remaining = (min_d - target_start).days if (min_d is not None and min_d > target_start) else 0
    return {
        "view": archive_view_id,
        "live_view": live_id,
        "retention_days": days,
        "seeded": max_d is not None,
        "fully_covered": fully_covered,
        "target_start": target_start.isoformat(),
        "target_end": target_end.isoformat(),
        "ingested_start": ingested_min.isoformat() if ingested_min else None,
        "ingested_end": ingested_max.isoformat() if ingested_max else None,
        "covered_start": min_d.isoformat() if min_d else None,
        "covered_end": max_d.isoformat() if max_d else None,
        "missing_start": miss[0].isoformat() if miss else None,
        "missing_end": miss[1].isoformat() if miss else None,
        "missing_days": ((miss[1] - miss[0]).days + 1) if miss else 0,
        "deep_backfill_remaining_days": backfill_remaining,
    }


def coverage_report(tenant: str | None = None, today: date | None = None, *, log_limit: int = 20) -> dict:
    """Täckning + senaste synk-logg per tenant/vy. Svarar frågan 'vad saknas efter nedtid?'."""
    tenants = [tenant] if tenant else active_tenants()
    day = today or datetime.now(LOCAL_TZ).date()
    return {
        "enabled": store.is_enabled(),
        "today": day.isoformat(),
        "views": list(SYNC_ARCHIVE_VIEWS),
        "snapshot_views": list(SYNC_SNAPSHOT_VIEWS),
        "tenants": [
            {
                "tenant": t,
                "views": [view_coverage(t, v, today=day) for v in SYNC_ARCHIVE_VIEWS],
                "snapshots": [store.snapshot_status(t, v) for v in SYNC_SNAPSHOT_VIEWS],
                "recent_syncs": store.read_sync_log(t, limit=log_limit),
            }
            for t in tenants
        ],
    }


def _emit(progress: Callable[[dict], None] | None, event: dict) -> None:
    if progress is None:
        return
    try:
        progress(event)
    except Exception:  # noqa: BLE001 – progress får aldrig fälla hämtningen
        pass


def _covered_days(min_d: date | None, max_d: date | None, target_start: date, target_end: date) -> int:
    if min_d is None or max_d is None:
        return 0
    lo, hi = max(min_d, target_start), min(max_d, target_end)
    return (hi - lo).days + 1 if lo <= hi else 0


def run_view(
    tenant: str | None,
    archive_view_id: str,
    today: date | None = None,
    *,
    deep_seed: bool = True,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Bringa vyns lokala cache till full täckning [today−SEED_DAYS .. igår], chunkat.

    Idempotent och återupptagningsbar: fyller bara det som saknas i ändarna. En avbruten
    seed fortsätter där den slutade – aldrig en full omhämtning bara för att appen startats om.

    ``deep_seed=False`` (serverns schemaläggare): toppa bara på redan seedade vyer framåt,
    starta aldrig den tunga djup-seeden och rör inte oseedade vyer. Den seeden görs via CLI.
    ``progress`` får event-dictar (start/chunk/done) för live-progressbar.
    """
    days, live_id = ARCHIVE_TO_LIVE[archive_view_id]
    today = today or datetime.now(LOCAL_TZ).date()
    cutoff = today - timedelta(days=days)
    seed_days = max(1, int(getattr(settings, "ARCHIVE_CACHE_SEED_DAYS", 400) or 400))
    target_start = today - timedelta(days=seed_days)
    target_end = today - timedelta(days=1)  # bara hela dygn

    min_d, max_d = store.covered_range(tenant, archive_view_id)
    was_fully = store.is_window_covered(tenant, archive_view_id, target_start, target_end)
    target_span = max(0, (target_end - target_start).days + 1)
    covered_before = _covered_days(min_d, max_d, target_start, target_end)

    # Vilka delintervall ska fyllas? (kind, start, slut, descending)
    jobs: list[tuple[str, date, date, bool]] = []
    if target_start <= target_end:
        if max_d is None:
            if deep_seed:
                jobs.append(("seed", target_start, target_end, True))
        else:
            if max_d < target_end:  # framåt (dagar sedan senaste synk) – alltid
                jobs.append(("forward", max_d + timedelta(days=1), target_end, False))
            if deep_seed and min_d > target_start:  # djup historik – bara i deep-läge
                jobs.append(("backfill", target_start, min_d - timedelta(days=1), True))

    todo_days = sum((end - start).days + 1 for _kind, start, end, _desc in jobs)
    will_seed = max_d is None and deep_seed
    skipped = max_d is None and not deep_seed
    _emit(progress, {
        "type": "start", "tenant": tenant, "view": archive_view_id,
        "target_start": target_start.isoformat(), "target_end": target_end.isoformat(),
        "target_span_days": target_span, "covered_before_days": covered_before,
        "todo_days": todo_days, "will_seed": will_seed, "skipped": skipped,
    })

    done_days = [0]

    def report(source: str, seg_start: date, seg_end: date, rows: int) -> None:
        done_days[0] += (seg_end - seg_start).days + 1
        _emit(progress, {
            "type": "chunk", "tenant": tenant, "view": archive_view_id, "source": source,
            "start": seg_start.isoformat(), "end": seg_end.isoformat(), "rows": rows,
            "done_days": covered_before + done_days[0], "total_days": target_span,
        })

    filled = {"seed": 0, "forward": 0, "backfill": 0}
    empty_stopped = False
    for kind, start, end, descending in jobs:
        detail = {
            "seed": f"initial seed {start.isoformat()}..{end.isoformat()} (chunkat)",
            "forward": f"{(end - start).days + 1} dag(ar) saknas framåt ({start.isoformat()}..{end.isoformat()}) – fylls på nu",
            "backfill": f"fyller djup historik {start.isoformat()}..{end.isoformat()} (chunkat)",
        }[kind]
        store.record_sync(tenant, archive_view_id, "plan", start=start, end=end, rows=0, status="planned", detail=detail)
        logger.info("Archive cache: %s tenant=%s %s.", archive_view_id, tenant, detail)
        result = _fill_range(
            tenant, archive_view_id, live_id, cutoff, start, end, descending=descending, report=report
        )
        filled[kind] += result.written
        empty_stopped = empty_stopped or result.empty_stopped

    # Loggmarkör när hela vyns intervall är på plats. `newly_complete` = det var inte
    # fullständigt innan men är det nu (dvs. seeden/ikappkörningen blev klar denna körning).
    fully_covered = store.is_window_covered(tenant, archive_view_id, target_start, target_end)
    newly_complete = fully_covered and not was_fully
    total_new = filled["seed"] + filled["forward"] + filled["backfill"]
    if newly_complete:
        store.record_sync(
            tenant, archive_view_id, "complete", start=target_start, end=target_end,
            rows=total_new, status="ok",
            detail=f"hela intervallet {target_start.isoformat()}..{target_end.isoformat()} är hämtat",
        )
        logger.info(
            "Archive cache: %s tenant=%s FÄRDIGSEEDAD – hela %s..%s finns nu lokalt (%d nya rader).",
            archive_view_id, tenant, target_start.isoformat(), target_end.isoformat(), total_new,
        )
    _emit(progress, {
        "type": "done", "tenant": tenant, "view": archive_view_id,
        "fully_covered": fully_covered, "newly_complete": newly_complete,
        "rows": total_new, "skipped": skipped,
        "empty_stopped": empty_stopped,
    })
    return {
        "view": archive_view_id,
        "forward_rows": filled["forward"],
        "backfill_rows": filled["seed"] + filled["backfill"],
        "fully_covered": fully_covered,
        "newly_complete": newly_complete,
        "skipped": skipped,
        "empty_stopped": empty_stopped,
    }


def run_snapshot_view(
    tenant: str | None,
    view_id: str,
    today: date | None = None,
    *,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Refresh a date-less support-view snapshot with a full replace."""
    if view_id not in SYNC_SNAPSHOT_VIEWS:
        raise ValueError(f"{view_id} ar inte en kand snapshot-vy.")
    day = today or datetime.now(LOCAL_TZ).date()
    _emit(progress, {
        "type": "start", "tenant": tenant, "view": view_id,
        "target_start": None, "target_end": day.isoformat(),
        "target_span_days": 1, "covered_before_days": 0,
        "todo_days": 1, "will_seed": False, "skipped": False,
    })
    try:
        rows = _fetch_snapshot(tenant, view_id, day)
        written = store.replace_snapshot_rows(tenant, view_id, rows)
    except ExternalDataClientError as exc:
        store.record_sync(tenant, view_id, "snapshot", start=None, end=None, rows=0, status="error", detail=str(exc))
        raise
    store.record_sync(
        tenant,
        view_id,
        "snapshot",
        start=None,
        end=None,
        rows=written,
        status="ok",
        detail=f"full refresh {day.isoformat()}",
    )
    _emit(progress, {
        "type": "chunk", "tenant": tenant, "view": view_id, "source": "snapshot",
        "start": None, "end": day.isoformat(), "rows": written,
        "done_days": 1, "total_days": 1,
    })
    _emit(progress, {
        "type": "done", "tenant": tenant, "view": view_id,
        "fully_covered": True, "newly_complete": True,
        "rows": written, "skipped": False,
    })
    logger.info("Archive cache snapshot: %s tenant=%s -> %d rader.", view_id, tenant, written)
    return {
        "view": view_id,
        "snapshot": True,
        "rows": written,
        "fully_covered": True,
        "newly_complete": True,
        "skipped": False,
    }


def sync_tenant(
    tenant: str | None,
    today: date | None = None,
    *,
    deep_seed: bool = True,
    progress: Callable[[dict], None] | None = None,
    view_ids: list[str] | None = None,
) -> dict:
    results: list[dict] = []
    errors: list[dict] = []
    views = list(view_ids or SYNC_CACHE_VIEWS)
    for view_id in views:
        try:
            if view_id in SYNC_ARCHIVE_VIEWS:
                results.append(run_view(tenant, view_id, today=today, deep_seed=deep_seed, progress=progress))
            elif view_id in SYNC_SNAPSHOT_VIEWS:
                results.append(run_snapshot_view(tenant, view_id, today=today, progress=progress))
            else:
                raise ArchiveCacheSyncError(f"Okand cache-vy: {view_id}")
        except ExternalDataClientError as exc:
            errors.append({"view": view_id, "error": str(exc)})
            logger.warning("Archive cache sync misslyckades för %s tenant=%s: %s", view_id, tenant, exc)
        except Exception as exc:  # noqa: BLE001 – en trasig vy ska inte stoppa övriga
            errors.append({"view": view_id, "error": repr(exc)})
            logger.warning("Archive cache sync fel för %s tenant=%s.", view_id, tenant, exc_info=True)
    all_covered = bool(results) and not errors and all(r.get("fully_covered") for r in results)
    if all_covered:
        logger.info(
            "Archive cache: tenant=%s KLAR – alla %d vyer fullständigt hämtade lokalt.",
            tenant, len(views),
        )
    return {"tenant": tenant, "results": results, "errors": errors, "all_covered": all_covered}


def _run_cache_view(
    tenant: str | None,
    view_id: str,
    today: date | None,
    *,
    deep_seed: bool,
    progress: Callable[[dict], None] | None,
) -> dict:
    if view_id in SYNC_ARCHIVE_VIEWS:
        return run_view(tenant, view_id, today=today, deep_seed=deep_seed, progress=progress)
    if view_id in SYNC_SNAPSHOT_VIEWS:
        return run_snapshot_view(tenant, view_id, today=today, progress=progress)
    raise ArchiveCacheSyncError(f"Okand cache-vy: {view_id}")


def seed_all(
    tenants: list[str] | None = None,
    today: date | None = None,
    *,
    max_workers: int | None = None,
    progress: Callable[[dict], None] | None = None,
    view_ids: list[str] | None = None,
) -> dict:
    """Full djup-seed av alla (tenant, vy) parallellt. Används av CLI:t.

    Varje vy hämtas i en egen tråd (DuckDB-skrivningar serialiseras per fil av store-låset,
    men nätverkshämtningarna – den långsamma delen – körs parallellt). Återupptagningsbart.
    """
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"status": "running"}
    try:
        tenants = tenants if tenants is not None else active_tenants()
        views = list(view_ids or SYNC_CACHE_VIEWS)
        jobs = [(t, v) for t in tenants for v in views]
        if not jobs:
            return {"status": "ok", "tenants": tenants, "results": []}
        workers = max_workers or int(getattr(settings, "ARCHIVE_CACHE_SEED_WORKERS", 5) or 5)
        workers = max(1, min(workers, len(jobs)))
        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ArchiveSeed") as executor:
            futures = {
                executor.submit(_run_cache_view, t, v, today, deep_seed=True, progress=progress): (t, v)
                for (t, v) in jobs
            }
            for future in as_completed(futures):
                t, v = futures[future]
                try:
                    results.append({"tenant": t, **future.result()})
                except Exception as exc:  # noqa: BLE001
                    results.append({"tenant": t, "view": v, "error": repr(exc)})
                    logger.warning("Archive cache seed-fel för %s tenant=%s.", v, t, exc_info=True)
        return {"status": "ok", "tenants": tenants, "results": results}
    finally:
        _SYNC_LOCK.release()


def active_tenants() -> list[str]:
    try:
        db = SessionLocal()
    except Exception:
        logger.warning("Archive cache: kunde inte öppna DB-session för tenants.", exc_info=True)
        return []
    try:
        rows = (
            db.query(Business.tenant)
            .filter(Business.is_active.is_(True))
            .order_by(Business.sort_order, Business.id)
            .all()
        )
    except Exception:
        logger.warning("Archive cache: kunde inte lista aktiva businesses.", exc_info=True)
        return []
    finally:
        db.close()
    tenants: list[str] = []
    seen: set[str] = set()
    for row in rows:
        try:
            cleaned = clean_data_source_tenant(row[0])
        except ValueError:
            cleaned = None
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            tenants.append(cleaned)
    return tenants


def sync_all_tenants(today: date | None = None, *, deep_seed: bool = True) -> dict:
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"status": "running"}
    try:
        tenants = active_tenants()
        return {
            "status": "ok",
            "tenants": [sync_tenant(tenant, today=today, deep_seed=deep_seed) for tenant in tenants],
        }
    finally:
        _SYNC_LOCK.release()


def _next_sync_at(now: datetime) -> datetime:
    hour = max(0, min(23, int(getattr(settings, "ARCHIVE_CACHE_SYNC_HOUR", 0) or 0)))
    minute = max(0, min(59, int(getattr(settings, "ARCHIVE_CACHE_SYNC_MINUTE", 1) or 0)))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _scheduler_loop() -> None:
    # Djup-seeden görs via CLI. Schemaläggaren toppar bara på redan seedade vyer framåt
    # (deep_seed styrs av ARCHIVE_CACHE_SEED_ON_START, default av) – ingen tung hämtning vid start.
    deep = bool(getattr(settings, "ARCHIVE_CACHE_SEED_ON_START", False))
    try:
        sync_all_tenants(deep_seed=deep)  # första passet direkt vid start
    except Exception:
        logger.warning("Archive cache: initialt synkpass misslyckades.", exc_info=True)
    while True:
        try:
            now = datetime.now(LOCAL_TZ)
            next_run = _next_sync_at(now)
            time.sleep(max(1.0, (next_run - now).total_seconds()))
            sync_all_tenants(deep_seed=deep)
        except Exception:
            logger.warning("Archive cache scheduler-fel.", exc_info=True)
            time.sleep(60)


def start_archive_cache_scheduler() -> None:
    """Starta daglig topp-på (endast lokalt, gate:at)."""
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    if not store.is_enabled():
        return
    if settings.is_production:
        logger.info("Archive cache scheduler startas inte i produktion.")
        return
    _SCHEDULER_STARTED = True
    threading.Thread(target=_scheduler_loop, name="ArchiveCacheSync", daemon=True).start()
    logger.info("Archive cache scheduler startad (lokal dev).")


def main() -> None:
    import json
    import sys

    logging.basicConfig(level=logging.INFO)
    if not store.is_enabled():
        print("ARCHIVE_CACHE_ENABLED är av – inget att göra.")
        return
    command = sys.argv[1] if len(sys.argv) > 1 else "sync"
    if command == "status":
        print(json.dumps(coverage_report(), ensure_ascii=False, indent=2, default=str))
        return
    result = sync_all_tenants()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
