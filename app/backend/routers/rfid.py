from __future__ import annotations

from datetime import datetime, time as datetime_time, timezone
import unicodedata
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..business_scope import scoped_get, visible_business_id
from ..config import settings
from ..deps import get_db, require_view_access
from ..models import Activity, Person, RfidDevice, RfidScanEvent, ScheduleCell, User
from ..schedule_locks import assert_can_modify_schedule_cells, foreign_schedule_cell_lock_applies
from .schedule_shared import HOURS, _cell_audit_dict, _cell_to_dict, _load_hour_segments, _schedule_date


router = APIRouter(prefix="/api/rfid", tags=["rfid"])

LOCAL_TZ = ZoneInfo("Europe/Berlin")
STATUS_PENDING = "pending"
STATUS_APPLIED = "applied"
STATUS_IGNORED = "ignored"
STATUS_DUPLICATE_IGNORED = "duplicate_ignored"
STATUS_UNKNOWN_PERSON = "unknown_person"
STATUS_UNKNOWN_ACTIVITY = "unknown_activity"
STATUS_CONFLICT = "conflict"


class RfidScanIn(BaseModel):
    device_id: str | None = None
    module_name: str
    tag_hex: str | None = None
    tag_dec: str | None = None
    scan_count: int | None = None


def _compact_key(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return "".join(ch for ch in without_marks.strip().lower() if ch.isalnum())


def _rfid_code(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _local_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ)


def _schedule_parts(value: datetime) -> tuple[int, int, int, int, int]:
    local = _local_time(value)
    iso = local.date().isocalendar()
    return iso.year, iso.week, iso.weekday, local.hour, local.minute


def _assert_device_token(request: Request) -> None:
    expected = settings.RFID_DEVICE_TOKEN.strip()
    if not expected:
        return
    provided = request.headers.get("x-flow-rfid-token", "")
    if provided != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="RFID-token saknas eller stammer inte")


def _activity_for_module(db: Session, module_name: str) -> Activity | None:
    key = _compact_key(module_name)
    if not key:
        return None
    rows = db.query(Activity).filter(Activity.is_active.is_(True)).all()
    exact = [
        activity
        for activity in rows
        if key in {_compact_key(activity.label), _compact_key(activity.code)}
    ]
    if exact:
        return sorted(exact, key=lambda activity: (activity.business_id or 0, activity.sort_order or 0, activity.id))[0]
    contains = [
        activity
        for activity in rows
        if key and (_compact_key(activity.label).startswith(key) or _compact_key(activity.code).startswith(key))
    ]
    return sorted(contains, key=lambda activity: (activity.business_id or 0, activity.sort_order or 0, activity.id))[0] if contains else None


def _upsert_device(db: Session, *, device_identifier: str, module_name: str, activity: Activity | None, seen_at: datetime) -> RfidDevice:
    device = db.query(RfidDevice).filter(func.lower(RfidDevice.device_id) == device_identifier.lower()).first()
    if device is None:
        device = RfidDevice(
            device_id=device_identifier,
            module_name=module_name,
            activity_id=activity.id if activity is not None else None,
            business_id=activity.business_id if activity is not None else None,
            is_active=True,
            last_seen_at=seen_at,
        )
        db.add(device)
        db.flush()
        return device
    device.module_name = module_name
    if activity is not None:
        device.activity_id = activity.id
        device.business_id = activity.business_id
    device.last_seen_at = seen_at
    return device


def _person_for_tag(db: Session, tag_code: str, tag_dec: str | None, activity: Activity | None) -> Person | None:
    candidates = {_rfid_code(tag_code), _rfid_code(tag_dec)}
    candidates.discard("")
    if not candidates:
        return None
    query = db.query(Person).filter(Person.is_active.is_(True), Person.rfid_code.isnot(None))
    if activity is not None and activity.business_id is not None:
        query = query.filter(Person.business_id == activity.business_id)
    for person in query.all():
        if _rfid_code(person.rfid_code) in candidates:
            return person
    return None


def _is_consecutive_duplicate_scan(db: Session, *, person: Person | None, activity: Activity | None) -> bool:
    if person is None or activity is None:
        return False
    latest = (
        db.query(RfidScanEvent)
        .filter(RfidScanEvent.person_id == person.id, RfidScanEvent.activity_id.isnot(None))
        .order_by(RfidScanEvent.scan_time.desc(), RfidScanEvent.id.desc())
        .first()
    )
    return latest is not None and latest.activity_id == activity.id


def _event_status_for(db: Session, *, person: Person | None, activity: Activity | None) -> tuple[str, str | None]:
    if person is None:
        return STATUS_UNKNOWN_PERSON, "RFID-brickan ar inte kopplad till en person."
    if activity is None:
        return STATUS_UNKNOWN_ACTIVITY, "RFID-modulen ar inte kopplad till en aktivitet."
    latest = (
        db.query(RfidScanEvent)
        .filter(RfidScanEvent.person_id == person.id, RfidScanEvent.activity_id.isnot(None))
        .order_by(RfidScanEvent.scan_time.desc(), RfidScanEvent.id.desc())
        .first()
    )
    if latest is not None and latest.activity_id == activity.id:
        return STATUS_DUPLICATE_IGNORED, "Samma person stämplade samma aktivitet två gånger i rad."
    return STATUS_PENDING, None


def _serialize_event(event: RfidScanEvent, *, person: Person | None = None, activity: Activity | None = None) -> dict:
    person = person if person is not None else event.person
    activity = activity if activity is not None else event.activity
    local = _local_time(event.scan_time)
    return {
        "id": event.id,
        "business_id": event.business_id,
        "device_id": event.device_identifier,
        "module_name": event.module_name,
        "tag_code": event.tag_code,
        "tag_dec": event.tag_dec,
        "scan_count": event.scan_count,
        "person_id": event.person_id,
        "person_name": person.name if person is not None else None,
        "activity_id": event.activity_id,
        "activity_label": activity.label if activity is not None else None,
        "activity_code": activity.code if activity is not None else None,
        "scan_time": event.scan_time.isoformat() if event.scan_time else None,
        "local_date": local.date().isoformat(),
        "local_time": local.strftime("%H:%M"),
        "hour": int(event.schedule_hour if event.schedule_hour is not None else local.hour),
        "minute": int(event.schedule_minute if event.schedule_minute is not None else local.minute),
        "status": event.status,
        "status_reason": event.status_reason,
        "applied_at": event.applied_at.isoformat() if event.applied_at else None,
        "ignored_at": event.ignored_at.isoformat() if event.ignored_at else None,
        "schedule_year": event.schedule_year,
        "schedule_week": event.schedule_week,
        "schedule_weekday": event.schedule_weekday,
    }


@router.post("/scans", status_code=status.HTTP_201_CREATED)
def receive_rfid_scan(
    payload: RfidScanIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    _assert_device_token(request)
    module_name = payload.module_name.strip()
    if not module_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="module_name kravs")
    tag_code = _rfid_code(payload.tag_hex) or _rfid_code(payload.tag_dec)
    if not tag_code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="tag_hex eller tag_dec kravs")

    seen_at = _now_utc()
    device_identifier = (payload.device_id or module_name).strip()
    activity = _activity_for_module(db, module_name)
    device = _upsert_device(
        db,
        device_identifier=device_identifier,
        module_name=module_name,
        activity=activity,
        seen_at=seen_at,
    )
    person = _person_for_tag(db, tag_code, payload.tag_dec, activity)
    if _is_consecutive_duplicate_scan(db, person=person, activity=activity):
        db.commit()
        response.status_code = status.HTTP_200_OK
        return {
            "event": None,
            "registered": False,
            "duplicate": True,
            "status": "duplicate_dropped",
            "status_reason": "Samma person stamplade samma aktivitet tva ganger i rad.",
        }
    event_status, status_reason = _event_status_for(db, person=person, activity=activity)
    schedule_year, schedule_week, schedule_weekday, schedule_hour, schedule_minute = _schedule_parts(seen_at)
    business_id = (
        activity.business_id
        if activity is not None
        else person.business_id if person is not None else device.business_id
    )
    event = RfidScanEvent(
        business_id=business_id,
        device_id=device.id,
        device_identifier=device.device_id,
        module_name=module_name,
        tag_code=tag_code,
        tag_dec=_rfid_code(payload.tag_dec) or None,
        scan_count=payload.scan_count,
        person_id=person.id if person is not None else None,
        activity_id=activity.id if activity is not None else None,
        scan_time=seen_at,
        status=event_status,
        status_reason=status_reason,
        schedule_year=schedule_year,
        schedule_week=schedule_week,
        schedule_weekday=schedule_weekday,
        schedule_hour=schedule_hour,
        schedule_minute=schedule_minute,
    )
    db.add(event)
    db.flush()
    audit_log(
        db,
        entity_type="rfid_scan_event",
        entity_id=event.id,
        action="receive",
        old_value=None,
        new_value=_serialize_event(event, person=person, activity=activity),
        user_id=None,
        business_id=event.business_id,
    )
    db.commit()
    db.refresh(event)
    return {"event": _serialize_event(event)}


def _event_query_for_user(db: Session, user: User):
    query = db.query(RfidScanEvent)
    scoped_business_id = visible_business_id(db, user)
    if scoped_business_id is not None:
        query = query.filter(RfidScanEvent.business_id == scoped_business_id)
    return query


@router.get("/events")
def list_rfid_events(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    area_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    selected_date = _schedule_date(year, week, weekday)
    start = datetime.combine(selected_date, datetime_time.min, LOCAL_TZ).astimezone(timezone.utc)
    end = datetime.combine(selected_date, datetime_time.max, LOCAL_TZ).astimezone(timezone.utc)
    query = _event_query_for_user(db, user).filter(
        RfidScanEvent.scan_time >= start,
        RfidScanEvent.scan_time <= end,
    )
    if area_id is not None:
        query = (
            query.outerjoin(Person, Person.id == RfidScanEvent.person_id)
            .outerjoin(Activity, Activity.id == RfidScanEvent.activity_id)
            .filter(or_(Person.home_area_id == area_id, Activity.area_id == area_id))
        )
    events = query.order_by(RfidScanEvent.scan_time.asc(), RfidScanEvent.id.asc()).all()
    return {
        "date": selected_date.isoformat(),
        "events": [_serialize_event(event) for event in events],
    }


def _get_event_for_update(db: Session, event_id: int, user: User) -> RfidScanEvent:
    event = _event_query_for_user(db, user).filter(RfidScanEvent.id == event_id).first()
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="RFID-händelse hittades inte")
    return event


@router.post("/events/{event_id}/ignore")
def ignore_rfid_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
) -> dict:
    event = _get_event_for_update(db, event_id, user)
    if event.status == STATUS_APPLIED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="RFID-händelsen är redan applicerad")
    old = _serialize_event(event)
    if event.status != STATUS_DUPLICATE_IGNORED:
        event.status = STATUS_IGNORED
        event.status_reason = "Ignorerad i Bemanning."
        event.ignored_at = _now_utc()
        event.ignored_by = user.id
    db.flush()
    audit_log(
        db,
        entity_type="rfid_scan_event",
        entity_id=event.id,
        action="ignore",
        old_value=old,
        new_value=_serialize_event(event),
        user_id=user.id,
        business_id=event.business_id,
    )
    db.commit()
    db.refresh(event)
    return {"event": _serialize_event(event)}


def _implicit_segment(person_id: int, hour: int, minute_start: int, minute_end: int) -> dict:
    return {
        "person_id": person_id,
        "hour": hour,
        "minute_start": minute_start,
        "minute_end": minute_end,
        "activity_id": None,
        "loan_area_id": None,
        "remark": None,
        "empty_override": False,
    }


def _segment_from_cell(cell: ScheduleCell, minute_start: int, minute_end: int) -> dict:
    return {
        "person_id": cell.person_id,
        "hour": cell.hour,
        "minute_start": minute_start,
        "minute_end": minute_end,
        "activity_id": cell.activity_id,
        "loan_area_id": cell.loan_area_id,
        "remark": cell.remark,
        "empty_override": cell.empty_override,
    }


def _rfid_schedule_segments(
    *,
    person_id: int,
    hour: int,
    minute: int,
    activity_id: int,
    current: list[ScheduleCell],
) -> list[dict]:
    if minute <= 0:
        return [{
            "person_id": person_id,
            "hour": hour,
            "minute_start": 0,
            "minute_end": 60,
            "activity_id": activity_id,
            "loan_area_id": None,
            "remark": None,
            "empty_override": False,
        }]
    before: list[dict] = []
    cursor = 0
    for cell in sorted(current, key=lambda item: (item.minute_start, item.minute_end)):
        start = max(0, int(cell.minute_start))
        end = min(60, int(cell.minute_end))
        if end <= cursor or start >= minute:
            continue
        if start > cursor and cursor < minute:
            before.append(_implicit_segment(person_id, hour, cursor, min(start, minute)))
        clipped_start = max(start, cursor)
        clipped_end = min(end, minute)
        if clipped_end > clipped_start:
            before.append(_segment_from_cell(cell, clipped_start, clipped_end))
        cursor = max(cursor, end)
        if cursor >= minute:
            break
    if cursor < minute:
        before.append(_implicit_segment(person_id, hour, cursor, minute))
    if len(before) > 3:
        before = [_implicit_segment(person_id, hour, 0, minute)]
    return [
        *before,
        {
            "person_id": person_id,
            "hour": hour,
            "minute_start": minute,
            "minute_end": 60,
            "activity_id": activity_id,
            "loan_area_id": None,
            "empty_override": False,
        },
    ]


@router.post("/events/{event_id}/apply")
def apply_rfid_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
) -> dict:
    event = _get_event_for_update(db, event_id, user)
    if event.status == STATUS_APPLIED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="RFID-händelsen är redan applicerad")
    if event.status == STATUS_DUPLICATE_IGNORED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Dubblettscanningar appliceras inte")
    if event.person_id is None or event.activity_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=event.status_reason or "RFID-händelsen kan inte appliceras")

    person = scoped_get(db, Person, event.person_id, user, detail="Person hittades inte")
    activity = scoped_get(db, Activity, event.activity_id, user, detail="Aktivitet hittades inte")
    if person.business_id != activity.business_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och aktivitet tillhör olika verksamheter")

    local = _local_time(event.scan_time)
    if local.hour not in HOURS:
        old = _serialize_event(event)
        event.status = STATUS_CONFLICT
        event.status_reason = "RFID-scanningen ligger utanfor Bemanningens timmar."
        db.flush()
        audit_log(
            db,
            entity_type="rfid_scan_event",
            entity_id=event.id,
            action="apply_conflict",
            old_value=old,
            new_value=_serialize_event(event),
            user_id=user.id,
            business_id=event.business_id,
        )
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=event.status_reason)

    iso = local.date().isocalendar()
    current = _load_hour_segments(
        db,
        year=iso.year,
        week=iso.week,
        weekday=iso.weekday,
        hour=local.hour,
        person_id=person.id,
        lock=True,
    )
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    assert_can_modify_schedule_cells(current, user, owner_lock_enabled)
    old_event = _serialize_event(event)
    old_cells = [(cell, _cell_audit_dict(cell)) for cell in current]
    for cell, old_cell in old_cells:
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=cell.id,
            action="rfid_apply_delete",
            old_value=old_cell,
            new_value=None,
            user_id=user.id,
            business_id=person.business_id,
        )
        db.delete(cell)
    if old_cells:
        db.flush()

    created: list[ScheduleCell] = []
    for segment in _rfid_schedule_segments(
        person_id=person.id,
        hour=local.hour,
        minute=local.minute,
        activity_id=activity.id,
        current=current,
    ):
        cell = ScheduleCell(
            year=iso.year,
            week=iso.week,
            weekday=iso.weekday,
            hour=segment["hour"],
            minute_start=segment["minute_start"],
            minute_end=segment["minute_end"],
            person_id=person.id,
            activity_id=segment["activity_id"],
            loan_area_id=segment["loan_area_id"],
            remark=segment.get("remark"),
            empty_override=segment["empty_override"],
            version=1,
            updated_by=user.id,
        )
        db.add(cell)
        created.append(cell)
    db.flush()
    for cell in created:
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=cell.id,
            action="rfid_apply_create",
            old_value=None,
            new_value=_cell_audit_dict(cell),
            user_id=user.id,
            business_id=person.business_id,
        )

    event.status = STATUS_APPLIED
    event.status_reason = None
    event.applied_at = _now_utc()
    event.applied_by = user.id
    event.schedule_year = iso.year
    event.schedule_week = iso.week
    event.schedule_weekday = iso.weekday
    event.schedule_hour = local.hour
    event.schedule_minute = local.minute
    db.flush()
    audit_log(
        db,
        entity_type="rfid_scan_event",
        entity_id=event.id,
        action="apply",
        old_value=old_event,
        new_value=_serialize_event(event),
        user_id=user.id,
        business_id=event.business_id,
    )
    db.commit()
    for cell in created:
        db.refresh(cell)
    db.refresh(event)
    return {
        "event": _serialize_event(event),
        "segments": [_cell_to_dict(cell) for cell in sorted(created, key=lambda item: (item.minute_start, item.minute_end))],
    }
