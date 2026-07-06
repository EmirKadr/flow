"""Tester för apphjälpens nya systemstatus-tools (nattpass 2026-07-06).

Täcker: archive_cache_status och data_fetch_catalog.
Arkiv- och produktivitetslagren patchas i implementationsmodulerna;
katalogtoolen körs mot repots riktiga data/external_data_catalog.json.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend import archive_cache_sync, assistant_tools, local_archive_store
from app.backend.data_fetch import catalog as data_fetch_catalog_module
from app.backend.database import Base
from app.backend.models import Business, User
from app.backend.routers import data_fetch as data_fetch_router


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
    session.add(leader)
    session.commit()
    return {"leader": leader}


FAKE_PRODUCTIVITY = {"snapshots": {"days": 12, "first": "2026-06-24", "last": "2026-07-05", "overview_reports": 12}, "backfill": {"state": "idle"}}


def test_archive_cache_status_disabled(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        monkeypatch.setattr(local_archive_store, "is_enabled", lambda: False)
        monkeypatch.setattr(data_fetch_router, "_productivity_build_status", lambda: FAKE_PRODUCTIVITY)
        payload = assistant_tools.run_tool(session, data["leader"], "archive_cache_status", {})
        assert "error" not in payload, payload
        result = payload["result"]
        assert result["enabled"] is False
        assert result["productivity"]["snapshots"]["days"] == 12
    finally:
        session.close()
        engine.dispose()


def test_archive_cache_status_trims_coverage(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        monkeypatch.setattr(local_archive_store, "is_enabled", lambda: True)
        monkeypatch.setattr(data_fetch_router, "_productivity_build_status", lambda: FAKE_PRODUCTIVITY)
        monkeypatch.setattr(
            archive_cache_sync,
            "coverage_report",
            lambda log_limit: {
                "enabled": True,
                "today": "2026-07-06",
                "tenants": [
                    {
                        "tenant": "stigamo",
                        "views": [
                            {
                                "view": "dblog_pick_log",
                                "covered_start": "2026-01-01",
                                "covered_end": "2026-07-05",
                                "missing_days": 0,
                                "fully_covered": True,
                                "target_start": "2025-06-01",  # ska trimmas bort
                                "ingested_start": "2026-01-01",
                            }
                        ],
                        "recent_syncs": [{"noise": "ska inte med"}],
                    }
                ],
            },
        )
        payload = assistant_tools.run_tool(session, data["leader"], "archive_cache_status", {})
        assert "error" not in payload, payload
        result = payload["result"]
        assert result["enabled"] is True
        view = result["tenants"][0]["views"][0]
        assert view == {
            "view": "dblog_pick_log",
            "covered_start": "2026-01-01",
            "covered_end": "2026-07-05",
            "missing_days": 0,
            "fully_covered": True,
        }
        assert "recent_syncs" not in result["tenants"][0]
    finally:
        session.close()
        engine.dispose()


def test_data_fetch_catalog_lists_and_filters():
    engine, session = make_session()
    data = seed(session)
    try:
        payload = assistant_tools.run_tool(session, data["leader"], "data_fetch_catalog", {})
        assert "error" not in payload, payload
        result = payload["result"]
        assert result["total_views"] >= 1
        assert len(result["views"]) <= 30  # kort default så svaret inte slår i teckentaket
        first = result["views"][0]
        assert set(first) == {"id", "label_sv", "columns"}
        assert first["columns"] > 0

        filtered = assistant_tools.run_tool(
            session, data["leader"], "data_fetch_catalog", {"search": first["id"]}
        )["result"]
        assert any(view["id"] == first["id"] for view in filtered["views"])
        assert filtered["total_views"] <= result["total_views"]

        nothing = assistant_tools.run_tool(
            session, data["leader"], "data_fetch_catalog", {"search": "zzz-finns-inte-zzz"}
        )["result"]
        assert nothing["views"] == []
    finally:
        session.close()
        engine.dispose()


def test_data_fetch_catalog_missing_catalog(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        from app.backend.data_fetch.core import DataFetchConfigError

        def broken():
            raise DataFetchConfigError("Extern datakatalog saknas i servermiljön.")

        monkeypatch.setattr(data_fetch_catalog_module, "load_catalog", broken)
        payload = assistant_tools.run_tool(session, data["leader"], "data_fetch_catalog", {})
        assert "inte tillgänglig" in payload["error"]
    finally:
        session.close()
        engine.dispose()
