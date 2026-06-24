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


def test_productivity_finance_is_hidden_without_finance_permission():
    report = {
        "people": [
            {
                "time_cells": [
                    {"kind": "kpi", "activity_id": 1, "minutes": 60, "points": 10},
                ],
            }
        ],
    }

    productivity_router._attach_productivity_finance(report, {"visible": False})

    assert report["finance"] == {"visible": False}
    assert "finance" not in report["people"][0]["time_cells"][0]


def test_productivity_finance_calculates_cost_revenue_and_result():
    report = {
        "people": [
            {
                "person_id": 4,
                "name": "Alvin",
                "collar_type": "white_collar",
                "time_cells": [
                    {"kind": "kpi", "activity_id": 1, "minutes": 60, "points": 50},
                    {"kind": "support", "activity_id": 2, "minutes": 30, "points": 0},
                ],
            }
        ],
    }
    context = {
        "visible": True,
        "currency": "SEK",
        "hourly_cost": 200,
        "vas_hourly_revenue_by_company": {
            "GG": {"blue_collar": 500, "white_collar": 650},
        },
        "company_codes": ["GG"],
        "activity_meta": {
            1: {"is_vas": True, "company": "GG"},
            2: {"is_vas": False, "company": "GG"},
        },
    }

    productivity_router._attach_productivity_finance(report, context)

    vas_cell = report["people"][0]["time_cells"][0]["finance"]
    support_cell = report["people"][0]["time_cells"][1]["finance"]
    assert vas_cell["revenue"] == 650.0
    assert vas_cell["cost"] == 200.0
    assert vas_cell["result"] == 450.0
    assert vas_cell["collar_type"] == "white_collar"
    assert support_cell["revenue"] == 0.0
    assert support_cell["cost"] == 100.0
    assert support_cell["result"] == -100.0
    assert report["people"][0]["finance"] == {
        "visible": True,
        "currency": "SEK",
        "revenue": 650.0,
        "cost": 300.0,
        "result": 350.0,
        "work_minutes": 90,
        "vas_minutes": 60,
    }
    assert report["finance"] == report["people"][0]["finance"]


def test_productivity_finance_does_not_treat_non_company_area_as_company():
    report = {
        "people": [
            {
                "time_cells": [
                    {"kind": "kpi", "activity_id": 1, "activity_area_code": "AS", "minutes": 60, "points": 50},
                ],
            }
        ],
    }
    context = {
        "visible": True,
        "currency": "SEK",
        "hourly_cost": 200,
        "vas_hourly_revenue_by_company": {
            "GG": {"blue_collar": 500, "white_collar": 650},
            "MG": {"blue_collar": 450, "white_collar": 600},
        },
        "company_codes": ["GG", "MG"],
        "activity_meta": {
            1: {"is_vas": True, "company": ""},
        },
    }

    productivity_router._attach_productivity_finance(report, context)

    finance = report["people"][0]["time_cells"][0]["finance"]
    assert finance["company"] is None
    assert finance["revenue"] == 0.0
    assert finance["cost"] == 200.0
    assert finance["result"] == -200.0


def test_productivity_finance_uses_person_collar_from_context():
    report = {
        "people": [
            {
                "person_id": 4,
                "time_cells": [
                    {"kind": "kpi", "activity_id": 1, "minutes": 60, "points": 50},
                ],
            }
        ],
    }
    context = {
        "visible": True,
        "currency": "SEK",
        "hourly_cost": 200,
        "vas_hourly_revenue_by_company": {
            "GG": {"blue_collar": 500, "white_collar": 750},
        },
        "company_codes": ["GG"],
        "activity_meta": {
            1: {"is_vas": True, "company": "GG"},
        },
        "person_collar_by_id": {4: "white_collar"},
    }

    productivity_router._attach_productivity_finance(report, context)

    finance = report["people"][0]["time_cells"][0]["finance"]
    assert finance["collar_type"] == "white_collar"
    assert finance["revenue"] == 750.0
    assert finance["cost"] == 200.0
    assert finance["result"] == 550.0


def test_productivity_finance_adds_linked_process_revenue_to_report_summary():
    report = {
        "people": [
            {
                "person_id": 4,
                "time_cells": [
                    {"kind": "kpi", "activity_id": 1, "minutes": 60, "points": 50},
                ],
            }
        ],
    }
    context = {
        "visible": True,
        "currency": "SEK",
        "hourly_cost": 200,
        "vas_hourly_revenue_by_company": {},
        "company_codes": ["GG"],
        "activity_meta": {1: {"is_vas": False, "company": "GG"}},
        "process_revenue_rows": [
            {
                "company": "GG",
                "row_id": "store_picked_rows",
                "label": "Outbound | Plockade rader | Per rad",
                "process_key": "MANUAL_PICK",
                "process_label": "Manual Pick",
                "quantity": 10,
                "price": 6.5,
                "revenue": 65.0,
                "currency": "SEK",
            }
        ],
    }

    productivity_router._attach_productivity_finance(report, context)

    assert report["finance"]["revenue"] == 65.0
    assert report["finance"]["cost"] == 200.0
    assert report["finance"]["result"] == -135.0
    assert report["finance"]["process_revenues"][0]["process_key"] == "MANUAL_PICK"
    assert report["people"][0]["finance"]["revenue"] == 0.0


def test_productivity_overview_business_summary_groups_finance_and_zero_pick_rows(monkeypatch, tmp_path):
    source_files = {
        key: tmp_path / f"{key}.csv"
        for key in ("pick", "trans", "pallet", "receive", "order_log", "sort", "base_pallet", "kpi")
    }
    source_files["pick"].write_text(
        "company\tqty_suf\n"
        "GG\t0\n"
        "GG\t1\n"
        "MG\t0\n",
        encoding="utf-8",
    )
    for key, path in source_files.items():
        if key != "pick":
            path.write_text(f"{key}\n", encoding="utf-8")

    report = {
        "date": "2026-06-03",
        "sync": {"source": "api_snapshot"},
        "people": [
            {
                "person_id": 4,
                "time_cells": [
                    {"kind": "kpi", "activity_id": 1, "minutes": 60, "points": 50},
                    {"kind": "support", "activity_id": 2, "minutes": 30, "points": 0},
                ],
            }
        ],
    }
    finance_context = {
        "visible": True,
        "currency": "SEK",
        "hourly_cost": 120,
        "vas_hourly_revenue_by_company": {
            "GG": {"blue_collar": 600, "white_collar": 600},
            "MG": {"blue_collar": 500, "white_collar": 500},
        },
        "company_codes": ["GG", "MG"],
        "activity_meta": {
            1: {"is_vas": True, "company": "GG"},
            2: {"is_vas": False, "company": "MG"},
        },
        "process_revenue_rows": [
            {
                "company": "MG",
                "row_id": "store_picked_rows",
                "label": "Outbound | Plockade rader | Per rad",
                "process_key": "MANUAL_PICK",
                "process_label": "Manual Pick",
                "quantity": 10,
                "price": 7.5,
                "revenue": 75.0,
                "currency": "SEK",
            }
        ],
    }

    monkeypatch.setattr(productivity_router, "_productivity_business_id", lambda _db, _user: 1)
    monkeypatch.setattr(productivity_router, "_productivity_business_code", lambda _db, _user: "STIGAMO")
    monkeypatch.setattr(productivity_router, "_productivity_finance_context", lambda _db, _user, _business_id: finance_context)
    monkeypatch.setattr(productivity_router, "productivity_snapshot_files", lambda *_args, **_kwargs: source_files)
    monkeypatch.setattr(
        productivity_router,
        "_build_productivity_report_for_date",
        lambda *_args, **_kwargs: (report.copy(), [{"key": "pick", "status": "api"}]),
    )

    payload = productivity_router.get_productivity_overview_business_summary(
        SimpleNamespace(session={}),
        period="day",
        date_filter=date(2026, 6, 3),
        start_date=None,
        end_date=None,
        user=route_user(),
        db=object(),
    )

    rows = {row["company"]: row for row in payload["companies"]}
    assert payload["period"]["start_date"] == "2026-06-03"
    assert payload["period"]["end_date"] == "2026-06-03"
    assert rows["GG"]["revenue"] == 600.0
    assert rows["GG"]["cost"] == 120.0
    assert rows["GG"]["result"] == 480.0
    assert rows["GG"]["zero_pick_rows"] == 1
    assert rows["MG"]["revenue"] == 75.0
    assert rows["MG"]["cost"] == 60.0
    assert rows["MG"]["result"] == 15.0
    assert rows["MG"]["zero_pick_rows"] == 1
    assert payload["totals"]["revenue"] == 675.0
    assert payload["totals"]["cost"] == 180.0
    assert payload["totals"]["result"] == 495.0
    assert payload["totals"]["zero_pick_rows"] == 2


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
