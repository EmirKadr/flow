from datetime import date
from types import SimpleNamespace

from app.backend.routers import productivity as productivity_router


def route_user():
    return SimpleNamespace(id=7, username="productivity-user", business_id=1)


def test_productivity_router_no_longer_registers_file_upload_routes():
    routes = {(next(iter(route.methods or [])), route.path) for route in productivity_router.router.routes}

    assert ("GET", "/api/productivity/files") not in routes
    assert ("GET", "/api/productivity/targets") not in routes
    assert ("POST", "/api/productivity/files") not in routes
    assert ("POST", "/api/productivity/files/raw") not in routes
    assert ("DELETE", "/api/productivity/files/{file_type}") not in routes


def test_productivity_report_uses_api_snapshot_and_audits(monkeypatch, tmp_path):
    source_files = {
        key: tmp_path / f"{key}.csv"
        for key in ("pick", "trans", "pallet", "receive", "order_log", "sort", "base_pallet", "kpi")
    }
    for key, path in source_files.items():
        path.write_text(f"{key}\n", encoding="utf-8")
    audits = []

    monkeypatch.setattr(productivity_router, "_productivity_business_code", lambda _db, _user: "STIGAMO")
    monkeypatch.setattr(productivity_router, "_productivity_business_id", lambda _db, _user: 1)
    monkeypatch.setattr(productivity_router, "sources_available", lambda _keys: True)
    monkeypatch.setattr(
        productivity_router,
        "ensure_productivity_snapshot",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "sources": [
                {"key": key, "view": f"v_{key}", "status": "api", "rows": 1}
                for key in source_files
            ],
        },
    )
    monkeypatch.setattr(productivity_router, "productivity_snapshot_files", lambda *_args, **_kwargs: source_files)
    monkeypatch.setattr(
        productivity_router,
        "productivity_snapshot_status",
        lambda *_args, **_kwargs: {"source": "api_snapshot", "status": "ok", "last_sync_at": "2026-06-08T10:00:00"},
    )
    monkeypatch.setattr(
        productivity_router,
        "build_person_productivity_report_from_files",
        lambda _db, files, report_date=None, business_id=None, sync=None: {
            "sources": {},
            "people": [],
            "summary": {"people": len(files)},
            "date": str(report_date or ""),
            "sync": sync,
        },
    )
    monkeypatch.setattr(productivity_router.audit, "log_and_commit", lambda *args, **kwargs: audits.append(kwargs["new_value"]))

    report = productivity_router.get_productivity(SimpleNamespace(session={}), user=route_user(), db=object())

    assert report["summary"]["people"] == 8
    assert {entry["status"] for entry in report["source_status"]} == {"api"}
    assert audits == [
        {
            "status": "ok",
            "source_status": report["source_status"],
        }
    ]


def test_productivity_overview_period_reads_existing_snapshots_without_history_sync(monkeypatch, tmp_path):
    source_files = {
        key: tmp_path / f"{key}.csv"
        for key in ("pick", "trans", "pallet", "receive", "order_log", "sort", "base_pallet", "kpi")
    }
    for key, path in source_files.items():
        path.write_text(f"{key}\n", encoding="utf-8")
    history_calls = []
    audits = []

    monkeypatch.setattr(productivity_router, "_productivity_business_code", lambda _db, _user: "STIGAMO")
    monkeypatch.setattr(productivity_router, "_productivity_business_id", lambda _db, _user: 1)
    monkeypatch.setattr(productivity_router, "sources_available", lambda _keys: True)
    monkeypatch.setattr(productivity_router, "productivity_snapshot_files", lambda *_args, **_kwargs: source_files)
    monkeypatch.setattr(
        productivity_router,
        "productivity_snapshot_status",
        lambda day=None, **_kwargs: {"source": "api_snapshot", "status": "ok", "ready": True, "date": str(day or "")},
    )
    monkeypatch.setattr(
        productivity_router,
        "build_person_productivity_report_from_files",
        lambda _db, files, report_date=None, business_id=None, sync=None: {
            "date": report_date.isoformat(),
            "available_dates": [report_date.isoformat()],
            "sources": {},
            "people": [],
            "summary": {
                "people": 0,
                "kpi_points": 10,
                "planned_kpi_points": 20,
                "kpi_minutes": 60,
                "diff_count": 0,
                "unmatched_event_count": 0,
            },
            "sync": sync,
        },
    )
    monkeypatch.setattr(productivity_router.audit, "log_and_commit", lambda *args, **kwargs: audits.append(kwargs["new_value"]))

    payload = productivity_router.get_productivity_overview(
        SimpleNamespace(session={}),
        period="week",
        date_filter=date(2026, 6, 3),
        user=route_user(),
        db=object(),
    )

    assert payload["period"]["start_date"] == "2026-06-01"
    assert payload["period"]["end_date"] == "2026-06-07"
    assert payload["period"]["requested_days"] == 7
    assert len(payload["reports"]) == 7
    assert payload["summary"]["kpi_points"] == 70
    assert payload["summary"]["points_per_hour"] == 10
    assert history_calls == []
    assert audits and audits[0]["status"] == "ok"


def test_person_productivity_aggregates_activity_cells_for_period(monkeypatch):
    person = SimpleNamespace(id=4, name="Alvin", noman="ALV94", business_id=1)

    def fake_files(_request, _db, _user, report_date):
        if report_date in {date(2026, 6, 8), date(2026, 6, 9)}:
            return {}, {"source": "api_snapshot", "status": "ok"}
        raise productivity_router.ProductivitySyncError("saknas")

    def fake_report(_db, _files, report_date=None, business_id=None, sync=None):
        cells = {
            date(2026, 6, 8): [
                {"kind": "kpi", "activity_label": "Plock", "points": 100, "expected_points": 100, "minutes": 60, "event_count": 2, "diff_count": 0},
                {"kind": "kpi", "activity_label": "Pack", "points": 40, "expected_points": 100, "minutes": 60, "event_count": 1, "diff_count": 1},
                {"kind": "support", "activity_label": "Stöd", "points": 25, "expected_points": 0, "minutes": 30, "event_count": 1, "diff_count": 0},
            ],
            date(2026, 6, 9): [
                {"kind": "kpi", "activity_label": "Plock", "points": 50, "expected_points": 100, "minutes": 60, "event_count": 1, "diff_count": 0},
            ],
        }[report_date]
        return {
            "date": report_date.isoformat(),
            "people": [
                {
                    "person_id": 4,
                    "support_minutes": 15,
                    "absence_minutes": 0,
                    "time_cells": cells,
                }
            ],
        }

    monkeypatch.setattr(productivity_router, "scoped_get", lambda *_args, **_kwargs: person)
    monkeypatch.setattr(productivity_router, "_person_productivity_files_for_date", fake_files)
    monkeypatch.setattr(productivity_router, "build_person_productivity_report_from_files", fake_report)
    monkeypatch.setattr(productivity_router, "productivity_backfill_status", lambda *_args, **_kwargs: {"status": "ok"})

    result = productivity_router.get_person_productivity(
        4,
        SimpleNamespace(session={}),
        period="week",
        date_filter=date(2026, 6, 9),
        start_date=None,
        end_date=None,
        user=route_user(),
        db=object(),
    )

    plock = next(item for item in result["activities"] if item["activity"] == "Plock")
    pack = next(item for item in result["activities"] if item["activity"] == "Pack")

    assert result["period"]["start_date"] == "2026-06-08"
    assert result["period"]["end_date"] == "2026-06-14"
    assert result["summary"]["days_with_activity"] == 2
    assert len(result["missing_dates"]) == 5
    assert {item["activity"] for item in result["activities"]} == {"Plock", "Pack"}
    assert plock["kpi_points"] == 150
    assert plock["planned_kpi_points"] == 200
    assert plock["productivity_pct"] == 0.75
    assert pack["productivity_pct"] == 0.4
    assert result["summary"]["kpi_minutes"] == 180
