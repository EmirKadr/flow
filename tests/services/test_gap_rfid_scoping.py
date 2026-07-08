"""W02 — RFID cross-business scoping (routers/rfid.py).

Kontrakt: _event_query_for_user / list_rfid_events / _get_event_for_update
filtrerar per verksamhet via visible_business_id.

- Icke-super-ledare i verksamhet B ser ENDAST B:s RFID-händelser i listan.
- ignore/apply på en händelse i verksamhet A ger 404 "RFID-händelse hittades inte".
- Super User ser båda verksamheternas händelser.

Följer mönstret i tests/services/test_bug_reports.py: in-memory SQLite
(StaticPool) + Base.metadata.create_all + TestClient med get_db-override +
login via POST /api/auth/login.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import Business, RfidScanEvent, User
from app.backend.security import hash_password

# Alla händelser läggs på samma kalenderdag så list-fönstret fångar dem.
SCAN_DAY = date(2026, 6, 15)
_ISO = SCAN_DAY.isocalendar()
# Mitt på dagen i UTC ligger tryggt inom Europe/Berlin-dygnet (sommartid = UTC+2).
SCAN_TIME = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


def _make_event(business_id: int, tag_code: str) -> RfidScanEvent:
    return RfidScanEvent(
        business_id=business_id,
        device_identifier=f"esp32-{tag_code}",
        module_name="MG Plock",
        tag_code=tag_code,
        scan_time=SCAN_TIME,
        status="pending",
    )


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

    biz_a = Business(id=1, code="STIGAMO", name="Stigamo", sort_order=1, is_active=True)
    biz_b = Business(id=2, code="R3", name="R3", sort_order=2, is_active=True)
    session.add_all([biz_a, biz_b])
    session.add_all(
        [
            # Icke-super-ledare i verksamhet B.
            User(
                username="bleader", password_hash=hash_password("pass"), role="leader",
                roles=["leader"], business_id=2, is_active=True, must_change_password=False,
            ),
            # Super User (registrerad i A men ser globalt).
            User(
                username="root", password_hash=hash_password("pass"), role="super_user",
                roles=["super_user"], business_id=1, is_active=True, must_change_password=False,
            ),
        ]
    )
    session.commit()

    event_a = _make_event(1, "AAAA0001")
    event_b = _make_event(2, "BBBB0002")
    session.add_all([event_a, event_b])
    session.commit()
    # Håll id:na tillgängliga för testerna.
    session.refresh(event_a)
    session.refresh(event_b)
    session.event_a_id = event_a.id
    session.event_b_id = event_b.id

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
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def login(client, username):
    response = client.post("/api/auth/login", json={"username": username, "password": "pass"})
    assert response.status_code == 200, response.text
    return client


def list_events(client):
    return client.get(
        "/api/rfid/events",
        params={"year": _ISO[0], "week": _ISO[1], "weekday": _ISO[2]},
    )


def test_non_super_leader_lists_only_own_business_events(client, db_session):
    login(client, "bleader")
    response = list_events(client)
    assert response.status_code == 200, response.text
    events = response.json()["events"]
    assert len(events) == 1
    assert events[0]["id"] == db_session.event_b_id
    assert events[0]["business_id"] == 2
    # A-händelsen får aldrig läcka in.
    assert all(evt["business_id"] == 2 for evt in events)


def test_super_user_lists_events_from_all_businesses(client, db_session):
    login(client, "root")
    response = list_events(client)
    assert response.status_code == 200, response.text
    events = response.json()["events"]
    business_ids = {evt["business_id"] for evt in events}
    assert business_ids == {1, 2}
    ids = {evt["id"] for evt in events}
    assert ids == {db_session.event_a_id, db_session.event_b_id}


def test_leader_cannot_ignore_event_from_other_business(client, db_session):
    login(client, "bleader")
    response = client.post(f"/api/rfid/events/{db_session.event_a_id}/ignore")
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "RFID-händelse hittades inte"
    # A-händelsen ska förbli oförändrad (pending), inte ignorerad.
    db_session.expire_all()
    event_a = db_session.get(RfidScanEvent, db_session.event_a_id)
    assert event_a.status == "pending"
    assert event_a.ignored_at is None


def test_leader_cannot_apply_event_from_other_business(client, db_session):
    login(client, "bleader")
    response = client.post(f"/api/rfid/events/{db_session.event_a_id}/apply")
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "RFID-händelse hittades inte"


def test_leader_can_ignore_own_business_event(client, db_session):
    # Positiv kontroll: samma endpoint fungerar på den egna verksamhetens händelse.
    login(client, "bleader")
    response = client.post(f"/api/rfid/events/{db_session.event_b_id}/ignore")
    assert response.status_code == 200, response.text
    assert response.json()["event"]["status"] == "ignored"


def test_super_user_can_ignore_event_from_any_business(client, db_session):
    login(client, "root")
    response = client.post(f"/api/rfid/events/{db_session.event_a_id}/ignore")
    assert response.status_code == 200, response.text
    assert response.json()["event"]["status"] == "ignored"
