"""ETag-mutationskontrakt + samtidighets-smoke.

1) Cache-lagret får aldrig servera inaktuellt data: efter en mutation måste
   en villkorad GET med gammal ETag ge 200 med nytt innehåll, aldrig 304.
2) Samtidighets-smoke: parallella autentiserade GET får aldrig ge 5xx eller
   inkonsistenta svar — fångar klassen "funkar för en användare, låser för
   två" och är förutsättningsbeviset den dag workers-frågan öppnas
   (se DEPLOY.md om _TRACE_CACHE).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import Activity, Area, Business, User
from app.backend.security import hash_password


@pytest.fixture
def session_factory(tmp_path):
    # Filbaserad SQLite + NullPool: varje request-session får egen anslutning,
    # så samtidighetstestet testar appens trådning, inte en delad testsession.
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'etag_concurrency.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    seed = factory()
    try:
        seed.add(Business(id=1, code="MG", name="Mestergruppen", sort_order=1, is_active=True))
        seed.add(Area(id=1, business_id=1, code="PACK", name="Pack", sort_order=1, is_active=True))
        seed.add(
            Activity(id=1, business_id=1, code="PACK_VM", label="Packning", area_id=1, sort_order=1, is_active=True)
        )
        seed.add(
            User(
                username="root",
                password_hash=hash_password("adminpass"),
                role="super_user",
                roles=["super_user"],
                is_active=True,
                must_change_password=False,
            )
        )
        seed.commit()
        yield factory
    finally:
        seed.close()
        engine.dispose()


@pytest.fixture
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            login = test_client.post("/api/auth/login", json={"username": "root", "password": "adminpass"})
            assert login.status_code == 200, login.text
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_stale_etag_after_mutation_returns_fresh_body_not_304(client):
    first = client.get("/api/areas")
    assert first.status_code == 200
    old_etag = first.headers["etag"]

    unchanged = client.get("/api/areas", headers={"If-None-Match": old_etag})
    assert unchanged.status_code == 304

    created = client.post("/api/areas", json={"code": "LOTS", "name": "Lots", "business_id": 1})
    assert created.status_code == 201, created.text

    after = client.get("/api/areas", headers={"If-None-Match": old_etag})
    assert after.status_code == 200, "gammal ETag efter mutation måste ge färskt svar, aldrig 304"
    assert any(area["code"] == "LOTS" for area in after.json())
    assert after.headers["etag"] != old_etag

    revalidated = client.get("/api/areas", headers={"If-None-Match": after.headers["etag"]})
    assert revalidated.status_code == 304


def test_parallel_authenticated_gets_never_5xx_and_stay_consistent(client):
    endpoints = ["/api/areas", "/api/activities", "/api/health", "/api/auth/me"] * 10

    def fetch(path: str):
        response = client.get(path)
        return path, response.status_code, response.content

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fetch, endpoints))

    server_errors = [f"{path} -> {status}" for path, status, _content in results if status >= 500]
    assert server_errors == [], server_errors

    areas_bodies = {content for path, _status, content in results if path == "/api/areas"}
    assert len(areas_bodies) == 1, "parallella /api/areas-svar ska vara identiska"
