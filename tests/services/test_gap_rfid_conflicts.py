"""Gap-täckning W06: 409-grenarna i RFID apply/ignore.

Driver varje guard i routers/rfid.py:apply_rfid_event och ignore_rfid_event:
- apply på redan applicerad händelse -> 409
- apply på dubblett (duplicate_ignored) -> 409
- apply när person/aktivitet saknas -> 409 med event.status_reason (annars fallback)
- apply när person och aktivitet tillhör olika verksamheter -> 409
- apply när scan-timmen ligger utanför Bemanningens timmar (HOURS)
  -> STATUS_CONFLICT + apply_conflict-audit + 409
- ignore på redan applicerad händelse -> 409

Mönster lånat från tests/services/test_bug_reports.py: in-memory SQLite (StaticPool)
+ Base.metadata.create_all + TestClient med get_db-override + login via /api/auth/login.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import Activity, AuditLog, Business, Person, RfidScanEvent, User
from app.backend.routers.rfid import (
    STATUS_APPLIED,
    STATUS_CONFLICT,
    STATUS_DUPLICATE_IGNORED,
    STATUS_IGNORED,
    STATUS_PENDING,
    STATUS_UNKNOWN_PERSON,
)
from app.backend.security import hash_password

# scan_time som ger lokal timme inom HOURS (06..23). 09:00 UTC = 11:00 Europe/Berlin (CEST).
INSIDE_HOURS = datetime(2026, 6, 14, 9, 0, tzinfo=timezone.utc)
# 01:00 UTC = 03:00 Europe/Berlin (CEST) -> timme 3, utanför HOURS.
OUTSIDE_HOURS = datetime(2026, 6, 14, 1, 0, tzinfo=timezone.utc)


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
    session.add_all(
        [
            Business(id=1, code="STIGAMO", name="Stigamo", sort_order=1, is_active=True),
            Business(id=2, code="R3", name="R3", sort_order=2, is_active=True),
        ]
    )
    session.add_all(
        [
            User(
                username="anna", password_hash=hash_password("pass"), role="leader",
                roles=["leader"], business_id=1, is_active=True, must_change_password=False,
            ),
            User(
                username="root", password_hash=hash_password("pass"), role="super_user",
                roles=["super_user"], business_id=1, is_active=True, must_change_password=False,
            ),
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
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def login(client, username):
    response = client.post("/api/auth/login", json={"username": username, "password": "pass"})
    assert response.status_code == 200, response.text
    return client


_person_seq = 0
_activity_seq = 0


def add_person(db, *, business_id=1):
    global _person_seq
    _person_seq += 1
    person = Person(
        business_id=business_id,
        name=f"Person {_person_seq}",
        rfid_code=f"CODE{_person_seq:04d}",
        competencies=[],
        is_active=True,
        sort_order=_person_seq,
    )
    db.add(person)
    db.commit()
    return person


def add_activity(db, *, business_id=1):
    global _activity_seq
    _activity_seq += 1
    activity = Activity(
        business_id=business_id,
        code=f"ACT{_activity_seq:04d}",
        label=f"Activity {_activity_seq}",
        color="#ffffff",
        category="work",
        sort_order=_activity_seq,
        is_active=True,
    )
    db.add(activity)
    db.commit()
    return activity


def add_event(db, *, business_id=1, status=STATUS_PENDING, person_id=None,
              activity_id=None, status_reason=None, scan_time=INSIDE_HOURS):
    event = RfidScanEvent(
        business_id=business_id,
        device_identifier="esp32-test-01",
        module_name="Test Modul",
        tag_code="AABBCCDD",
        person_id=person_id,
        activity_id=activity_id,
        scan_time=scan_time,
        status=status,
        status_reason=status_reason,
    )
    db.add(event)
    db.commit()
    return event


def apply(client, event_id):
    return client.post(f"/api/rfid/events/{event_id}/apply")


def ignore(client, event_id):
    return client.post(f"/api/rfid/events/{event_id}/ignore")


# --- apply-grenar ---------------------------------------------------------


def test_apply_on_already_applied_returns_409(client, db_session):
    login(client, "anna")
    person = add_person(db_session)
    activity = add_activity(db_session)
    event = add_event(
        db_session, status=STATUS_APPLIED, person_id=person.id, activity_id=activity.id
    )

    response = apply(client, event.id)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "RFID-händelsen är redan applicerad"


def test_apply_on_duplicate_ignored_returns_409(client, db_session):
    login(client, "anna")
    person = add_person(db_session)
    activity = add_activity(db_session)
    event = add_event(
        db_session, status=STATUS_DUPLICATE_IGNORED, person_id=person.id, activity_id=activity.id
    )

    response = apply(client, event.id)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Dubblettscanningar appliceras inte"


def test_apply_without_person_returns_409_with_status_reason(client, db_session):
    login(client, "anna")
    activity = add_activity(db_session)
    reason = "RFID-brickan ar inte kopplad till en person."
    event = add_event(
        db_session,
        status=STATUS_UNKNOWN_PERSON,
        person_id=None,
        activity_id=activity.id,
        status_reason=reason,
    )

    response = apply(client, event.id)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == reason


def test_apply_without_person_falls_back_when_no_status_reason(client, db_session):
    login(client, "anna")
    activity = add_activity(db_session)
    # person_id None och status_reason None -> fallback-text.
    event = add_event(
        db_session,
        status=STATUS_PENDING,
        person_id=None,
        activity_id=activity.id,
        status_reason=None,
    )

    response = apply(client, event.id)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "RFID-händelsen kan inte appliceras"


def test_apply_without_activity_returns_409(client, db_session):
    login(client, "anna")
    person = add_person(db_session)
    reason = "RFID-modulen ar inte kopplad till en aktivitet."
    event = add_event(
        db_session,
        status=STATUS_PENDING,
        person_id=person.id,
        activity_id=None,
        status_reason=reason,
    )

    response = apply(client, event.id)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == reason


def test_apply_cross_business_person_activity_returns_409(client, db_session):
    # Superuser krävs: annars 404:ar business-scope (scoped_get) på det främmande objektet
    # innan olika-verksamheter-guarden hinner utvärderas.
    login(client, "root")
    person = add_person(db_session, business_id=1)
    activity = add_activity(db_session, business_id=2)
    event = add_event(
        db_session, business_id=1, status=STATUS_PENDING,
        person_id=person.id, activity_id=activity.id,
    )

    response = apply(client, event.id)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Person och aktivitet tillhör olika verksamheter"


def test_apply_scan_outside_hours_sets_conflict_audit_and_409(client, db_session):
    login(client, "anna")
    person = add_person(db_session)
    activity = add_activity(db_session)
    event = add_event(
        db_session,
        status=STATUS_PENDING,
        person_id=person.id,
        activity_id=activity.id,
        scan_time=OUTSIDE_HOURS,
    )

    response = apply(client, event.id)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "RFID-scanningen ligger utanfor Bemanningens timmar."

    # Guarden ska ha persisterat konflikt-status och skrivit apply_conflict-audit.
    db_session.expire_all()
    refreshed = db_session.get(RfidScanEvent, event.id)
    assert refreshed.status == STATUS_CONFLICT
    assert refreshed.status_reason == "RFID-scanningen ligger utanfor Bemanningens timmar."
    conflict_audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.entity_type == "rfid_scan_event",
            AuditLog.entity_id == event.id,
            AuditLog.action == "apply_conflict",
        )
        .one()
    )
    assert conflict_audit is not None


# --- ignore-grenar --------------------------------------------------------


def test_ignore_on_already_applied_returns_409(client, db_session):
    login(client, "anna")
    person = add_person(db_session)
    activity = add_activity(db_session)
    event = add_event(
        db_session, status=STATUS_APPLIED, person_id=person.id, activity_id=activity.id
    )

    response = ignore(client, event.id)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "RFID-händelsen är redan applicerad"

    # Statusen ska vara oförändrad efter ett avvisat ignore-försök.
    db_session.expire_all()
    assert db_session.get(RfidScanEvent, event.id).status == STATUS_APPLIED


def test_ignore_on_duplicate_ignored_keeps_status_and_is_not_409(client, db_session):
    # Dokumenterar att ignore på en dubblett INTE är en 409-gren: status behålls,
    # men anropet lyckas (200) och skriver audit.
    login(client, "anna")
    person = add_person(db_session)
    activity = add_activity(db_session)
    event = add_event(
        db_session, status=STATUS_DUPLICATE_IGNORED, person_id=person.id, activity_id=activity.id
    )

    response = ignore(client, event.id)
    assert response.status_code == 200, response.text
    assert response.json()["event"]["status"] == STATUS_DUPLICATE_IGNORED

    db_session.expire_all()
    assert db_session.get(RfidScanEvent, event.id).status == STATUS_DUPLICATE_IGNORED


def test_ignore_pending_event_sets_ignored(client, db_session):
    # Positiv kontroll: en väntande händelse går att ignorera (ingen 409-gren).
    login(client, "anna")
    person = add_person(db_session)
    activity = add_activity(db_session)
    event = add_event(
        db_session, status=STATUS_PENDING, person_id=person.id, activity_id=activity.id
    )

    response = ignore(client, event.id)
    assert response.status_code == 200, response.text
    assert response.json()["event"]["status"] == STATUS_IGNORED
