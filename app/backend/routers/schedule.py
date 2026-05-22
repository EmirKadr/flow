from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..business_scope import assert_scoped_object, scoped_get, visible_business_id
from ..deps import get_db, require_view_access
from ..home_activity import build_home_activity_resolver, person_out_with_home_activity
from ..models import Activity, Area, Person, ScheduleCell, User
from ..schedule_locks import assert_can_modify_schedule_cells, foreign_schedule_cell_lock_applies
from ..template_service import get_template_hours, get_template_hours_map
from ..schemas import (
    BulkCellRequest,
    CellOut,
    CellUpdate,
    PersonOut,
    RestoreHoursRequest,
    ScheduleOut,
    SplitCellRequest,
    SummaryRow,
)

router = APIRouter(prefix="/api/schedule", tags=["schedule"])

HOURS = list(range(6, 24))           # 06..23 = 18 timslots
HOURS_PER_PERSON_DAY = 8             # för persons_equiv = hours / 8
FULL_SEGMENT = (0, 60)
HALF_SEGMENTS = ((0, 30), (30, 60))
VALID_SEGMENTS = {FULL_SEGMENT, *HALF_SEGMENTS}


def _iso(value) -> str:
    return value.isoformat() if value is not None else ""


def _visible_schedule_persons(
    db: Session,
    user: User,
    area_id: int | None = None,
    business_id: int | None = None,
) -> tuple[list[Person], int | None]:
    scoped_business_id = visible_business_id(db, user, business_id)
    persons_q = select(Person).where(Person.is_active.is_(True))
    if scoped_business_id is not None:
        persons_q = persons_q.where(Person.business_id == scoped_business_id)
    if area_id is not None:
        scoped_get(db, Area, area_id, user, detail="Område hittades inte")
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


def _cell_to_dict(cell: ScheduleCell) -> dict:
    return {
        "person_id": cell.person_id,
        "hour": cell.hour,
        "minute_start": cell.minute_start,
        "minute_end": cell.minute_end,
        "activity_id": cell.activity_id,
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
        "empty_override": False,
        "version": 0,
        "updated_at": None,
        "updated_by": None,
    }


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
    if ranges == {FULL_SEGMENT} or ranges == set(HALF_SEGMENTS):
        return
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail="Undo kan bara återställa en hel timme, två halvtimmar eller en tom implicit timme.",
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


def _is_scheduled_hour(db: Session, person_id: int, weekday: int, hour: int) -> bool:
    template = get_template_hours(db, person_id, weekday)
    return bool(template and hour in template)


def _empty_override_for(
    db: Session,
    *,
    person_id: int,
    weekday: int,
    hour: int,
    activity_id: int | None,
) -> bool:
    return activity_id is None and _is_scheduled_hour(db, person_id, weekday, hour)


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
    if (minute_start, minute_end) not in VALID_SEGMENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ogiltigt segment. Tillåtna värden är 0-60, 0-30 eller 30-60.")


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
    persons, _scoped_business_id = _visible_schedule_persons(db, user, area_id, business_id)
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
    scoped_business_id = visible_business_id(db, user, business_id)
    persons_q = select(Person).where(Person.is_active.is_(True))
    if scoped_business_id is not None:
        persons_q = persons_q.where(Person.business_id == scoped_business_id)
    if area_id is not None:
        scoped_get(db, Area, area_id, user, detail="Område hittades inte")
        persons_q = persons_q.where(Person.home_area_id == area_id)
    persons_q = persons_q.order_by(Person.sort_order, Person.name)
    persons = db.execute(persons_q).scalars().all()
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

    template_hours_map = get_template_hours_map(db, person_ids, [weekday])
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
        hrs = template_hours_map.get((p.id, weekday))
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
            empty_override=_empty_override_for(
                db,
                person_id=payload.person_id,
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
            weekday=payload.weekday,
            hour=payload.hour,
            activity_id=payload.activity_id,
        )
        if cell.activity_id == payload.activity_id and cell.empty_override == desired_empty_override:
            return {"cell": _cell_to_dict(cell)}
        assert_can_modify_schedule_cells([cell], user, owner_lock_enabled)
        old = _cell_to_dict(cell)
        cell.activity_id = payload.activity_id
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

    if len(hour_segments) == 2 and {(cell.minute_start, cell.minute_end) for cell in hour_segments} == set(HALF_SEGMENTS):
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
        other = next(cell for cell in hour_segments if cell.id != preferred.id)

        old_preferred = _cell_to_dict(preferred)
        old_other = _cell_to_dict(other)

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
        preferred.empty_override = preferred.empty_override or other.empty_override
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
        for minute_start, minute_end in HALF_SEGMENTS:
            cell = ScheduleCell(
                year=payload.year,
                week=payload.week,
                weekday=payload.weekday,
                hour=payload.hour,
                minute_start=minute_start,
                minute_end=minute_end,
                person_id=payload.person_id,
                activity_id=None,
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
    source.minute_end = 30
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

    second = ScheduleCell(
        year=source.year,
        week=source.week,
        weekday=source.weekday,
        hour=source.hour,
        minute_start=30,
        minute_end=60,
        person_id=source.person_id,
        activity_id=source.activity_id,
        empty_override=source.empty_override,
        version=1,
        updated_by=user.id,
    )
    db.add(second)
    db.flush()
    audit_log(
        db,
        entity_type="schedule_cell",
        entity_id=second.id,
        action="split_create",
        old_value=None,
        new_value=_cell_to_dict(second),
        user_id=user.id,
    )

    db.commit()
    return {"segments": _serialize_segments([source, second])}


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
    weekdays: set[int] = set()

    for item in payload.cells:
        _validate_segment(item.hour, item.minute_start, item.minute_end)
        grouped_items[(item.person_id, item.year, item.week, item.weekday, item.hour)].append(item)
        person_ids.add(item.person_id)
        weekdays.add(item.weekday)
        if item.activity_id is not None:
            activity_ids.add(item.activity_id)

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

    template_hours_map = get_template_hours_map(db, person_ids, weekdays)
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

            template_hours = template_hours_map.get((person_id, weekday))
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
            wants_half_segments = any(
                (item.minute_start, item.minute_end) in HALF_SEGMENTS
                for item in group_items
            )

            if wants_half_segments:
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
                    original_empty_override = full_segment.empty_override
                    full_segment.minute_start = 0
                    full_segment.minute_end = 30
                    full_segment.version += 1
                    full_segment.updated_by = user.id

                    other_half = ScheduleCell(
                        year=year,
                        week=week,
                        weekday=weekday,
                        hour=hour,
                        minute_start=30,
                        minute_end=60,
                        person_id=person_id,
                        activity_id=original_activity_id,
                        empty_override=original_empty_override,
                        version=1,
                        updated_by=user.id,
                    )
                    db.add(other_half)
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
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=other_half.id,
                        action=f"{payload.action}_split_create",
                        old_value=None,
                        new_value=_cell_to_dict(other_half),
                        user_id=user.id,
                    )
                    hour_segments = sorted(
                        [full_segment, other_half],
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
                    for minute_start, minute_end in HALF_SEGMENTS:
                        desired_item = item_by_range.get((minute_start, minute_end))
                        desired_activity_id = (
                            desired_item.activity_id if desired_item is not None else None
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
                    and matching.empty_override == desired_empty_override
                ):
                    continue

                assert_can_modify_schedule_cells([matching], user, owner_lock_enabled)
                old = _cell_to_dict(matching)
                matching.activity_id = item.activity_id
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
    for item in payload.hours:
        _validate_segment(item.hour, 0, 60)
        _validate_restore_segments(item)
        key = (item.person_id, item.year, item.week, item.weekday, item.hour)
        if key in seen_hours:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Duplicerade timmar i undo.")
        seen_hours.add(key)
        person_ids.add(item.person_id)
        activity_ids.update(segment.activity_id for segment in item.segments if segment.activity_id is not None)

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
    scoped_business_id = visible_business_id(db, user, business_id)
    persons_q = select(Person).where(Person.is_active.is_(True))
    if scoped_business_id is not None:
        persons_q = persons_q.where(Person.business_id == scoped_business_id)
    if area_id is not None:
        scoped_get(db, Area, area_id, user, detail="Område hittades inte")
        persons_q = persons_q.where(Person.home_area_id == area_id)
    persons = db.execute(persons_q).scalars().all()
    person_ids = [person.id for person in persons]

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
                minutes_by_activity[row.activity_id] = (
                    minutes_by_activity.get(row.activity_id, 0) + duration
                )
            if row.activity_id is not None or row.empty_override:
                key = (row.person_id, row.hour)
                covered_minutes[key] = min(60, covered_minutes.get(key, 0) + duration)

        template_hours_map = get_template_hours_map(db, person_ids, [weekday])
        for person in persons:
            template_hours = template_hours_map.get((person.id, weekday))
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
