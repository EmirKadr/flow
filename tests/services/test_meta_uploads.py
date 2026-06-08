import asyncio
import io
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers, UploadFile

from app.backend.config import Settings, settings
from app.backend.database import Base
from app.backend.deps import get_current_user, get_db
from app.backend.main import app
from app.backend.models import AuditLog, MetaMediaUpload, MetaShipmentObservation, User
from app.backend import meta_analysis_service
from app.backend.routers import meta_uploads


@pytest.fixture(autouse=True)
def disable_meta_analysis_provider(monkeypatch, tmp_path):
    from app.backend import media_store

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "MEDIA_STORE_ROOT", str(tmp_path / "media_store"))
    monkeypatch.setattr(meta_uploads, "_probe_video_duration_from_path", lambda path: None)
    media_store.reset_media_store_cache()
    yield
    media_store.reset_media_store_cache()


def make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    return engine, session


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def store_bytes(content: bytes, suffix: str = ".bin") -> str:
    """Skriv bytes till MediaStore och returnera storage_key (för testrader)."""
    from app.backend.media_store import get_media_store

    writer = get_media_store().create_writer(suffix=suffix)
    writer.write(content)
    return writer.commit().key


def test_meta_upload_default_rate_limit_allows_long_sequential_queues(monkeypatch):
    monkeypatch.delenv("META_UPLOAD_RATE_LIMIT_PER_MINUTE", raising=False)
    defaults = Settings(_env_file=None)
    assert defaults.META_UPLOAD_RATE_LIMIT_PER_MINUTE == 0
    assert defaults.MAX_META_UPLOAD_FILES >= 1


def test_meta_analysis_uses_gemini_config_and_parses_json_response(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-2.5-pro")

    assert meta_analysis_service.meta_analysis_configured()
    assert meta_analysis_service.gemini_model_name() == "gemini-2.5-pro"

    extracted = meta_analysis_service._extract_json_candidate(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"order_number":"12345","username":"lots1","customer_name":"Kund AB",'
                                    '"shipment_number":"RIG-REF-260601-0000000-0",'
                                    '"pallet_id":"PALL-1","deviations":["Dåligt byggd pall"],'
                                    '"uncertainty_notes":"Kontrollera kundnamn","label_frame_time_seconds":2.5}'
                                )
                            }
                        ]
                    }
                }
            ]
        }
    )
    fields = meta_analysis_service.normalize_meta_analysis(extracted)

    assert fields["order_number"] is None
    assert fields["shipment_number"] is None
    assert fields["username"] is None
    assert fields["customer_name"] is None
    assert fields["pallet_id"] == "PALL-1"
    assert fields["deviations"] == ["Dåligt byggd pall"]
    assert fields["uncertainty_notes"] == "Kontrollera kundnamn"
    assert fields["label_frame_time_seconds"] is None
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        meta_analysis_service.calculate_record_hash(
            video_hash="b" * 64,
            order_number=fields["order_number"],
            shipment_number=fields["shipment_number"],
            username=fields["username"],
            customer_name=fields["customer_name"],
            pallet_id=fields["pallet_id"],
            deviations=fields["deviations"],
        ),
    )


def test_meta_analysis_normalizes_audio_only_fields():
    fields = meta_analysis_service.normalize_meta_analysis(
        {
            "order_numbers": ["100001", "100002"],
            "sändnings-id": "RIG-REF-260601-0000000-0",
            "användarnamn": "LOTS01",
            "kund": "Kund AB",
            "pallet_ids": ["BOX-001", "BOX-002"],
            "avvikelser": [{"description": "Pall behöver plastas"}],
        }
    )

    assert fields["order_number"] is None
    assert fields["shipment_number"] is None
    assert fields["username"] is None
    assert fields["customer_name"] is None
    assert fields["pallet_id"] == "BOX-001"
    assert fields["deviations"] == ["Pall behöver plastas"]


def test_meta_analysis_treats_godsmarkning_as_pallet_id():
    fields = meta_analysis_service.normalize_meta_analysis(
        {
            "godsm\u00e4rkning": "PALL-7788",
            "deviations": ["Fel m\u00e5tt"],
        }
    )

    assert fields["pallet_id"] == "PALL-7788"
    assert fields["deviations"] == ["Fel m\u00e5tt"]


def test_meta_record_hash_ignores_future_lookup_fields():
    base = {
        "video_hash": "b" * 64,
        "order_number": "100001",
        "username": "LOTS01",
        "customer_name": "Kund AB",
        "pallet_id": "BOX-001",
        "deviations": ["Pall behöver plastas"],
    }

    first = meta_analysis_service.calculate_record_hash(**base, shipment_number="RIG-REF-260601-0000000-0")
    second = meta_analysis_service.calculate_record_hash(**base, shipment_number="RIG-REF-260601-0000001-0")
    third = meta_analysis_service.calculate_record_hash(**{**base, "pallet_id": "BOX-002"})

    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert re.fullmatch(r"[0-9a-f]{64}", second)
    assert first == second
    assert first != third


def test_meta_analysis_status_requires_only_pallet_id_and_deviations():
    assert meta_analysis_service._status_for_analysis(
        {"pallet_id": "BOX-001", "deviations": ["Pall lutar"], "uncertainty_notes": None},
        None,
    ) == "analyzed"
    assert meta_analysis_service._status_for_analysis(
        {"pallet_id": None, "deviations": ["Pall lutar"], "uncertainty_notes": None},
        None,
    ) == "manual_review"
    assert meta_analysis_service._status_for_analysis(
        {"pallet_id": "BOX-001", "deviations": [], "uncertainty_notes": None},
        None,
    ) == "manual_review"
    assert meta_analysis_service._status_for_analysis(
        {"pallet_id": "BOX-001", "deviations": ["Pall lutar"], "uncertainty_notes": "Flera pall-id hors."},
        None,
    ) == "manual_review"


def test_meta_ffmpeg_resolver_uses_imageio_fallback(monkeypatch):
    monkeypatch.setattr(meta_analysis_service.shutil, "which", lambda name: None)
    monkeypatch.setattr(meta_analysis_service, "_imageio_ffmpeg_exe", lambda: "bundled-ffmpeg")

    assert meta_analysis_service._resolve_ffmpeg() == "bundled-ffmpeg"


def test_analyze_meta_upload_keeps_lookup_fields_blank_without_dispatch_api(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(settings, "META_LABEL_STILL_TIME_SECONDS", 1.0)
    monkeypatch.setattr(
        meta_analysis_service,
        "_call_meta_analysis_provider",
        lambda upload: {
            "order_number": "100001",
            "shipment_number": "RIG-REF-1",
            "username": "lots1",
            "customer_name": "Kund AB",
            "pallet_id": "BOX-001",
            "deviations": ["Pall lutar"],
        },
    )
    monkeypatch.setattr(meta_analysis_service, "extract_label_still_bytes", lambda upload, seconds: None)
    monkeypatch.setattr(meta_analysis_service, "workflow_api_configured", lambda: False)
    engine, session = make_session()
    row = MetaMediaUpload(
        batch_id="batch",
        original_filename="voice.mov",
        stored_filename="20260531_120102_123456Z_01.mov",
        content_type="video/quicktime",
        media_type="video",
        size_bytes=11,
        content_hash="b" * 64,
        storage_backend="filesystem",
        storage_key=store_bytes(b"hello-video", ".mov"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    try:
        result = meta_analysis_service.analyze_meta_upload(session, row.id)

        assert result.analysis_status == "analyzed"
        assert result.order_number is None
        assert result.shipment_number is None
        assert result.username is None
        assert result.customer_name is None
        assert result.pallet_id == "BOX-001"
        assert result.deviations == ["Pall lutar"]
        assert result.label_image_upload_id is None
        assert result.label_frame_time_seconds == "1"
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_analyze_meta_upload_enriches_lookup_fields_from_dispatch_api(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(settings, "META_LABEL_STILL_TIME_SECONDS", 1.0)
    monkeypatch.setattr(
        meta_analysis_service,
        "_call_meta_analysis_provider",
        lambda upload: {
            "pallet_id": "BOX-001",
            "deviations": ["Pall lutar"],
        },
    )
    monkeypatch.setattr(meta_analysis_service, "extract_label_still_bytes", lambda upload, seconds: None)
    monkeypatch.setattr(meta_analysis_service, "workflow_api_configured", lambda: True)

    class FakeDispatchClient:
        def __init__(self):
            self.calls = []

        def fetch_data(self, view, filters=None, identifiers=None):
            self.calls.append((view, filters, identifiers))
            return [
                {
                    "pick_pall_num": "BOX-001",
                    "order_num": "100001",
                    "shipment_id": "RIG-REF-1",
                    "user_id": "LOTS01",
                    "custom_desc": "Kund AB",
                }
            ]

    fake_client = FakeDispatchClient()
    monkeypatch.setattr(meta_analysis_service, "_api_client", lambda: fake_client)
    engine, session = make_session()
    row = MetaMediaUpload(
        batch_id="batch",
        original_filename="voice.mov",
        stored_filename="20260531_120102_123456Z_01.mov",
        content_type="video/quicktime",
        media_type="video",
        size_bytes=11,
        content_hash="b" * 64,
        storage_backend="filesystem",
        storage_key=store_bytes(b"hello-video", ".mov"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    try:
        result = meta_analysis_service.analyze_meta_upload(session, row.id)

        assert fake_client.calls == [
            (
                "v_ask_dispatch_pallet",
                [{"id": "pick_pall_num", "value": "BOX-001", "operator": "EQ"}],
                None,
            )
        ]
        assert result.analysis_status == "analyzed"
        assert result.order_number == "100001"
        assert result.shipment_number == "RIG-REF-1"
        assert result.username == "LOTS01"
        assert result.customer_name == "Kund AB"
        assert result.pallet_id == "BOX-001"
        assert result.deviations == ["Pall lutar"]
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_analyze_meta_upload_marks_audio_extraction_failure(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(meta_analysis_service, "_resolve_ffmpeg", lambda: None)
    engine, session = make_session()
    row = MetaMediaUpload(
        batch_id="batch",
        original_filename="silent.mov",
        stored_filename="20260531_120102_123456Z_01.mov",
        content_type="video/quicktime",
        media_type="video",
        size_bytes=11,
        content_hash="b" * 64,
        storage_backend="filesystem",
        storage_key=store_bytes(b"hello-video", ".mov"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    try:
        result = meta_analysis_service.analyze_meta_upload(session, row.id)

        assert result.analysis_status == "analysis_failed"
        assert "ffmpeg saknas" in (result.analysis_error or "")
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_queued_meta_analysis_upload_ids_returns_oldest_queued_video():
    engine, session = make_session()
    first = MetaMediaUpload(
        batch_id="batch",
        original_filename="first.mov",
        stored_filename="first.mov",
        content_type="video/quicktime",
        media_type="video",
        size_bytes=11,
        content_hash="1" * 64,
        storage_backend="filesystem",
        storage_key=store_bytes(b"first-video", ".mov"),
        status="pending_analysis",
        source="public_upload",
    )
    second = MetaMediaUpload(
        batch_id="batch",
        original_filename="second.mov",
        stored_filename="second.mov",
        content_type="video/quicktime",
        media_type="video",
        size_bytes=11,
        content_hash="2" * 64,
        storage_backend="filesystem",
        storage_key=store_bytes(b"second-video", ".mov"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add_all([first, second])
    session.commit()
    session.refresh(first)
    session.refresh(second)
    session.add_all(
        [
            MetaShipmentObservation(
                media_upload_id=first.id,
                video_hash=first.content_hash,
                record_hash="a" * 64,
                analysis_status="queued",
            ),
            MetaShipmentObservation(
                media_upload_id=second.id,
                video_hash=second.content_hash,
                record_hash="b" * 64,
                analysis_status="manual_review",
            ),
        ]
    )
    session.commit()
    try:
        assert meta_analysis_service.queued_meta_analysis_upload_ids(session, limit=5) == [first.id]
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_public_meta_upload_route_accepts_multiple_media_without_login(monkeypatch):
    monkeypatch.setattr(meta_uploads, "_probe_video_duration_from_path", lambda path: 42.4)
    engine, session = make_session()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/meta/uploads",
            files=[
                ("files", ("bild.jpg", b"image-bytes", "image/jpeg")),
                ("files", ("film.mov", b"video-bytes", "video/quicktime")),
            ],
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["saved_count"] == 2
        assert payload["status"] == "pending_analysis"

        rows = session.query(MetaMediaUpload).order_by(MetaMediaUpload.id).all()
        assert [row.original_filename for row in rows] == ["bild.jpg", "film.mov"]
        assert re.fullmatch(r"\d{8}_\d{6}_\d{6}Z_01\.jpg", rows[0].stored_filename)
        assert re.fullmatch(r"\d{8}_\d{6}_\d{6}Z_02\.mov", rows[1].stored_filename)
        assert [item["filename"] for item in payload["saved"]] == [row.stored_filename for row in rows]
        assert all(re.fullmatch(r"[0-9a-f]{64}", row.content_hash or "") for row in rows)
        assert len({row.content_hash for row in rows}) == 2
        assert [row.media_type for row in rows] == ["image", "video"]
        # Bytena ligger i MediaStore, inte i DB-kolumnen.
        from app.backend.media_store import get_media_store

        store = get_media_store()
        assert rows[0].storage_key and rows[1].storage_key
        assert rows[0].storage_backend == "filesystem"
        assert b"".join(store.open_all(rows[0].storage_key)) == b"image-bytes"
        assert b"".join(store.open_all(rows[1].storage_key)) == b"video-bytes"
        assert rows[0].storage_key and rows[1].storage_key
        assert rows[0].duration_seconds is None
        assert rows[1].duration_seconds == 42.4
        assert len({row.batch_id for row in rows}) == 1
        assert payload["saved"][1]["duration_seconds"] == 42.4
        assert payload["saved"][1]["duration_label"] == "0:42"
        shipment = session.query(MetaShipmentObservation).one()
        assert shipment.media_upload_id == rows[1].id
        assert shipment.video_hash == rows[1].content_hash
        assert re.fullmatch(r"[0-9a-f]{64}", shipment.record_hash)
        assert shipment.analysis_status == "needs_configuration"
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_public_meta_upload_server_failure_is_visible_in_error_audit(monkeypatch):
    engine, session = make_session()
    original_commit = session.commit
    commit_calls = 0

    def flaky_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            raise RuntimeError("database write failed")
        return original_commit()

    monkeypatch.setattr(session, "commit", flaky_commit)

    def override_get_db():
        yield session

    def super_user():
        return User(id=99, username="root", role="super_user", roles=["super_user"], is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = super_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/meta/uploads",
            files=[("files", ("film.mp4", b"video-bytes", "video/mp4"))],
        )

        assert response.status_code == 500
        assert "Uppladdningen misslyckades" in response.json()["detail"]
        assert session.query(MetaMediaUpload).count() == 0

        audit = session.query(AuditLog).filter_by(entity_type="meta_media_upload", action="upload_failed").one()
        assert audit.user_id is None
        assert audit.new_value["status_code"] == 500
        assert audit.new_value["error_code"] == "HTTP 500"
        assert audit.new_value["error_type"] == "RuntimeError"
        assert audit.new_value["path"] == "/api/meta/uploads"
        assert audit.new_value["attempted_count"] == 1
        assert audit.new_value["accepted_count"] == 1
        assert audit.new_value["uploaded_bytes"] == len(b"video-bytes")
        assert "film.mp4" not in str(audit.new_value)
        assert "database write failed" not in str(audit.new_value)

        errors = client.get("/api/audit/errors")
        assert errors.status_code == 200
        event = errors.json()["recent"][0]
        assert event["entity_type"] == "meta_media_upload"
        assert event["action"] == "upload_failed"
        assert event["status_code"] == 500
        assert event["path"] == "/api/meta/uploads"
        assert event["username"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_meta_upload_skips_duplicate_media_bytes():
    engine, session = make_session()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        first = client.post(
            "/api/meta/uploads",
            files=[
                ("files", ("film-a.mov", b"same-video", "video/quicktime")),
                ("files", ("film-b.mov", b"same-video", "video/quicktime")),
            ],
        )

        assert first.status_code == 201
        first_payload = first.json()
        assert first_payload["saved_count"] == 1
        assert first_payload["skipped_count"] == 1
        assert first_payload["skipped"][0]["reason"] == "duplicate"
        assert first_payload["skipped"][0]["duplicate_of_filename"] == first_payload["saved"][0]["filename"]
        assert session.query(MetaMediaUpload).count() == 1

        second = client.post(
            "/api/meta/uploads",
            files=[("files", ("film-c.mov", b"same-video", "video/quicktime"))],
        )
        assert second.status_code == 201
        second_payload = second.json()
        assert second_payload["saved_count"] == 0
        assert second_payload["skipped_count"] == 1
        assert second_payload["skipped"][0]["duplicate_of_id"] is not None
        assert session.query(MetaMediaUpload).count() == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_meta_upload_rejects_non_media_files():
    engine, session = make_session()
    fake_request = SimpleNamespace(client=SimpleNamespace(host="test-client"))
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                meta_uploads.upload_meta_media(
                    request=fake_request,
                    background_tasks=BackgroundTasks(),
                    files=[make_upload("anteckning.txt", b"text", "text/plain")],
                    db=session,
                )
            )

        assert exc_info.value.status_code == 400
        assert session.query(MetaMediaUpload).count() == 0
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_super_user_can_list_meta_uploads_and_stream_content():
    engine, session = make_session()
    row = MetaMediaUpload(
        batch_id="batch",
        original_filename="semesterfilm.mov",
        stored_filename="20260531_120102_123456Z_01.mov",
        content_type="video/quicktime",
        media_type="video",
        size_bytes=11,
        duration_seconds=65.1,
        storage_backend="filesystem",
        storage_key=store_bytes(b"hello-video", ".mov"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    def override_get_db():
        yield session

    def super_user():
        return User(id=99, username="root", role="super_user", roles=["super_user"], is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = super_user
    try:
        client = TestClient(app)
        response = client.get("/api/meta/uploads")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["filename"] == "20260531_120102_123456Z_01.mov"
        assert item["original_filename"] == "semesterfilm.mov"
        assert item["media_type"] == "video"
        assert item["duration_seconds"] == 65.1
        assert item["duration_label"] == "1:05"

        content = client.get(f"/api/meta/uploads/{row.id}/content", headers={"Range": "bytes=0-4"})
        assert content.status_code == 206
        assert content.content == b"hello"
        assert content.headers["content-range"] == "bytes 0-4/11"
        assert content.headers["content-disposition"].startswith("inline;")
        assert "20260531_120102_123456Z_01.mov" in content.headers["content-disposition"]

        head = client.head(f"/api/meta/uploads/{row.id}/content?download=1")
        assert head.status_code == 200
        assert head.content == b""
        assert head.headers["content-type"].startswith("video/quicktime")
        assert head.headers["content-length"] == "11"
        assert head.headers["content-disposition"].startswith("attachment;")

        download = client.get(f"/api/meta/uploads/{row.id}/content?download=1", headers={"Range": "bytes=0-4"})
        assert download.status_code == 206
        assert download.content == b"hello"
        assert download.headers["content-disposition"].startswith("attachment;")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_meta_video_content_response_normalizes_audio_mime_from_upload_client():
    engine, session = make_session()
    row = MetaMediaUpload(
        batch_id="batch-audio-mime",
        original_filename="metavideo.mp4",
        stored_filename="20260531_120102_123456Z_01.mp4",
        content_type="audio/mp4",
        media_type="video",
        size_bytes=11,
        duration_seconds=65.1,
        storage_backend="filesystem",
        storage_key=store_bytes(b"hello-video", ".mp4"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    def override_get_db():
        yield session

    def super_user():
        return User(id=99, username="root", role="super_user", roles=["super_user"], is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = super_user
    try:
        client = TestClient(app)
        content = client.get(f"/api/meta/uploads/{row.id}/content")

        assert content.status_code == 200
        assert content.content == b"hello-video"
        assert content.headers["content-type"].startswith("video/mp4")
        assert "20260531_120102_123456Z_01.mp4" in content.headers["content-disposition"]

        ranged = client.get(f"/api/meta/uploads/{row.id}/content", headers={"Range": "bytes=0-4"})
        assert ranged.status_code == 206
        assert ranged.headers["content-type"].startswith("video/mp4")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_public_meta_upload_normalizes_audio_mp4_content_type_for_video_filename():
    engine, session = make_session()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/meta/uploads",
            files=[("files", ("film.mp4", b"video-bytes", "audio/mp4"))],
        )

        assert response.status_code == 201
        row = session.query(MetaMediaUpload).one()
        assert row.media_type == "video"
        assert row.content_type == "video/mp4"
        assert response.json()["saved"][0]["content_type"] == "video/mp4"
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_meta_video_content_playable_variant_transcodes_to_h264_download(monkeypatch):
    engine, session = make_session()
    row = MetaMediaUpload(
        batch_id="batch-playable",
        original_filename="metavideo.mp4",
        stored_filename="20260531_120102_123456Z_01.mp4",
        content_type="video/mp4",
        media_type="video",
        size_bytes=11,
        duration_seconds=65.1,
        storage_backend="filesystem",
        storage_key=store_bytes(b"source-video", ".mp4"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    def fake_run(command, capture_output, timeout, check):
        Path(command[-1]).write_bytes(b"playable-video")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(meta_uploads, "_resolve_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(meta_uploads.subprocess, "run", fake_run)
    queue_events = []

    class FakeSemaphore:
        def __enter__(self):
            queue_events.append("enter")

        def __exit__(self, exc_type, exc, tb):
            queue_events.append("exit")

    monkeypatch.setattr(meta_uploads, "_PLAYABLE_TRANSCODE_SEMAPHORE", FakeSemaphore())

    def override_get_db():
        yield session

    def super_user():
        return User(id=99, username="root", role="super_user", roles=["super_user"], is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = super_user
    try:
        client = TestClient(app)
        content = client.get(f"/api/meta/uploads/{row.id}/content?variant=playable")

        assert content.status_code == 200
        assert content.content == b"playable-video"
        assert content.headers["content-type"].startswith("video/mp4")
        assert "20260531_120102_123456Z_01.mp4" in content.headers["content-disposition"]
        assert queue_events == ["enter", "exit"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_super_user_can_list_and_request_meta_shipment_analysis_without_configuration(monkeypatch):
    monkeypatch.setattr(meta_uploads, "meta_analysis_configured", lambda: False)
    engine, session = make_session()
    row = MetaMediaUpload(
        batch_id="batch",
        original_filename="etikettfilm.mov",
        stored_filename="20260531_120102_123456Z_01.mov",
        content_type="video/quicktime",
        media_type="video",
        size_bytes=11,
        duration_seconds=75.4,
        content_hash="b" * 64,
        storage_backend="filesystem",
        storage_key=store_bytes(b"hello-video", ".mov"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    shipment = MetaShipmentObservation(
        media_upload_id=row.id,
        video_hash=row.content_hash,
        record_hash="c" * 64,
        order_number=None,
        shipment_number=None,
        username=None,
        customer_name=None,
        pallet_id="PALL-1",
        deviations=["Dåligt byggd pall"],
        analysis_status="manual_review",
    )
    session.add(shipment)
    session.commit()

    def override_get_db():
        yield session

    def super_user():
        return User(id=99, username="root", role="super_user", roles=["super_user"], is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = super_user
    try:
        client = TestClient(app)
        response = client.get("/api/meta/shipment-observations")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["order_number"] is None
        assert item["shipment_number"] is None
        assert item["username"] is None
        assert item["customer_name"] is None
        assert item["pallet_id"] == "PALL-1"
        assert item["deviations"] == ["Dåligt byggd pall"]
        assert item["video_url"] == f"/api/meta/uploads/{row.id}/content"
        assert item["video_filename"] == "20260531_120102_123456Z_01.mov"
        assert item["video_duration_seconds"] == 75.4
        assert item["video_duration_label"] == "1:15"
        assert item["created_at"]
        assert item["updated_at"]

        analysis = client.post(f"/api/meta/uploads/{row.id}/analyze")
        assert analysis.status_code == 200
        assert analysis.json()["status"] == "needs_configuration"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_super_user_can_export_meta_shipment_observations_excel():
    engine, session = make_session()
    row = MetaMediaUpload(
        batch_id="batch-export",
        original_filename="etikettfilm.mov",
        stored_filename="20260531_120102_123456Z_01.mov",
        content_type="video/quicktime",
        media_type="video",
        size_bytes=11,
        duration_seconds=75.4,
        content_hash="b" * 64,
        storage_backend="filesystem",
        storage_key=store_bytes(b"hello-video", ".mov"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    shipment = MetaShipmentObservation(
        media_upload_id=row.id,
        video_hash=row.content_hash,
        record_hash="c" * 64,
        order_number="100001",
        shipment_number="RIG-REF-1",
        username="LOTS01",
        customer_name="Kund AB",
        pallet_id="PALL-1",
        deviations=["D\u00e5ligt byggd pall"],
        analysis_status="manual_review",
        uncertainty_notes="Kontrollera",
    )
    session.add(shipment)
    session.commit()
    session.refresh(shipment)

    def override_get_db():
        yield session

    def super_user():
        return User(id=99, username="root", role="super_user", roles=["super_user"], is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = super_user
    try:
        client = TestClient(app)
        response = client.get(f"/api/meta/shipment-observations/export?ids={shipment.id}")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        workbook = load_workbook(io.BytesIO(response.content), read_only=True, data_only=True)
        sheet = workbook.active
        assert [cell.value for cell in sheet[1]][:7] == [
            "Ordernummer",
            "S\u00e4ndningsnummer",
            "Anv\u00e4ndarnamn",
            "Kund",
            "Pall-ID",
            "Avvikelser",
            "Status",
        ]
        values = [cell.value for cell in sheet[2]]
        assert values[:8] == [
            "100001",
            "RIG-REF-1",
            "LOTS01",
            "Kund AB",
            "PALL-1",
            "D\u00e5ligt byggd pall",
            "manual_review",
            "Kontrollera",
        ]
        assert values[9] == "20260531_120102_123456Z_01.mov"
        assert values[10] == "1:15"
        assert values[12] == "c" * 64
        workbook.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_super_user_can_delete_meta_uploads_and_audit_without_blob():
    engine, session = make_session()
    row = MetaMediaUpload(
        batch_id="batch-delete",
        original_filename="lagerbild.jpg",
        stored_filename="20260531_120102_123456Z_01.jpg",
        content_type="image/jpeg",
        media_type="image",
        size_bytes=10,
        content_hash="a" * 64,
        storage_backend="filesystem",
        storage_key=store_bytes(b"image-data", ".jpg"),
        status="pending_analysis",
        source="public_upload",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    upload_id = row.id

    def override_get_db():
        yield session

    def super_user():
        return User(id=99, username="root", role="super_user", roles=["super_user"], is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = super_user
    try:
        client = TestClient(app)
        response = client.delete(f"/api/meta/uploads/{upload_id}")

        assert response.status_code == 204
        assert session.get(MetaMediaUpload, upload_id) is None
        audit = session.query(AuditLog).filter_by(entity_type="meta_media_upload", action="delete").one()
        assert audit.entity_id == upload_id
        assert audit.old_value["filename"] == "20260531_120102_123456Z_01.jpg"
        assert audit.old_value["content_hash"] == "a" * 64
        assert "data" not in audit.old_value
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_non_super_user_cannot_list_meta_uploads(monkeypatch):
    monkeypatch.setattr(settings, "SUPER_USER_USERNAMES", "admin,emikad")
    engine, session = make_session()

    def override_get_db():
        yield session

    def admin_user():
        return User(id=100, username="regular-admin", role="admin", roles=["admin"], is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = admin_user
    try:
        client = TestClient(app)
        response = client.get("/api/meta/uploads")
        assert response.status_code == 403
        delete_response = client.delete("/api/meta/uploads/1")
        assert delete_response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
