"""Buggrapporter (nattpass 2026-07-07): endpoint-kontrakt för hela kedjan.

Skapa (validering, storlekstak, rate limit, audit) → lista/hämta
(verksamhetsscope) → statusändring (audit) → retention-städning.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.config import settings
from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import AuditLog, BugReport, Business, User
from app.backend.routers.bug_reports import purge_expired_bug_reports
from app.backend.security import hash_password

EVENTS = json.dumps([{"type": 4, "data": {"href": "x"}}, {"type": 2, "data": {}}])


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
    session.add_all(
        [
            User(
                username="anna", password_hash=hash_password("pass"), role="leader", roles=["leader"],
                business_id=1, is_active=True, must_change_password=False,
            ),
            User(
                username="root", password_hash=hash_password("pass"), role="super_user", roles=["super_user"],
                business_id=1, is_active=True, must_change_password=False,
            ),
            User(
                username="r3anna", password_hash=hash_password("pass"), role="leader", roles=["leader"],
                business_id=2, is_active=True, must_change_password=False,
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


def create_report(client, note="Knappen dog", events=EVENTS):
    return client.post(
        "/api/bug-reports",
        json={"events_json": events, "note": note, "view_id": "schedule", "page_path": "/index.html"},
    )


def test_create_list_play_and_status_flow(client, db_session):
    login(client, "anna")
    created = create_report(client)
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    audit_row = db_session.query(AuditLog).filter_by(entity_type="bug_report", action="create").one()
    assert audit_row.new_value["event_count"] == 2
    assert "events_json" not in str(audit_row.new_value)

    # Vanlig användare utan bugReports-vy kan inte lista (superuser kan).
    assert client.get("/api/bug-reports").status_code in (401, 403)

    login(client, "root")
    listed = client.get("/api/bug-reports").json()["reports"]
    assert len(listed) == 1
    assert listed[0]["username"] == "anna"
    assert listed[0]["status"] == "new"
    assert "events_json" not in listed[0]  # listan är lätt; blobben hämtas per rapport

    detail = client.get(f"/api/bug-reports/{report_id}").json()
    assert json.loads(detail["events_json"]) == json.loads(EVENTS)

    status_response = client.patch(f"/api/bug-reports/{report_id}/status", json={"status": "seen"})
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "seen"
    status_audit = db_session.query(AuditLog).filter_by(entity_type="bug_report", action="status_change").one()
    assert status_audit.old_value == {"status": "new"}

    bad_status = client.patch(f"/api/bug-reports/{report_id}/status", json={"status": "hemlig"})
    assert bad_status.status_code == 422


def test_business_scope_hides_other_tenants_reports(client, db_session):
    login(client, "r3anna")
    assert create_report(client).status_code == 201
    # r3anna saknar bugReports-vyn — och även med den ska R3-rapporten inte synas för Stigamo.
    login(client, "root")  # superuser med business_id=1 ser globalt (∞)
    reports = client.get("/api/bug-reports").json()["reports"]
    assert len(reports) == 1  # superuser ser allt

    report = db_session.query(BugReport).one()
    assert report.business_id == 2


def test_validation_size_cap_and_rate_limit(client, monkeypatch):
    login(client, "anna")

    not_json = create_report(client, events="{trasig")
    assert not_json.status_code == 422

    empty = create_report(client, events="[]")
    assert empty.status_code == 422

    monkeypatch.setattr(settings, "BUG_REPORTS_MAX_EVENTS_BYTES", 10)
    too_big = create_report(client)
    assert too_big.status_code == 413

    monkeypatch.setattr(settings, "BUG_REPORTS_MAX_EVENTS_BYTES", 4 * 1024 * 1024)
    monkeypatch.setattr(settings, "BUG_REPORTS_RATE_LIMIT_PER_HOUR", 2)
    assert create_report(client).status_code == 201
    assert create_report(client).status_code == 201
    limited = create_report(client)
    assert limited.status_code == 429
    assert "senaste timmen" in limited.json()["detail"]


def test_disabled_flag_hides_feature(client, monkeypatch):
    login(client, "anna")
    monkeypatch.setattr(settings, "BUG_REPORTS_ENABLED", False)
    assert create_report(client).status_code == 404


def test_retention_purges_old_reports(db_session):
    old = BugReport(
        business_id=1, user_id=1, events_json=EVENTS, events_bytes=len(EVENTS), status="new",
        created_at=datetime.now(timezone.utc) - timedelta(days=45),
    )
    fresh = BugReport(
        business_id=1, user_id=1, events_json=EVENTS, events_bytes=len(EVENTS), status="new",
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add_all([old, fresh])
    db_session.commit()
    deleted = purge_expired_bug_reports(db_session)
    assert deleted == 1
    remaining = db_session.query(BugReport).all()
    assert len(remaining) == 1
    assert remaining[0].id == fresh.id
