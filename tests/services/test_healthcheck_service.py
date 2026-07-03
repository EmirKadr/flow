from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.healthcheck_service import clean_text, run_healthcheck
from app.backend.models import Business, User, UserWaitMetric
from app.backend.routers import healthcheck
from app.backend.schemas import WaitMetricBatchIn, WaitMetricIn


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def test_healthcheck_reports_sqlite_database():
    engine, db = make_session()
    try:
        report = run_healthcheck(db=db)
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert report["status"] in {"ok", "info"}
    assert report["database"]["connected"] is True
    assert report["database"]["dialect"] == "sqlite"
    assert any(item["name"] == "Databas" for item in report["checks"])


def test_healthcheck_can_skip_database():
    report = run_healthcheck(db=None)

    assert report["database"]["skipped"] is True
    assert report["database"]["connected"] is None
    assert any(
        item["name"] == "Databas" and item["status"] == "info"
        for item in report["checks"]
    )
    assert all(item["severity"] != "error" for item in report["recommendations"])


def test_wait_metric_collection_summarizes_slowest_steps():
    engine, db = make_session()
    try:
        business = Business(code="STIGAMO", name="Stigamo")
        db.add(business)
        db.flush()
        user = User(username="admin", password_hash="x", role="admin", business_id=business.id)
        db.add(user)
        db.commit()
        db.refresh(user)

        payload = WaitMetricBatchIn(items=[
            WaitMetricIn(event_type="view_load", view_id="analytics", target="/historik.html", duration_ms=120),
            WaitMetricIn(event_type="api_request", view_id="analytics", target="GET /api/audit", duration_ms=850),
            WaitMetricIn(event_type="background_prefetch", view_id="analytics", target="GET /api/users", duration_ms=40),
        ])
        response = healthcheck.record_wait_metrics(payload=payload, db=db, user=user)
        assert response.status_code == 204

        rows = db.query(UserWaitMetric).all()
        assert len(rows) == 3
        summary = healthcheck.wait_metrics_summary(period="all", limit=100, db=db, _=user)
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert summary["count"] == 3
    assert summary["max_ms"] == 850
    assert summary["by_target"][0]["key"] == "GET /api/audit"
    assert summary["analysis"]


def test_wait_metric_summary_can_filter_by_business():
    engine, db = make_session()
    try:
        stigamo = Business(code="STIGAMO", name="Stigamo")
        r3 = Business(code="R3", name="R3")
        db.add_all([stigamo, r3])
        db.flush()
        user = User(username="root", password_hash="x", role="super_user", business_id=stigamo.id)
        db.add(user)
        db.flush()
        db.add_all([
            UserWaitMetric(
                business_id=stigamo.id,
                user_id=user.id,
                event_type="api_request",
                view_id="analytics",
                target="GET /api/audit",
                duration_ms=100,
                status="ok",
            ),
            UserWaitMetric(
                business_id=r3.id,
                user_id=user.id,
                event_type="api_request",
                view_id="analytics",
                target="GET /api/r3",
                duration_ms=900,
                status="ok",
            ),
        ])
        db.commit()

        summary = healthcheck.wait_metrics_summary(
            period="all",
            limit=100,
            business_id=r3.id,
            user_id=None,
            q=None,
            db=db,
            _=user,
        )
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert summary["count"] == 1
    assert summary["max_ms"] == 900
    assert summary["by_target"][0]["key"] == "GET /api/r3"


def test_wait_metric_summary_surfaces_critical_targets_and_long_tasks():
    engine, db = make_session()
    try:
        business = Business(code="STIGAMO", name="Stigamo")
        db.add(business)
        db.flush()
        user = User(username="root", password_hash="x", role="super_user", business_id=business.id)
        db.add(user)
        db.flush()
        db.add_all([
            UserWaitMetric(
                business_id=business.id,
                user_id=user.id,
                event_type="api_request",
                view_id="myProductivity",
                target="GET /api/personal/productivity",
                duration_ms=9000,
                status="ok",
            ),
            UserWaitMetric(
                business_id=business.id,
                user_id=user.id,
                event_type="api_request",
                view_id="allocationProcess",
                target="GET /api/allokering/process-matrix",
                duration_ms=2200,
                status="ok",
            ),
            UserWaitMetric(
                business_id=business.id,
                user_id=user.id,
                event_type="client_long_task",
                view_id="schedule",
                target="main_thread",
                duration_ms=420,
                status="warn",
            ),
            UserWaitMetric(
                business_id=business.id,
                user_id=user.id,
                event_type="background_prefetch",
                view_id="allocationSettings",
                target="GET /api/allokering/ytgenerering-map-layout",
                duration_ms=180,
                status="ok",
            ),
        ])
        db.commit()

        summary = healthcheck.wait_metrics_summary(
            period="all",
            limit=100,
            business_id=business.id,
            user_id=None,
            q=None,
            db=db,
            _=user,
        )
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()

    targets = {item["key"]: item for item in summary["by_target"]}
    events = {item["key"]: item for item in summary["by_event"]}
    assert summary["slow_events"][0]["target"] == "GET /api/personal/productivity"
    assert targets["GET /api/personal/productivity"]["p95_ms"] == 9000
    assert targets["main_thread"]["max_ms"] == 420
    assert events["client_long_task"]["count"] == 1
    assert any("Klientens huvudtrad" in item["message"] for item in summary["analysis"])
    assert any("Tyngsta steg: GET /api/personal/productivity" in item["message"] for item in summary["analysis"])


def test_healthcheck_redacts_secret_like_text():
    assert "secret[redacted]" in clean_text("secret=abc123")
    assert "abc123" not in clean_text("token=abc123")
