"""Tester för apphjälpens nya Historik-/fel-tools (nattpass 2026-07-06).

Täcker: error_trend, error_top_endpoints, audit_entity_history,
wait_metrics_by_endpoint, user_activity_summary, rfid_error_summary.
Fokus: verksamhetsscope, felvägar och deterministisk aggregering.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend import assistant_tools
from app.backend.database import Base
from app.backend.models import (
    AuditLog,
    Business,
    RfidScanEvent,
    User,
    UserInteractionEvent,
    UserWaitMetric,
)

NOW = datetime.now(timezone.utc)


def make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def seed(session):
    stigamo = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    r3 = Business(code="R3", name="R3", sort_order=2)
    session.add_all([stigamo, r3])
    session.flush()
    leader = User(username="ledare", role="leader", roles=["leader"], business_id=stigamo.id, is_active=True)
    root = User(username="root", role="super_user", roles=["super_user"], business_id=stigamo.id, is_active=True)
    r3_user = User(username="r3ledare", role="leader", roles=["leader"], business_id=r3.id, is_active=True)
    session.add_all([leader, root, r3_user])
    session.flush()

    # Audit: två fel i Stigamo (olika dagar), ett fel i R3, en vanlig update.
    session.add_all(
        [
            AuditLog(
                business_id=stigamo.id, entity_type="import", entity_id=1,
                action="import_failed", user_id=leader.id,
                created_at=NOW - timedelta(hours=2),
            ),
            AuditLog(
                business_id=stigamo.id, entity_type="import", entity_id=2,
                action="sync_error", user_id=leader.id,
                created_at=NOW - timedelta(days=1, hours=2),
            ),
            AuditLog(
                business_id=r3.id, entity_type="import", entity_id=3,
                action="import_failed", user_id=r3_user.id,
                created_at=NOW - timedelta(hours=3),
            ),
            AuditLog(
                business_id=stigamo.id, entity_type="person", entity_id=7,
                action="update", user_id=leader.id,
                old_value={"name": "Gamla Namnet"}, new_value={"name": "Nya Namnet"},
                created_at=NOW - timedelta(hours=4),
            ),
            AuditLog(
                business_id=stigamo.id, entity_type="person", entity_id=7,
                action="create", user_id=root.id,
                new_value={"name": "Gamla Namnet"},
                created_at=NOW - timedelta(hours=5),
            ),
        ]
    )
    # Väntetider: fyra ok-mätningar mot samma mål + två fel mot annat mål.
    for duration in (100, 200, 300, 400):
        session.add(
            UserWaitMetric(
                business_id=stigamo.id, user_id=leader.id, event_type="api",
                view_id="schedule", target="/api/schedule", duration_ms=duration,
                status="ok", created_at=NOW - timedelta(hours=1),
            )
        )
    for _ in range(2):
        session.add(
            UserWaitMetric(
                business_id=stigamo.id, user_id=leader.id, event_type="api",
                view_id="productivity", target="/api/productivity", duration_ms=900,
                status="error", created_at=NOW - timedelta(hours=1),
            )
        )
    session.add(
        UserWaitMetric(
            business_id=r3.id, user_id=r3_user.id, event_type="api",
            view_id="schedule", target="/api/schedule", duration_ms=50,
            status="error", created_at=NOW - timedelta(hours=1),
        )
    )
    # Interaktioner: två klick i schedule för ledaren, ett fel-event.
    session.add_all(
        [
            UserInteractionEvent(
                business_id=stigamo.id, user_id=leader.id, event_type="click",
                view_id="schedule", control_id="btn_save", control_label="Spara",
                status="ok", created_at=NOW - timedelta(hours=1),
            ),
            UserInteractionEvent(
                business_id=stigamo.id, user_id=leader.id, event_type="click",
                view_id="schedule", control_id="btn_copy", control_label="Kopiera",
                status="ok", created_at=NOW - timedelta(hours=1),
            ),
            UserInteractionEvent(
                business_id=stigamo.id, user_id=leader.id, event_type="api_result",
                view_id="schedule", control_id="btn_save", control_label="Spara",
                status="error", created_at=NOW - timedelta(hours=1),
            ),
        ]
    )
    # RFID: en applied, två pending på samma modul, en ignorerad i R3.
    session.add_all(
        [
            RfidScanEvent(
                business_id=stigamo.id, device_identifier="esp-1", module_name="MG_Plock",
                tag_code="AA11", status="applied", scan_time=NOW - timedelta(hours=1),
            ),
            RfidScanEvent(
                business_id=stigamo.id, device_identifier="esp-1", module_name="MG_Plock",
                tag_code="BB22", status="pending", scan_time=NOW - timedelta(hours=1),
            ),
            RfidScanEvent(
                business_id=stigamo.id, device_identifier="esp-1", module_name="MG_Plock",
                tag_code="CC33", status="pending", scan_time=NOW - timedelta(hours=1),
            ),
            RfidScanEvent(
                business_id=r3.id, device_identifier="esp-9", module_name="R3_VM",
                tag_code="DD44", status="ignored", scan_time=NOW - timedelta(hours=1),
            ),
        ]
    )
    session.commit()
    return {"stigamo": stigamo, "r3": r3, "leader": leader, "root": root, "r3_user": r3_user}


def run(session, user, name, args=None):
    payload = assistant_tools.run_tool(session, user, name, args or {})
    assert "error" not in payload, payload
    return payload["result"]


def test_error_trend_counts_sources_and_respects_scope():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(session, data["leader"], "error_trend", {"period": "7d"})
        # Stigamo: 2 audit-fel, 2 wait-fel, 1 interaktionsfel = 5. R3-felen syns inte.
        assert result["total"] == 5
        assert sum(day["audit"] for day in result["days"]) == 2
        assert sum(day["waits"] for day in result["days"]) == 2
        assert sum(day["interactions"] for day in result["days"]) == 1
        assert [day["date"] for day in result["days"]] == sorted(day["date"] for day in result["days"])

        # Super user utan verksamhetsfilter ser globalt: +1 audit-fel och +1 wait-fel från R3.
        result_root = run(session, data["root"], "error_trend", {"period": "7d", "business": ""})
        assert result_root["total"] == 7
    finally:
        session.close()
        engine.dispose()


def test_error_top_endpoints_orders_by_count():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(session, data["leader"], "error_top_endpoints", {"period": "7d"})
        assert result["endpoints"][0] == {
            "view_id": "productivity",
            "target": "/api/productivity",
            "error_count": 2,
        }
        targets = [row["target"] for row in result["endpoints"]]
        assert "/api/schedule" not in targets  # R3-felet är utanför scope, ok-raderna räknas inte
    finally:
        session.close()
        engine.dispose()


def test_audit_entity_history_is_chronological_with_usernames():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(
            session, data["leader"], "audit_entity_history",
            {"entity_type": "person", "entity_id": 7},
        )
        assert result["count"] == 2
        assert [entry["action"] for entry in result["entries"]] == ["create", "update"]
        assert result["entries"][0]["username"] == "root"
        assert "Gamla Namnet" in (result["entries"][1]["old_value"] or "")

        missing = assistant_tools.run_tool(
            session, data["leader"], "audit_entity_history", {"entity_id": 7}
        )
        assert "entity_type" in missing["error"]
    finally:
        session.close()
        engine.dispose()


def test_wait_metrics_by_endpoint_percentiles():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(session, data["leader"], "wait_metrics_by_endpoint", {"period": "24h"})
        schedule = next(row for row in result["endpoints"] if row["target"] == "/api/schedule")
        assert schedule["count"] == 4
        assert schedule["p50_ms"] == 200
        assert schedule["p95_ms"] == 400
        assert schedule["max_ms"] == 400

        filtered = run(
            session, data["leader"], "wait_metrics_by_endpoint",
            {"period": "24h", "target": "productivity"},
        )
        assert all("productivity" in row["target"] for row in filtered["endpoints"])
    finally:
        session.close()
        engine.dispose()


def test_user_activity_summary_scopes_and_errors():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(session, data["leader"], "user_activity_summary", {"username": "ledare"})
        assert result["username"] == "ledare"
        assert result["last_seen"] is not None
        assert any(row["view_id"] == "schedule" for row in result["views_used"])
        assert any(row["action"] == "import_failed" for row in result["audit_actions"])

        # Ledaren kan inte slå upp användare i annan verksamhet.
        outside = assistant_tools.run_tool(
            session, data["leader"], "user_activity_summary", {"username": "r3ledare"}
        )
        assert "error" in outside

        missing = assistant_tools.run_tool(
            session, data["leader"], "user_activity_summary", {}
        )
        assert "error" in missing
    finally:
        session.close()
        engine.dispose()


def test_rfid_error_summary_groups_by_status_and_module():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(session, data["leader"], "rfid_error_summary", {"period": "7d"})
        by_status = {row["status"]: row["count"] for row in result["by_status"]}
        assert by_status == {"pending": 2, "applied": 1}  # R3:s ignorerade syns inte
        assert result["not_applied_by_module"] == [
            {"module": "MG_Plock", "status": "pending", "count": 2}
        ]
    finally:
        session.close()
        engine.dispose()
