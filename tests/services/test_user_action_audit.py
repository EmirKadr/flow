import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import AuditLog, Business, User
from app.backend.routers import allocation, audit_logs, productivity
from app.backend.schemas import AuditClientErrorIn


class FakeAuditDb:
    def __init__(self):
        self.items = []
        self.committed = False
        self.rolled_back = False

    def add(self, item):
        self.items.append(item)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


@pytest.fixture
def audit_db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_productivity_upload_audit_omits_file_names():
    db = FakeAuditDb()
    user = SimpleNamespace(id=42)

    productivity._audit_productivity_files(
        db,
        user,
        action="upload",
        attempted_count=1,
        saved=[{"key": "kpi", "name": "kund-hemlig.csv"}],
        unknown=["privat-underlag.csv"],
    )

    assert db.committed is True
    entry = db.items[0]
    assert isinstance(entry, AuditLog)
    assert entry.entity_type == "productivity_file"
    assert entry.action == "upload"
    assert entry.user_id == 42
    assert entry.new_value == {
        "saved_types": ["kpi"],
        "saved_count": 1,
        "unknown_count": 1,
        "attempted_count": 1,
    }
    payload = json.dumps(entry.new_value, ensure_ascii=False)
    assert "kund-hemlig" not in payload
    assert "privat-underlag" not in payload


def test_productivity_failed_upload_audit_omits_file_names():
    db = FakeAuditDb()
    user = SimpleNamespace(id=42)

    productivity._audit_productivity_files(
        db,
        user,
        action="upload_failed",
        attempted_count=2,
        saved=[{"key": "pick", "name": "kund-plock.csv"}],
        unknown=["privat-underlag.csv"],
        error_type="OSError",
    )

    entry = db.items[0]
    assert entry.entity_type == "productivity_file"
    assert entry.action == "upload_failed"
    assert entry.new_value == {
        "saved_types": ["pick"],
        "saved_count": 1,
        "unknown_count": 1,
        "attempted_count": 2,
        "error_type": "OSError",
    }
    payload = json.dumps(entry.new_value, ensure_ascii=False)
    assert "kund-plock" not in payload
    assert "privat-underlag" not in payload


def test_productivity_endpoint_logs_failed_upload(monkeypatch):
    db = FakeAuditDb()
    user = SimpleNamespace(id=42)

    async def fail_save_upload(_upload):
        raise OSError("disk full")

    monkeypatch.setattr(productivity, "_save_upload_temp", fail_save_upload)

    with pytest.raises(OSError):
        asyncio.run(
            productivity.upload_productivity_files(
                SimpleNamespace(session={}),
                [SimpleNamespace(filename="privat.csv")],
                user,
                db,
            )
        )

    entry = db.items[0]
    assert entry.entity_type == "productivity_file"
    assert entry.action == "upload_failed"
    assert entry.new_value == {
        "saved_types": [],
        "saved_count": 0,
        "unknown_count": 0,
        "attempted_count": 1,
        "error_type": "OSError",
    }


def test_allocation_flow_audit_payload_omits_file_and_param_values():
    payload = allocation._flow_audit_payload(
        "split-values",
        files={"orders": "C:/hemlig/kundorder.xlsx"},
        params={"values": "A\nB\nC"},
        result={"tables": [{"key": "report"}], "session_id": "abc"},
    )

    assert payload == {
        "flow_id": "split-values",
        "file_keys": ["orders"],
        "param_keys": ["values"],
        "table_count": 1,
        "has_session": True,
    }
    text = json.dumps(payload, ensure_ascii=False)
    assert "kundorder.xlsx" not in text
    assert "A\\nB" not in text


def test_allocation_flow_failed_payload_includes_error_context_without_values():
    payload = allocation._flow_audit_payload(
        "forecast",
        files={"orders": "C:/hemlig/kundorder.xlsx"},
        params={"secret_value": "A\nB\nC"},
        area_focus="MG",
        business_code="R3",
        filter_log=["orders: 10 -> 0 rader (Bolag, Kundnr)."],
        path="/api/allokering/flow/forecast",
        error_type="ValueError",
        error_code="allocation_flow_failed",
        status_code=400,
        message="Flödet fick inga rader att sammanställa.",
        technical_message="No objects to concatenate",
    )

    assert payload == {
        "flow_id": "forecast",
        "file_keys": ["orders"],
        "param_keys": ["secret_value"],
        "area_focus": "MG",
        "business_code": "R3",
        "filter_log": ["orders: 10 -> 0 rader (Bolag, Kundnr)."],
        "path": "/api/allokering/flow/forecast",
        "error_type": "ValueError",
        "error_code": "allocation_flow_failed",
        "status_code": 400,
        "message": "Flödet fick inga rader att sammanställa.",
        "technical_message": "No objects to concatenate",
    }
    text = json.dumps(payload, ensure_ascii=False)
    assert "kundorder.xlsx" not in text
    assert "A\\nB" not in text


def test_allocation_upload_failure_payload_omits_file_and_param_values():
    payload = allocation._upload_failure_payload(
        flow_id="allocate",
        stage="parse_upload",
        error_type="OSError",
        status_code=400,
    )

    assert payload == {
        "stage": "parse_upload",
        "error_type": "OSError",
        "flow_id": "allocate",
        "status_code": 400,
    }
    text = json.dumps(payload, ensure_ascii=False)
    assert "kundorder.xlsx" not in text
    assert "A\\nB" not in text


def test_allocation_endpoint_logs_failed_upload_parse():
    db = FakeAuditDb()
    user = SimpleNamespace(id=43, role="warehouse_clerk", roles=["warehouse_clerk"])

    class FailingRequest:
        async def form(self):
            raise OSError("multipart failed")

    with pytest.raises(OSError):
        asyncio.run(allocation.run_flow("split-values", FailingRequest(), user, db))

    entry = db.items[0]
    assert entry.entity_type == "allocation_flow"
    assert entry.action == "upload_failed"
    assert entry.new_value == {
        "stage": "parse_upload",
        "error_type": "OSError",
        "flow_id": "split-values",
        "message": "multipart failed",
    }


def test_client_error_report_writes_sanitized_audit_event(audit_db_session):
    business = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    audit_db_session.add(business)
    audit_db_session.flush()
    user = User(
        username="admin",
        display_name="Admin",
        role="super_user",
        roles=["super_user"],
        business_id=business.id,
        is_active=True,
    )
    audit_db_session.add(user)
    audit_db_session.commit()
    audit_db_session.refresh(user)

    response = audit_logs.report_client_error(
        AuditClientErrorIn(
            path="/api/persons?token=secret",
            method="put",
            status=500,
            error_code="HTTP 500",
            message="Kunde inte spara",
            detail={"message": "Serverfel", "token": "secret"},
            page_path="/personer.html?token=secret",
        ),
        db=audit_db_session,
        user=user,
    )

    entry = audit_db_session.query(AuditLog).filter_by(entity_type="client_error").one()
    assert response.status_code == 204
    assert entry.business_id == business.id
    assert entry.user_id == user.id
    assert entry.entity_id == 500
    assert entry.action == "client_error"
    assert entry.new_value == {
        "path": "/api/persons",
        "method": "PUT",
        "status_code": 500,
        "error_code": "HTTP 500",
        "message": "Kunde inte spara",
        "detail": "Serverfel",
        "page_path": "/personer.html",
    }
    assert "secret" not in json.dumps(entry.new_value, ensure_ascii=False)


def test_audit_errors_groups_client_and_failed_events(audit_db_session):
    business = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    audit_db_session.add(business)
    audit_db_session.flush()
    user = User(
        username="admin",
        display_name="Admin",
        role="super_user",
        roles=["super_user"],
        business_id=business.id,
        is_active=True,
    )
    audit_db_session.add(user)
    audit_db_session.flush()
    now = datetime.now(timezone.utc)
    audit_db_session.add_all(
        [
            AuditLog(
                business_id=business.id,
                entity_type="client_error",
                entity_id=500,
                action="client_error",
                old_value=None,
                new_value={
                    "path": "/api/persons",
                    "method": "PUT",
                    "status_code": 500,
                    "error_code": "HTTP 500",
                    "message": "Kunde inte spara",
                },
                user_id=user.id,
                created_at=now,
            ),
            AuditLog(
                business_id=business.id,
                entity_type="productivity_file",
                entity_id=0,
                action="upload_failed",
                old_value=None,
                new_value={"error_type": "OSError", "status_code": 400},
                user_id=user.id,
                created_at=now,
            ),
            AuditLog(
                business_id=business.id,
                entity_type="person",
                entity_id=1,
                action="update",
                old_value={"name": "A"},
                new_value={"name": "B"},
                user_id=user.id,
                created_at=now,
            ),
        ]
    )
    audit_db_session.commit()

    summary = audit_logs.audit_errors(
        limit=100,
        scan_limit=5000,
        user_id=None,
        entity_type=None,
        action=None,
        entity_id=None,
        from_at=None,
        to_at=None,
        db=audit_db_session,
        _=user,
    )

    assert summary.total_errors == 2
    assert summary.events_last_24h == 2
    assert summary.unique_users == 1
    assert summary.truncated is False
    assert {bucket.label for bucket in summary.top_error_codes} == {"HTTP 500", "OSError"}
    assert {bucket.label for bucket in summary.top_actions} == {"client_error", "upload_failed"}
    assert any(bucket.label == "/api/persons" for bucket in summary.top_paths)
    assert {event.action for event in summary.recent} == {"client_error", "upload_failed"}
