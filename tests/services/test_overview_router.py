"""Servicetester för Översikt-routern (nattpass 2026-07-07, uppgift 8).

routers/overview.py låg på 27 % täckning. Kontrakten här: veckomatrisens
dominant/mixed/timmar, revision_key som cache-nyckel (ändras vid mutation),
områdesvalidering, månadsvyns dagslista, dagssättning via POST /day med
verksamhetskonflikt-409 och bulk-gränserna.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import Activity, Area, Business, Person, PersonScheduleTemplate, ScheduleCell, User
from app.backend.security import hash_password

# Nästa vecka, dynamiskt: mallar gäller inte datum före personens created_at
# (tredje produktregeln testerna dokumenterar) — ett hårdkodat veckonummer
# hade blivit en tidsbomb när kalendern hann ikapp.
from datetime import date, timedelta

_iso = (date.today() + timedelta(days=7)).isocalendar()
YEAR, WEEK = _iso[0], _iso[1]


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    stigamo = Business(id=1, code="STIGAMO", name="Stigamo", sort_order=1, is_active=True)
    r3 = Business(id=2, code="R3", name="R3", sort_order=2, is_active=True)
    session.add_all([stigamo, r3])
    session.flush()
    session.add_all(
        [
            Area(id=1, business_id=1, code="GG", name="Granngården", sort_order=1, is_active=True),
            Area(id=2, business_id=1, code="GAMMAL", name="Nedlagd", sort_order=2, is_active=False),
        ]
    )
    session.add_all(
        [
            Activity(id=1, business_id=1, code="PLOCK", label="Plock", category="work", sort_order=1, is_active=True),
            Activity(id=2, business_id=1, code="PACK", label="Pack", category="work", sort_order=2, is_active=True),
            Activity(id=3, business_id=2, code="R3P", label="R3 Plock", category="work", sort_order=1, is_active=True),
        ]
    )
    # has_fixed_schedule krävs — annars behandlas alla dagar som lediga i dagssättningen.
    session.add(Person(id=1, business_id=1, name="Anna", home_area_id=1, is_active=True, has_fixed_schedule=True))
    session.flush()
    # Veckomall mån-fre 08-16; helgen saknar mall = "ledig" för dagssättningen.
    for weekday in range(1, 6):
        session.add(PersonScheduleTemplate(person_id=1, weekday=weekday, start_hour=8, end_hour=16))
    session.add(
        User(
            username="ledare", password_hash=hash_password("pass"), role="leader", roles=["leader"],
            business_id=1, is_active=True, must_change_password=False,
        )
    )
    # Måndag V27: 2 h plock + 1 h pack => dominant plock, mixed.
    session.add_all(
        [
            ScheduleCell(year=YEAR, week=WEEK, weekday=1, hour=8, person_id=1, activity_id=1),
            ScheduleCell(year=YEAR, week=WEEK, weekday=1, hour=9, person_id=1, activity_id=1),
            ScheduleCell(year=YEAR, week=WEEK, weekday=1, hour=10, person_id=1, activity_id=2),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            login = test_client.post("/api/auth/login", json={"username": "ledare", "password": "pass"})
            assert login.status_code == 200, login.text
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def monday_cell(payload):
    return next(c for c in payload["matrix"] if c["person_id"] == 1 and c["weekday"] == 1)


def test_week_overview_dominant_mixed_and_hours(client):
    response = client.get(f"/api/overview?year={YEAR}&week={WEEK}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["revision_key"]
    assert [p["id"] for p in payload["persons"]] == [1]
    cell = monday_cell(payload)
    assert cell["activity_id"] == 1  # plock dominerar (2 h mot 1 h)
    assert cell["mixed"] is True
    assert cell["hours_total"] == 3.0
    tuesday = next(c for c in payload["matrix"] if c["weekday"] == 2)
    assert tuesday["activity_id"] is None
    assert tuesday["hours_total"] == 0


def test_inactive_or_unknown_area_gives_404(client):
    assert client.get(f"/api/overview?year={YEAR}&week={WEEK}&area_id=2").status_code == 404
    assert client.get(f"/api/overview?year={YEAR}&week={WEEK}&area_id=999").status_code == 404


def test_revision_key_changes_when_schedule_changes(client):
    before = client.get(f"/api/overview/revision?year={YEAR}&week={WEEK}").json()["revision_key"]
    apply_response = client.post(
        "/api/overview/day",
        json={"person_id": 1, "year": YEAR, "week": WEEK, "weekday": 3, "activity_id": 2},
    )
    assert apply_response.status_code == 200, apply_response.text
    after = client.get(f"/api/overview/revision?year={YEAR}&week={WEEK}").json()["revision_key"]
    assert before != after

    onsdag = next(
        c for c in client.get(f"/api/overview?year={YEAR}&week={WEEK}").json()["matrix"] if c["weekday"] == 3
    )
    assert onsdag["activity_id"] == 2
    assert onsdag["hours_total"] > 0


def test_day_apply_refuses_day_off_without_template(client):
    # Produktregel: dag utan mallade timmar räknas som ledig — dagssättning avvisas.
    response = client.post(
        "/api/overview/day",
        json={"person_id": 1, "year": YEAR, "week": WEEK, "weekday": 6, "activity_id": 1},
    )
    assert response.status_code == 400
    assert "ledig" in response.json()["detail"]


def test_day_apply_rejects_cross_business_activity(client):
    response = client.post(
        "/api/overview/day",
        json={"person_id": 1, "year": YEAR, "week": WEEK, "weekday": 4, "activity_id": 3},
    )
    # Aktiviteten tillhör R3: scopad hämtning ger 404 (eller 409 om synlig).
    assert response.status_code in (404, 409)


def test_day_apply_validates_iso_week(client):
    response = client.post(
        "/api/overview/day",
        json={"person_id": 1, "year": YEAR, "week": 60, "weekday": 1, "activity_id": 1},
    )
    assert response.status_code in (400, 422)


def test_month_overview_lists_all_days(client):
    response = client.get("/api/overview/month?year=2026&month=6")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["days"]) == 30
    assert payload["days"][0]["date"] == "2026-06-01"
    assert payload["days"][-1]["date"] == "2026-06-30"
    assert client.get("/api/overview/revision/month?year=2026&month=6").json()["revision_key"]


def test_bulk_day_limits(client):
    empty = client.post("/api/overview/days/bulk", json={"days": []})
    assert empty.status_code == 200
    assert empty.json() == {"applied": [], "errors": [], "written": 0, "deleted": 0}

    too_many = client.post(
        "/api/overview/days/bulk",
        json={
            "days": [
                {"person_id": 1, "year": YEAR, "week": WEEK, "weekday": 1, "activity_id": 1}
                for _ in range(101)
            ]
        },
    )
    assert too_many.status_code == 400
    assert "max 100" in too_many.json()["detail"]
