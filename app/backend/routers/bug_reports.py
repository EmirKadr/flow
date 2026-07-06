"""Buggrapporter: 30 sekunders DOM-inspelning (rrweb) + kontext från användare.

Flöde: användaren klickar Bugg i sidebar-footern, godkänner i popupen,
återskapar buggen under inspelning och skickar. Admin/Super User spelar upp
rapporten i vyn Buggrapporter. Inspelningen visar bara det användaren själv
såg i appen; lösenordsfält maskas av rrweb i klienten.

Skyddsräcken: storlekstak, rate limit per användare (DB-räknad — fungerar
oavsett antal workers), retention-städning och auditrader utan inspelnings-
innehåll.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..business_scope import visible_business_id
from ..config import settings
from ..deps import get_current_user, get_db, require_view_access
from ..models import BugReport, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bug-reports", tags=["bug-reports"])

_ALLOWED_STATUSES = ("new", "seen", "done")
_CONTEXT_CHAR_LIMIT = 20000


class BugReportIn(BaseModel):
    events_json: str = Field(min_length=2)
    note: str | None = None
    view_id: str | None = None
    page_path: str | None = None
    context: dict | None = None


class BugReportStatusIn(BaseModel):
    status: str


def purge_expired_bug_reports(db: Session) -> int:
    """Radera rapporter äldre än retentionen. Returnerar antal raderade."""
    days = max(1, int(settings.BUG_REPORTS_RETENTION_DAYS))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = db.query(BugReport).filter(BugReport.created_at < cutoff).delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


def _sanitized_context(raw: dict | None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    text = json.dumps(raw, ensure_ascii=False, default=str)
    if len(text) > _CONTEXT_CHAR_LIMIT:
        return {"truncated": True, "note": "Kontexten var för stor och utelämnades."}
    return raw


@router.post("", status_code=status.HTTP_201_CREATED)
def create_bug_report(
    payload: BugReportIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not settings.BUG_REPORTS_ENABLED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Buggrapportering är avstängd.")

    events_bytes = len(payload.events_json.encode("utf-8"))
    if events_bytes > settings.BUG_REPORTS_MAX_EVENTS_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Inspelningen är för stor för att skickas. Prova en kortare inspelning.",
        )
    try:
        events = json.loads(payload.events_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ogiltig inspelningsdata.") from exc
    if not isinstance(events, list) or not events:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Inspelningen saknar händelser.")

    window_start = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = (
        db.query(func.count(BugReport.id))
        .filter(BugReport.user_id == user.id, BugReport.created_at >= window_start)
        .scalar()
    )
    if int(recent or 0) >= settings.BUG_REPORTS_RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Du har redan skickat flera buggrapporter senaste timmen. Vänta en stund.",
        )

    report = BugReport(
        business_id=getattr(user, "business_id", None),
        user_id=user.id,
        view_id=(payload.view_id or "")[:80] or None,
        page_path=(payload.page_path or "")[:300] or None,
        note=(payload.note or "").strip()[:2000] or None,
        status="new",
        events_json=payload.events_json,
        events_bytes=events_bytes,
        context=_sanitized_context(payload.context),
    )
    db.add(report)
    db.flush()
    audit_log(
        db,
        entity_type="bug_report",
        entity_id=report.id,
        action="create",
        old_value=None,
        new_value={
            "view_id": report.view_id,
            "page_path": report.page_path,
            "note_chars": len(report.note or ""),
            "events_bytes": events_bytes,
            "event_count": len(events),
        },
        user_id=user.id,
        business_id=report.business_id,
    )
    db.commit()
    try:
        purge_expired_bug_reports(db)
    except Exception:  # noqa: BLE001 - städning får aldrig fälla inskicket
        logger.warning("Kunde inte städa gamla buggrapporter.", exc_info=True)
    return {"id": report.id, "status": report.status}


def _report_row(report: BugReport, usernames: dict[int, str]) -> dict:
    return {
        "id": report.id,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "username": usernames.get(report.user_id or -1),
        "business_id": report.business_id,
        "view_id": report.view_id,
        "page_path": report.page_path,
        "note": report.note,
        "status": report.status,
        "events_bytes": report.events_bytes,
        "handled_at": report.handled_at.isoformat() if report.handled_at else None,
    }


@router.get("")
def list_bug_reports(
    status_filter: str | None = None,
    user: User = Depends(require_view_access("bugReports", "view")),
    db: Session = Depends(get_db),
) -> dict:
    business_id = visible_business_id(db, user, None)
    query = db.query(BugReport)
    if business_id is not None:
        query = query.filter(BugReport.business_id == business_id)
    if status_filter in _ALLOWED_STATUSES:
        query = query.filter(BugReport.status == status_filter)
    reports = query.order_by(BugReport.created_at.desc()).limit(200).all()
    user_ids = {report.user_id for report in reports if report.user_id is not None}
    usernames = (
        {row.id: row.username for row in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    return {"reports": [_report_row(report, usernames) for report in reports]}


def _visible_report_or_404(db: Session, user: User, report_id: int) -> BugReport:
    report = db.get(BugReport, report_id)
    business_id = visible_business_id(db, user, None)
    if report is None or (business_id is not None and report.business_id != business_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Buggrapporten hittades inte.")
    return report


@router.get("/{report_id}")
def get_bug_report(
    report_id: int,
    user: User = Depends(require_view_access("bugReports", "view")),
    db: Session = Depends(get_db),
) -> dict:
    report = _visible_report_or_404(db, user, report_id)
    usernames = (
        {row.id: row.username for row in db.query(User).filter(User.id == report.user_id).all()}
        if report.user_id is not None
        else {}
    )
    row = _report_row(report, usernames)
    row["events_json"] = report.events_json
    row["context"] = report.context
    return row


@router.patch("/{report_id}/status")
def set_bug_report_status(
    report_id: int,
    payload: BugReportStatusIn,
    user: User = Depends(require_view_access("bugReports", "edit")),
    db: Session = Depends(get_db),
) -> dict:
    new_status = str(payload.status or "").strip().lower()
    if new_status not in _ALLOWED_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ogiltig status. Välj en av: {', '.join(_ALLOWED_STATUSES)}.",
        )
    report = _visible_report_or_404(db, user, report_id)
    old_status = report.status
    report.status = new_status
    report.handled_at = datetime.now(timezone.utc) if new_status != "new" else None
    report.handled_by = user.id if new_status != "new" else None
    audit_log(
        db,
        entity_type="bug_report",
        entity_id=report.id,
        action="status_change",
        old_value={"status": old_status},
        new_value={"status": new_status},
        user_id=user.id,
        business_id=report.business_id,
    )
    db.commit()
    return {"id": report.id, "status": report.status}
