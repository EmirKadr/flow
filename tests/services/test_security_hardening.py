"""Säkerhetshärdning (nattpass 2026-07-06): headers, cookieflaggor, login-rate-limit.

- Alla svar får X-Content-Type-Options/X-Frame-Options/Referrer-Policy;
  HSTS bara över https (direkt eller via X-Forwarded-Proto).
- Sessionscookien är HttpOnly + SameSite=lax.
- /api/auth/login blockeras efter för många misslyckade försök per
  (användarnamn, IP), lyckad inloggning nollställer, och allt auditloggas
  utan att avslöja om kontot finns.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.config import settings
from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.login_rate_limit import LoginRateLimiter, login_rate_limiter
from app.backend.main import app
from app.backend.models import AuditLog, Business, User
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
    session.add(Business(id=1, code="MG", name="Mestergruppen", sort_order=1, is_active=True))
    session.add(
        User(
            username="root",
            password_hash=hash_password("adminpass"),
            role="super_user",
            roles=["super_user"],
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
    login_rate_limiter._failures.clear()  # limitern är modul-global; isolera testerna
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        login_rate_limiter._failures.clear()


# ---------------------------------------------------------------- headers


def test_all_responses_carry_security_headers(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    # TestClient kör http — HSTS får INTE sättas då (skulle förstöra lokal dev).
    assert "Strict-Transport-Security" not in response.headers


def test_hsts_only_over_https(client):
    behind_ingress = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert behind_ingress.headers["Strict-Transport-Security"] == "max-age=31536000"

    plain = client.get("/api/health", headers={"X-Forwarded-Proto": "http"})
    assert "Strict-Transport-Security" not in plain.headers


def test_session_cookie_flags(client):
    response = client.post("/api/auth/login", json={"username": "root", "password": "adminpass"})
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "flow_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


# ---------------------------------------------------------------- rate limit


def _fail_login(client, username="root", password="fel"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_login_blocks_after_too_many_failures(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 3)
    for _ in range(3):
        assert _fail_login(client).status_code == 401

    blocked = _fail_login(client)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert "För många" in blocked.json()["detail"]

    # Även RÄTT lösenord blockeras under spärren — annars är spärren meningslös.
    still_blocked = client.post("/api/auth/login", json={"username": "root", "password": "adminpass"})
    assert still_blocked.status_code == 429

    failed_rows = db_session.query(AuditLog).filter_by(entity_type="auth", action="login_failed").all()
    assert len(failed_rows) == 3
    assert all("password" not in str(row.new_value).lower() for row in failed_rows)
    limited_rows = db_session.query(AuditLog).filter_by(entity_type="auth", action="login_rate_limited").all()
    assert len(limited_rows) >= 1


def test_unknown_user_gets_same_treatment(client, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 3)
    for _ in range(3):
        response = _fail_login(client, username="finns-inte")
        assert response.status_code == 401
        assert response.json()["detail"] == "Felaktigt användarnamn eller lösenord"
    assert _fail_login(client, username="finns-inte").status_code == 429


def test_successful_login_resets_counter(client, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 3)
    assert _fail_login(client).status_code == 401
    assert _fail_login(client).status_code == 401
    assert client.post("/api/auth/login", json={"username": "root", "password": "adminpass"}).status_code == 200
    # Räknaren nollställd: två nya felförsök ger 401, inte 429.
    assert _fail_login(client).status_code == 401
    assert _fail_login(client).status_code == 401


def test_rate_limit_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 2)
    for _ in range(6):
        assert _fail_login(client).status_code == 401


def test_limiter_window_expires_with_injected_clock(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)
    clock = {"now": 1000.0}
    limiter = LoginRateLimiter(now=lambda: clock["now"])
    limiter.register_failure("anna", "10.0.0.1")
    limiter.register_failure("anna", "10.0.0.1")
    assert limiter.retry_after_seconds("anna", "10.0.0.1") is not None
    # Annan IP eller annat namn påverkas inte.
    assert limiter.retry_after_seconds("anna", "10.0.0.2") is None
    assert limiter.retry_after_seconds("bert", "10.0.0.1") is None
    clock["now"] += 61
    assert limiter.retry_after_seconds("anna", "10.0.0.1") is None
