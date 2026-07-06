"""Tester för apphjälpens ekonomi-tool finance_summary (nattpass 2026-07-06).

Pengamatten ägs av build_business_summary_payload (samma som Produktivitets
periodöversikt) och testas där; här testas tool-kontraktet: behörighetsgaten,
trimmad payload och argumentvalidering. Patchar implementationsmodulerna,
inte fasaden.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend import assistant_tools
from app.backend.database import Base
from app.backend.models import Business, User
from app.backend.routers import productivity_finance_helpers, productivity_helpers


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
    session.add(stigamo)
    session.flush()
    leader = User(username="ledare", role="leader", roles=["leader"], business_id=stigamo.id, is_active=True)
    root = User(username="root", role="super_user", roles=["super_user"], business_id=stigamo.id, is_active=True)
    session.add_all([leader, root])
    session.commit()
    return {"stigamo": stigamo, "leader": leader, "root": root}


CANNED_PAYLOAD = {
    "generated_at": "2026-07-06T22:00:00",
    "business": {"id": 1, "code": "STIGAMO"},
    "period": {"type": "day", "label": "Dag", "start_date": "2026-07-06", "end_date": "2026-07-06",
               "requested_days": 1, "days_with_data": 1},
    "finance_visible": True,
    "currency": "SEK",
    "companies": [
        {"company": "GG", "revenue": 1000.0, "cost": 400.0, "result": 600.0,
         "vas_revenue": 0.0, "process_revenue": 0.0, "work_minutes": 480}
    ],
    "totals": {"revenue": 1000.0, "cost": 400.0, "result": 600.0},
    "source_status": [{"date": "2026-07-06", "status": "ok"}],
    "missing_dates": ["2026-07-05"],
    "errors": [],
}


def test_registry_metadata_requires_finance_view():
    tool = assistant_tools.tool_by_name("finance_summary")
    assert tool is not None
    assert tool.view_id == "productivityFinance"
    assert tool.min_level == "view"


def test_finance_summary_denied_without_view_access(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        monkeypatch.setattr(
            productivity_finance_helpers, "_can_view_productivity_finance", lambda db, user: False
        )
        result = assistant_tools.run_tool(session, data["leader"], "finance_summary", {})
        assert "behörighet" in result["error"]
    finally:
        session.close()
        engine.dispose()


def test_finance_summary_trims_payload_for_super_user(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        captured = {}

        def fake_builder(db, user, *, period, anchor_date, start_date, end_date):
            captured.update(period=period, anchor_date=anchor_date, start_date=start_date, end_date=end_date)
            return dict(CANNED_PAYLOAD)

        monkeypatch.setattr(productivity_helpers, "build_business_summary_payload", fake_builder)
        payload = assistant_tools.run_tool(
            session, data["root"], "finance_summary", {"period": "day", "date": "2026-07-06"}
        )
        assert "error" not in payload, payload
        result = payload["result"]
        assert captured["period"] == "day"
        assert result["totals"]["result"] == 600.0
        assert result["companies"][0]["company"] == "GG"
        assert result["missing_dates_count"] == 1
        assert result["errors_count"] == 0
        # Trimmningen: inga råa source_status/missing_dates-listor till modellen.
        assert "source_status" not in result
        assert "missing_dates" not in result
    finally:
        session.close()
        engine.dispose()


def test_finance_summary_hides_when_context_invisible(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        hidden = dict(CANNED_PAYLOAD, finance_visible=False)
        monkeypatch.setattr(
            productivity_helpers, "build_business_summary_payload",
            lambda db, user, **kwargs: hidden,
        )
        result = assistant_tools.run_tool(session, data["root"], "finance_summary", {})
        assert "inte synligt" in result["error"]
    finally:
        session.close()
        engine.dispose()


def test_finance_summary_validates_arguments(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        bad_period = assistant_tools.run_tool(
            session, data["root"], "finance_summary", {"period": "quarter"}
        )
        assert "Ogiltig period" in bad_period["error"]

        too_long = assistant_tools.run_tool(
            session, data["root"], "finance_summary",
            {"period": "custom", "start_date": "2026-01-01", "end_date": "2026-06-30"},
        )
        assert "högst 92" in too_long["error"]
    finally:
        session.close()
        engine.dispose()
