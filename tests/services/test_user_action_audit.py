import asyncio
import json
from types import SimpleNamespace

import pytest

from app.backend.models import AuditLog
from app.backend.routers import allocation, productivity


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
    }
