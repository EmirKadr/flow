from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..business_scope import scoped_get, visible_business_id
from ..deps import get_db, require_view_access
from ..models import Area, Person, ScheduleCell, User
from ..schedule_locks import assert_can_modify_schedule_cells, foreign_schedule_cell_lock_applies
from ..schemas import ClearRequest, CopyRequest, FillFromLeftRequest

router = APIRouter(prefix="/api/schedule", tags=["schedule-bulk"])


def _segment_to_dict(cell: ScheduleCell) -> dict:
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


def _person_ids_for_area(db: Session, area_id: int | None, user: User) -> list[int] | None:
    business_id = visible_business_id(db, user)
    if area_id is None and business_id is None:
        return None
    query = select(Person.id)
    if business_id is not None:
        query = query.where(Person.business_id == business_id)
    if area_id is not None:
        scoped_get(db, Area, area_id, user, detail="Område hittades inte")
        query = query.where(Person.home_area_id == area_id)
    rows = db.execute(query).scalars().all()
    return list(rows)


@router.post("/copy")
def copy_schedule(
    payload: CopyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
) -> dict:
    if (payload.from_weekday is None) != (payload.to_weekday is None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Antingen båda eller ingen weekday")

    weekdays = (
        [payload.from_weekday] if payload.from_weekday is not None else [1, 2, 3, 4, 5, 6, 7]
    )
    to_weekdays = (
        [payload.to_weekday] if payload.to_weekday is not None else [1, 2, 3, 4, 5, 6, 7]
    )

    area_person_ids = _person_ids_for_area(db, payload.area_id, user)
    if area_person_ids is not None and not area_person_ids:
        return {"copied": 0, "applied": []}

    copied = 0
    applied: list[dict] = []
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    for from_wd, to_wd in zip(weekdays, to_weekdays):
        src_q = select(ScheduleCell).where(
            ScheduleCell.year == payload.from_year,
            ScheduleCell.week == payload.from_week,
            ScheduleCell.weekday == from_wd,
        )
        if area_person_ids is not None:
            src_q = src_q.where(ScheduleCell.person_id.in_(area_person_ids))
        src_cells = db.execute(src_q).scalars().all()
        if not src_cells:
            continue

        # Hämta existerande mål-celler för att hantera overwrite per timme
        person_ids_in_src = list({c.person_id for c in src_cells})
        existing_q = select(ScheduleCell).where(
            ScheduleCell.year == payload.to_year,
            ScheduleCell.week == payload.to_week,
            ScheduleCell.weekday == to_wd,
            ScheduleCell.person_id.in_(person_ids_in_src),
        )
        existing_by_hour: dict[tuple[int, int], list[ScheduleCell]] = defaultdict(list)
        for cell in db.execute(existing_q).scalars().all():
            existing_by_hour[(cell.person_id, cell.hour)].append(cell)

        src_by_hour: dict[tuple[int, int], list[ScheduleCell]] = defaultdict(list)
        for cell in src_cells:
            src_by_hour[(cell.person_id, cell.hour)].append(cell)

        cells_to_delete: list[ScheduleCell] = []
        cells_to_create: list[ScheduleCell] = []
        for key, source_segments in src_by_hour.items():
            target_segments = existing_by_hour.get(key, [])
            if target_segments and not payload.overwrite:
                continue

            if target_segments:
                assert_can_modify_schedule_cells(target_segments, user, owner_lock_enabled)
                for target in target_segments:
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=target.id,
                        action="bulk_copy_clear",
                        old_value={
                            "minute_start": target.minute_start,
                            "minute_end": target.minute_end,
                            "activity_id": target.activity_id,
                            "version": target.version,
                        },
                        new_value=None,
                        user_id=user.id,
                    )
                    cells_to_delete.append(target)

            for src in sorted(source_segments, key=lambda cell: (cell.minute_start, cell.minute_end)):
                cells_to_create.append(
                    ScheduleCell(
                        year=payload.to_year,
                        week=payload.to_week,
                        weekday=to_wd,
                        hour=src.hour,
                        minute_start=src.minute_start,
                        minute_end=src.minute_end,
                        person_id=src.person_id,
                        activity_id=src.activity_id,
                        empty_override=src.empty_override,
                        version=1,
                        updated_by=user.id,
                    )
                )

        for target in cells_to_delete:
            db.delete(target)
        if cells_to_delete:
            db.flush()

        if cells_to_create:
            db.add_all(cells_to_create)
            db.flush()
            for new_cell in cells_to_create:
                audit_log(
                    db,
                    entity_type="schedule_cell",
                    entity_id=new_cell.id,
                    action="bulk_copy",
                    old_value=None,
                    new_value={
                        "minute_start": new_cell.minute_start,
                        "minute_end": new_cell.minute_end,
                        "activity_id": new_cell.activity_id,
                        "version": 1,
                    },
                    user_id=user.id,
                )
                copied += 1
                applied.append(_segment_to_dict(new_cell))

    db.commit()
    return {"copied": copied, "applied": applied}


@router.post("/clear")
def clear_schedule(
    payload: ClearRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
) -> dict:
    q = select(ScheduleCell).where(
        ScheduleCell.year == payload.year,
        ScheduleCell.week == payload.week,
        ScheduleCell.weekday == payload.weekday,
    )
    if payload.person_id is not None:
        scoped_get(db, Person, payload.person_id, user, detail="Person hittades inte")
        q = q.where(ScheduleCell.person_id == payload.person_id)
    elif payload.area_id is not None:
        pids = _person_ids_for_area(db, payload.area_id, user)
        if not pids:
            return {"cleared": 0}
        q = q.where(ScheduleCell.person_id.in_(pids))

    cells = db.execute(q).scalars().all()
    assert_can_modify_schedule_cells(cells, user, foreign_schedule_cell_lock_applies(db, user))
    for c in cells:
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=c.id,
            action="clear",
            old_value={"activity_id": c.activity_id, "version": c.version},
            new_value=None,
            user_id=user.id,
        )
    cleared = len(cells)
    for c in cells:
        db.delete(c)
    db.commit()
    return {"cleared": cleared}


@router.post("/fill-from-left")
def fill_from_left(
    payload: FillFromLeftRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
) -> dict:
    """För varje person: kopiera senaste icke-tomma aktivitet till efterföljande tomma celler samma dag."""
    pids = _person_ids_for_area(db, payload.area_id, user)
    q = select(ScheduleCell).where(
        ScheduleCell.year == payload.year,
        ScheduleCell.week == payload.week,
        ScheduleCell.weekday == payload.weekday,
    )
    if pids is not None:
        if not pids:
            return {"updated": 0}
        q = q.where(ScheduleCell.person_id.in_(pids))
    cells = db.execute(q).scalars().all()
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)

    # Bygg map person → hour → [segments]
    per_person: dict[int, dict[int, list[ScheduleCell]]] = {}
    for c in cells:
        per_person.setdefault(c.person_id, {}).setdefault(c.hour, []).append(c)

    def _sorted_segments(segments: list[ScheduleCell]) -> list[ScheduleCell]:
        return sorted(segments, key=lambda cell: (cell.minute_start, cell.minute_end))

    # Hämta alla aktuella personer i området (de utan celler ska också få chans att fyllas? nej, fill-from-left förutsätter befintliga celler)
    updated = 0
    HOURS = list(range(6, 24))

    person_ids = pids if pids is not None else list(per_person.keys())
    for pid in person_ids:
        last_pattern: list[tuple[int, int, int | None]] | None = None
        for h in HOURS:
            existing_segments = _sorted_segments(per_person.get(pid, {}).get(h, []))
            if existing_segments and any(seg.activity_id is not None for seg in existing_segments):
                last_pattern = [(seg.minute_start, seg.minute_end, seg.activity_id) for seg in existing_segments]
                continue
            if last_pattern is None:
                continue

            existing_by_start = {seg.minute_start: seg for seg in existing_segments}
            desired_starts = {minute_start for minute_start, _, _ in last_pattern}
            new_segments_for_hour: list[ScheduleCell] = []
            for minute_start, minute_end, activity_id in last_pattern:
                existing = existing_by_start.get(minute_start)
                if existing:
                    assert_can_modify_schedule_cells([existing], user, owner_lock_enabled)
                    old = {
                        "minute_start": existing.minute_start,
                        "minute_end": existing.minute_end,
                        "activity_id": existing.activity_id,
                        "version": existing.version,
                    }
                    existing.minute_end = minute_end
                    existing.activity_id = activity_id
                    existing.version += 1
                    existing.updated_by = user.id
                    db.flush()
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=existing.id,
                        action="fill_left",
                        old_value=old,
                        new_value={
                            "minute_start": existing.minute_start,
                            "minute_end": existing.minute_end,
                            "activity_id": existing.activity_id,
                            "version": existing.version,
                        },
                        user_id=user.id,
                    )
                    new_segments_for_hour.append(existing)
                    updated += 1
                else:
                    new_cell = ScheduleCell(
                        year=payload.year,
                        week=payload.week,
                        weekday=payload.weekday,
                        hour=h,
                        minute_start=minute_start,
                        minute_end=minute_end,
                        person_id=pid,
                        activity_id=activity_id,
                        empty_override=False,
                        version=1,
                        updated_by=user.id,
                    )
                    db.add(new_cell)
                    db.flush()
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=new_cell.id,
                        action="fill_left",
                        old_value=None,
                        new_value={
                            "minute_start": new_cell.minute_start,
                            "minute_end": new_cell.minute_end,
                            "activity_id": new_cell.activity_id,
                            "version": 1,
                        },
                        user_id=user.id,
                    )
                    new_segments_for_hour.append(new_cell)
                    updated += 1

            for existing in existing_segments:
                if existing.minute_start in desired_starts:
                    continue
                assert_can_modify_schedule_cells([existing], user, owner_lock_enabled)
                audit_log(
                    db,
                    entity_type="schedule_cell",
                    entity_id=existing.id,
                    action="fill_left_clear",
                    old_value={
                        "minute_start": existing.minute_start,
                        "minute_end": existing.minute_end,
                        "activity_id": existing.activity_id,
                        "version": existing.version,
                    },
                    new_value=None,
                    user_id=user.id,
                )
                db.delete(existing)
            per_person.setdefault(pid, {})[h] = new_segments_for_hour

    db.commit()
    return {"updated": updated}
