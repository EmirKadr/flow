"""Gap W09 — validering i routers/meta_uploads.py.

Täcker de renodlade valideringsgrindarna som saknade egen täckning:

* ``POST /uploads/{id}/analyze`` — okänt id → 404, bild (media_type != video) → 400.
* ``DELETE /uploads/{id}`` — okänt id → 404.
* ``POST /uploads`` — 0 filer → 400 "Inga filer skickades" (handler-grenen),
  och > ``MAX_META_UPLOAD_FILES`` → 400 med en fel-audit-rad.

Auth följer test_bug_reports-mönstret (login via POST /api/auth/login med en
seedad super_user). Media-store-roten pekas om till en tempkatalog så inga
bytes hamnar på riktig disk. make_session/store_bytes-hjälparna från
test_meta_uploads återanvänds (importeras, redigeras ej).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend import media_store
from app.backend.config import settings
from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import AuditLog, Business, MetaMediaUpload, User
from app.backend.routers import meta_uploads
from app.backend.security import hash_password


@pytest.fixture(autouse=True)
def _isolate_media_store(monkeypatch, tmp_path):
    """Peka MediaStore till en temp-katalog och nollställ cachen runt varje test."""
    monkeypatch.setattr(settings, "MEDIA_STORE_ROOT", str(tmp_path / "media_store"))
    media_store.reset_media_store_cache()
    yield
    media_store.reset_media_store_cache()


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


def _image_row(session) -> MetaMediaUpload:
    row = MetaMediaUpload(
        batch_id="batch-image",
        original_filename="lagerbild.jpg",
        stored_filename="20260531_120102_123456Z_01.jpg",
        content_type="image/jpeg",
        media_type="image",
        size_bytes=10,
        content_hash="a" * 64,
        storage_backend="filesystem",
        storage_key=None,
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# --------------------------------------------------------------------------- #
# analyze
# --------------------------------------------------------------------------- #
def test_analyze_unknown_upload_returns_404(client):
    login(client)
    response = client.post("/api/meta/uploads/999999/analyze")
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Uppladdningen hittades inte."


def test_analyze_image_upload_returns_400(client, db_session):
    login(client)
    row = _image_row(db_session)
    response = client.post(f"/api/meta/uploads/{row.id}/analyze")
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Bara videor kan analyseras."
    # Bilden ska ligga kvar orörd — 400 är en ren valideringsgrind.
    assert db_session.get(MetaMediaUpload, row.id) is not None


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #
def test_delete_unknown_upload_returns_404(client):
    login(client)
    response = client.delete("/api/meta/uploads/999999")
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Uppladdningen hittades inte."


# --------------------------------------------------------------------------- #
# upload — 0 filer
# --------------------------------------------------------------------------- #
def test_upload_zero_files_http_is_rejected_by_validation(client):
    """Via HTTP fångas 0 filer av FastAPI:s File(...)-krav → 422 (når ej handlern)."""
    login(client)
    response = client.post("/api/meta/uploads")
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][-1] == "files"


def test_upload_zero_files_handler_returns_400_and_audits(db_session):
    """Handler-grenen ``if not files`` → 400 "Inga filer skickades" + fel-audit.

    Nås bara genom att anropa coroutinen direkt (samma mönster som
    test_meta_upload_rejects_non_media_files), eftersom HTTP-lagret annars
    stoppar tomma uppladdningar med 422.
    """
    fake_request = SimpleNamespace(client=SimpleNamespace(host="test-client"))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            meta_uploads.upload_meta_media(
                request=fake_request,
                background_tasks=BackgroundTasks(),
                files=[],
                db=db_session,
            )
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Inga filer skickades."
    assert db_session.query(MetaMediaUpload).count() == 0

    audit = (
        db_session.query(AuditLog)
        .filter_by(entity_type="meta_media_upload", action="upload_failed")
        .one()
    )
    assert audit.new_value["status_code"] == 400
    assert audit.new_value["attempted_count"] == 0
    assert audit.new_value["error_type"] == "HTTPException"
    assert audit.new_value["path"] == "/api/meta/uploads"


# --------------------------------------------------------------------------- #
# upload — för många filer
# --------------------------------------------------------------------------- #
def test_upload_too_many_files_returns_400_and_writes_failure_audit(client, db_session, monkeypatch):
    login(client)
    monkeypatch.setattr(settings, "MAX_META_UPLOAD_FILES", 2)
    files = [("files", (f"bild{i}.jpg", b"x", "image/jpeg")) for i in range(3)]

    response = client.post("/api/meta/uploads", files=files)

    assert response.status_code == 400, response.text
    assert "max 2 filer" in response.json()["detail"]
    # Grinden slår före loopen → ingen rad sparad.
    assert db_session.query(MetaMediaUpload).count() == 0

    audit = (
        db_session.query(AuditLog)
        .filter_by(entity_type="meta_media_upload", action="upload_failed")
        .one()
    )
    assert audit.new_value["status_code"] == 400
    assert audit.new_value["attempted_count"] == 3
    assert audit.new_value["accepted_count"] == 0
    assert audit.new_value["error_type"] == "HTTPException"
    assert audit.new_value["path"] == "/api/meta/uploads"
    assert audit.user_id is None
