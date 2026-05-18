"""Seed initial data: areas, activities, admin-user, demo persons.

Idempotent – kan köras flera gånger utan att duplicera rader.
Körs automatiskt av Render vid varje deploy (se render.yaml).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Activity, Area, Person, User
from .security import hash_password


AREAS: list[dict] = [
    {"code": "GG", "name": "Granngården", "sort_order": 1},
    {"code": "MG", "name": "Mestergruppen", "sort_order": 2},
    {"code": "AS", "name": "Autostore", "sort_order": 3},
    {"code": "ANNAT", "name": "Annat", "sort_order": 9},
]

ACTIVITIES: list[dict] = [
    # Granngården
    {"code": "GG_PLOCK",      "label": "GG Plock",      "area": "GG", "color": "#b7d7ff", "sort_order": 11},
    {"code": "GG_ART_PL",     "label": "GG Art. Pl",    "area": "GG", "color": "#ffd4a3", "sort_order": 12},
    {"code": "GG_VM",         "label": "GG VM",         "area": "GG", "color": "#9be35a", "sort_order": 13},
    {"code": "GG_LKON",       "label": "GG Lkon",       "area": "GG", "color": "#d7f1d0", "sort_order": 14},
    {"code": "GG_HELPALL",    "label": "GG Helpall",    "area": "GG", "color": "#ffd4a3", "sort_order": 15},
    {"code": "GG_PAFYLLNING", "label": "GG Påfyllning", "area": "GG", "color": "#c9a0ff", "sort_order": 16},
    {"code": "GG_SKRYMME",    "label": "GG Skrymme",    "area": "GG", "color": "#ffe900", "sort_order": 17},
    {"code": "GG_LOTSVARD",   "label": "GG Lotsvård",   "area": "GG", "color": "#cfe8ff", "sort_order": 18},
    {"code": "GG_STOD",       "label": "GG Stöd",       "area": "GG", "color": "#e0e0e0", "sort_order": 19},
    {"code": "GG_LEDARE",     "label": "GG Ledare",     "area": "GG", "color": "#fff3a3", "sort_order": 20},
    {"code": "GG_OP",         "label": "GG OP",         "area": "GG", "color": "#bfe1c5", "sort_order": 21},
    {"code": "GG_VAS",        "label": "GG VAS",        "area": "GG", "color": "#b3d9ba", "sort_order": 22},
    {"code": "GG_VK",         "label": "GG VK",         "area": "GG", "color": "#c1d8ff", "sort_order": 23},

    # Mestergruppen
    {"code": "MG_PLOCK",      "label": "MG Plock",      "area": "MG", "color": "#ffb7b7", "sort_order": 31},
    {"code": "MG_ART_PL",     "label": "MG Art. Pl",    "area": "MG", "color": "#ffc299", "sort_order": 32},
    {"code": "MG_VM",         "label": "MG VM",         "area": "MG", "color": "#ffd966", "sort_order": 33},
    {"code": "MG_LKON",       "label": "MG Lkon",       "area": "MG", "color": "#ffe5b3", "sort_order": 34},
    {"code": "MG_LOTS",       "label": "MG Lots",       "area": "MG", "color": "#ffadad", "sort_order": 35},
    {"code": "MG_SKJUTARE",   "label": "MG Skjutare",   "area": "MG", "color": "#ffcccb", "sort_order": 36},
    {"code": "MG_SKRYMME",    "label": "MG Skrymme",    "area": "MG", "color": "#ffe066", "sort_order": 37},
    {"code": "MG_STOD",       "label": "MG Stöd",       "area": "MG", "color": "#e6b3b3", "sort_order": 38},
    {"code": "MG_VAS",        "label": "MG VAS",        "area": "MG", "color": "#ffd1a3", "sort_order": 39},
    {"code": "MG_AL",         "label": "MG AL",         "area": "MG", "color": "#ffbe7a", "sort_order": 40},
    {"code": "MG_PL",         "label": "MG PL",         "area": "MG", "color": "#ffa873", "sort_order": 41},

    # Autostore
    {"code": "AS_PLOCK",      "label": "AS Plock",      "area": "AS", "color": "#c1b3ff", "sort_order": 51},
    {"code": "AS_STOD",       "label": "AS Stöd",       "area": "AS", "color": "#d4c5ff", "sort_order": 52},
    {"code": "AS_DEK",        "label": "AS Dek",        "area": "AS", "color": "#a89cff", "sort_order": 53},
    {"code": "AS_UTLAST",     "label": "AS Utlast",     "area": "AS", "color": "#b3a3e6", "sort_order": 54},
    {"code": "AS_VAS",        "label": "AS VAS",        "area": "AS", "color": "#c2b5ff", "sort_order": 55},

    # Frånvaro & övrigt
    {"code": "LEDIG", "label": "Ledig", "area": None, "color": "#dddddd", "category": "absence", "sort_order": 91},
    {"code": "SJUK",  "label": "Sjuk",  "area": None, "color": "#ffb7b7", "category": "absence", "sort_order": 92},
    {"code": "VAB",   "label": "VAB",   "area": None, "color": "#ffd1b7", "category": "absence", "sort_order": 93},
]

PERSONS: list[str] = [
    "Filip Malmqvist", "Oscar Pihl", "Henric", "Sebastian Färg", "Malin Kling",
    "Emanuel", "Fation", "Isak", "Linus P", "Clara", "Lisa", "Nathalie",
    "Ludwig Ek", "Abdi A", "Alex Vico", "Emil J", "Hugo M", "Josef K",
    "Marcus Svensson", "Trey", "Henrik Axelsson",
]


def seed_areas(db: Session) -> dict[str, Area]:
    by_code: dict[str, Area] = {}
    for spec in AREAS:
        area = db.query(Area).filter_by(code=spec["code"]).one_or_none()
        if area is None:
            area = Area(**spec)
            db.add(area)
        else:
            area.name = spec["name"]
            area.sort_order = spec["sort_order"]
        by_code[spec["code"]] = area
    db.flush()
    return by_code


def seed_activities(db: Session, areas: dict[str, Area]) -> None:
    for spec in ACTIVITIES:
        area_code = spec.get("area")
        area_id = areas[area_code].id if area_code else None
        existing = db.query(Activity).filter_by(code=spec["code"]).one_or_none()
        payload = {
            "code": spec["code"],
            "label": spec["label"],
            "area_id": area_id,
            "color": spec["color"],
            "category": spec.get("category", "work"),
            "sort_order": spec["sort_order"],
            "is_active": True,
        }
        if existing is None:
            db.add(Activity(**payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)


def seed_admin(db: Session) -> None:
    if db.query(User).filter_by(username="admin").one_or_none() is None:
        db.add(
            User(
                username="admin",
                password_hash=hash_password("admin123"),
                display_name="Administratör",
                role="admin",
                roles=["admin"],
            )
        )


def seed_persons(db: Session, areas: dict[str, Area]) -> None:
    gg = areas["GG"].id
    gg_vm = db.query(Activity).filter_by(code="GG_VM").one_or_none()
    gg_vm_id = gg_vm.id if gg_vm else None
    for i, name in enumerate(PERSONS, start=1):
        existing = db.query(Person).filter_by(name=name).one_or_none()
        if existing is None:
            db.add(Person(name=name, home_area_id=gg, home_activity_id=gg_vm_id, sort_order=i, competencies=[]))
        elif existing.home_area_id == gg and existing.home_activity_id is None:
            existing.home_activity_id = gg_vm_id


def backfill_home_activities(db: Session) -> None:
    activities_by_code = {
        activity.code: activity
        for activity in db.query(Activity).filter(Activity.is_active.is_(True)).all()
    }
    fallback_by_area: dict[int | None, Activity] = {}
    for activity in sorted(activities_by_code.values(), key=lambda a: (a.sort_order, a.label)):
        if activity.area_id is None or activity.category == "absence":
            continue
        fallback_by_area.setdefault(activity.area_id, activity)

    areas = db.query(Area).all()
    area_by_id = {area.id: area for area in areas}
    for person in db.query(Person).filter(Person.home_activity_id.is_(None)).all():
        home_area = area_by_id.get(person.home_area_id)
        if home_area is None:
            continue
        preferred = activities_by_code.get(f"{home_area.code}_VM")
        fallback = preferred or fallback_by_area.get(home_area.id)
        if fallback is not None:
            person.home_activity_id = fallback.id


def run() -> None:
    db = SessionLocal()
    try:
        areas = seed_areas(db)
        seed_activities(db, areas)
        seed_admin(db)
        seed_persons(db, areas)
        backfill_home_activities(db)
        db.commit()
        print("Seed OK")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
