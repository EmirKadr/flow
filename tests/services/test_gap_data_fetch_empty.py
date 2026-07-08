"""Tomt run-request (routers/data_fetch.py: run_data_fetch).

När varken plan eller prompt skickas (plan falsy + tom/blank prompt) ska
/api/query-data/run ge 400 "Skicka antingen prompt eller plan." och kortsluta
INNAN någon extern datahämtning sker. Testet monkeypatchar den externa
hämtningen (_fetch_rows_with_segments) och verifierar att den aldrig anropas.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.login_rate_limit import login_rate_limiter
from app.backend.main import app
from app.backend.models import Business, User
from app.backend.routers import data_fetch as data_fetch_router
from app.backend.security import hash_password


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
    session.add(Business(id=1, code="STIGAMO", name="Stigamo", sort_order=1, is_active=True))
    # Super user passerar require_view_access("dataFetch", "view") oavsett
    # role-view-access-matris (role_view_access_level -> "edit").
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
    login_rate_limiter._failures.clear()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        login_rate_limiter._failures.clear()


@pytest.fixture
def no_external_calls(monkeypatch):
    """Fånga varje anrop till den externa datahämtningen.

    _fetch_rows_with_segments är router-nivåns enda ingång till den externa
    klienten (ExternalDataClient/fetch_all_rows). Om den anropas har 400-
    kortslutningen misslyckats.
    """
    calls: list = []

    def _boom(*args, **kwargs):  # pragma: no cover - ska aldrig köras
        calls.append((args, kwargs))
        raise AssertionError("Extern datahämtning anropades trots tomt request")

    monkeypatch.setattr(data_fetch_router, "_fetch_rows_with_segments", _boom)
    return calls


def login(client, username="root"):
    response = client.post("/api/auth/login", json={"username": username, "password": "pass"})
    assert response.status_code == 200, response.text
    return client


def test_empty_body_returns_400_without_external_call(client, no_external_calls):
    login(client)

    response = client.post("/api/query-data/run", json={})

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Skicka antingen prompt eller plan."
    assert no_external_calls == []


def test_blank_prompt_and_falsy_plan_returns_400(client, no_external_calls):
    login(client)

    # plan=None (falsy) och prompt bara whitespace (strip() -> tomt).
    response = client.post(
        "/api/query-data/run",
        json={"plan": None, "prompt": "   \t  "},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Skicka antingen prompt eller plan."
    assert no_external_calls == []


def test_empty_plan_dict_is_falsy_and_returns_400(client, no_external_calls):
    login(client)

    # Tom dict är falsy -> går inte in i plan-grenen, ingen prompt heller.
    response = client.post(
        "/api/query-data/run",
        json={"plan": {}, "prompt": ""},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Skicka antingen prompt eller plan."
    assert no_external_calls == []
