from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..business_scope import assert_scoped_object, scoped_get, visible_business_id
from ..deps import get_db, require_view_access
from ..home_activity import build_home_activity_resolver, person_out_with_home_activity
from ..models import Activity, Area, Business, Person, ScheduleCell, StaffingCalculatorProfile, User
from ..schedule_locks import assert_can_modify_schedule_cells, foreign_schedule_cell_lock_applies
from ..staffing_calculator_service import (
    calculate_staffing_automatic,
    empty_staffing_calculator_profile,
    normalize_staffing_calculator_profile,
    schedule_activity_capacity,
    schedule_activity_capacity_cell,
    schedule_productivity_summary,
    staffing_calculator_profile_count,
    staffing_process_options,
)
from ..template_service import get_template_hours_for_date, get_template_hours_map_for_dates
from ..user_access import is_super_user
from ..schemas import (
    BulkCellRequest,
    CellOut,
    CellUpdate,
    PersonOut,
    PresenceBusinessGroup,
    PresenceOut,
    PresenceRow,
    RestoreHoursRequest,
    ScheduleOut,
    SplitCellRequest,
    SummaryRow,
)

router = APIRouter(prefix="/api/schedule", tags=["schedule"])

HOURS = list(range(6, 24))           # 06..23 = 18 timslots
HOURS_PER_PERSON_DAY = 8             # för persons_equiv = hours / 8
FULL_SEGMENT = (0, 60)
DEFAULT_SPLIT_MINUTE = 30
MIN_SPLIT_PARTS = 2
MAX_SPLIT_PARTS = 4


class StaffingCalculatorProfileUpdate(BaseModel):
    profile: dict


class StaffingCalculatorProfileImport(BaseModel):
    user_id: int


def _iso(value) -> str:
    return value.isoformat() if value is not None else ""


def _visible_schedule_persons(
    db: Session,
    user: User,
    area_id: int | None = None,
    business_id: int | None = None,
    *,
    year: int | None = None,
    week: int | None = None,
    weekdays: list[int] | None = None,
) -> tuple[list[Person], int | None]:
    scoped_business_id = visible_business_id(db, user, business_id)
    persons_q = select(Person).where(Person.is_active.is_(True))
    if scoped_business_id is not None:
        persons_q = persons_q.where(Person.business_id == scoped_business_id)
    if area_id is not None:
        area = scoped_get(db, Area, area_id, user, detail="Område hittades inte")
        if area.is_active is not True:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
        assigned_person_ids = None
        if year is not None and week is not None and weekdays:
            assigned_person_ids = (
                select(ScheduleCell.person_id)
                .outerjoin(Activity, ScheduleCell.activity_id == Activity.id)
                .where(
                    ScheduleCell.year == year,
                    ScheduleCell.week == week,
                    ScheduleCell.weekday.in_(weekdays),
                    or_(Activity.area_id == area_id, ScheduleCell.loan_area_id == area_id),
                )
                .distinct()
            )
        if assigned_person_ids is not None:
            persons_q = persons_q.where(or_(Person.home_area_id == area_id, Person.id.in_(assigned_person_ids)))
        else:
            persons_q = persons_q.where(Person.home_area_id == area_id)
    persons_q = persons_q.order_by(Person.sort_order, Person.name)
    return db.execute(persons_q).scalars().all(), scoped_business_id


def _schedule_revision_key_from_parts(
    *,
    person_count: int,
    person_latest,
    cell_count: int,
    cell_latest,
    version_sum: int,
) -> str:
    return (
        f"p:{person_count}:{_iso(person_latest)}|"
        f"c:{cell_count}:{_iso(cell_latest)}:{int(version_sum or 0)}"
    )


def _schedule_revision_key(persons: list[Person], cells: list[ScheduleCell]) -> str:
    return _schedule_revision_key_from_parts(
        person_count=len(persons),
        person_latest=max((person.updated_at for person in persons if person.updated_at is not None), default=None),
        cell_count=len(cells),
        cell_latest=max((cell.updated_at for cell in cells if cell.updated_at is not None), default=None),
        version_sum=sum(int(cell.version or 0) for cell in cells),
    )


def _schedule_revision_for_persons(
    db: Session,
    *,
    year: int,
    week: int,
    weekdays: list[int],
    persons: list[Person],
) -> str:
    person_ids = [person.id for person in persons]
    if not person_ids:
        return _schedule_revision_key_from_parts(
            person_count=0,
            person_latest=None,
            cell_count=0,
            cell_latest=None,
            version_sum=0,
        )
    cell_count, cell_latest, version_sum = (
        db.query(
            func.count(ScheduleCell.id),
            func.max(ScheduleCell.updated_at),
            func.coalesce(func.sum(ScheduleCell.version), 0),
        )
        .filter(
            ScheduleCell.year == year,
            ScheduleCell.week == week,
            ScheduleCell.weekday.in_(weekdays),
            ScheduleCell.person_id.in_(person_ids),
        )
        .one()
    )
    return _schedule_revision_key_from_parts(
        person_count=len(persons),
        person_latest=max((person.updated_at for person in persons if person.updated_at is not None), default=None),
        cell_count=int(cell_count or 0),
        cell_latest=cell_latest,
        version_sum=int(version_sum or 0),
    )


def _covered_intervals(cells: list[ScheduleCell]) -> list[tuple[int, int]]:
    intervals = sorted(
        (
            max(0, int(cell.minute_start)),
            min(60, int(cell.minute_end)),
        )
        for cell in cells
        if cell.activity_id is not None or cell.empty_override
    )
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _uncovered_intervals(covered: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = 0
    for start, end in covered:
        if start > cursor:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < 60:
        result.append((cursor, 60))
    return result


def _effective_activity_ids_for_hour(
    cells: list[ScheduleCell],
    *,
    is_scheduled: bool,
    home_activity_id: int | None,
) -> list[int]:
    intervals: list[tuple[int, int, int]] = []
    sorted_cells = sorted(cells, key=lambda cell: (cell.minute_start, cell.minute_end))
    for cell in sorted_cells:
        if cell.activity_id is not None:
            intervals.append((int(cell.minute_start), int(cell.minute_end), int(cell.activity_id)))

    if is_scheduled and home_activity_id is not None:
        for start, end in _uncovered_intervals(_covered_intervals(sorted_cells)):
            intervals.append((start, end, int(home_activity_id)))

    return [activity_id for _start, _end, activity_id in sorted(intervals)]


def _unique_activity_ids(activity_ids: list[int]) -> list[int]:
    seen: set[int] = set()
    unique: list[int] = []
    for activity_id in activity_ids:
        if activity_id in seen:
            continue
        seen.add(activity_id)
        unique.append(activity_id)
    return unique


def _has_activity_category(activity_ids: list[int], activities_by_id: dict[int, Activity], category: str) -> bool:
    return any(
        (activity := activities_by_id.get(activity_id)) is not None and activity.category == category
        for activity_id in activity_ids
    )


def _has_non_absence_activity(activity_ids: list[int], activities_by_id: dict[int, Activity]) -> bool:
    return any(
        (activity := activities_by_id.get(activity_id)) is not None and activity.category != "absence"
        for activity_id in activity_ids
    )


def _presence_current_activity(
    activity_ids: list[int],
    activities_by_id: dict[int, Activity],
) -> tuple[int | None, str, str | None]:
    unique_ids = _unique_activity_ids([activity_id for activity_id in activity_ids if activity_id in activities_by_id])
    if not unique_ids:
        return None, "Ingen", None
    if len(unique_ids) == 1:
        activity = activities_by_id[unique_ids[0]]
        return activity.id, activity.label, activity.category
    labels = [activities_by_id[activity_id].label for activity_id in unique_ids]
    return None, "Blandat: " + " / ".join(labels), "mixed"


def _presence_business_sort_key(group: PresenceBusinessGroup, businesses_by_id: dict[int, Business]) -> tuple[int, str, int]:
    if group.business_id is None:
        return (999999, group.business_name.lower(), 999999)
    business = businesses_by_id.get(group.business_id)
    return (
        int(business.sort_order if business is not None else 999999),
        (business.name if business is not None else group.business_name).lower(),
        int(group.business_id),
    )


def _presence_business_group(
    business_id: int | None,
    businesses_by_id: dict[int, Business],
) -> PresenceBusinessGroup:
    business = businesses_by_id.get(business_id) if business_id is not None else None
    if business is None:
        return PresenceBusinessGroup(
            business_id=business_id,
            business_code="",
            business_name="Utan verksamhet",
            rows=[],
        )
    return PresenceBusinessGroup(
        business_id=business.id,
        business_code=business.code,
        business_name=business.name,
        rows=[],
    )

def _cell_to_dict(cell: ScheduleCell) -> dict:
    return {
        "person_id": cell.person_id,
        "hour": cell.hour,
        "minute_start": cell.minute_start,
        "minute_end": cell.minute_end,
        "activity_id": cell.activity_id,
        "loan_area_id": cell.loan_area_id,
        "empty_override": cell.empty_override,
        "version": cell.version,
        "updated_at": cell.updated_at.isoformat() if cell.updated_at else None,
        "updated_by": cell.updated_by,
    }


def _empty_segment_dict(person_id: int, hour: int, minute_start: int, minute_end: int) -> dict:
    return {
        "person_id": person_id,
        "hour": hour,
        "minute_start": minute_start,
        "minute_end": minute_end,
        "activity_id": None,
        "loan_area_id": None,
        "empty_override": False,
        "version": 0,
        "updated_at": None,
        "updated_by": None,
    }


def _schedule_date(year: int, week: int, weekday: int) -> date:
    try:
        return date.fromisocalendar(year, week, weekday)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ogiltig ISO-vecka eller dag")


def _serialize_segments(cells: list[ScheduleCell]) -> list[dict]:
    return [_cell_to_dict(cell) for cell in sorted(cells, key=lambda c: (c.minute_start, c.minute_end))]


def _load_hour_segments(
    db: Session,
    *,
    year: int,
    week: int,
    weekday: int,
    hour: int,
    person_id: int,
    lock: bool = False,
) -> list[ScheduleCell]:
    query = select(ScheduleCell).where(
        ScheduleCell.year == year,
        ScheduleCell.week == week,
        ScheduleCell.weekday == weekday,
        ScheduleCell.hour == hour,
        ScheduleCell.person_id == person_id,
    )
    if lock:
        query = query.with_for_update()
    return list(db.execute(query).scalars().all())


def _segment_signature(cells: list[ScheduleCell]) -> list[tuple[int, int, int]]:
    return sorted((cell.minute_start, cell.minute_end, cell.version) for cell in cells)


def _expected_signature(segments: list) -> list[tuple[int, int, int]]:
    return sorted((item.minute_start, item.minute_end, item.expected_version) for item in segments)


def _split_ranges(split_minute: int = DEFAULT_SPLIT_MINUTE) -> tuple[tuple[int, int], ...]:
    minute = int(split_minute)
    return ((0, minute), (minute, 60))


def _is_valid_minute_range(minute_start: int, minute_end: int) -> bool:
    return (
        isinstance(minute_start, int)
        and isinstance(minute_end, int)
        and 0 <= minute_start < minute_end <= 60
    )


def _validate_split_minute(split_minute: int) -> int:
    minute = int(split_minute)
    if minute <= 0 or minute >= 60:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Forsta delen maste vara 1-59 minuter.",
        )
    return minute


def _normalize_split_ranges(ranges: list | tuple) -> tuple[tuple[int, int], ...]:
    ordered = sorted((int(item.minute_start), int(item.minute_end)) for item in ranges)
    if len(set(ordered)) != len(ordered) or not _is_split_ranges(set(ordered)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Delningen maste ha 2-4 sammanhangande delar som tacker 0-60 minuter.",
        )
    return tuple(ordered)


def _split_ranges_from_payload(payload: SplitCellRequest) -> tuple[tuple[int, int], ...]:
    if payload.split_segments:
        return _normalize_split_ranges(payload.split_segments)
    split_minute = _validate_split_minute(payload.split_minute)
    return _split_ranges(split_minute)


def _is_split_ranges(ranges: set[tuple[int, int]]) -> bool:
    if len(ranges) < MIN_SPLIT_PARTS or len(ranges) > MAX_SPLIT_PARTS:
        return False
    ordered = sorted(ranges)
    if ordered[0][0] != 0 or ordered[-1][1] != 60:
        return False
    return all(
        _is_valid_minute_range(start, end)
        and (index == 0 or ordered[index - 1][1] == start)
        for index, (start, end) in enumerate(ordered)
    )


def _split_ranges_for_range(range_key: tuple[int, int]) -> tuple[tuple[int, int], ...] | None:
    minute_start, minute_end = range_key
    if minute_start == 0 and 0 < minute_end < 60:
        return _split_ranges(minute_end)
    if minute_end == 60 and 0 < minute_start < 60:
        return _split_ranges(minute_start)
    return None


def _split_ranges_for_items(items: list) -> tuple[tuple[int, int], ...] | None:
    ranges = {(int(item.minute_start), int(item.minute_end)) for item in items}
    if _is_split_ranges(ranges):
        return tuple(sorted(ranges))
    partials = [range_key for range_key in ranges if range_key != FULL_SEGMENT]
    if len(partials) == 1:
        return _split_ranges_for_range(partials[0])
    return None


def _is_split_cells(cells: list[ScheduleCell]) -> bool:
    return _is_split_ranges({(int(cell.minute_start), int(cell.minute_end)) for cell in cells})


def _validate_restore_segments(item) -> None:
    ranges: set[tuple[int, int]] = set()
    for segment in item.segments:
        _validate_segment(item.hour, segment.minute_start, segment.minute_end)
        range_key = (segment.minute_start, segment.minute_end)
        if range_key in ranges:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Duplicerade segment i samma timme.")
        ranges.add(range_key)

    if not ranges:
        return
    if ranges == {FULL_SEGMENT} or _is_split_ranges(ranges):
        return
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail="Undo kan bara aterstalla en hel timme, 2-4 sammanhangande delar eller en tom implicit timme.",
    )


def _conflict_response(*, person_id: int, hour: int, current: list[ScheduleCell]):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "version_conflict",
            "segments": _serialize_segments(current),
            "current": _serialize_segments(current) or [_empty_segment_dict(person_id, hour, 0, 60)],
        },
    )


def _hours_from_minutes(total_minutes: int) -> float:
    return round(float(total_minutes) / 60.0, 2)


def _is_scheduled_hour(db: Session, person_id: int, year: int, week: int, weekday: int, hour: int) -> bool:
    template = get_template_hours_for_date(db, person_id, _schedule_date(year, week, weekday))
    return bool(template and hour in template)


def _empty_override_for(
    db: Session,
    *,
    person_id: int,
    year: int,
    week: int,
    weekday: int,
    hour: int,
    activity_id: int | None,
) -> bool:
    return activity_id is None and _is_scheduled_hour(db, person_id, year, week, weekday, hour)


def _empty_override_for_template(
    template_hours: set[int] | None,
    *,
    hour: int,
    activity_id: int | None,
) -> bool:
    return activity_id is None and bool(template_hours and hour in template_hours)


def _bulk_conflict_dict(item, current_segments: list[ScheduleCell]) -> dict:
    return {
        "person_id": item.person_id,
        "hour": item.hour,
        "minute_start": item.minute_start,
        "minute_end": item.minute_end,
        "current": _serialize_segments(current_segments)
        or [_empty_segment_dict(item.person_id, item.hour, item.minute_start, item.minute_end)],
    }


def _validate_segment(hour: int, minute_start: int, minute_end: int) -> None:
    if hour not in HOURS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Timme måste vara {HOURS[0]}-{HOURS[-1]}")
    if not _is_valid_minute_range(minute_start, minute_end):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ogiltigt segment. Minuter maste ligga inom 0-60 och starta fore slut.")


def _calculator_profile_display_name(user: User) -> str:
    return str(getattr(user, "display_name", None) or getattr(user, "username", None) or getattr(user, "id", "")).strip()


def _accessible_calculator_profile_user_query(db: Session, user: User):
    query = db.query(User).filter(User.is_active.is_(True))
    if not is_super_user(user):
        business_id = getattr(user, "business_id", None)
        if business_id is not None:
            query = query.filter(User.business_id == business_id)
    return query


def _assert_calculator_profile_source_allowed(db: Session, user: User, source_user_id: int) -> User:
    source_user = _accessible_calculator_profile_user_query(db, user).filter(User.id == source_user_id).first()
    if source_user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Anvandarens bemanningskalkyler hittades inte")
    return source_user


def _user_calculator_profile(db: Session | object, user: User) -> dict:
    user_id = getattr(user, "id", None)
    if user_id is None or not hasattr(db, "query"):
        return empty_staffing_calculator_profile()
    try:
        row = db.query(StaffingCalculatorProfile).filter(StaffingCalculatorProfile.user_id == user_id).first()
    except Exception:
        return empty_staffing_calculator_profile()
    return normalize_staffing_calculator_profile(getattr(row, "profile", None) if row is not None else None)


def _calculator_profile_users(db: Session, user: User) -> list[dict]:
    users = _accessible_calculator_profile_user_query(db, user).order_by(func.lower(User.username)).all()
    user_ids = [int(item.id) for item in users if getattr(item, "id", None) is not None]
    rows = []
    if user_ids:
        rows = db.query(StaffingCalculatorProfile).filter(StaffingCalculatorProfile.user_id.in_(user_ids)).all()
    profile_by_user = {int(row.user_id): normalize_staffing_calculator_profile(row.profile) for row in rows}
    result = []
    for item in users:
        item_id = int(item.id)
        profile = profile_by_user.get(item_id, empty_staffing_calculator_profile())
        count = staffing_calculator_profile_count(profile)
        result.append({
            "id": item_id,
            "username": str(item.username),
            "name": _calculator_profile_display_name(item),
            "is_current": item_id == getattr(user, "id", None),
            "has_calculators": count > 0,
            "calculator_count": count,
        })
    return result


def _calculator_profile_response(db: Session, user: User) -> dict:
    return {
        "profile": _user_calculator_profile(db, user),
        "users": _calculator_profile_users(db, user),
        "process_options": staffing_process_options(db, user),
    }


def _set_user_calculator_profile(db: Session, user: User, profile: object) -> dict:
    user_id = getattr(user, "id", None)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Anvandare saknas")
    normalized = normalize_staffing_calculator_profile(profile)
    row = db.query(StaffingCalculatorProfile).filter(StaffingCalculatorProfile.user_id == user_id).first()
    if row is None:
        row = StaffingCalculatorProfile(user_id=user_id, profile=normalized)
        db.add(row)
    else:
        row.profile = normalized
    db.flush()
    return normalized


@router.get("/calculator-profile")
def get_calculator_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    return _calculator_profile_response(db, user)


@router.put("/calculator-profile")
def update_calculator_profile(
    payload: StaffingCalculatorProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    before = _user_calculator_profile(db, user)
    after = _set_user_calculator_profile(db, user, payload.profile)
    if before != after:
        audit_log(
            db,
            entity_type="staffing_calculator_profile",
            entity_id=int(getattr(user, "id", 0) or 0),
            action="update_staffing_calculator_profile",
            old_value={"calculator_count": staffing_calculator_profile_count(before)},
            new_value={"calculator_count": staffing_calculator_profile_count(after)},
            user_id=getattr(user, "id", None),
            business_id=getattr(user, "business_id", None),
        )
    db.commit()
    return _calculator_profile_response(db, user)


@router.post("/calculator-profile/import")
def import_calculator_profile(
    payload: StaffingCalculatorProfileImport,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    source_user = _assert_calculator_profile_source_allowed(db, user, payload.user_id)
    source_profile = _user_calculator_profile(db, source_user)
    if staffing_calculator_profile_count(source_profile) <= 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Anvandaren har inga sparade bemanningskalkyler")
    before = _user_calculator_profile(db, user)
    after = _set_user_calculator_profile(db, user, source_profile)
    audit_log(
        db,
        entity_type="staffing_calculator_profile",
        entity_id=int(getattr(user, "id", 0) or 0),
        action="import_staffing_calculator_profile",
        old_value={"calculator_count": staffing_calculator_profile_count(before)},
        new_value={
            "calculator_count": staffing_calculator_profile_count(after),
            "source_user_id": getattr(source_user, "id", None),
        },
        user_id=getattr(user, "id", None),
        business_id=getattr(user, "business_id", None),
    )
    db.commit()
    return _calculator_profile_response(db, user)


@router.get("/calculator/automatic")
def get_automatic_calculator_results(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    return calculate_staffing_automatic(
        db,
        user,
        _user_calculator_profile(db, user),
        year=year,
        week=week,
        weekday=weekday,
    )


@router.get("/activity-capacity")
def get_activity_capacity(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    return schedule_activity_capacity(
        db,
        user,
        year=year,
        week=week,
        weekday=weekday,
    )


@router.get("/activity-capacity/cell")
def get_activity_capacity_cell(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    person_id: int = Query(..., ge=1),
    activity_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    return schedule_activity_capacity_cell(
        db,
        user,
        year=year,
        week=week,
        weekday=weekday,
        person_id=person_id,
        activity_id=activity_id,
    )


@router.get("/productivity-summary")
def get_schedule_productivity_summary(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
    _productivity_user: User = Depends(require_view_access("productivity", "view")),
) -> dict:
    return schedule_productivity_summary(
        db,
        user,
        year=year,
        week=week,
        weekday=weekday,
    )


@router.get("/revision")
def get_schedule_revision(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    area_id: int | None = Query(None),
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict[str, str | int | None]:
    if not isinstance(area_id, int):
        area_id = None
    if not isinstance(business_id, int):
        business_id = None
    persons, _scoped_business_id = _visible_schedule_persons(
        db,
        user,
        area_id,
        business_id,
        year=year,
        week=week,
        weekdays=[weekday],
    )
    return {
        "year": year,
        "week": week,
        "weekday": weekday,
        "area_id": area_id,
        "revision_key": _schedule_revision_for_persons(
            db,
            year=year,
            week=week,
            weekdays=[weekday],
            persons=persons,
        ),
    }


@router.get("/presence", response_model=PresenceOut)
def get_schedule_presence(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    hour: int = Query(..., ge=0, le=23),
    area_id: int | None = Query(None),
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> PresenceOut:
    selected_date = _schedule_date(year, week, weekday)
    scoped_business_id = visible_business_id(db, user, business_id)

    persons_q = select(Person).where(Person.is_active.is_(True))
    if scoped_business_id is not None:
        persons_q = persons_q.where(Person.business_id == scoped_business_id)
    if area_id is not None:
        area = scoped_get(db, Area, area_id, user, detail="Område hittades inte")
        if area.is_active is not True:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
        if scoped_business_id is not None and area.business_id != scoped_business_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
        persons_q = persons_q.where(Person.home_area_id == area_id)
    persons_q = persons_q.order_by(Person.sort_order, Person.name)
    persons = db.execute(persons_q).scalars().all()
    person_ids = [person.id for person in persons]

    rest_hours = [candidate for candidate in HOURS if candidate >= hour]
    near_hours = [candidate for candidate in (hour, hour + 1) if candidate in HOURS]
    cells_by_person_hour: dict[tuple[int, int], list[ScheduleCell]] = defaultdict(list)
    if person_ids and rest_hours:
        rows = db.execute(
            select(ScheduleCell).where(
                ScheduleCell.year == year,
                ScheduleCell.week == week,
                ScheduleCell.weekday == weekday,
                ScheduleCell.person_id.in_(person_ids),
                ScheduleCell.hour.in_(rest_hours),
            )
        ).scalars().all()
        for cell in rows:
            cells_by_person_hour[(cell.person_id, cell.hour)].append(cell)

    activity_query = db.query(Activity)
    area_query = db.query(Area)
    business_query = db.query(Business)
    if scoped_business_id is not None:
        activity_query = activity_query.filter(Activity.business_id == scoped_business_id)
        area_query = area_query.filter(Area.business_id == scoped_business_id)
        business_query = business_query.filter(Business.id == scoped_business_id)
    activities = activity_query.all()
    areas = area_query.all()
    businesses = business_query.all()
    activities_by_id = {activity.id: activity for activity in activities}
    areas_by_id = {area.id: area for area in areas}
    businesses_by_id = {business.id: business for business in businesses}
    home_activity_for = build_home_activity_resolver(activities, areas)
    home_activity_by_person_id = {person.id: home_activity_for(person) for person in persons}
    template_hours_map = get_template_hours_map_for_dates(db, person_ids, [selected_date])

    groups_by_business_id: dict[int | None, PresenceBusinessGroup] = {}
    for person in persons:
        template_hours = template_hours_map.get((person.id, selected_date))
        home_activity_id = home_activity_by_person_id.get(person.id)

        effective_by_hour = {
            candidate: _effective_activity_ids_for_hour(
                cells_by_person_hour.get((person.id, candidate), []),
                is_scheduled=template_hours is not None and candidate in template_hours,
                home_activity_id=home_activity_id,
            )
            for candidate in set(rest_hours + near_hours)
        }
        has_non_absence_rest = any(
            _has_non_absence_activity(effective_by_hour.get(candidate, []), activities_by_id)
            for candidate in rest_hours
        )
        has_work_now_or_next = any(
            _has_activity_category(effective_by_hour.get(candidate, []), activities_by_id, "work")
            for candidate in near_hours
        )
        if not has_non_absence_rest or not has_work_now_or_next:
            continue

        current_activity_id, current_activity, current_category = _presence_current_activity(
            effective_by_hour.get(hour, []),
            activities_by_id,
        )
        group = groups_by_business_id.setdefault(
            person.business_id,
            _presence_business_group(person.business_id, businesses_by_id),
        )
        home_area = areas_by_id.get(person.home_area_id)
        group.rows.append(
            PresenceRow(
                person_id=person.id,
                name=person.name,
                home_area_id=person.home_area_id,
                home_area=home_area.name if home_area is not None else None,
                current_activity_id=current_activity_id,
                current_activity=current_activity,
                current_activity_category=current_category,
            )
        )

    groups = sorted(groups_by_business_id.values(), key=lambda group: _presence_business_sort_key(group, businesses_by_id))
    return PresenceOut(
        date=selected_date.isoformat(),
        year=year,
        week=week,
        weekday=weekday,
        hour=hour,
        generated_at=datetime.now(timezone.utc),
        area_id=area_id,
        groups=groups,
    )


@router.get("", response_model=ScheduleOut)
def get_schedule(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    area_id: int | None = Query(None),
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> ScheduleOut:
    selected_date = _schedule_date(year, week, weekday)
    persons, scoped_business_id = _visible_schedule_persons(
        db,
        user,
        area_id,
        business_id,
        year=year,
        week=week,
        weekdays=[weekday],
    )
    person_ids = [p.id for p in persons]

    cells: list[ScheduleCell] = []
    if person_ids:
        cells = (
            db.execute(
                select(ScheduleCell).where(
                    ScheduleCell.year == year,
                    ScheduleCell.week == week,
                    ScheduleCell.weekday == weekday,
                    ScheduleCell.person_id.in_(person_ids),
                )
            )
            .scalars()
            .all()
        )

    template_hours_map = get_template_hours_map_for_dates(db, person_ids, [selected_date])
    activity_query = db.query(Activity)
    area_query = db.query(Area)
    if scoped_business_id is not None:
        activity_query = activity_query.filter(Activity.business_id == scoped_business_id)
        area_query = area_query.filter(Area.business_id == scoped_business_id)
    home_activity_for = build_home_activity_resolver(activity_query.all(), area_query.all())
    home_activity_by_person_id = {p.id: home_activity_for(p) for p in persons}

    scheduled_hours: dict[int, list[int]] = {}
    scheduled_defaults: dict[int, dict[int, int]] = {}
    for p in persons:
        hrs = template_hours_map.get((p.id, selected_date))
        if hrs:
            sorted_hours = sorted(hrs)
            scheduled_hours[p.id] = sorted_hours
            home_activity_id = home_activity_by_person_id.get(p.id)
            if home_activity_id is not None:
                scheduled_defaults[p.id] = {hour: home_activity_id for hour in sorted_hours}

    return ScheduleOut(
        year=year,
        week=week,
        weekday=weekday,
        area_id=area_id,
        revision_key=_schedule_revision_key(persons, cells),
        persons=[person_out_with_home_activity(p, home_activity_by_person_id.get(p.id)) for p in persons],
        cells=[CellOut(**_cell_to_dict(c)) for c in sorted(cells, key=lambda c: (c.person_id, c.hour, c.minute_start))],
        scheduled_hours=scheduled_hours,
        scheduled_defaults=scheduled_defaults,
        lock_foreign_schedule_cells=foreign_schedule_cell_lock_applies(db, user),
    )


@router.put("/cell")
def update_cell(
    payload: CellUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
):
    _validate_segment(payload.hour, payload.minute_start, payload.minute_end)

    person = scoped_get(db, Person, payload.person_id, user, detail="Person hittades inte")
    activity = None
    if payload.activity_id is not None:
        activity = scoped_get(db, Activity, payload.activity_id, user, detail="Aktivitet hittades inte")
        if activity.business_id != person.business_id:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och aktivitet tillhör olika verksamheter")

    hour_segments = _load_hour_segments(
        db,
        year=payload.year,
        week=payload.week,
        weekday=payload.weekday,
        hour=payload.hour,
        person_id=payload.person_id,
        lock=True,
    )
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    matching = next(
        (
            cell
            for cell in hour_segments
            if cell.minute_start == payload.minute_start and cell.minute_end == payload.minute_end
        ),
        None,
    )

    current_version = matching.version if matching else 0
    if current_version != payload.expected_version:
        return _conflict_response(person_id=payload.person_id, hour=payload.hour, current=hour_segments)

    if matching is None and hour_segments:
        return _conflict_response(person_id=payload.person_id, hour=payload.hour, current=hour_segments)

    if matching is None:
        cell = ScheduleCell(
            year=payload.year,
            week=payload.week,
            weekday=payload.weekday,
            hour=payload.hour,
            minute_start=payload.minute_start,
            minute_end=payload.minute_end,
            person_id=payload.person_id,
            activity_id=payload.activity_id,
            loan_area_id=None,
            empty_override=_empty_override_for(
                db,
                person_id=payload.person_id,
                year=payload.year,
                week=payload.week,
                weekday=payload.weekday,
                hour=payload.hour,
                activity_id=payload.activity_id,
            ),
            version=1,
            updated_by=user.id,
        )
        db.add(cell)
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=cell.id,
            action="create",
            old_value=None,
            new_value=_cell_to_dict(cell),
            user_id=user.id,
            business_id=person.business_id,
        )
    else:
        cell = matching
        desired_empty_override = _empty_override_for(
            db,
            person_id=payload.person_id,
            year=payload.year,
            week=payload.week,
            weekday=payload.weekday,
            hour=payload.hour,
            activity_id=payload.activity_id,
        )
        if (
            cell.activity_id == payload.activity_id
            and cell.loan_area_id is None
            and cell.empty_override == desired_empty_override
        ):
            return {"cell": _cell_to_dict(cell)}
        assert_can_modify_schedule_cells([cell], user, owner_lock_enabled)
        old = _cell_to_dict(cell)
        cell.activity_id = payload.activity_id
        cell.loan_area_id = None
        cell.empty_override = desired_empty_override
        cell.version += 1
        cell.updated_by = user.id
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=cell.id,
            action="update",
            old_value=old,
            new_value=_cell_to_dict(cell),
            user_id=user.id,
            business_id=person.business_id,
        )

    db.commit()
    db.refresh(cell)
    return {"cell": _cell_to_dict(cell)}


@router.put("/cell/split")
def split_cell(
    payload: SplitCellRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
):
    if payload.hour not in HOURS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Timme måste vara {HOURS[0]}-{HOURS[-1]}")
    split_ranges = _split_ranges_from_payload(payload)
    person = scoped_get(db, Person, payload.person_id, user, detail="Person hittades inte")

    hour_segments = _load_hour_segments(
        db,
        year=payload.year,
        week=payload.week,
        weekday=payload.weekday,
        hour=payload.hour,
        person_id=payload.person_id,
        lock=True,
    )
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    if _segment_signature(hour_segments) != _expected_signature(payload.segments):
        return _conflict_response(person_id=payload.person_id, hour=payload.hour, current=hour_segments)

    if len(hour_segments) >= MIN_SPLIT_PARTS and _is_split_cells(hour_segments):
        assert_can_modify_schedule_cells(hour_segments, user, owner_lock_enabled)
        preferred = next(
            (
                cell
                for cell in hour_segments
                if cell.minute_start == payload.merge_minute_start
            ),
            None,
        )
        if preferred is None:
            preferred = next((cell for cell in hour_segments if cell.activity_id is not None), None) or hour_segments[0]
        other_segments = [cell for cell in hour_segments if cell.id != preferred.id]

        old_preferred = _cell_to_dict(preferred)
        old_others = [(other, _cell_to_dict(other)) for other in other_segments]
        merged_loan_area_id = preferred.loan_area_id
        if preferred.activity_id is None:
            merged_loan_area_id = preferred.loan_area_id or next(
                (cell.loan_area_id for cell in other_segments if cell.loan_area_id is not None),
                None,
            )
        merged_empty_override = any(cell.empty_override for cell in hour_segments)

        for other, old_other in old_others:
            audit_log(
                db,
                entity_type="schedule_cell",
                entity_id=other.id,
                action="split_merge_delete",
                old_value=old_other,
                new_value=None,
                user_id=user.id,
            )
            db.delete(other)
        db.flush()

        preferred.minute_start = 0
        preferred.minute_end = 60
        preferred.loan_area_id = None if preferred.activity_id is not None else merged_loan_area_id
        preferred.empty_override = merged_empty_override
        preferred.version += 1
        preferred.updated_by = user.id
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=preferred.id,
            action="split_merge_update",
            old_value=old_preferred,
            new_value=_cell_to_dict(preferred),
            user_id=user.id,
        )
        db.commit()
        db.refresh(preferred)
        return {"segments": [_cell_to_dict(preferred)]}

    if len(hour_segments) > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Kan bara dela en tom timme eller en hel timcell.")

    if not hour_segments:
        created: list[ScheduleCell] = []
        for minute_start, minute_end in split_ranges:
            cell = ScheduleCell(
                year=payload.year,
                week=payload.week,
                weekday=payload.weekday,
                hour=payload.hour,
                minute_start=minute_start,
                minute_end=minute_end,
                person_id=payload.person_id,
                activity_id=None,
                loan_area_id=None,
                empty_override=False,
                version=1,
                updated_by=user.id,
            )
            db.add(cell)
            db.flush()
            audit_log(
                db,
                entity_type="schedule_cell",
                entity_id=cell.id,
                action="split_create",
                old_value=None,
                new_value=_cell_to_dict(cell),
                user_id=user.id,
            )
            created.append(cell)
        db.commit()
        return {"segments": _serialize_segments(created)}

    source = hour_segments[0]
    if (source.minute_start, source.minute_end) != FULL_SEGMENT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cellen är redan delad eller har ogiltigt segmentformat.")

    assert_can_modify_schedule_cells([source], user, owner_lock_enabled)
    old = _cell_to_dict(source)
    original_activity_id = source.activity_id
    original_loan_area_id = source.loan_area_id
    original_empty_override = source.empty_override
    first_start, first_end = split_ranges[0]
    source.minute_start = first_start
    source.minute_end = first_end
    source.version += 1
    source.updated_by = user.id
    db.flush()
    audit_log(
        db,
        entity_type="schedule_cell",
        entity_id=source.id,
        action="split_update",
        old_value=old,
        new_value=_cell_to_dict(source),
        user_id=user.id,
    )

    created_segments = [source]
    for minute_start, minute_end in split_ranges[1:]:
        segment = ScheduleCell(
            year=source.year,
            week=source.week,
            weekday=source.weekday,
            hour=source.hour,
            minute_start=minute_start,
            minute_end=minute_end,
            person_id=source.person_id,
            activity_id=original_activity_id,
            loan_area_id=original_loan_area_id,
            empty_override=original_empty_override,
            version=1,
            updated_by=user.id,
        )
        db.add(segment)
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=segment.id,
            action="split_create",
            old_value=None,
            new_value=_cell_to_dict(segment),
            user_id=user.id,
        )
        created_segments.append(segment)

    db.commit()
    return {"segments": _serialize_segments(created_segments)}


@router.post("/cells")
def bulk_update_cells(
    payload: BulkCellRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
):
    if not payload.cells:
        return {"applied": [], "conflicts": []}
    if len(payload.cells) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="För många celler (max 200)")

    applied: list[dict] = []
    conflicts: list[dict] = []
    grouped_items: dict[tuple[int, int, int, int, int], list] = defaultdict(list)
    person_ids: set[int] = set()
    activity_ids: set[int] = set()
    loan_area_ids: set[int] = set()
    dates_by_ywd: dict[tuple[int, int, int], date] = {}

    for item in payload.cells:
        _validate_segment(item.hour, item.minute_start, item.minute_end)
        if item.activity_id is not None and item.loan_area_id is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Aktivitet och låneområde kan inte sättas samtidigt.",
            )
        grouped_items[(item.person_id, item.year, item.week, item.weekday, item.hour)].append(item)
        person_ids.add(item.person_id)
        dates_by_ywd.setdefault(
            (item.year, item.week, item.weekday),
            _schedule_date(item.year, item.week, item.weekday),
        )
        if item.activity_id is not None:
            activity_ids.add(item.activity_id)
        if item.loan_area_id is not None:
            loan_area_ids.add(item.loan_area_id)

    scoped_business_id = visible_business_id(db, user)
    person_query = select(Person).where(Person.id.in_(person_ids))
    if scoped_business_id is not None:
        person_query = person_query.where(Person.business_id == scoped_business_id)
    persons_by_id = {person.id: person for person in db.execute(person_query).scalars().all()}
    existing_person_ids = set(persons_by_id)
    missing_person_ids = sorted(person_ids - existing_person_ids)
    if missing_person_ids:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Person {missing_person_ids[0]} hittades inte",
        )

    if activity_ids:
        activity_query = select(Activity).where(Activity.id.in_(activity_ids))
        if scoped_business_id is not None:
            activity_query = activity_query.where(Activity.business_id == scoped_business_id)
        activities_by_id = {activity.id: activity for activity in db.execute(activity_query).scalars().all()}
        existing_activity_ids = set(activities_by_id)
        missing_activity_ids = sorted(activity_ids - existing_activity_ids)
        if missing_activity_ids:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Aktivitet {missing_activity_ids[0]} hittades inte",
            )
        for item in payload.cells:
            if item.activity_id is None:
                continue
            if activities_by_id[item.activity_id].business_id != persons_by_id[item.person_id].business_id:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och aktivitet tillhör olika verksamheter")

    if loan_area_ids:
        area_query = select(Area).where(Area.id.in_(loan_area_ids))
        if scoped_business_id is not None:
            area_query = area_query.where(Area.business_id == scoped_business_id)
        areas_by_id = {area.id: area for area in db.execute(area_query).scalars().all()}
        existing_area_ids = set(areas_by_id)
        missing_area_ids = sorted(loan_area_ids - existing_area_ids)
        if missing_area_ids:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Område {missing_area_ids[0]} hittades inte",
            )
        for item in payload.cells:
            if item.loan_area_id is None:
                continue
            loan_area = areas_by_id[item.loan_area_id]
            if loan_area.is_active is not True:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
            if loan_area.business_id != persons_by_id[item.person_id].business_id:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och område tillhör olika verksamheter")

    template_hours_map = get_template_hours_map_for_dates(db, person_ids, dates_by_ywd.values())
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)

    try:
        for (person_id, year, week, weekday, hour), group_items in grouped_items.items():
            group_items = sorted(group_items, key=lambda item: (item.minute_start, item.minute_end))
            seen_ranges: set[tuple[int, int]] = set()
            for item in group_items:
                range_key = (item.minute_start, item.minute_end)
                if range_key in seen_ranges:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail="Duplicerade segment i samma timme.",
                    )
                seen_ranges.add(range_key)

            selected_date = dates_by_ywd[(year, week, weekday)]
            template_hours = template_hours_map.get((person_id, selected_date))
            hour_segments = _load_hour_segments(
                db,
                year=year,
                week=week,
                weekday=weekday,
                hour=hour,
                person_id=person_id,
                lock=True,
            )
            item_by_range = {
                (item.minute_start, item.minute_end): item
                for item in group_items
            }
            version_checked_ranges: set[tuple[int, int]] = set()
            split_ranges = _split_ranges_for_items(group_items)
            wants_split_segments = split_ranges is not None

            if wants_split_segments:
                full_segment = (
                    hour_segments[0]
                    if len(hour_segments) == 1
                    and (hour_segments[0].minute_start, hour_segments[0].minute_end) == FULL_SEGMENT
                    else None
                )

                if full_segment is not None:
                    if any(item.expected_version != full_segment.version for item in group_items):
                        conflicts.append(_bulk_conflict_dict(group_items[0], hour_segments))
                        if payload.atomic:
                            db.rollback()
                            return JSONResponse(
                                status_code=status.HTTP_409_CONFLICT,
                                content={"error": "version_conflict", "conflicts": conflicts},
                            )
                        continue

                    assert_can_modify_schedule_cells([full_segment], user, owner_lock_enabled)
                    old_full = _cell_to_dict(full_segment)
                    original_activity_id = full_segment.activity_id
                    original_loan_area_id = full_segment.loan_area_id
                    original_empty_override = full_segment.empty_override
                    first_start, first_end = split_ranges[0]
                    full_segment.minute_start = first_start
                    full_segment.minute_end = first_end
                    full_segment.version += 1
                    full_segment.updated_by = user.id

                    created_split_segments: list[ScheduleCell] = []
                    for minute_start, minute_end in split_ranges[1:]:
                        segment = ScheduleCell(
                            year=year,
                            week=week,
                            weekday=weekday,
                            hour=hour,
                            minute_start=minute_start,
                            minute_end=minute_end,
                            person_id=person_id,
                            activity_id=original_activity_id,
                            loan_area_id=original_loan_area_id,
                            empty_override=original_empty_override,
                            version=1,
                            updated_by=user.id,
                        )
                        db.add(segment)
                        created_split_segments.append(segment)
                    db.flush()
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=full_segment.id,
                        action=f"{payload.action}_split_update",
                        old_value=old_full,
                        new_value=_cell_to_dict(full_segment),
                        user_id=user.id,
                    )
                    for segment in created_split_segments:
                        audit_log(
                            db,
                            entity_type="schedule_cell",
                            entity_id=segment.id,
                            action=f"{payload.action}_split_create",
                            old_value=None,
                            new_value=_cell_to_dict(segment),
                            user_id=user.id,
                        )
                    hour_segments = sorted(
                        [full_segment, *created_split_segments],
                        key=lambda cell: (cell.minute_start, cell.minute_end),
                    )
                    version_checked_ranges = set(item_by_range.keys())
                elif not hour_segments:
                    if any(item.expected_version != 0 for item in group_items):
                        conflicts.append(_bulk_conflict_dict(group_items[0], hour_segments))
                        if payload.atomic:
                            db.rollback()
                            return JSONResponse(
                                status_code=status.HTTP_409_CONFLICT,
                                content={"error": "version_conflict", "conflicts": conflicts},
                            )
                        continue

                    created: list[ScheduleCell] = []
                    for minute_start, minute_end in split_ranges:
                        desired_item = item_by_range.get((minute_start, minute_end))
                        desired_activity_id = (
                            desired_item.activity_id if desired_item is not None else None
                        )
                        desired_loan_area_id = (
                            desired_item.loan_area_id if desired_item is not None else None
                        )
                        cell = ScheduleCell(
                            year=year,
                            week=week,
                            weekday=weekday,
                            hour=hour,
                            minute_start=minute_start,
                            minute_end=minute_end,
                            person_id=person_id,
                            activity_id=desired_activity_id,
                            loan_area_id=desired_loan_area_id,
                            empty_override=_empty_override_for_template(
                                template_hours,
                                hour=hour,
                                activity_id=desired_activity_id,
                            ),
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
                            action=payload.action,
                            old_value=None,
                            new_value=_cell_to_dict(cell),
                            user_id=user.id,
                        )
                    applied.extend(_serialize_segments(created))
                    continue

            current_by_range = {
                (cell.minute_start, cell.minute_end): cell for cell in hour_segments
            }
            created_cells: list[ScheduleCell] = []
            updated_cells: list[tuple[ScheduleCell, dict]] = []
            group_conflict = False

            for item in group_items:
                range_key = (item.minute_start, item.minute_end)
                matching = current_by_range.get(range_key)
                if matching is None and hour_segments:
                    conflicts.append(_bulk_conflict_dict(item, hour_segments))
                    group_conflict = True
                    break

                current_version = matching.version if matching else 0
                if range_key not in version_checked_ranges and current_version != item.expected_version:
                    conflicts.append(_bulk_conflict_dict(item, hour_segments))
                    group_conflict = True
                    break

                desired_empty_override = _empty_override_for_template(
                    template_hours,
                    hour=hour,
                    activity_id=item.activity_id,
                )

                if matching is None:
                    cell = ScheduleCell(
                        year=year,
                        week=week,
                        weekday=weekday,
                        hour=hour,
                        minute_start=item.minute_start,
                        minute_end=item.minute_end,
                        person_id=person_id,
                        activity_id=item.activity_id,
                        loan_area_id=item.loan_area_id,
                        empty_override=desired_empty_override,
                        version=1,
                        updated_by=user.id,
                    )
                    db.add(cell)
                    hour_segments.append(cell)
                    current_by_range[range_key] = cell
                    created_cells.append(cell)
                    continue

                if (
                    matching.activity_id == item.activity_id
                    and matching.loan_area_id == item.loan_area_id
                    and matching.empty_override == desired_empty_override
                ):
                    continue

                assert_can_modify_schedule_cells([matching], user, owner_lock_enabled)
                old = _cell_to_dict(matching)
                matching.activity_id = item.activity_id
                matching.loan_area_id = item.loan_area_id
                matching.empty_override = desired_empty_override
                matching.version += 1
                matching.updated_by = user.id
                updated_cells.append((matching, old))

            if group_conflict:
                if payload.atomic:
                    db.rollback()
                    return JSONResponse(
                        status_code=status.HTTP_409_CONFLICT,
                        content={"error": "version_conflict", "conflicts": conflicts},
                    )
                continue

            if created_cells or updated_cells:
                db.flush()
                for cell in created_cells:
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=cell.id,
                        action=payload.action,
                        old_value=None,
                        new_value=_cell_to_dict(cell),
                        user_id=user.id,
                    )
                for cell, old in updated_cells:
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=cell.id,
                        action=payload.action,
                        old_value=old,
                        new_value=_cell_to_dict(cell),
                        user_id=user.id,
                    )

            applied.extend(_serialize_segments(hour_segments))

        db.commit()
        return {"applied": applied, "conflicts": conflicts}
    except HTTPException:
        db.rollback()
        raise


@router.put("/hours/restore")
def restore_hours(
    payload: RestoreHoursRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
):
    if not payload.hours:
        return {"hours": []}
    if len(payload.hours) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="För många timmar (max 200)")

    seen_hours: set[tuple[int, int, int, int, int]] = set()
    person_ids: set[int] = set()
    activity_ids: set[int] = set()
    loan_area_ids: set[int] = set()
    for item in payload.hours:
        _validate_segment(item.hour, 0, 60)
        _validate_restore_segments(item)
        key = (item.person_id, item.year, item.week, item.weekday, item.hour)
        if key in seen_hours:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Duplicerade timmar i undo.")
        seen_hours.add(key)
        person_ids.add(item.person_id)
        for segment in item.segments:
            if segment.activity_id is not None and segment.loan_area_id is not None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Aktivitet och låneområde kan inte sättas samtidigt.",
                )
            if segment.activity_id is not None:
                activity_ids.add(segment.activity_id)
            if segment.loan_area_id is not None:
                loan_area_ids.add(segment.loan_area_id)

    scoped_business_id = visible_business_id(db, user)
    person_query = select(Person).where(Person.id.in_(person_ids))
    if scoped_business_id is not None:
        person_query = person_query.where(Person.business_id == scoped_business_id)
    persons_by_id = {person.id: person for person in db.execute(person_query).scalars().all()}
    existing_person_ids = set(persons_by_id)
    missing_person_ids = sorted(person_ids - existing_person_ids)
    if missing_person_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Person {missing_person_ids[0]} hittades inte")

    if activity_ids:
        activity_query = select(Activity).where(Activity.id.in_(activity_ids))
        if scoped_business_id is not None:
            activity_query = activity_query.where(Activity.business_id == scoped_business_id)
        activities_by_id = {activity.id: activity for activity in db.execute(activity_query).scalars().all()}
        existing_activity_ids = set(activities_by_id)
        missing_activity_ids = sorted(activity_ids - existing_activity_ids)
        if missing_activity_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Aktivitet {missing_activity_ids[0]} hittades inte")
        for item in payload.hours:
            for segment in item.segments:
                if segment.activity_id is None:
                    continue
                if activities_by_id[segment.activity_id].business_id != persons_by_id[item.person_id].business_id:
                    raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och aktivitet tillhör olika verksamheter")

    if loan_area_ids:
        area_query = select(Area).where(Area.id.in_(loan_area_ids))
        if scoped_business_id is not None:
            area_query = area_query.where(Area.business_id == scoped_business_id)
        areas_by_id = {area.id: area for area in db.execute(area_query).scalars().all()}
        existing_area_ids = set(areas_by_id)
        missing_area_ids = sorted(loan_area_ids - existing_area_ids)
        if missing_area_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Område {missing_area_ids[0]} hittades inte")
        for item in payload.hours:
            for segment in item.segments:
                if segment.loan_area_id is None:
                    continue
                loan_area = areas_by_id[segment.loan_area_id]
                if loan_area.is_active is not True:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
                if loan_area.business_id != persons_by_id[item.person_id].business_id:
                    raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och område tillhör olika verksamheter")

    restored: list[dict] = []
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    try:
        for item in payload.hours:
            current = _load_hour_segments(
                db,
                year=item.year,
                week=item.week,
                weekday=item.weekday,
                hour=item.hour,
                person_id=item.person_id,
                lock=True,
            )
            if _segment_signature(current) != _expected_signature(item.expected_segments):
                db.rollback()
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={
                        "error": "version_conflict",
                        "conflicts": [
                            {
                                "person_id": item.person_id,
                                "hour": item.hour,
                                "current": _serialize_segments(current)
                                or [_empty_segment_dict(item.person_id, item.hour, 0, 60)],
                            }
                        ],
                    },
                )

            assert_can_modify_schedule_cells(current, user, owner_lock_enabled)
            for cell in current:
                audit_log(
                    db,
                    entity_type="schedule_cell",
                    entity_id=cell.id,
                    action=f"{payload.action}_delete",
                    old_value=_cell_to_dict(cell),
                    new_value=None,
                    user_id=user.id,
                )
                db.delete(cell)
            if current:
                db.flush()

            created: list[ScheduleCell] = []
            for segment in sorted(item.segments, key=lambda s: (s.minute_start, s.minute_end)):
                cell = ScheduleCell(
                    year=item.year,
                    week=item.week,
                    weekday=item.weekday,
                    hour=item.hour,
                    minute_start=segment.minute_start,
                    minute_end=segment.minute_end,
                    person_id=item.person_id,
                    activity_id=segment.activity_id,
                    loan_area_id=segment.loan_area_id,
                    empty_override=segment.empty_override,
                    version=1,
                    updated_by=user.id,
                )
                db.add(cell)
                created.append(cell)

            if created:
                db.flush()
                for cell in created:
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=cell.id,
                        action=f"{payload.action}_create",
                        old_value=None,
                        new_value=_cell_to_dict(cell),
                        user_id=user.id,
                    )

            restored.append({
                "person_id": item.person_id,
                "hour": item.hour,
                "segments": _serialize_segments(created),
            })

        db.commit()
        return {"hours": restored}
    except HTTPException:
        db.rollback()
        raise


@router.get("/summary", response_model=list[SummaryRow])
def get_summary(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    area_id: int | None = Query(None),
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> list[SummaryRow]:
    selected_date = _schedule_date(year, week, weekday)
    persons, scoped_business_id = _visible_schedule_persons(
        db,
        user,
        area_id,
        business_id,
        year=year,
        week=week,
        weekdays=[weekday],
    )
    person_ids = [person.id for person in persons]
    home_area_person_ids = {
        person.id
        for person in persons
        if area_id is None or person.home_area_id == area_id
    }

    activity_query = db.query(Activity)
    area_query = db.query(Area)
    if scoped_business_id is not None:
        activity_query = activity_query.filter(Activity.business_id == scoped_business_id)
        area_query = area_query.filter(Area.business_id == scoped_business_id)
    activity_rows = activity_query.all()
    activities = {activity.id: activity for activity in activity_rows}
    home_activity_for = build_home_activity_resolver(activity_rows, area_query.all())
    minutes_by_activity: dict[int, int] = {}

    if person_ids:
        explicit_rows = db.execute(
            select(
                ScheduleCell.person_id,
                ScheduleCell.hour,
                ScheduleCell.activity_id,
                ScheduleCell.empty_override,
                ScheduleCell.minute_start,
                ScheduleCell.minute_end,
            ).where(
                ScheduleCell.year == year,
                ScheduleCell.week == week,
                ScheduleCell.weekday == weekday,
                ScheduleCell.person_id.in_(person_ids),
            )
        ).all()

        covered_minutes: dict[tuple[int, int], int] = {}
        for row in explicit_rows:
            duration = int(row.minute_end - row.minute_start)
            if row.activity_id is not None:
                activity = activities.get(row.activity_id)
                count_for_area = (
                    area_id is None
                    or row.person_id in home_area_person_ids
                    or (activity is not None and activity.area_id == area_id)
                )
                if count_for_area:
                    minutes_by_activity[row.activity_id] = (
                        minutes_by_activity.get(row.activity_id, 0) + duration
                    )
            if row.activity_id is not None or row.empty_override:
                key = (row.person_id, row.hour)
                covered_minutes[key] = min(60, covered_minutes.get(key, 0) + duration)

        template_hours_map = get_template_hours_map_for_dates(db, person_ids, [selected_date])
        for person in persons:
            if area_id is not None and person.id not in home_area_person_ids:
                continue
            template_hours = template_hours_map.get((person.id, selected_date))
            home_activity_id = home_activity_for(person)
            if template_hours is None or home_activity_id is None:
                continue
            for hour in template_hours:
                remaining = 60 - covered_minutes.get((person.id, hour), 0)
                if remaining <= 0:
                    continue
                minutes_by_activity[home_activity_id] = (
                    minutes_by_activity.get(home_activity_id, 0) + remaining
                )

    def resolve_summary_target(activity_id: int) -> Activity | None:
        current = activities.get(activity_id)
        visited: set[int] = set()
        while current and current.summary_activity_id is not None and current.id not in visited:
            visited.add(current.id)
            current = activities.get(current.summary_activity_id)
        return current

    grouped: dict[int, dict] = {}
    for activity_id, minutes in minutes_by_activity.items():
        target = resolve_summary_target(activity_id) or activities.get(activity_id)
        if target is None:
            continue
        bucket = grouped.setdefault(
            target.id,
            {
                "activity_id": target.id,
                "activity_code": target.code,
                "activity_label": target.label,
                "color": target.color,
                "sort_order": target.sort_order,
                "minutes": 0,
            },
        )
        bucket["minutes"] += minutes

    return [
        SummaryRow(
            activity_id=item["activity_id"],
            activity_code=item["activity_code"],
            activity_label=item["activity_label"],
            color=item["color"],
            hours=_hours_from_minutes(item["minutes"]),
            persons_equiv=round(_hours_from_minutes(item["minutes"]) / HOURS_PER_PERSON_DAY, 1),
        )
        for item in sorted(grouped.values(), key=lambda x: (x["sort_order"], x["activity_label"]))
    ]
