"""Gap W08 — 400-guards på produktivitet/finans-rutterna i routers/settings.py.

Två POST-rutter körs som admin (super_user har edit på allt):

* ``/api/settings/productivity-finance/calculation/test``
  (``test_productivity_finance_calculation_route``)
* ``/api/settings/productivity-finance/process-check``
  (``check_productivity_finance_processes_route``)

Testade guards:
  - company_code utanför verksamhetens tillåtna koder -> 400 ("... inte i vald verksamhet")
  - framtida månad -> 400 ("... har startat ...")
  - plan ``needs_clarification`` -> 400 (frågetext)
  - icke-numeriskt beräkningsvärde -> 400 ("numeriskt värde")

Beteendet är verifierat mot källkoden (raderna ~443–530 i settings.py).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.backend.routers.settings as settings_router
from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import Business, User
from app.backend.security import hash_password


# ---------------------------------------------------------------------------
# Fixtures — in-memory SQLite + TestClient med get_db-override.
# ---------------------------------------------------------------------------
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
    # Verksamhet med en enda tillåten bolagskod.
    session.add(
        Business(
            id=1,
            code="STIGAMO",
            name="Stigamo",
            sort_order=1,
            is_active=True,
            company_codes=["ABC"],
        )
    )
    session.add(
        User(
            username="root",
            password_hash=hash_password("pass"),
            role="super_user",
            roles=["super_user"],
            business_id=1,
            is_active=True,
            must_change_password=False,
        )
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


def login(client, username="root"):
    response = client.post("/api/auth/login", json={"username": username, "password": "pass"})
    assert response.status_code == 200, response.text
    return client


CALC_URL = "/api/settings/productivity-finance/calculation/test"
CHECK_URL = "/api/settings/productivity-finance/process-check"


def _future_month():
    """Returnerar en månad > dagens månad inom innevarande år, annars None (dec)."""
    today = date.today()
    return today.month + 1 if today.month < 12 else None


# ---------------------------------------------------------------------------
# calculation/test — company_code-guard (körs FÖRE LLM-anropet).
# ---------------------------------------------------------------------------
def test_calc_company_code_outside_business_returns_400(client):
    login(client)
    # business_id=1 (Stigamo) tillåter bara "ABC"; "ZZZ" ligger utanför.
    resp = client.post(
        f"{CALC_URL}?business_id=1",
        json={"prompt": "testa uträkning", "month": 1, "company_code": "ZZZ"},
    )
    assert resp.status_code == 400, resp.text
    assert "inte i vald verksamhet" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# calculation/test — framtida månad -> 400 "har startat".
# ---------------------------------------------------------------------------
def test_calc_future_month_returns_400(client):
    login(client)
    future = _future_month()
    if future is None:
        pytest.skip("Dagens månad är december — ingen framtida månad inom året att testa.")
    resp = client.post(
        f"{CALC_URL}?business_id=1",
        json={"prompt": "testa uträkning", "month": future},
    )
    assert resp.status_code == 400, resp.text
    assert "har startat" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# calculation/test — plan needs_clarification -> 400 med frågetext.
# ---------------------------------------------------------------------------
def test_calc_needs_clarification_returns_400(client, monkeypatch):
    login(client)

    async def fake_plan(prompt):
        return {"status": "needs_clarification", "question": "Vilket lager avses?"}

    monkeypatch.setattr(settings_router, "_plan_from_prompt", fake_plan)

    resp = client.post(
        f"{CALC_URL}?business_id=1",
        json={"prompt": "otydlig fråga", "month": 1},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "Vilket lager avses?"


def test_calc_needs_clarification_without_question_uses_fallback(client, monkeypatch):
    login(client)

    async def fake_plan(prompt):
        return {"status": "needs_clarification"}

    monkeypatch.setattr(settings_router, "_plan_from_prompt", fake_plan)

    resp = client.post(
        f"{CALC_URL}?business_id=1",
        json={"prompt": "otydlig fråga", "month": 1},
    )
    assert resp.status_code == 400, resp.text
    assert "förtydligas" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# calculation/test — icke-numeriskt beräkningsvärde -> 400 "numeriskt värde".
# ---------------------------------------------------------------------------
def test_calc_non_numeric_value_returns_400(client, monkeypatch):
    login(client)

    async def fake_plan(prompt):
        return {"status": "ok", "view": "", "filters": []}

    async def fake_compute(plan, rows, key, tenant):
        return {"value": "inte-ett-tal"}

    monkeypatch.setattr(settings_router, "_plan_from_prompt", fake_plan)
    monkeypatch.setattr(settings_router, "plan_with_default_calculation", lambda plan, default="count": plan)
    monkeypatch.setattr(settings_router, "_business_tenant", lambda db, business_id: None)
    monkeypatch.setattr(settings_router, "_fetch_rows", lambda *a, **k: [])
    monkeypatch.setattr(settings_router, "compute_calculation", fake_compute)

    resp = client.post(
        f"{CALC_URL}?business_id=1",
        json={"prompt": "testa uträkning", "month": 1},
    )
    assert resp.status_code == 400, resp.text
    assert "numeriskt värde" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# process-check — company_code-guard.
# ---------------------------------------------------------------------------
def test_process_check_company_code_outside_business_returns_400(client):
    login(client)
    resp = client.post(
        f"{CHECK_URL}?business_id=1",
        json={"month": 1, "year": date.today().year, "company_code": "ZZZ"},
    )
    assert resp.status_code == 400, resp.text
    assert "inte i vald verksamhet" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# process-check — framtida månad/år -> 400 "har startat".
# ---------------------------------------------------------------------------
def test_process_check_future_year_returns_400(client):
    login(client)
    # Framtida år tvingar guarden oavsett dagens månad (undviker december-kanten).
    resp = client.post(
        f"{CHECK_URL}?business_id=1",
        json={"month": 1, "year": date.today().year + 1},
    )
    assert resp.status_code == 400, resp.text
    assert "har startat" in resp.json()["detail"]


def test_process_check_future_month_current_year_returns_400(client):
    login(client)
    future = _future_month()
    if future is None:
        pytest.skip("Dagens månad är december — ingen framtida månad inom året att testa.")
    resp = client.post(
        f"{CHECK_URL}?business_id=1",
        json={"month": future, "year": date.today().year},
    )
    assert resp.status_code == 400, resp.text
    assert "har startat" in resp.json()["detail"]
