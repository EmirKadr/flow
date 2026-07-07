"""Servicetester för schema-bulkrutterna (nattpass 2026-07-07, uppgift 8).

routers/bulk.py låg på 12 % täckning — copy/clear/fill-from-left var i
praktiken otestade trots att de raderar och skapar schemaceller i bulk.
Kontrakten här: kopiering med/utan overwrite, validering, scopad rensning,
fyll-från-vänster-mönstret och att auditrader alltid skrivs.
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
from app.backend.models import Activity, Area, AuditLog, Business, Person, ScheduleCell, User
from app.backend.security import hash_password

V27 = {"year": 2026, "week": 27}
V28 = {"year": 2026, "week": 28}


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
    session.add(stigamo)
    session.flush()
    gg = Area(id=1, business_id=1, code="GG", name="Granngården", sort_order=1, is_active=True)
    tom = Area(id=2, business_id=1, code="TOM", name="Tomt område", sort_order=2, is_active=True)
    session.add_all([gg, tom])
    plock = Activity(id=1, business_id=1, code="PLOCK", label="Plock", category="work", sort_order=1, is_active=True)
    session.add(plock)
    anna = Person(id=1, business_id=1, name="Anna", home_area_id=1, is_active=True)
    session.add(anna)
    session.add(
        User(
            username="ledare", password_hash=hash_password("pass"), role="leader", roles=["leader"],
            business_id=1, is_active=True, must_change_password=False,
        )
    )
    # V27 måndag: Anna plock kl 8 och 9.
    session.add_all(
        [
            ScheduleCell(year=2026, week=27, weekday=1, hour=8, person_id=1, activity_id=1),
            ScheduleCell(year=2026, week=27, weekday=1, hour=9, person_id=1, activity_id=1),
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


def cells(db, **filters):
    query = db.query(ScheduleCell)
    for key, value in filters.items():
        query = query.filter(getattr(ScheduleCell, key) == value)
    return query.all()


def test_copy_day_creates_cells_and_audit(client, db_session):
    response = client.post(
        "/api/schedule/copy",
        json={**{"from_" + k: v for k, v in V27.items()}, "from_weekday": 1,
              **{"to_" + k: v for k, v in V28.items()}, "to_weekday": 1, "overwrite": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["copied"] == 2
    created = cells(db_session, year=2026, week=28, weekday=1, person_id=1)
    assert sorted(cell.hour for cell in created) == [8, 9]
    audit = db_session.query(AuditLog).filter_by(entity_type="schedule_cell", action="bulk_copy").all()
    assert len(audit) == 2
    # Auditpayload är sanerad: remark-innehåll sparas aldrig, bara närvaro/längd.
    assert all("remark_present" in row.new_value and "remark" not in row.new_value for row in audit)


def test_copy_respects_overwrite_flag(client, db_session):
    db_session.add(ScheduleCell(year=2026, week=28, weekday=1, hour=8, person_id=1, activity_id=None, remark="rör ej"))
    db_session.commit()

    keep = client.post(
        "/api/schedule/copy",
        json={"from_year": 2026, "from_week": 27, "from_weekday": 1,
              "to_year": 2026, "to_week": 28, "to_weekday": 1, "overwrite": False},
    )
    assert keep.status_code == 200
    # Kl 8 var upptagen och behölls; bara kl 9 kopierades.
    assert keep.json()["copied"] == 1
    hour8 = cells(db_session, year=2026, week=28, weekday=1, hour=8)
    assert len(hour8) == 1 and hour8[0].remark == "rör ej"

    overwrite = client.post(
        "/api/schedule/copy",
        json={"from_year": 2026, "from_week": 27, "from_weekday": 1,
              "to_year": 2026, "to_week": 28, "to_weekday": 1, "overwrite": True},
    )
    assert overwrite.status_code == 200
    hour8 = cells(db_session, year=2026, week=28, weekday=1, hour=8)
    assert len(hour8) == 1 and hour8[0].activity_id == 1 and hour8[0].remark is None
    assert db_session.query(AuditLog).filter_by(action="bulk_copy_clear").count() >= 1


def test_copy_validates_weekday_pairing_and_empty_area(client):
    mismatch = client.post(
        "/api/schedule/copy",
        json={"from_year": 2026, "from_week": 27, "from_weekday": 1,
              "to_year": 2026, "to_week": 28, "overwrite": False},
    )
    assert mismatch.status_code == 400
    assert "weekday" in mismatch.json()["detail"]

    empty_area = client.post(
        "/api/schedule/copy",
        json={"from_year": 2026, "from_week": 27, "from_weekday": 1,
              "to_year": 2026, "to_week": 28, "to_weekday": 1, "overwrite": False, "area_id": 2},
    )
    assert empty_area.status_code == 200
    assert empty_area.json() == {"copied": 0, "applied": []}


def test_clear_scopes_to_person_and_writes_audit(client, db_session):
    response = client.post(
        "/api/schedule/clear",
        json={"year": 2026, "week": 27, "weekday": 1, "person_id": 1},
    )
    assert response.status_code == 200
    assert response.json()["cleared"] == 2
    assert cells(db_session, year=2026, week=27, weekday=1) == []
    assert db_session.query(AuditLog).filter_by(entity_type="schedule_cell", action="clear").count() == 2

    unknown_person = client.post(
        "/api/schedule/clear",
        json={"year": 2026, "week": 27, "weekday": 1, "person_id": 999},
    )
    assert unknown_person.status_code == 404


def test_fill_from_left_extends_last_pattern(client, db_session):
    response = client.post(
        "/api/schedule/fill-from-left",
        json={"year": 2026, "week": 27, "weekday": 1, "area_id": 1},
    )
    assert response.status_code == 200
    # Sista mönstret (plock kl 9) fylls in i alla efterföljande timmar t.o.m. 23.
    assert response.json()["updated"] == 14
    day_cells = cells(db_session, year=2026, week=27, weekday=1, person_id=1)
    hours = sorted(cell.hour for cell in day_cells)
    assert hours == list(range(8, 24))
    assert all(cell.activity_id == 1 for cell in day_cells)
    assert db_session.query(AuditLog).filter_by(action="fill_left").count() == 14

    empty_area = client.post(
        "/api/schedule/fill-from-left",
        json={"year": 2026, "week": 27, "weekday": 2, "area_id": 2},
    )
    assert empty_area.status_code == 200
    assert empty_area.json() == {"updated": 0}
