from pathlib import Path
import logging

from fastapi.testclient import TestClient

from app.backend.config import settings
from app.backend import main as main_module
from app.backend.main import app
from app.backend.observability import (
    _logs_endpoint,
    attach_trace_context,
    begin_request_trace,
    current_operation_id,
    current_trace_id,
    emit_flow_event,
    end_request_trace,
    safe_event_attributes,
    safe_span_attributes,
    trace_id_from_traceparent,
)


TRACE_ID = "1234567890abcdef1234567890abcdef"
SPAN_ID = "1234567890abcdef"
ROOT = Path(__file__).resolve().parents[2]


def test_traceparent_parsing_and_context_attachment():
    traceparent = f"00-{TRACE_ID}-{SPAN_ID}-01"
    assert trace_id_from_traceparent(traceparent) == TRACE_ID

    token = begin_request_trace({"traceparent": traceparent})
    try:
        assert current_trace_id() == TRACE_ID
        assert current_operation_id() == TRACE_ID
        assert attach_trace_context({"status": "error"}) == {
            "status": "error",
            "trace_id": TRACE_ID,
            "operation_id": TRACE_ID,
        }
    finally:
        end_request_trace(token)


def test_health_response_exposes_trace_and_operation_headers():
    client = TestClient(app)
    response = client.get("/api/health", headers={"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01"})

    assert response.status_code == 200
    assert response.headers["x-flow-trace-id"] == TRACE_ID
    assert response.headers["x-flow-operation-id"] == TRACE_ID


def test_operation_header_is_normalized_and_returned():
    client = TestClient(app)
    response = client.get(
        "/api/health",
        headers={
            "traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01",
            "x-flow-operation-id": "flow-debug-123456",
        },
    )

    assert response.status_code == 200
    assert response.headers["x-flow-trace-id"] == TRACE_ID
    assert response.headers["x-flow-operation-id"] == "flow-debug-123456"


def test_request_observability_log_is_sanitized(monkeypatch):
    events = []

    def capture_event(name, **kwargs):
        events.append({"name": name, **kwargs})

    monkeypatch.setattr(settings, "OTEL_REQUEST_LOG_ENABLED", True)
    monkeypatch.setattr(main_module, "emit_flow_event", capture_event)

    client = TestClient(app)
    response = client.get("/api/unknown?token=secret")

    assert response.status_code == 404
    event = next(row for row in events if row.get("event_alias") == "http_request")
    assert event["name"] == "flow.http.request"
    assert event["outcome"] == "blocked"
    assert event["attributes"]["http_method"] == "GET"
    assert event["attributes"]["http_route"] == "/api/unknown"
    assert event["attributes"]["http_status_code"] == 404
    assert "token=secret" not in event["message"]


def test_flow_events_keep_operation_id_and_sanitize_attributes(caplog):
    token = begin_request_trace(
        {
            "traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01",
            "x-flow-operation-id": "seq-debug-123456",
        }
    )
    try:
        caplog.set_level(logging.INFO, logger="tests.flow_event")
        emit_flow_event(
            "flow.test.event",
            feature="tests",
            outcome="ok",
            logger_=logging.getLogger("tests.flow_event"),
            attributes={
                "page_path": "/bearbeta.html?token=secret",
                "request_body": {"token": "secret"},
                "duration_ms": 12.5,
            },
        )
    finally:
        end_request_trace(token)

    record = next(row for row in caplog.records if getattr(row, "event_name", "") == "flow.test.event")
    assert record.feature == "tests"
    assert record.outcome == "ok"
    assert record.operation_id == "seq-debug-123456"
    assert record.__dict__["operation.id"] == "seq-debug-123456"
    assert record.page_path == "/bearbeta.html"
    assert not hasattr(record, "request_body")
    assert "secret" not in record.getMessage()


def test_otlp_logs_endpoint_defaults_from_trace_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "")

    assert _logs_endpoint("https://seq.example/ingest/otlp/v1/traces") == (
        "https://seq.example/ingest/otlp/v1/logs"
    )


def test_flow_route_span_attributes_are_allowed():
    assert safe_span_attributes({"flow.http_route": "/api/allokering/flows"}) == {
        "flow.http_route": "/api/allokering/flows"
    }


def test_flow_event_route_attributes_strip_query_secrets():
    assert safe_event_attributes(
        {
            "http_route": "/api/allokering/flows?token=secret",
            "request_body": "secret",
            "duration_ms": 41,
        }
    ) == {
        "http_route": "/api/allokering/flows",
        "duration_ms": 41,
    }


def test_k8s_seq_observability_contract():
    manifest = (ROOT / "k8s" / "flow.yml").read_text(encoding="utf-8")

    assert "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" in manifest
    assert "#{OPENTELEMETRY_URL}/v1/logs" in manifest
    assert "OTEL_LOGS_ENABLED" in manifest
    assert "OTEL_REQUEST_LOG_ENABLED" in manifest
    assert '- name: OTEL_SQLALCHEMY_ENABLED\n              value: "false"' in manifest


def test_high_value_flow_events_are_declared():
    allocation = (ROOT / "app" / "backend" / "routers" / "allocation.py").read_text(encoding="utf-8")
    data_fetch = (ROOT / "app" / "backend" / "routers" / "data_fetch.py").read_text(encoding="utf-8")
    meta_uploads = (ROOT / "app" / "backend" / "routers" / "meta_uploads.py").read_text(encoding="utf-8")

    assert '"flow.allocation.run"' in allocation
    assert 'event_alias="allocation_run"' in allocation
    assert '"flow.data_fetch.run"' in data_fetch
    assert 'event_alias="data_fetch_run"' in data_fetch
    assert '"flow.meta.upload"' in meta_uploads
    assert 'event_alias="meta_upload"' in meta_uploads
    assert '"flow.meta.analyze"' in meta_uploads
    assert 'event_alias="meta_analyze"' in meta_uploads
    for source in (allocation, data_fetch, meta_uploads):
        assert 'outcome="started"' in source
        assert 'outcome="ok"' in source
        assert '"duration_ms"' in source
