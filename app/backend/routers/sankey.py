from __future__ import annotations

import asyncio
import json
import queue
import re
import threading
from datetime import date
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import audit
from ..business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code, user_business_id
from ..database import SessionLocal
from ..deps import get_db, require_view_access
from ..models import Business, User
from ..observability import log_json_payload_size
from ..sankey_inbound_service import (
    SANKEY_SOURCE_VIEWS,
    SankeyInboundError,
    filter_trace_rows,
    get_trace_rows,
    load_sankey_inbound_payload,
    trace_rows_to_csv_lines,
)
from ..settings_service import clean_productivity_finance_company_code, get_productivity_finance_settings


router = APIRouter(prefix="/api/sankey", tags=["sankey"])
logger = logging.getLogger(__name__)


def _sankey_business(db: Session, user: User) -> Business | None:
    try:
        business_id = user_business_id(db, user)
        return db.get(Business, business_id) if business_id is not None else None
    except Exception:
        return None


def _sankey_business_id(db: Session, user: User) -> int | None:
    business = _sankey_business(db, user)
    return getattr(business, "id", None) or getattr(user, "business_id", None)


def _sankey_business_payload(business: Business | None) -> dict:
    return {
        "id": getattr(business, "id", None),
        "code": normalize_business_code(getattr(business, "code", None)) or DEFAULT_BUSINESS_CODE,
        "name": getattr(business, "name", None) or "Verksamhet",
        "company_codes": [
            code
            for code in (
                clean_productivity_finance_company_code(item)
                for item in (getattr(business, "company_codes", None) or [])
            )
            if code
        ],
    }


def _audit_sankey_report(
    db: Session,
    user: User,
    *,
    business_id: int | None,
    action: str,
    payload: dict,
) -> None:
    report_payload = {
        "period": payload.get("period"),
        "filters": payload.get("filters"),
        "summary": {
            "labels_received": (payload.get("summary") or {}).get("labels_received"),
            "purchase_lines_received": (payload.get("summary") or {}).get("purchase_lines_received"),
            "labels_traced": (payload.get("summary") or {}).get("labels_traced"),
            "labels_consumed": (payload.get("summary") or {}).get("labels_consumed"),
            "gross_income": (payload.get("summary") or {}).get("gross_income"),
            "inbound_income": (payload.get("summary") or {}).get("inbound_income"),
            "outbound_income": (payload.get("summary") or {}).get("outbound_income"),
            "gross_income_labels": (payload.get("summary") or {}).get("gross_income_labels"),
            "gross_income_purchase_lines": (payload.get("summary") or {}).get("gross_income_purchase_lines"),
            "outbound_picked_orders": (payload.get("summary") or {}).get("outbound_picked_orders"),
            "outbound_picked_rows": (payload.get("summary") or {}).get("outbound_picked_rows"),
            "outbound_picked_pcs": (payload.get("summary") or {}).get("outbound_picked_pcs"),
            "outbound_full_pallets": (payload.get("summary") or {}).get("outbound_full_pallets"),
            "outbound_loaded_pallets": (payload.get("summary") or {}).get("outbound_loaded_pallets"),
        },
        "source_status": [
            {
                "key": item.get("key"),
                "view": item.get("view"),
                "archive_view": item.get("archive_view"),
                "segment": item.get("segment"),
                "status": item.get("status"),
                "rows": item.get("rows"),
                "start": item.get("start"),
                "end": item.get("end"),
                "company": item.get("company"),
                "message": item.get("message"),
            }
            for item in (payload.get("source_status") or [])
            if isinstance(item, dict)
        ],
        "warning_codes": [
            item.get("code")
            for item in (payload.get("warnings") or [])
            if isinstance(item, dict) and item.get("code")
        ][:50],
    }
    audit.log_and_commit(
        db,
        entity_type="sankey_inbound_report",
        entity_id=0,
        action=action,
        old_value=None,
        new_value=report_payload,
        user_id=getattr(user, "id", None),
        business_id=business_id,
        logger=logger,
        context="sankey inbound report audit",
    )


@router.get("/inbound")
def get_sankey_inbound(
    period: str = Query(default="day", pattern="^(day|week|month|year)$"),
    selected_date: date | None = Query(default=None, alias="date"),
    company: str | None = Query(default=None),
    only_consumed: bool = Query(default=False),
    user: User = Depends(require_view_access("sankeyInbound", "view")),
    db: Session = Depends(get_db),
) -> dict:
    business = _sankey_business(db, user)
    business_id = getattr(business, "id", None) or _sankey_business_id(db, user)
    business_payload = _sankey_business_payload(business)
    company_codes = business_payload["company_codes"]
    selected = selected_date or date.today()
    try:
        payload = load_sankey_inbound_payload(
            finance_settings=get_productivity_finance_settings(db, business_id=business_id),
            company_codes=company_codes,
            period=period,
            selected_date=selected,
            business_id=business_id,
            business_code=business_payload["code"],
            company_filter=company,
            only_consumed=only_consumed,
            tenant=getattr(business, "tenant", None),
            db=db,
        )
        payload["business"] = business_payload
        _audit_sankey_report(db, user, business_id=business_id, action="run", payload=payload)
        return payload
    except SankeyInboundError as exc:
        error_payload = {
            "period": {"type": period, "date": selected.isoformat()},
            "filters": {
                "company": clean_productivity_finance_company_code(company) or "ALL",
                "only_consumed": bool(only_consumed),
            },
            "summary": {},
            "source_status": exc.source_status,
            "warnings": [{"code": "sankey_inbound_error", "message": str(exc)}],
        }
        _audit_sankey_report(db, user, business_id=business_id, action="run_failed", payload=error_payload)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/inbound/stream")
async def stream_sankey_inbound(
    period: str = Query(default="day", pattern="^(day|week|month|year)$"),
    selected_date: date | None = Query(default=None, alias="date"),
    company: str | None = Query(default=None),
    only_consumed: bool = Query(default=False),
    user: User = Depends(require_view_access("sankeyInbound", "view")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Hämtar Sankey - Inbound och strömmar äkta progress per källa via SSE.

    Allt som behöver request-sessionen löses här; själva hämtningen körs i en tråd
    med en egen DB-session så att vi kan strömma progress medan den jobbar.
    """
    business = _sankey_business(db, user)
    business_id = getattr(business, "id", None) or _sankey_business_id(db, user)
    business_payload = _sankey_business_payload(business)
    company_codes = business_payload["company_codes"]
    finance_settings = get_productivity_finance_settings(db, business_id=business_id)
    tenant = getattr(business, "tenant", None)
    selected = selected_date or date.today()
    total_steps = len(SANKEY_SOURCE_VIEWS) + 1

    events: queue.Queue = queue.Queue()

    def progress(event: dict) -> None:
        events.put({"type": "progress", **event})

    def worker() -> None:
        worker_db = SessionLocal()
        try:
            payload = load_sankey_inbound_payload(
                finance_settings=finance_settings,
                company_codes=company_codes,
                period=period,
                selected_date=selected,
                business_id=business_id,
                business_code=business_payload["code"],
                company_filter=company,
                only_consumed=only_consumed,
                tenant=tenant,
                db=worker_db,
                progress_callback=progress,
            )
            payload["business"] = business_payload
            events.put({"type": "done", "payload": payload})
            # Mätpunkt (#46): done-eventet bär hela rapporten, och text/event-stream
            # undantas från GZipMiddleware - payloaden går alltså rå över nätet utan
            # att någon vet hur stor den är. Mäts EFTER put() så användarens data
            # aldrig fördröjs av mätningen. Bara storlekar loggas, aldrig innehåll.
            log_json_payload_size(
                "flow.sankey_inbound.payload_size",
                feature="sankey_inbound",
                payload=payload,
                attributes={
                    "sse_period": period,
                    "sse_only_consumed": bool(only_consumed),
                    "client_filter_views": len(((payload.get("client_filters") or {}).get("views") or {})),
                    "source_count": len(payload.get("source_status") or []),
                },
                event_alias="sankey_inbound_payload_size",
                logger_=logger,
            )
            try:
                _audit_sankey_report(worker_db, user, business_id=business_id, action="run", payload=payload)
            except Exception:
                logger.warning("Sankey inbound stream audit failed", exc_info=True)
        except SankeyInboundError as exc:
            logger.warning(
                "Sankey inbound stream failed: period=%s date=%s company=%s status=%s detail=%s sources=%s",
                period, selected.isoformat(), company, exc.status_code, str(exc), exc.source_status,
            )
            events.put({
                "type": "error",
                "status": exc.status_code,
                "message": str(exc),
                "source_status": exc.source_status,
            })
            try:
                error_payload = {
                    "period": {"type": period, "date": selected.isoformat()},
                    "filters": {
                        "company": clean_productivity_finance_company_code(company) or "ALL",
                        "only_consumed": bool(only_consumed),
                    },
                    "summary": {},
                    "source_status": exc.source_status,
                    "warnings": [{"code": "sankey_inbound_error", "message": str(exc)}],
                }
                _audit_sankey_report(worker_db, user, business_id=business_id, action="run_failed", payload=error_payload)
            except Exception:
                logger.warning("Sankey inbound stream failed-audit failed", exc_info=True)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Sankey inbound stream failed (oväntat)")
            events.put({"type": "error", "status": 500, "message": str(exc)})
        finally:
            worker_db.close()
            events.put(None)

    threading.Thread(target=worker, name="sankey-inbound-stream", daemon=True).start()

    async def event_source():
        loop = asyncio.get_running_loop()
        yield _sse_event({"type": "start", "total": total_steps})
        while True:
            item = await loop.run_in_executor(None, events.get)
            if item is None:
                break
            yield _sse_event(item)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/inbound/trace")
def get_sankey_inbound_trace(
    token: str = Query(...),
    scope: str = Query(default="all", pattern="^(all|node|link)$"),
    id: str | None = Query(default=None),
    company: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    only_consumed: bool | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    _: User = Depends(require_view_access("sankeyInbound", "view")),
) -> dict:
    """Paginerad drill-down av spårade pallgrenar för vald nod/länk (lazy-load)."""
    rows = get_trace_rows(token)
    if rows is None:
        raise HTTPException(status_code=410, detail="Spårningen har gått ut. Kör om rapporten.")
    filtered = filter_trace_rows(
        rows,
        scope,
        id,
        company=company,
        start_date=start_date,
        end_date=end_date,
        only_consumed=only_consumed,
    )
    total = len(filtered)
    page = filtered[offset : offset + limit]
    return {"rows": page, "total": total, "offset": offset, "limit": limit}


@router.get("/inbound/trace.csv")
def export_sankey_inbound_trace(
    token: str = Query(...),
    scope: str = Query(default="all", pattern="^(all|node|link)$"),
    id: str | None = Query(default=None),
    company: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    only_consumed: bool | None = Query(default=None),
    name: str = Query(default="urval"),
    _: User = Depends(require_view_access("sankeyInbound", "view")),
) -> StreamingResponse:
    """Streamad CSV-export av spårade pallgrenar för urvalet (helår utan att spränga minnet)."""
    rows = get_trace_rows(token)
    if rows is None:
        raise HTTPException(status_code=410, detail="Spårningen har gått ut. Kör om rapporten.")
    filtered = filter_trace_rows(
        rows,
        scope,
        id,
        company=company,
        start_date=start_date,
        end_date=end_date,
        only_consumed=only_consumed,
    )
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name or "urval")).strip("-") or "urval"
    filename = f"sankey-inbound-sparning-{safe}.csv"
    return StreamingResponse(
        trace_rows_to_csv_lines(filtered),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
