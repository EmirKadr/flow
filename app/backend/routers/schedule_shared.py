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



__all__ = [name for name in globals() if not name.startswith("__")]
