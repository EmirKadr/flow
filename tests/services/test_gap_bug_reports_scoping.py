"""GAP W03 — Buggrapporter, korsverksamhets-scope (cross-tenant).

Även när en ledare uttryckligen har `bugReports: edit` (monkeypatchad
åtkomstmatris) får hen aldrig se, hämta, ta bort eller statusändra en rapport
som tillhör en ANNAN verksamhet. Rapporter är hårt bundna till skaparens
`business_id` och en ledare är verksamhetsscopad (till skillnad från Super User).

Kontrakt som verifieras för leader i biz1 mot en rapport skapad i biz2:
  * GET  /api/bug-reports            -> {"reports": []}
  * GET  /api/bug-reports/{id}       -> 404
  * DELETE /api/bug-reports/{id}     -> 404
  * PATCH /api/bug-reports/{id}/status (giltig status) -> 404

Fixturstilen speglar tests/services/test_bug_reports.py: in-memory SQLite med
StaticPool, Base.metadata.create_all, TestClient med get_db-override och
inloggning via POST /api/auth/login.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend import deps
from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import BugReport, Business, User
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
    # Två separata verksamheter (tenants).
    session.add_all(
        [
            Business(id=1, code="STIGAMO", name="Stigamo", sort_order=1, is_active=True),
            Business(id=2, code="R3", name="R3", sort_order=2, is_active=True),
        ]
    )
    session.add_all(
        [
            # Ledare i biz1 — ska INTE se biz2:s rapporter trots edit-behörighet.
            User(
                username="leader1", password_hash=hash_password("pass"), role="leader",
                roles=["leader"], business_id=1, is_active=True, must_change_password=False,
            ),
            # Vanlig användare i biz2 som skapar rapporten.
            User(
                username="user2", password_hash=hash_password("pass"), role="leader",
                roles=["leader"], business_id=2, is_active=True, must_change_password=False,
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


@pytest.fixture
def leader_has_bug_reports_edit(monkeypatch):
    """Ge rollen `leader` uttrycklig `bugReports: edit` i åtkomstmatrisen.

    require_view_access i deps.py slår upp get_role_view_access i sitt eget
    modulnamnrymd, så patchen måste träffa app.backend.deps.get_role_view_access.
    """

    def fake_get_role_view_access(db, business_id=None):
        return {"leader": {"bugReports": "edit"}}

    monkeypatch.setattr(deps, "get_role_view_access", fake_get_role_view_access)
    return fake_get_role_view_access


def login(client, username):
    response = client.post("/api/auth/login", json={"username": username, "password": "pass"})
    assert response.status_code == 200, response.text
    return client


def create_report(client, note="Trasig knapp"):
    return client.post(
        "/api/bug-reports",
        json={"events_json": EVENTS, "note": note, "view_id": "schedule", "page_path": "/index.html"},
    )


def _seed_report_in_biz2(client, db_session):
    """user2 (biz2) skapar en rapport; returnera dess id och verifiera scope."""
    login(client, "user2")
    created = create_report(client)
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]
    report = db_session.query(BugReport).one()
    assert report.business_id == 2
    return report_id


def test_leader_edit_access_still_scoped_to_own_business(leader_has_bug_reports_edit, client, db_session):
    """Sanity: monkeypatchen ger leader edit-nivå (annars 403, inte 404)."""
    report_id = _seed_report_in_biz2(client, db_session)

    login(client, "leader1")
    # Med bugReports:edit passerar require_view_access — svaret blir alltså
    # 200 (tom lista) resp. 404 (scope), aldrig 401/403.
    listed = client.get("/api/bug-reports")
    assert listed.status_code == 200, listed.text
    assert client.get(f"/api/bug-reports/{report_id}").status_code == 404


def test_list_hides_other_tenant_reports(leader_has_bug_reports_edit, client, db_session):
    report_id = _seed_report_in_biz2(client, db_session)

    login(client, "leader1")
    body = client.get("/api/bug-reports").json()
    assert body["reports"] == []
    # Även med explicit statusfilter ska inget läcka.
    assert client.get("/api/bug-reports?status_filter=new").json()["reports"] == []
    # Rapporten finns fortfarande i DB (den bara filtreras bort per scope).
    assert db_session.get(BugReport, report_id).business_id == 2


def test_get_other_tenant_report_is_404(leader_has_bug_reports_edit, client, db_session):
    report_id = _seed_report_in_biz2(client, db_session)

    login(client, "leader1")
    response = client.get(f"/api/bug-reports/{report_id}")
    assert response.status_code == 404, response.text
    assert "events_json" not in response.text


def test_delete_other_tenant_report_is_404_and_no_op(leader_has_bug_reports_edit, client, db_session):
    report_id = _seed_report_in_biz2(client, db_session)

    login(client, "leader1")
    response = client.delete(f"/api/bug-reports/{report_id}")
    assert response.status_code == 404, response.text
    # Rapporten får inte raderas av en främmande tenant.
    assert db_session.query(BugReport).count() == 1


def test_patch_status_other_tenant_report_is_404_and_unchanged(leader_has_bug_reports_edit, client, db_session):
    report_id = _seed_report_in_biz2(client, db_session)

    login(client, "leader1")
    # Giltig status (statusvalideringen sker före scope-kollen i routern);
    # scope-kollen måste ändå ge 404.
    response = client.patch(f"/api/bug-reports/{report_id}/status", json={"status": "seen"})
    assert response.status_code == 404, response.text
    # Statusen ska vara oförändrad i DB.
    db_session.expire_all()
    assert db_session.get(BugReport, report_id).status == "new"
