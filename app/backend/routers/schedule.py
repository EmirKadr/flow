from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..deps import get_current_user, get_db
from ..models import Activity, Person, ScheduleCell, User
from ..template_service import get_template_hours
from ..schemas import (
    BulkCellRequest,
    CellOut,
    CellUpdate,
    PersonOut,
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


def _cell_to_dict(cell: ScheduleCell) -> dict:
    return {
        "person_id": cell.person_id,
        "hour": cell.hour,
        "minute_start": cell.minute_start,
        "minute_end": cell.minute_end,
        "activity_id": cell.activity_id,
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


def _validate_segment(hour: int, minute_start: int, minute_end: int) -> None:
    if hour not in HOURS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Timme måste vara {HOURS[0]}-{HOURS[-1]}")
    if (minute_start, minute_end) not in VALID_SEGMENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ogiltigt segment. Tillåtna värden är 0-60, 0-30 eller 30-60.")


@router.get("", response_model=ScheduleOut)
def get_schedule(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    area_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ScheduleOut:
    persons_q = select(Person).where(Person.is_active.is_(True))
    if area_id is not None:
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

    scheduled_hours: dict[int, list[int]] = {}
    for p in persons:
        hrs = get_template_hours(db, p.id, weekday)
        if hrs:
            scheduled_hours[p.id] = sorted(hrs)

    return ScheduleOut(
        year=year,
        week=week,
        weekday=weekday,
        area_id=area_id,
        persons=[PersonOut.model_validate(p) for p in persons],
        cells=[CellOut(**_cell_to_dict(c)) for c in sorted(cells, key=lambda c: (c.person_id, c.hour, c.minute_start))],
        scheduled_hours=scheduled_hours,
    )


@router.put("/cell")
def update_cell(
    payload: CellUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_segment(payload.hour, payload.minute_start, payload.minute_end)

    if not db.get(Person, payload.person_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")
    if payload.activity_id is not None and not db.get(Activity, payload.activity_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aktivitet hittades inte")

    hour_segments = _load_hour_segments(
        db,
        year=payload.year,
        week=payload.week,
        weekday=payload.weekday,
        hour=payload.hour,
        person_id=payload.person_id,
        lock=True,
    )
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
        )
    else:
        cell = matching
        old = _cell_to_dict(cell)
        cell.activity_id = payload.activity_id
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
        )

    db.commit()
    db.refresh(cell)
    return {"cell": _cell_to_dict(cell)}


@router.put("/cell/split")
def split_cell(
    payload: SplitCellRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.hour not in HOURS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Timme måste vara {HOURS[0]}-{HOURS[-1]}")
    if not db.get(Person, payload.person_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")

    hour_segments = _load_hour_segments(
        db,
        year=payload.year,
        week=payload.week,
        weekday=payload.weekday,
        hour=payload.hour,
        person_id=payload.person_id,
        lock=True,
    )
    if _segment_signature(hour_segments) != _expected_signature(payload.segments):
        return _conflict_response(person_id=payload.person_id, hour=payload.hour, current=hour_segments)

    if len(hour_segments) == 2 and {(cell.minute_start, cell.minute_end) for cell in hour_segments} == set(HALF_SEGMENTS):
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

        preferred.minute_start = 0
        preferred.minute_end = 60
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
    user: User = Depends(get_current_user),
):
    if not payload.cells:
        return {"applied": [], "conflicts": []}
    if len(payload.cells) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="För många celler (max 200)")

    applied: list[dict] = []
    conflicts: list[dict] = []

    try:
        for item in payload.cells:
            _validate_segment(item.hour, item.minute_start, item.minute_end)
            if not db.get(Person, item.person_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Person {item.person_id} hittades inte")
            if item.activity_id is not None and not db.get(Activity, item.activity_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Aktivitet {item.activity_id} hittades inte")

            hour_segments = _load_hour_segments(
                db,
                year=item.year,
                week=item.week,
                weekday=item.weekday,
                hour=item.hour,
                person_id=item.person_id,
                lock=True,
            )
            matching = next(
                (
                    cell
                    for cell in hour_segments
                    if cell.minute_start == item.minute_start and cell.minute_end == item.minute_end
                ),
                None,
            )
            version_checked = False

            if matching is None and (item.minute_start, item.minute_end) in HALF_SEGMENTS:
                full_segment = hour_segments[0] if len(hour_segments) == 1 and (hour_segments[0].minute_start, hour_segments[0].minute_end) == FULL_SEGMENT else None

                if full_segment is not None:
                    if full_segment.version != item.expected_version:
                        conflicts.append(
                            {
                                "person_id": item.person_id,
                                "hour": item.hour,
                                "minute_start": item.minute_start,
                                "minute_end": item.minute_end,
                                "current": _serialize_segments(hour_segments),
                            }
                        )
                        if payload.atomic:
                            db.rollback()
                            return JSONResponse(
                                status_code=status.HTTP_409_CONFLICT,
                                content={"error": "version_conflict", "conflicts": conflicts},
                            )
                        continue

                    version_checked = True
                    original_activity_id = full_segment.activity_id
                    old_full = _cell_to_dict(full_segment)
                    full_segment.minute_start = 0
                    full_segment.minute_end = 30
                    full_segment.version += 1
                    full_segment.updated_by = user.id
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

                    other_half = ScheduleCell(
                        year=item.year,
                        week=item.week,
                        weekday=item.weekday,
                        hour=item.hour,
                        minute_start=30,
                        minute_end=60,
                        person_id=item.person_id,
                        activity_id=original_activity_id,
                        version=1,
                        updated_by=user.id,
                    )
                    db.add(other_half)
                    db.flush()
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=other_half.id,
                        action=f"{payload.action}_split_create",
                        old_value=None,
                        new_value=_cell_to_dict(other_half),
                        user_id=user.id,
                    )

                    hour_segments = _load_hour_segments(
                        db,
                        year=item.year,
                        week=item.week,
                        weekday=item.weekday,
                        hour=item.hour,
                        person_id=item.person_id,
                        lock=True,
                    )
                    matching = next(
                        (
                            cell
                            for cell in hour_segments
                            if cell.minute_start == item.minute_start and cell.minute_end == item.minute_end
                        ),
                        None,
                    )
                elif not hour_segments:
                    created: list[ScheduleCell] = []
                    for minute_start, minute_end in HALF_SEGMENTS:
                        cell = ScheduleCell(
                            year=item.year,
                            week=item.week,
                            weekday=item.weekday,
                            hour=item.hour,
                            minute_start=minute_start,
                            minute_end=minute_end,
                            person_id=item.person_id,
                            activity_id=item.activity_id if minute_start == item.minute_start else None,
                            version=1,
                            updated_by=user.id,
                        )
                        db.add(cell)
                        db.flush()
                        audit_log(
                            db,
                            entity_type="schedule_cell",
                            entity_id=cell.id,
                            action=payload.action,
                            old_value=None,
                            new_value=_cell_to_dict(cell),
                            user_id=user.id,
                        )
                        created.append(cell)

                    applied.extend(_serialize_segments(created))
                    continue

            current_version = matching.version if matching else 0
            if ((not version_checked) and current_version != item.expected_version) or (matching is None and hour_segments):
                conflicts.append(
                    {
                        "person_id": item.person_id,
                        "hour": item.hour,
                        "minute_start": item.minute_start,
                        "minute_end": item.minute_end,
                        "current": _serialize_segments(hour_segments) or [_empty_segment_dict(item.person_id, item.hour, item.minute_start, item.minute_end)],
                    }
                )
                if payload.atomic:
                    db.rollback()
                    return JSONResponse(
                        status_code=status.HTTP_409_CONFLICT,
                        content={"error": "version_conflict", "conflicts": conflicts},
                    )
                continue

            if matching is None:
                cell = ScheduleCell(
                    year=item.year,
                    week=item.week,
                    weekday=item.weekday,
                    hour=item.hour,
                    minute_start=item.minute_start,
                    minute_end=item.minute_end,
                    person_id=item.person_id,
                    activity_id=item.activity_id,
                    version=1,
                    updated_by=user.id,
                )
                db.add(cell)
                db.flush()
                audit_log(
                    db,
                    entity_type="schedule_cell",
                    entity_id=cell.id,
                    action=payload.action,
                    old_value=None,
                    new_value=_cell_to_dict(cell),
                    user_id=user.id,
                )
            else:
                cell = matching
                old = _cell_to_dict(cell)
                cell.activity_id = item.activity_id
                cell.version += 1
                cell.updated_by = user.id
                db.flush()
                audit_log(
                    db,
                    entity_type="schedule_cell",
                    entity_id=cell.id,
                    action=payload.action,
                    old_value=old,
                    new_value=_cell_to_dict(cell),
                    user_id=user.id,
                )
            applied.extend(_serialize_segments(_load_hour_segments(
                db,
                year=item.year,
                week=item.week,
                weekday=item.weekday,
                hour=item.hour,
                person_id=item.person_id,
            )))

        db.commit()
        return {"applied": applied, "conflicts": conflicts}
    except HTTPException:
        db.rollback()
        raise


@router.get("/summary", response_model=list[SummaryRow])
def get_summary(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    area_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[SummaryRow]:
    q = (
        select(
            Activity.id,
            Activity.code,
            Activity.label,
            Activity.color,
            Activity.sort_order,
            Activity.summary_activity_id,
            func.sum(ScheduleCell.minute_end - ScheduleCell.minute_start).label("minutes"),
        )
        .join(ScheduleCell, ScheduleCell.activity_id == Activity.id)
        .where(
            ScheduleCell.year == year,
            ScheduleCell.week == week,
            ScheduleCell.weekday == weekday,
        )
        .group_by(
            Activity.id,
            Activity.code,
            Activity.label,
            Activity.color,
            Activity.sort_order,
            Activity.summary_activity_id,
        )
        .order_by(Activity.sort_order)
    )
    if area_id is not None:
        q = q.join(Person, Person.id == ScheduleCell.person_id).where(Person.home_area_id == area_id)

    rows = db.execute(q).all()
    activities = {activity.id: activity for activity in db.query(Activity).all()}

    def resolve_summary_target(activity_id: int) -> Activity | None:
        current = activities.get(activity_id)
        visited: set[int] = set()
        while current and current.summary_activity_id is not None and current.id not in visited:
            visited.add(current.id)
            current = activities.get(current.summary_activity_id)
        return current

    grouped: dict[int, dict] = {}
    for row in rows:
        target = resolve_summary_target(row.id) or activities.get(row.id)
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
        bucket["minutes"] += int(row.minutes or 0)

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
