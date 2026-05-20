from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..deps import get_db, require_view_access
from ..models import Person, PersonScheduleTemplate, User
from ..schemas import TemplateDay, TemplateOut, TemplateUpdate
from ..template_service import get_all_default_days

router = APIRouter(prefix="/api/persons", tags=["person-schedules"])


def _validate_day(day: TemplateDay) -> None:
    if day.is_off:
        if day.start_hour is not None or day.end_hour is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Dag {day.weekday}: timmar maste vara null nar is_off=true",
            )
        return

    if day.start_hour is None or day.end_hour is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Dag {day.weekday}: start_hour och end_hour kravs",
        )
    if not (6 <= day.start_hour < day.end_hour <= 24):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Dag {day.weekday}: ogiltigt tidsintervall {day.start_hour}-{day.end_hour}",
        )


def _days_from_rows(rows: list[PersonScheduleTemplate]) -> list[TemplateDay]:
    by_weekday = {row.weekday: row for row in rows}
    defaults = {day["weekday"]: day for day in get_all_default_days()}
    has_custom_template = bool(rows)
    days: list[TemplateDay] = []

    for weekday in range(1, 8):
        row = by_weekday.get(weekday)
        if row is not None:
            days.append(
                TemplateDay(
                    weekday=weekday,
                    is_off=row.is_off,
                    start_hour=row.start_hour,
                    end_hour=row.end_hour,
                )
            )
        elif has_custom_template:
            days.append(TemplateDay(weekday=weekday, is_off=True))
        else:
            days.append(TemplateDay(**defaults[weekday]))

    return days


def _template_rows(db: Session, person_id: int) -> list[PersonScheduleTemplate]:
    return db.execute(
        select(PersonScheduleTemplate).where(PersonScheduleTemplate.person_id == person_id)
    ).scalars().all()


@router.get("/{person_id}/schedule", response_model=TemplateOut)
def get_schedule(
    person_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_view_access("persons", "view")),
) -> TemplateOut:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")

    return TemplateOut(
        person_id=person_id,
        has_fixed_schedule=person.has_fixed_schedule,
        days=_days_from_rows(_template_rows(db, person_id)),
    )


@router.put("/{person_id}/schedule", response_model=TemplateOut)
def put_schedule(
    person_id: int,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("persons", "edit")),
) -> TemplateOut:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")

    seen = set()
    for day in payload.days:
        _validate_day(day)
        if day.weekday in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Dubbel weekday {day.weekday}")
        seen.add(day.weekday)

    if payload.has_fixed_schedule is not None and person.has_fixed_schedule != payload.has_fixed_schedule:
        old = {"has_fixed_schedule": person.has_fixed_schedule}
        person.has_fixed_schedule = payload.has_fixed_schedule
        audit_log(
            db,
            entity_type="person",
            entity_id=person.id,
            action="update",
            old_value=old,
            new_value={"has_fixed_schedule": person.has_fixed_schedule},
            user_id=user.id,
        )

    existing_by_weekday = {row.weekday: row for row in _template_rows(db, person_id)}
    for day in payload.days:
        row = existing_by_weekday.get(day.weekday)
        if row is None:
            row = PersonScheduleTemplate(
                person_id=person_id,
                weekday=day.weekday,
                start_hour=day.start_hour,
                end_hour=day.end_hour,
                is_off=day.is_off,
                updated_by=user.id,
            )
            db.add(row)
            db.flush()
            audit_log(
                db,
                entity_type="person_schedule_template",
                entity_id=row.id,
                action="create",
                old_value=None,
                new_value={
                    "weekday": day.weekday,
                    "is_off": day.is_off,
                    "start_hour": day.start_hour,
                    "end_hour": day.end_hour,
                },
                user_id=user.id,
            )
            continue

        old = {
            "weekday": row.weekday,
            "is_off": row.is_off,
            "start_hour": row.start_hour,
            "end_hour": row.end_hour,
        }
        row.is_off = day.is_off
        row.start_hour = day.start_hour
        row.end_hour = day.end_hour
        row.updated_by = user.id
        db.flush()
        new = {
            "weekday": day.weekday,
            "is_off": day.is_off,
            "start_hour": day.start_hour,
            "end_hour": day.end_hour,
        }
        if old != new:
            audit_log(
                db,
                entity_type="person_schedule_template",
                entity_id=row.id,
                action="update",
                old_value=old,
                new_value=new,
                user_id=user.id,
            )

    db.commit()
    return TemplateOut(
        person_id=person_id,
        has_fixed_schedule=person.has_fixed_schedule,
        days=_days_from_rows(_template_rows(db, person_id)),
    )
