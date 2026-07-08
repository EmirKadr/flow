"""Servicetester för Översikt-routerns verksamhetsscoping (W05).

Kontrakt (app/backend/routers/overview.py ~617, get_overview via
visible_business_id i app/backend/business_scope.py ~146):

* En Super User som skickar ``business_id`` får bara den verksamhetens
  personer i svaret — aldrig andra verksamheters personer.
* En icke-super ledare i verksamhet 1 som ber om ``business_id=2`` (en annan
  verksamhet än sin egen) får 404 "Verksamhet hittades inte".

Fixturmönstret följer tests/services/test_overview_router.py: in-memory SQLite
med StaticPool, Base.metadata.create_all, TestClient med get_db-override och
inloggning via POST /api/auth/login.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import Area, Business, Person, User
from app.backend.security import hash_password

# Nästa vecka, dynamiskt (samma resonemang som i test_overview_router.py:
# ett hårdkodat veckonummer blir en tidsbomb).
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
            Area(id=2, business_id=2, code="R3A", name="R3 Område", sort_order=1, is_active=True),
        ]
    )
    session.flush()

    # En person i varje verksamhet så att scoping-utfallet är entydigt:
    # biz1 -> Anna(1), biz2 -> Bengt(2).
    session.add_all(
        [
            Person(id=1, business_id=1, name="Anna", home_area_id=1, is_active=True, has_fixed_schedule=True),
            Person(id=2, business_id=2, name="Bengt", home_area_id=2, is_active=True, has_fixed_schedule=True),
        ]
    )
    session.flush()

    session.add_all(
        [
            User(
                username="super", password_hash=hash_password("pass"),
                role="super_user", roles=["super_user"],
                business_id=None, is_active=True, must_change_password=False,
            ),
            # Icke-super ledare bunden till verksamhet 1.
            User(
                username="ledare1", password_hash=hash_password("pass"),
                role="leader", roles=["leader"],
                business_id=1, is_active=True, must_change_password=False,
            ),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _login_client(db_session, username: str) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    login = test_client.post("/api/auth/login", json={"username": username, "password": "pass"})
    assert login.status_code == 200, login.text
    return test_client


@pytest.fixture
def super_client(db_session):
    client = _login_client(db_session, "super")
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def leader1_client(db_session):
    client = _login_client(db_session, "ledare1")
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_super_user_business_id_scopes_to_that_business(super_client):
    # Super User väljer verksamhet 2 -> bara verksamhet 2:s personer (Bengt).
    response = super_client.get(f"/api/overview?year={YEAR}&week={WEEK}&business_id=2")
    assert response.status_code == 200, response.text
    payload = response.json()
    person_ids = [p["id"] for p in payload["persons"]]
    assert person_ids == [2]
    # Matrisen får inte läcka in personer utanför scopet.
    assert {c["person_id"] for c in payload["matrix"]} == {2}


def test_super_user_without_business_id_sees_all_businesses(super_client):
    # Kontroll: utan business_id är super-scopet None -> alla verksamheter.
    response = super_client.get(f"/api/overview?year={YEAR}&week={WEEK}")
    assert response.status_code == 200, response.text
    person_ids = {p["id"] for p in response.json()["persons"]}
    assert person_ids == {1, 2}


def test_non_super_leader_requesting_other_business_gets_404(leader1_client):
    # Ledare i verksamhet 1 begär verksamhet 2 -> 404 (får inte se annat scope).
    response = leader1_client.get(f"/api/overview?year={YEAR}&week={WEEK}&business_id=2")
    assert response.status_code == 404, response.text
    assert "hittades inte" in response.json()["detail"]


def test_non_super_leader_own_business_ok(leader1_client):
    # Kontroll: samma ledare med sin egen verksamhet (eller utan) ser bara sina.
    response = leader1_client.get(f"/api/overview?year={YEAR}&week={WEEK}&business_id=1")
    assert response.status_code == 200, response.text
    person_ids = {p["id"] for p in response.json()["persons"]}
    assert person_ids == {1}
