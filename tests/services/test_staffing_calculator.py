from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Activity, Area, Business, Person, PersonProductivityDaily, ScheduleCell, User
from app.backend.routers import schedule as schedule_router
from app.backend.person_productivity_cache import materialize_person_productivity_daily
from app.backend.staffing_calculator_service import (
    LOCAL_TZ,
    calculate_staffing_automatic,
    historical_output_per_hour_by_person_process,
    primary_metric_for_process,
    schedule_activity_capacity,
    schedule_activity_capacity_cell,
    schedule_productivity_summary,
)
from app.backend.productivity_kpi_rules import parse_kpi_rule_rows
from app.backend.productivity_sync import ProductivitySyncError
from app.backend.settings_service import set_staffing_activity_capacity_activity_ids
from app.backend.workflow_data import WorkflowSourceEntry


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def seed_staffing_data(session):
    business = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    session.add(business)
    session.flush()
    area = Area(business_id=business.id, code="GG", name="GG", sort_order=1)
    session.add(area)
    session.flush()
    activity = Activity(
        business_id=business.id,
        code="GG_PLOCK",
        label="GG Plock",
        area_id=area.id,
        color="#ffffff",
        category="work",
        sort_order=1,
        kpi_process_name="Manual_Pick",
    )
    person = Person(
        business_id=business.id,
        name="Anna Plock",
        noman="ANNA",
        home_area_id=area.id,
        competencies=[],
        has_fixed_schedule=False,
        sort_order=1,
    )
    user = User(username="planner", role="admin", roles=["admin"], business_id=business.id, is_active=True)
    session.add_all([activity, person, user])
    session.flush()
    for hour in range(10, 15):
        session.add(
            ScheduleCell(
                year=2026,
                week=24,
                weekday=2,
                hour=hour,
                minute_start=0,
                minute_end=60,
                person_id=person.id,
                activity_id=activity.id,
            )
        )
    session.commit()
    return business, area, activity, person, user


def test_automatic_staffing_calculator_filters_orders_and_projects_remaining_rows(
    db_session,
    tmp_path,
    monkeypatch,
):
    _business, _area, _activity, person, user = seed_staffing_data(db_session)
    captured = {}

    def fake_fetch_source_to_temp(source_key, filters=None):
        captured["source_key"] = source_key
        captured["filters"] = filters
        path = tmp_path / "orders.csv"
        matching = "\n".join("33,GG,A,2026-06-08" for _ in range(500))
        path.write_text(
            "line_status,company,pick_zone,order_date\n"
            f"{matching}\n"
            "34,GG,A,2026-06-08\n"
            "33,MG,A,2026-06-08\n"
            "33,GG,B,2026-06-08\n"
            "33,GG,A,2026-06-09\n",
            encoding="utf-8",
        )
        return path, WorkflowSourceEntry("orders", "Detalj Kundorder (Alla)", "v", "ok", row_count=504)

    def fake_rates(_db, *, selected_date, process_key, person_ids, business_id):
        assert selected_date.isoformat() == "2026-06-09"
        assert process_key == "MANUAL_PICK"
        assert person_ids == {person.id}
        return {person.id: {"rows": 4000.0, "hours": 40.0, "rows_per_hour": 100.0}}

    monkeypatch.setattr("app.backend.staffing_calculator_service.fetch_source_to_temp", fake_fetch_source_to_temp)
    monkeypatch.setattr("app.backend.staffing_calculator_service.historical_rows_per_hour_by_person", fake_rates)

    result = calculate_staffing_automatic(
        db_session,
        user,
        {
            "version": 1,
            "calculators": [
                {
                    "id": "gg-a",
                    "name": "GG A",
                    "process": "Manual_Pick",
                    "company": "GG",
                    "zone": "A",
                    "pick_days": 1,
                }
            ],
        },
        year=2026,
        week=24,
        weekday=2,
        now=datetime(2026, 6, 9, 11, 17, tzinfo=LOCAL_TZ),
    )

    row = result["calculators"][0]
    assert captured["source_key"] == "orders"
    assert {"id": "line_status", "value": 34, "operator": "LT"} in captured["filters"]
    assert {"id": "order_date", "value": "2026-06-08", "operator": "EQ"} in captured["filters"]
    assert row["status"] == "ok"
    assert row["order_rows"] == 500
    assert row["scheduled_hours"] == 3.5
    assert row["expected_rows"] == 350.0
    assert row["rows_remaining_after_schedule"] == 150.0


def test_staffing_calculator_profiles_are_user_saved_and_importable(db_session, monkeypatch):
    monkeypatch.setattr(schedule_router, "audit_log", lambda *args, **kwargs: None)
    business = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    db_session.add(business)
    db_session.flush()
    alice = User(username="alice", display_name="Alice", role="admin", roles=["admin"], business_id=business.id, is_active=True)
    bob = User(username="bob", display_name="Bob", role="admin", roles=["admin"], business_id=business.id, is_active=True)
    db_session.add_all([alice, bob])
    db_session.commit()

    profile = {
        "version": 1,
        "calculators": [
            {
                "id": "auto-1",
                "name": "Auto GG",
                "process": "Manual_Pick",
                "company": "GG",
                "zone": "A",
                "pick_days": 0,
            }
        ],
    }
    schedule_router.update_calculator_profile(
        schedule_router.StaffingCalculatorProfileUpdate(profile=profile),
        db_session,
        alice,
    )

    imported = schedule_router.import_calculator_profile(
        schedule_router.StaffingCalculatorProfileImport(user_id=alice.id),
        db_session,
        bob,
    )

    assert imported["profile"]["calculators"][0]["name"] == "Auto GG"
    users = {user["username"]: user for user in imported["users"]}
    assert users["alice"]["has_calculators"] is True
    assert users["alice"]["calculator_count"] == 1
    assert users["bob"]["is_current"] is True


def test_primary_metric_for_process_uses_kpi_rules_and_targets():
    rules = parse_kpi_rule_rows(
        [
            {"process": "Manual_Pick", "source": "pick", "metric": "rows"},
            {"process": "Ecom_Pack", "source": "pallet", "metric": "pallets"},
        ]
    )
    targets = {
        ("GG", "MANUAL_PICK"): SimpleNamespace(
            targets={"rows": 70.0, "packages": 0.0, "pallets": 0.0, "orders": 0.0},
            points={"rows": 1.43, "packages": 0.0, "pallets": 0.0, "orders": 0.0},
        )
    }

    assert primary_metric_for_process("Manual_Pick", targets, rules=rules) == "rows"
    assert primary_metric_for_process("Ecom_Pack", rules=rules) == "pallets"


def test_schedule_activity_capacity_returns_person_activity_average(db_session, monkeypatch):
    _business, _area, activity, person, user = seed_staffing_data(db_session)
    rules = parse_kpi_rule_rows([{"process": "Manual_Pick", "source": "pick", "metric": "rows"}])

    def fake_history(_db, *, selected_date, process_keys, person_ids, business_id, primary_metrics_by_process):
        assert selected_date.isoformat() == "2026-06-09"
        assert process_keys == {"MANUAL_PICK"}
        assert person_ids == {person.id}
        assert primary_metrics_by_process == {"MANUAL_PICK": "rows"}
        return {
            person.id: {
                "MANUAL_PICK": {
                    "units": 2800.0,
                    "hours": 40.0,
                    "units_per_hour": 70.0,
                    "metric": "rows",
                    "unit": "rader",
                }
            }
        }

    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.historical_output_per_hour_by_person_process",
        fake_history,
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.load_kpi_rules",
        lambda *_args, **_kwargs: (rules, {"key": "kpi_sql"}),
    )

    result = schedule_activity_capacity(db_session, user, year=2026, week=24, weekday=2)

    assert result["history_hours"] == 40.0
    payload = result["people"][str(person.id)][str(activity.id)]
    assert payload["activity_label"] == "GG Plock"
    assert payload["process_key"] == "MANUAL_PICK"
    assert payload["metric"] == "rows"
    assert payload["unit"] == "rader"
    assert payload["value_per_hour"] == 70.0


def test_schedule_activity_capacity_cell_returns_single_person_activity_average(db_session, monkeypatch):
    _business, _area, activity, person, user = seed_staffing_data(db_session)
    rules = parse_kpi_rule_rows([{"process": "Manual_Pick", "source": "pick", "metric": "rows"}])
    captured = {}

    def fake_history(_db, *, selected_date, process_keys, person_ids, business_id, primary_metrics_by_process):
        captured["selected_date"] = selected_date.isoformat()
        captured["process_keys"] = process_keys
        captured["person_ids"] = person_ids
        captured["primary_metrics_by_process"] = primary_metrics_by_process
        return {
            person.id: {
                "MANUAL_PICK": {
                    "units": 1400.0,
                    "hours": 20.0,
                    "units_per_hour": 70.0,
                    "metric": "rows",
                    "unit": "rader",
                }
            }
        }

    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.historical_output_per_hour_by_person_process",
        fake_history,
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.load_kpi_rules",
        lambda *_args, **_kwargs: (rules, {"key": "kpi_sql"}),
    )

    result = schedule_activity_capacity_cell(
        db_session,
        user,
        year=2026,
        week=24,
        weekday=2,
        person_id=person.id,
        activity_id=activity.id,
    )

    assert captured == {
        "selected_date": "2026-06-09",
        "process_keys": {"MANUAL_PICK"},
        "person_ids": {person.id},
        "primary_metrics_by_process": {"MANUAL_PICK": "rows"},
    }
    assert result["capacity"]["activity_label"] == "GG Plock"
    assert result["capacity"]["process_key"] == "MANUAL_PICK"
    assert result["capacity"]["unit"] == "rader"
    assert result["capacity"]["value_per_hour"] == 70.0


def test_schedule_activity_capacity_filters_configured_activities(db_session, monkeypatch):
    business, _area, activity, person, user = seed_staffing_data(db_session)
    set_staffing_activity_capacity_activity_ids(db_session, [], business_id=business.id)
    db_session.commit()
    rules = parse_kpi_rule_rows([{"process": "Manual_Pick", "source": "pick", "metric": "rows"}])
    captured = {}

    def fake_history(_db, *, selected_date, process_keys, person_ids, business_id, primary_metrics_by_process):
        captured["process_keys"] = process_keys
        captured["person_ids"] = person_ids
        captured["business_id"] = business_id
        captured["primary_metrics_by_process"] = primary_metrics_by_process
        return {}

    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.historical_output_per_hour_by_person_process",
        fake_history,
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.load_kpi_rules",
        lambda *_args, **_kwargs: (rules, {"key": "kpi_sql"}),
    )

    result = schedule_activity_capacity(db_session, user, year=2026, week=24, weekday=2)

    assert result["visible_activity_ids"] == []
    assert result["activities"] == {}
    assert result["people"] == {}
    assert captured == {
        "process_keys": set(),
        "person_ids": {person.id},
        "business_id": business.id,
        "primary_metrics_by_process": {},
    }
    assert str(activity.id) not in result["activities"]


def test_schedule_activity_capacity_cell_respects_configured_activities(db_session, monkeypatch):
    business, _area, activity, person, user = seed_staffing_data(db_session)
    set_staffing_activity_capacity_activity_ids(db_session, [], business_id=business.id)
    db_session.commit()

    result = schedule_activity_capacity_cell(
        db_session,
        user,
        year=2026,
        week=24,
        weekday=2,
        person_id=person.id,
        activity_id=activity.id,
    )

    assert result["capacity"] is None
    assert result["reason"] == "activity_hidden"


def test_historical_output_reads_materialized_person_productivity_cache(db_session, monkeypatch):
    business, _area, _activity, person, _user = seed_staffing_data(db_session)
    rules = parse_kpi_rule_rows([{"process": "Manual_Pick", "source": "pick", "metric": "rows"}])
    db_session.add(
        PersonProductivityDaily(
            business_id=business.id,
            snapshot_date=date(2026, 6, 8),
            person_id=person.id,
            row_type="process",
            item_key="process:MANUAL_PICK",
            metric="rows",
            unit="rader",
            process_key="MANUAL_PICK",
            process_label="Manual_Pick",
            kpi_points=3200.0,
            planned_kpi_points=4000.0,
            kpi_minutes=2400,
            units=3200.0,
            event_count=12,
            source_snapshot_at="2026-06-08T23:30:00",
            schedule_signature="test",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.productivity_snapshot_status",
        lambda day: {"ready": day == date(2026, 6, 8), "last_sync_at": "2026-06-08T23:30:00"},
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.productivity_snapshot_files",
        lambda day: {},
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.ensure_person_productivity_daily_cache",
        lambda *_args, **_kwargs: {"status": "current"},
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.load_kpi_rules",
        lambda *_args, **_kwargs: (rules, {"key": "kpi_target_rule"}),
    )

    result = historical_output_per_hour_by_person_process(
        db_session,
        selected_date=date(2026, 6, 9),
        process_keys={"MANUAL_PICK"},
        person_ids={person.id},
        business_id=business.id,
        primary_metrics_by_process={"MANUAL_PICK": "rows"},
    )

    row = result[person.id]["MANUAL_PICK"]
    assert row["hours"] == 40.0
    assert row["units"] == 3200.0
    assert row["units_per_hour"] == 80.0


def test_materialize_person_productivity_daily_stores_report_rows(db_session, monkeypatch):
    business, _area, _activity, person, _user = seed_staffing_data(db_session)
    monkeypatch.setattr(
        "app.backend.person_productivity_cache.productivity_cache_schedule_signature",
        lambda *_args, **_kwargs: "schedule-test",
    )
    monkeypatch.setattr(
        "app.backend.person_productivity_cache._build_process_rows",
        lambda *_args, **_kwargs: [],
    )
    report = {
        "date": "2026-06-09",
        "people": [
            {
                "person_id": person.id,
                "kpi_points": 160.0,
                "planned_kpi_points": 200.0,
                "kpi_minutes": 120,
                "support_minutes": 0,
                "absence_minutes": 0,
                "diffs": [],
                "time_cells": [
                    {
                        "kind": "kpi",
                        "start_minute": 600,
                        "end_minute": 660,
                        "minutes": 60,
                        "activity_id": _activity.id,
                        "activity_label": "GG Plock",
                        "points": 80.0,
                        "expected_points": 100.0,
                        "event_count": 2,
                        "diff_count": 0,
                    },
                    {
                        "kind": "kpi",
                        "start_minute": 660,
                        "end_minute": 720,
                        "minutes": 60,
                        "activity_id": _activity.id,
                        "activity_label": "GG Plock",
                        "points": 80.0,
                        "expected_points": 100.0,
                        "event_count": 2,
                        "diff_count": 0,
                    },
                ],
            }
        ],
    }

    result = materialize_person_productivity_daily(
        db_session,
        {},
        report_date=date(2026, 6, 9),
        business_id=business.id,
        sync={"last_sync_at": "2026-06-09T11:30:00"},
        report=report,
    )

    assert result["rows"] == 4
    rows = db_session.query(PersonProductivityDaily).order_by(PersonProductivityDaily.row_type, PersonProductivityDaily.start_minute).all()
    assert [row.row_type for row in rows] == ["activity", "cell", "cell", "person"]
    activity_row = next(row for row in rows if row.row_type == "activity")
    assert activity_row.kpi_points == 160.0
    assert activity_row.kpi_minutes == 120
    assert activity_row.source_snapshot_at == "2026-06-09T11:30:00"
    assert activity_row.schedule_signature == "schedule-test"


def test_schedule_productivity_summary_reads_materialized_cell_cache(db_session, monkeypatch):
    business, _area, _activity, person, user = seed_staffing_data(db_session)
    db_session.add_all(
        [
            PersonProductivityDaily(
                business_id=business.id,
                snapshot_date=date(2026, 6, 9),
                person_id=person.id,
                row_type="cell",
                item_key="cell:600:660:1",
                metric="points",
                unit="poang",
                kind="kpi",
                start_minute=600,
                end_minute=660,
                kpi_points=80.0,
                planned_kpi_points=100.0,
                kpi_minutes=60,
                units=80.0,
                source_snapshot_at="2026-06-09T11:30:00",
                schedule_signature="test",
            ),
            PersonProductivityDaily(
                business_id=business.id,
                snapshot_date=date(2026, 6, 9),
                person_id=person.id,
                row_type="cell",
                item_key="cell:660:720:1",
                metric="points",
                unit="poang",
                kind="kpi",
                start_minute=660,
                end_minute=720,
                kpi_points=100.0,
                planned_kpi_points=100.0,
                kpi_minutes=60,
                units=100.0,
                source_snapshot_at="2026-06-09T11:30:00",
                schedule_signature="test",
            ),
        ]
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.ensure_productivity_snapshot",
        lambda *_args, **_kwargs: {"ready": True, "last_sync_at": "2026-06-09T11:30:00"},
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.productivity_snapshot_files",
        lambda day: {},
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.ensure_person_productivity_daily_cache",
        lambda *_args, **_kwargs: {"status": "current"},
    )

    result = schedule_productivity_summary(
        db_session,
        user,
        year=2026,
        week=24,
        weekday=2,
        now=datetime(2026, 6, 9, 11, 17, tzinfo=LOCAL_TZ),
    )

    assert result["cutoff_minute"] == 11 * 60
    assert result["people"][str(person.id)]["percent"] == 80
    assert result["people"][str(person.id)]["kpi_minutes"] == 60


def test_schedule_productivity_summary_keeps_cached_rows_when_snapshot_sync_fails(db_session, monkeypatch):
    business, _area, _activity, person, user = seed_staffing_data(db_session)
    db_session.add(
        PersonProductivityDaily(
            business_id=business.id,
            snapshot_date=date(2026, 6, 9),
            person_id=person.id,
            row_type="cell",
            item_key="cell:600:660:1",
            metric="points",
            unit="poang",
            kind="kpi",
            start_minute=600,
            end_minute=660,
            kpi_points=80.0,
            planned_kpi_points=100.0,
            kpi_minutes=60,
            units=80.0,
            source_snapshot_at="2026-06-09T11:30:00",
            schedule_signature="test",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.ensure_productivity_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ProductivitySyncError("Extern datakälla kunde inte nås.")),
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.productivity_snapshot_status",
        lambda day: {
            "source": "api_snapshot",
            "date": day.isoformat(),
            "status": "error",
            "ready": False,
            "last_error": "Connection reset",
        },
    )
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.ensure_person_productivity_daily_cache",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache refresh should be skipped")),
    )

    result = schedule_productivity_summary(
        db_session,
        user,
        year=2026,
        week=24,
        weekday=2,
        now=datetime(2026, 6, 9, 11, 17, tzinfo=LOCAL_TZ),
    )

    assert result["cache"]["status"] == "source_unavailable"
    assert result["cache"]["message"] == "Extern datakälla kunde inte nås."
    assert result["cache"]["sync"]["last_error"] == "Connection reset"
    assert result["people"][str(person.id)]["percent"] == 80


def test_schedule_activity_capacity_uses_default_business_rules_for_super_user_all_scope(db_session, monkeypatch):
    business, _area, activity, person, _user = seed_staffing_data(db_session)
    super_user = User(username="root", role="super_user", roles=["super_user"], is_active=True)
    db_session.add(super_user)
    db_session.commit()
    rules = parse_kpi_rule_rows([{"process": "Manual_Pick", "source": "pick", "metric": "rows"}])
    captured = {}

    def fake_load_rules(_db, *, business_id=None, **_kwargs):
        captured["rules_business_id"] = business_id
        return rules, {"key": "kpi_sql"}

    def fake_history(_db, *, selected_date, process_keys, person_ids, business_id, primary_metrics_by_process):
        captured["history_business_id"] = business_id
        return {
            person.id: {
                "MANUAL_PICK": {
                    "units": 2800.0,
                    "hours": 40.0,
                    "units_per_hour": 70.0,
                    "metric": "rows",
                    "unit": "rader",
                }
            }
        }

    monkeypatch.setattr("app.backend.staffing_calculator_service.load_kpi_rules", fake_load_rules)
    monkeypatch.setattr(
        "app.backend.staffing_calculator_service.historical_output_per_hour_by_person_process",
        fake_history,
    )

    result = schedule_activity_capacity(db_session, super_user, year=2026, week=24, weekday=2)

    assert captured["rules_business_id"] == business.id
    assert captured["history_business_id"] == business.id
    assert result["people"][str(person.id)][str(activity.id)]["value_per_hour"] == 70.0
