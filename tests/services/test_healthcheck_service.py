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


def test_healthcheck_reports_sqlite_database_without_render():
    engine, db = make_session()
    try:
        report = run_healthcheck(db=db, include_render=False)
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert report["status"] in {"ok", "info"}
    assert report["database"]["connected"] is True
    assert report["database"]["dialect"] == "sqlite"
    assert any(item["name"] == "Databas" for item in report["checks"])


def test_healthcheck_can_skip_database_for_render_only_diagnostics():
    report = run_healthcheck(db=None, include_render=False)

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


def test_healthcheck_redacts_secret_like_text():
    assert "secret[redacted]" in clean_text("secret=abc123")
    assert "abc123" not in clean_text("token=abc123")
