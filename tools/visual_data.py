"""Seed deterministic local data for visual smoke screenshots.

Run this module with DATABASE_URL pointing at a disposable SQLite database.
It assumes `app.backend.bootstrap_local` has already created the schema and
base seed data.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.backend.config import settings
from app.backend.database import SessionLocal
from app.backend.models import (
    Activity,
    Area,
    AuditLog,
    Person,
    PersonScheduleTemplate,
    ScheduleCell,
    User,
)
from app.backend.security import hash_password


VISUAL_PASSWORD = "visual12345"


def _next_id(db, model) -> int:
    return int(db.scalar(select(func.max(model.id))) or 0) + 1


def _area_by_code(db, code: str) -> Area:
    area = db.scalar(select(Area).where(Area.code == code))
    if area is None:
        raise RuntimeError(f"Missing area: {code}")
    return area


def _activity_by_code(db, code: str) -> Activity:
    activity = db.scalar(select(Activity).where(Activity.code == code))
    if activity is None:
        raise RuntimeError(f"Missing activity: {code}")
    return activity


def _ensure_user(db, *, username: str, display_name: str, role: str, area: Area | None) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(username=username, password_hash=hash_password(VISUAL_PASSWORD))
        db.add(user)
    user.display_name = display_name
    user.role = role
    user.roles = [role]
    user.area_id = area.id if area else None
    user.is_active = True
    user.must_change_password = False
    if user.password_hash is None:
        user.password_hash = hash_password(VISUAL_PASSWORD)
    return user


def _ensure_person(
    db,
    *,
    name: str,
    area: Area,
    home_activity: Activity,
    sort_order: int,
) -> Person:
    person = db.scalar(select(Person).where(Person.name == name))
    if person is None:
        person = Person(name=name, competencies=[])
        db.add(person)
    person.home_area_id = area.id
    person.home_activity_id = home_activity.id
    person.sort_order = sort_order
    person.is_active = True
    return person


def _set_template(db, person: Person, updated_by: User) -> None:
    existing = {
        row.weekday: row
        for row in db.scalars(
            select(PersonScheduleTemplate).where(PersonScheduleTemplate.person_id == person.id)
        )
    }
    for weekday in range(1, 8):
        row = existing.get(weekday)
        if row is None:
            row = PersonScheduleTemplate(person_id=person.id, weekday=weekday)
            db.add(row)
        row.is_off = weekday in (6, 7)
        row.start_hour = None if row.is_off else 7
        row.end_hour = None if row.is_off else 16
        row.updated_by = updated_by.id


def _upsert_cell(
    db,
    *,
    year: int,
    week: int,
    weekday: int,
    hour: int,
    minute_start: int,
    minute_end: int,
    person: Person,
    activity: Activity | None,
    updated_by: User,
    empty_override: bool = False,
) -> None:
    cell = db.scalar(
        select(ScheduleCell).where(
            ScheduleCell.year == year,
            ScheduleCell.week == week,
            ScheduleCell.weekday == weekday,
            ScheduleCell.hour == hour,
            ScheduleCell.minute_start == minute_start,
            ScheduleCell.person_id == person.id,
        )
    )
    if cell is None:
        cell = ScheduleCell(
            id=_next_id(db, ScheduleCell),
            year=year,
            week=week,
            weekday=weekday,
            hour=hour,
            minute_start=minute_start,
            minute_end=minute_end,
            person_id=person.id,
        )
        db.add(cell)
        db.flush()
    cell.minute_end = minute_end
    cell.activity_id = activity.id if activity else None
    cell.empty_override = empty_override
    cell.version = max(int(cell.version or 0), 1)
    cell.updated_by = updated_by.id


def _replace_hour_with_halves(
    db,
    *,
    year: int,
    week: int,
    weekday: int,
    hour: int,
    person: Person,
    first_activity: Activity,
    second_activity: Activity,
    updated_by: User,
) -> None:
    rows = db.scalars(
        select(ScheduleCell).where(
            ScheduleCell.year == year,
            ScheduleCell.week == week,
            ScheduleCell.weekday == weekday,
            ScheduleCell.hour == hour,
            ScheduleCell.person_id == person.id,
        )
    ).all()
    for row in rows:
        db.delete(row)
    db.flush()
    _upsert_cell(
        db,
        year=year,
        week=week,
        weekday=weekday,
        hour=hour,
        minute_start=0,
        minute_end=30,
        person=person,
        activity=first_activity,
        updated_by=updated_by,
    )
    _upsert_cell(
        db,
        year=year,
        week=week,
        weekday=weekday,
        hour=hour,
        minute_start=30,
        minute_end=60,
        person=person,
        activity=second_activity,
        updated_by=updated_by,
    )


def _log_visual_seed(db, user: User) -> None:
    db.add(
        AuditLog(
            id=_next_id(db, AuditLog),
            entity_type="visual_test",
            entity_id=1,
            action="visual_seed",
            old_value=None,
            new_value={"tool": "tools.visual_data"},
            user_id=user.id,
        )
    )


def seed_visual_data() -> None:
    if not settings.DATABASE_URL.startswith("sqlite"):
        raise SystemExit("tools.visual_data ska bara koras mot en lokal SQLite-databas.")

    today = date.today()
    iso = today.isocalendar()

    db = SessionLocal()
    try:
        gg = _area_by_code(db, "GG")
        mg = _area_by_code(db, "MG")
        as_area = _area_by_code(db, "AS")

        admin = db.scalar(select(User).where(User.username == "admin"))
        if admin is None:
            raise RuntimeError("Base seed must create admin before visual seed")
        admin.display_name = "Visual Admin"
        admin.area_id = gg.id
        admin.is_active = True
        admin.must_change_password = False

        _ensure_user(db, username="visual_leader", display_name="Visual Arbetsledare", role="leader", area=gg)
        _ensure_user(db, username="visual_staffing", display_name="Visual Bemanningsansvarig", role="staffing_manager", area=gg)
        _ensure_user(db, username="visual_viewer", display_name="Visual Visning", role="viewer", area=mg)
        _ensure_user(db, username="visual_lager", display_name="Visual Lagerkontorist", role="warehouse_clerk", area=None)
        _ensure_user(db, username="visual_artikel", display_name="Visual Artikelplacerare", role="article_placer", area=None)

        gg_vm = _activity_by_code(db, "GG_VM")
        gg_plock = _activity_by_code(db, "GG_PLOCK")
        gg_op = _activity_by_code(db, "GG_OP")
        mg_vm = _activity_by_code(db, "MG_VM")
        mg_stod = _activity_by_code(db, "MG_STOD")
        as_plock = _activity_by_code(db, "AS_PLOCK")

        people = [
            _ensure_person(db, name="Visual GG Plock", area=gg, home_activity=gg_plock, sort_order=1),
            _ensure_person(db, name="Visual GG VM", area=gg, home_activity=gg_vm, sort_order=2),
            _ensure_person(db, name="Visual GG OP", area=gg, home_activity=gg_op, sort_order=3),
            _ensure_person(db, name="Visual MG VM", area=mg, home_activity=mg_vm, sort_order=4),
            _ensure_person(db, name="Visual MG Stod", area=mg, home_activity=mg_stod, sort_order=5),
            _ensure_person(db, name="Visual AS Plock", area=as_area, home_activity=as_plock, sort_order=6),
        ]
        db.flush()

        for person in people:
            _set_template(db, person, admin)

        plans = [
            (people[0], gg_plock, gg_vm),
            (people[1], gg_vm, gg_op),
            (people[2], gg_op, gg_plock),
            (people[3], mg_vm, mg_stod),
            (people[4], mg_stod, mg_vm),
            (people[5], as_plock, as_plock),
        ]
        for weekday in range(1, 6):
            for person, morning, afternoon in plans:
                for hour in (7, 8, 9, 11):
                    _upsert_cell(
                        db,
                        year=iso.year,
                        week=iso.week,
                        weekday=weekday,
                        hour=hour,
                        minute_start=0,
                        minute_end=60,
                        person=person,
                        activity=morning,
                        updated_by=admin,
                    )
                for hour in (13, 14, 15):
                    _upsert_cell(
                        db,
                        year=iso.year,
                        week=iso.week,
                        weekday=weekday,
                        hour=hour,
                        minute_start=0,
                        minute_end=60,
                        person=person,
                        activity=afternoon,
                        updated_by=admin,
                    )
            _replace_hour_with_halves(
                db,
                year=iso.year,
                week=iso.week,
                weekday=weekday,
                hour=10,
                person=people[0],
                first_activity=gg_plock,
                second_activity=gg_vm,
                updated_by=admin,
            )

        _log_visual_seed(db, admin)
        db.commit()
        print("Visual seed OK")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_visual_data()
