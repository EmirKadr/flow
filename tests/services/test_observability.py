from fastapi.testclient import TestClient

from app.backend.main import app
from app.backend.observability import (
    attach_trace_context,
    begin_request_trace,
    current_trace_id,
    end_request_trace,
    trace_id_from_traceparent,
)


TRACE_ID = "1234567890abcdef1234567890abcdef"
SPAN_ID = "1234567890abcdef"


def test_traceparent_parsing_and_context_attachment():
    traceparent = f"00-{TRACE_ID}-{SPAN_ID}-01"
    assert trace_id_from_traceparent(traceparent) == TRACE_ID

    token = begin_request_trace({"traceparent": traceparent})
    try:
        assert current_trace_id() == TRACE_ID
        assert attach_trace_context({"status": "error"}) == {
            "status": "error",
            "trace_id": TRACE_ID,
        }
    finally:
        end_request_trace(token)


def test_health_response_exposes_trace_id_header():
    client = TestClient(app)
    response = client.get("/api/health", headers={"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01"})

    assert response.status_code == 200
    assert response.headers["x-flow-trace-id"] == TRACE_ID
