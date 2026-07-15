import asyncio
import json
import queue
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import logging
from pathlib import Path
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from .. import audit
from ..business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code, scoped_get, user_business_id
from ..database import SessionLocal
from ..deps import get_db, require_view_access
from ..models import Activity, Business, Person, User
from ..observability import log_json_payload_size
from ..productivity_service import (
    ProductivitySourceError,
    _number,
    _read_csv_rows_with_headers,
    _row_value,
)
from ..productivity_kpi_rules import build_person_productivity_report_from_files, normalize_process
from ..productivity_sync import (
    LOCAL_TZ,
    ProductivitySyncError,
    ensure_productivity_snapshot,
    productivity_backfill_status,
    productivity_prebuild_status,
    productivity_snapshot_files,
    productivity_snapshot_status,
    sync_productivity_snapshot,
)
from ..settings_service import (
    PRODUCTIVITY_FINANCE_COLLAR_TYPES,
    PRODUCTIVITY_FINANCE_DEFAULT_VAS_RATE_TYPE,
    PRODUCTIVITY_FINANCE_VAS_RATE_TYPES,
    clean_productivity_finance_company_code,
    get_productivity_finance_settings,
    get_role_view_access,
    normalize_productivity_finance_collar_type,
    productivity_finance_default_invoice_rows,
    productivity_finance_vas_rates_from_invoice_rows,
)
from ..user_access import can_access_view
from ..workflow_data import productivity_api_source_map, sources_available


from . import productivity_finance_helpers, productivity_helpers

router = APIRouter(prefix="/api/productivity", tags=["productivity"])
logger = logging.getLogger(__name__)
@router.post("/sync")
def sync_productivity(
    date_filter: date | None = Query(default=None, alias="date"),
    user: User = Depends(require_view_access("productivity", "edit")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return sync_productivity_snapshot(
            date_filter,
            business_code=productivity_finance_helpers._productivity_business_code(db, user),
            db=db,
            user_id=getattr(user, "id", None),
        )
    except ProductivitySyncError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/persons/{person_id}")
def get_person_productivity(
    person_id: int,
    request: Request,
    period: str = Query(default="week"),
    date_filter: date | None = Query(default=None, alias="date"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(require_view_access("productivity", "view")),
    db: Session = Depends(get_db),
) -> dict:
    person = productivity_helpers.scoped_get(db, Person, person_id, user, detail="Person hittades inte")
    period_start, period_end, period_label = productivity_helpers._period_bounds(
        period,
        anchor_date=date_filter,
        start_date=start_date,
        end_date=end_date,
    )
    days = productivity_helpers._date_span(period_start, period_end)
    reports: list[dict] = []
    missing_dates: list[str] = []
    errors: list[dict] = []
    source_status: list[dict] = []

    for day in days:
        try:
            files, sync_status = productivity_helpers._person_productivity_files_for_date(request, db, user, day)
            report = productivity_helpers._build_cached_person_productivity_report(
                db,
                files,
                report_date=day,
                business_id=person.business_id,
                sync=sync_status,
            )
            reports.append(report)
            source_status.append({"date": day.isoformat(), "status": "ok", "source": sync_status.get("source")})
        except (ProductivitySourceError, ProductivitySyncError) as exc:
            missing_dates.append(day.isoformat())
            errors.append({"date": day.isoformat(), "error_type": type(exc).__name__, "message": str(exc)})

    aggregate = productivity_helpers._aggregate_person_activity_stats(reports, person.id)
    return {
        "person": {
            "id": person.id,
            "name": person.name,
            "noman": person.noman,
            "business_id": person.business_id,
        },
        "period": {
            "type": str(period or "week").strip().lower(),
            "label": period_label,
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "requested_days": len(days),
        },
        "dates": [str(report.get("date") or "") for report in reports],
        "missing_dates": missing_dates,
        "source_status": source_status,
        "errors": errors[:20],
        "backfill": productivity_helpers.productivity_backfill_status(),
        "prebuild": productivity_prebuild_status(),
        **aggregate,
    }


@router.get("/overview/business-summary")
def get_productivity_overview_business_summary(
    request: Request,
    period: str = Query(default="day"),
    date_filter: date | None = Query(default=None, alias="date"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(require_view_access("productivity", "view")),
    db: Session = Depends(get_db),
) -> dict:
    return productivity_helpers.build_business_summary_payload(
        db,
        user,
        period=period,
        anchor_date=date_filter,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/overview")
def get_productivity_overview(
    request: Request,
    period: str = Query(default="day"),
    date_filter: date | None = Query(default=None, alias="date"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(require_view_access("productivity", "view")),
    db: Session = Depends(get_db),
) -> dict:
    return productivity_helpers._run_productivity_overview(
        request,
        db,
        user,
        period=period,
        date_filter=date_filter,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/overview/stream")
async def stream_productivity_overview(
    request: Request,
    period: str = Query(default="day"),
    date_filter: date | None = Query(default=None, alias="date"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(require_view_access("productivity", "view")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Bygger produktivitetsöversikten och strömmar äkta progress per dag via SSE."""
    normalized_period = str(period or "day").strip().lower()
    period_start, period_end, _label = productivity_helpers._overview_period_bounds(
        normalized_period,
        anchor_date=date_filter,
        start_date=start_date,
        end_date=end_date,
    )
    total_steps = len(productivity_helpers._date_span(period_start, period_end)) + 1

    events: queue.Queue = queue.Queue()

    def progress(event: dict) -> None:
        events.put({"type": "progress", **event})

    def worker() -> None:
        worker_db = productivity_helpers.SessionLocal()
        try:
            payload = productivity_helpers._run_productivity_overview(
                request,
                worker_db,
                user,
                period=period,
                date_filter=date_filter,
                start_date=start_date,
                end_date=end_date,
                progress_callback=progress,
            )
            events.put({"type": "done", "payload": payload})
            # Mätpunkt (#46): se sankey.py - done-eventet bär hela rapporten och SSE
            # undantas från gzip. Mäts EFTER put() så användarens data inte fördröjs.
            log_json_payload_size(
                "flow.productivity.payload_size",
                feature="productivity",
                payload=payload,
                attributes={
                    "sse_period": normalized_period,
                    "sse_days": max(0, total_steps - 1),
                },
                event_alias="productivity_payload_size",
                logger_=logger,
            )
        except HTTPException as exc:
            events.put({"type": "error", "status": exc.status_code, "message": str(exc.detail)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Productivity overview stream failed")
            events.put({"type": "error", "status": 500, "message": str(exc)})
        finally:
            worker_db.close()
            events.put(None)

    threading.Thread(target=worker, name="productivity-overview-stream", daemon=True).start()

    async def event_source():
        loop = asyncio.get_running_loop()
        yield productivity_helpers._sse_event({"type": "start", "total": total_steps})
        while True:
            item = await loop.run_in_executor(None, events.get)
            if item is None:
                break
            yield productivity_helpers._sse_event(item)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("")
def get_productivity(
    request: Request,
    date_filter: date | None = Query(default=None, alias="date"),
    user: User = Depends(require_view_access("productivity", "view")),
    db: Session = Depends(get_db),
) -> dict:
    source_status: list[dict] = []
    try:
        selected_date_filter = date_filter if isinstance(date_filter, date) else None
        business_code = productivity_finance_helpers._productivity_business_code(db, user)
        business_id = productivity_finance_helpers._productivity_business_id(db, user)
        finance_context = productivity_finance_helpers._productivity_finance_context(db, user, business_id)
        if not productivity_helpers.sources_available(tuple(productivity_api_source_map().values())):
            raise ProductivitySyncError("Produktivitetens globala API-källor är inte konfigurerade.")
        sync_status = ensure_productivity_snapshot(
            selected_date_filter,
            business_code=business_code,
            db=db,
            user_id=getattr(user, "id", None),
            wait_seconds=10,
        )
        snapshot_date = selected_date_filter or date.fromisoformat(str(sync_status.get("date") or date.today().isoformat()))
        files = productivity_helpers.productivity_snapshot_files(snapshot_date)
        source_status = list(sync_status.get("sources") or [])
        report = productivity_helpers._build_cached_person_productivity_report(
            db,
            files,
            report_date=snapshot_date,
            business_id=business_id,
            sync=productivity_helpers.productivity_snapshot_status(snapshot_date),
        )
        productivity_finance_helpers._attach_productivity_finance(report, finance_context)
        report["source_status"] = source_status
        report["backfill"] = productivity_helpers.productivity_backfill_status()
        report["prebuild"] = productivity_prebuild_status()
        productivity_helpers._audit_productivity_report_sources(db, user, status_text="ok", source_status=source_status)
        return report
    except ProductivitySyncError as exc:
        productivity_helpers._audit_productivity_report_sources(
            db,
            user,
            status_text="error",
            source_status=source_status,
            error_type=type(exc).__name__,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ProductivitySourceError as exc:
        productivity_helpers._audit_productivity_report_sources(
            db,
            user,
            status_text="error",
            source_status=source_status,
            error_type=type(exc).__name__,
            status_code=status.HTTP_404_NOT_FOUND,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        productivity_helpers._audit_productivity_report_sources(
            db,
            user,
            status_text="error",
            source_status=source_status,
            error_type=type(exc).__name__,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte läsa produktivitetsunderlag: {exc}",
        ) from exc
    except Exception as exc:
        productivity_helpers._audit_productivity_report_sources(
            db,
            user,
            status_text="error",
            source_status=source_status,
            error_type=type(exc).__name__,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte beräkna produktivitet: {exc}",
        ) from exc
