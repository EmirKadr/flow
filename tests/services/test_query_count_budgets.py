"""Frågebudget per kärnendpoint — N+1-vakten (nattpass 2026-07-07, uppgift 3B).

Benchmarken mot flow-development (baslinje-20260707) visade att latensen är
rundresor × Azure-SQL-latens (~37 ms/fråga), inte frågeexplosion: tyngsta
endpointen kör 10 frågor oavsett datamängd. Det här testet låser den
egenskapen — en framtida ändring som råkar införa en fråga per person/rad
spränger taket direkt i pre-push i stället för att upptäckas som seghet i
produktion veckor senare.

Taken är satta med liten marginal över uppmätt antal (verifierat mot seedad
databas med 30 personer och fullt veckoschema — samma antal som med 1 person,
det är poängen).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import (
    Activity,
    Area,
    Business,
    Person,
    PersonScheduleTemplate,
    ScheduleCell,
    User,
)
from app.backend.security import hash_password

_TARGET = date.today() + timedelta(days=7)
_ISO = _TARGET.isocalendar()

# Max antal SQL-frågor per request. Uppmätt 2026-07-07: areas 2, activities 2,
# persons 4, schedule 10, summary 9, overview 10, revision 5. Marginal +2 för
# ofarlig drift (t.ex. ny settings-läsning) — en N+1 över 30 personer skulle
# ge +30 och spränga taket ändå.
QUERY_BUDGETS = {
    "/api/areas": 4,
    "/api/activities": 4,
    "/api/persons": 6,
    f"/api/schedule?year={_ISO[0]}&week={_ISO[1]}&weekday=3": 12,
    f"/api/schedule/summary?year={_ISO[0]}&week={_ISO[1]}&weekday=3": 11,
    f"/api/overview?year={_ISO[0]}&week={_ISO[1]}": 12,
    f"/api/overview/revision?year={_ISO[0]}&week={_ISO[1]}": 7,
}

PERSONS = 30


@pytest.fixture(scope="module")
def counted_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()

    business = Business(id=1, code="STIGAMO", name="Stigamo", sort_order=1, is_active=True)
    session.add(business)
    session.flush()
    for area_id in (1, 2):
        session.add(Area(id=area_id, business_id=1, code=f"A{area_id}", name=f"Område {area_id}", sort_order=area_id, is_active=True))
    for activity_id in range(1, 5):
        session.add(
            Activity(
                id=activity_id, business_id=1, code=f"AKT{activity_id}", label=f"Aktivitet {activity_id}",
                category="work", area_id=1 + (activity_id % 2), sort_order=activity_id, is_active=True,
            )
        )
    session.flush()
    for person_id in range(1, PERSONS + 1):
        session.add(
            Person(
                id=person_id, business_id=1, name=f"Person {person_id:02d}",
                home_area_id=1 + (person_id % 2), is_active=True, has_fixed_schedule=True,
            )
        )
    session.flush()
    for person_id in range(1, PERSONS + 1):
        for weekday in range(1, 6):
            session.add(PersonScheduleTemplate(person_id=person_id, weekday=weekday, start_hour=7, end_hour=16))
            for hour in range(7, 16):
                session.add(
                    ScheduleCell(
                        year=_ISO[0], week=_ISO[1], weekday=weekday, hour=hour,
                        person_id=person_id, activity_id=1 + (hour % 4),
                    )
                )
    session.add(
        User(
            username="ledare", password_hash=hash_password("pass"), role="leader", roles=["leader"],
            business_id=1, is_active=True, must_change_password=False,
        )
    )
    session.commit()

    counter = {"count": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        counter["count"] += 1

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "ledare", "password": "pass"})
            assert login.status_code == 200, login.text
            yield client, counter
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        engine.dispose()


@pytest.mark.parametrize("endpoint", sorted(QUERY_BUDGETS))
def test_endpoint_stays_within_query_budget(counted_client, endpoint):
    client, counter = counted_client
    counter["count"] = 0
    response = client.get(endpoint)
    assert response.status_code == 200, response.text
    used = counter["count"]
    budget = QUERY_BUDGETS[endpoint]
    assert used <= budget, (
        f"{endpoint} körde {used} SQL-frågor (budget {budget}). "
        f"Med {PERSONS} personer i seeden tyder en spräckt budget på en ny N+1 — "
        "batcha frågan i stället för att höja taket."
    )
