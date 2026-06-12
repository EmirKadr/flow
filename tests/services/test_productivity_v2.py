from __future__ import annotations

import gzip
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.backend.models import Activity, Area, Base, Business, Person, PersonScheduleTemplate, ScheduleCell
from app.backend.productivity_kpi_rules import (
    build_person_productivity_report_from_files,
    kpi_rule_contract,
    parse_kpi_rule_rows,
    parse_kpi_targets,
)
from app.backend import productivity_sync
from app.backend.workflow_data import WorkflowDataError, WorkflowSourceEntry


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_people_and_activities(db: Session) -> dict[str, Activity | Person | Business]:
    business = Business(code="STIGAMO", name="Stigamo")
    area = Area(code="MG", name="Mestergruppen", business=business)
    plock = Activity(code="MG_PLOCK", label="MG Plock", area=area, business=business, kpi_process_name="Manual_Pick")
    dekant = Activity(code="AS_DEK", label="Dekantering GG", area=area, business=business, kpi_process_name="Decanting")
    helpall = Activity(code="GG_HELPALL", label="Helpallar GG", area=area, business=business, kpi_process_name="Full_Manual_Buffer")
    support = Activity(code="MG_STOD", label="MG StÃ¶d", area=area, business=business, kpi_process_name="")
    absence = Activity(code="SJUK", label="Sjuk", area=area, business=business, category="absence", kpi_process_name="absence")
    alvin = Person(
        name="Alvin",
        noman="ALV94",
        business=business,
        home_area=area,
        home_activity_id=None,
        created_at=datetime(2026, 6, 1, 8, 0),
    )
    no_noman = Person(
        name="Saknar NoMan",
        business=business,
        home_area=area,
        home_activity_id=None,
        created_at=datetime(2026, 6, 1, 8, 0),
    )
    support_only = Person(
        name="StÃ¶d Hela Dagen",
        noman="STO01",
        business=business,
        home_area=area,
        home_activity_id=None,
        created_at=datetime(2026, 6, 1, 8, 0),
    )
    absence_only = Person(
        name="Absence Hela Dagen",
        noman="ABS01",
        business=business,
        home_area=area,
        home_activity_id=None,
        created_at=datetime(2026, 6, 1, 8, 0),
    )
    db.add_all([business, area, plock, dekant, helpall, support, absence, alvin, no_noman, support_only, absence_only])
    db.flush()
    alvin.home_activity_id = plock.id
    no_noman.home_activity_id = plock.id
    db.add(PersonScheduleTemplate(person_id=alvin.id, weekday=1, start_hour=7, end_hour=12))
    db.add(PersonScheduleTemplate(person_id=no_noman.id, weekday=1, start_hour=7, end_hour=12))
    db.add(PersonScheduleTemplate(person_id=support_only.id, weekday=1, start_hour=7, end_hour=12))
    db.add(PersonScheduleTemplate(person_id=absence_only.id, weekday=1, start_hour=7, end_hour=12))
    for hour, activity in ((7, plock), (8, dekant), (9, helpall), (10, support), (11, absence)):
        db.add(
            ScheduleCell(
                year=2026,
                week=24,
                weekday=1,
                hour=hour,
                minute_start=0,
                minute_end=60,
                person_id=alvin.id,
                activity_id=activity.id,
            )
        )
    for hour in range(7, 12):
        db.add(
            ScheduleCell(
                year=2026,
                week=24,
                weekday=1,
                hour=hour,
                minute_start=0,
                minute_end=60,
                person_id=support_only.id,
                activity_id=support.id,
            )
        )
        db.add(
            ScheduleCell(
                year=2026,
                week=24,
                weekday=1,
                hour=hour,
                minute_start=0,
                minute_end=60,
                person_id=absence_only.id,
                activity_id=absence.id,
            )
        )
    db.commit()
    return {
        "business": business,
        "alvin": alvin,
        "plock": plock,
        "dekant": dekant,
        "helpall": helpall,
    }


def base_kpi_file(tmp_path: Path) -> Path:
    return write(
        tmp_path / "kpi.csv",
        """
Bolag\tLager\tFlÃ¶desnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar\tPoÃ¤ng rader\tPoÃ¤ng kolli\tPoÃ¤ng pallar
MG\t404\tOUTBOUND\tManual_Pick\tManuellt plock\t1\t0\t0\t100\t0\t0
GG\t404\tINBOUND\tDecanting\tDekantering\t1\t0\t0\t100\t0\t0
GG\t404\tOUTBOUND\tFull_Manual_Buffer\tHelpall\t0\t0\t1\t0\t0\t100
""",
    )


def empty_file(tmp_path: Path, name: str, header: str) -> Path:
    return write(tmp_path / name, header)


def test_kpi_rule_registry_covers_sql_reference_process_sources():
    rules = parse_kpi_rule_rows(
        [
            {"process": "Manual_Pick", "source": "pick", "metric": "rows"},
            {"process": "Manual_Pick", "source": "pick", "metric": "packages"},
            {"process": "Decanting", "source": "trans", "metric": "rows"},
            {"process": "Decanting", "source": "trans", "metric": "packages"},
            {"process": "Receiving", "source": "receive", "metric": "rows"},
            {"process": "Ecom_Pack", "source": "pallet", "metric": "pallets"},
            {"process": "Sort_Ecom", "source": "sort", "metric": "pallets"},
        ]
    )
    contract = {(item["process"], item["metric"], item["source"]) for item in kpi_rule_contract(rules)}

    assert ("Manual_Pick", "rows", "pick") in contract
    assert ("Manual_Pick", "packages", "pick") in contract
    assert ("Decanting", "rows", "trans") in contract
    assert ("Decanting", "packages", "trans") in contract
    assert ("Receiving", "rows", "receive") in contract
    assert ("Ecom_Pack", "pallets", "pallet") in contract
    assert ("Sort_Ecom", "pallets", "sort") in contract


def test_kpi_targets_parse_swedish_and_api_point_columns():
    rows = [
        {
            "Bolag": "GG",
            "Processnamn": "Manual_Pick",
            "Rader": "10",
            "PoÃ¤ng rader": "10",
        },
        {
            "company": "MG",
            "action_id": "Decanting",
            "rows": "40",
            "loaded_rows": "2,5",
        },
    ]

    targets = parse_kpi_targets(rows)

    assert targets[("GG", "MANUAL_PICK")].points["rows"] == 10
    assert targets[("MG", "DECANTING")].targets["rows"] == 40
    assert targets[("MG", "DECANTING")].points["rows"] == 2.5


def test_person_productivity_rolls_up_activity_switches_support_absence_and_unknown_events(tmp_path):
    db = make_session()
    data = seed_people_and_activities(db)
    pick = write(
        tmp_path / "pick.csv",
        """
Zon\tPlockat\tAnvÃ¤ndare\tÃ„ndrad\tLokation\tBolag\tLager
A\t10\talvin\t2026-06-08 07:10:00\tA101\tMG\t404
H\t1\tALV94\t2026-06-08 09:10:00\tBUFF01\tGG\t404
A\t1\tALV94\t2026-06-08 10:10:00\tA101\tMG\t404
A\t1\tOkÃ¤nd\t2026-06-08 07:20:00\tA101\tMG\t404
""",
    )
    trans = write(
        tmp_path / "trans.csv",
        """
Typ\tTill\tAntal\tAnvÃ¤ndare\tTimestamp\tBolag\tLager
26\tAS100\t20\tALV94\t2026-06-08 08:10:00\tGG\t404
""",
    )
    files = {
        "pick": pick,
        "trans": trans,
        "pallet": empty_file(tmp_path, "pallet.csv", "Typ\tAnvÃ¤ndare\tÃ„ndrad\tBolag\tLager"),
        "receive": empty_file(tmp_path, "receive.csv", "Typ\tStatus\tAnvÃ¤ndare\tTimestamp\tBolag\tLager"),
        "sort": empty_file(tmp_path, "sort.csv", "SSCC\tAnvÃ¤ndare\tTimestamp\tSÃ¤ndningsnr"),
        "kpi": base_kpi_file(tmp_path),
    }

    report = build_person_productivity_report_from_files(
        db,
        files,
        report_date=date(2026, 6, 8),
        business_id=data["business"].id,
    )
    alvin = next(person for person in report["people"] if person["name"] == "Alvin")

    assert {person["name"] for person in report["people"]} == {"Alvin", "StÃ¶d Hela Dagen"}
    assert alvin["kpi_points"] == 300
    assert alvin["planned_kpi_points"] == 300
    assert alvin["productivity_pct"] == 1
    assert alvin["kpi_minutes"] == 180
    assert alvin["support_minutes"] == 60
    assert alvin["absence_minutes"] == 60
    assert [segment["display"] for segment in alvin["segments"][:3]] == [
        "Manual_Pick",
        "Decanting",
        "Full_Manual_Buffer",
    ]
    assert alvin["segments"][3]["kind"] == "support"
    assert alvin["segments"][4]["display"] == "absence"
    assert len(alvin["time_cells"]) == 5
    points_by_cell = {f"{cell['start']}-{cell['end']}": cell["points"] for cell in alvin["time_cells"]}
    status_by_cell = {f"{cell['start']}-{cell['end']}": cell["score_status"] for cell in alvin["time_cells"]}
    assert points_by_cell["08:00-09:00"] == 100
    assert points_by_cell["09:00-10:00"] == 100
    assert points_by_cell["10:00-11:00"] == 100
    assert status_by_cell["07:00-08:00"] == "low"
    assert status_by_cell["08:00-09:00"] == "good"
    assert status_by_cell["10:00-11:00"] is None
    support_cell = next(cell for cell in alvin["time_cells"] if cell["start"] == "10:00")
    assert support_cell["diff_count"] == 0
    assert support_cell["process_points"] == [{"process": "Manual_Pick", "points": 100.0, "event_count": 1}]
    support_only = next(person for person in report["people"] if person["name"] == "StÃ¶d Hela Dagen")
    assert support_only["kpi_points"] == 0
    assert support_only["planned_kpi_points"] == 0
    assert support_only["productivity_pct"] is None
    assert support_only["kpi_minutes"] == 0
    assert support_only["support_minutes"] == 300
    assert len(support_only["time_cells"]) == 5
    assert all(cell["kind"] == "support" for cell in support_only["time_cells"])
    assert "Absence Hela Dagen" not in {person["name"] for person in report["people"]}
    assert report["summary"]["people"] == 2
    assert report["summary"]["kpi_points"] == 300
    assert report["summary"]["planned_kpi_points"] == 300
    assert report["summary"]["kpi_minutes"] == 180
    assert report["summary"]["support_minutes"] == 360
    assert report["summary"]["unmatched_event_count"] == 2
    assert "kpi_target_rule" not in report["sources"]


def test_person_productivity_report_uses_internal_kpi_logic_without_rule_file(tmp_path):
    db = make_session()
    data = seed_people_and_activities(db)
    pick = write(
        tmp_path / "pick.csv",
        """
Zon\tPlockat\tAnvandare\tAndrad\tLokation\tBolag\tLager
A\t10\talvin\t2026-06-08 07:10:00\tA101\tMG\t404
H\t1\tALV94\t2026-06-08 09:10:00\tBUFF01\tGG\t404
A\t1\tALV94\t2026-06-08 10:10:00\tA101\tMG\t404
""",
    )
    trans = write(
        tmp_path / "trans.csv",
        """
Typ\tTill\tAntal\tAnvandare\tTimestamp\tBolag\tLager
26\tAS100\t20\tALV94\t2026-06-08 08:10:00\tGG\t404
""",
    )
    files = {
        "pick": pick,
        "trans": trans,
        "pallet": empty_file(tmp_path, "pallet.csv", "Typ\tAnvandare\tAndrad\tBolag\tLager"),
        "receive": empty_file(tmp_path, "receive.csv", "Typ\tStatus\tAnvandare\tTimestamp\tBolag\tLager"),
        "sort": empty_file(tmp_path, "sort.csv", "SSCC\tAnvandare\tTimestamp\tSandningsnr"),
        "kpi": base_kpi_file(tmp_path),
    }

    report = build_person_productivity_report_from_files(
        db,
        files,
        report_date=date(2026, 6, 8),
        business_id=data["business"].id,
    )
    alvin = next(person for person in report["people"] if person["name"] == "Alvin")
    support_only = next(person for person in report["people"] if person["support_minutes"] == 300)

    assert len(report["people"]) == 2
    assert {person["name"] for person in report["people"]} == {"Alvin", support_only["name"]}
    assert alvin["kpi_points"] == 300
    assert alvin["planned_kpi_points"] == 300
    assert alvin["productivity_pct"] == 1
    assert alvin["missing_rule_processes"] == []
    assert support_only["support_minutes"] == 300
    assert support_only["productivity_pct"] is None
    assert "Absence Hela Dagen" not in {person["name"] for person in report["people"]}
    assert "kpi_target_rule" not in report["sources"]
    assert report["summary"]["scored_event_count"] == 4
    assert report["summary"]["missing_rule_processes"] == []


def test_productivity_time_cells_use_activity_area_not_person_home_area(tmp_path):
    db = make_session()
    business = Business(code="STIGAMO", name="Stigamo")
    autostore = Area(code="AS", name="Autostore", business=business)
    granngarden = Area(code="GG", name="GranngÃ¥rden", business=business)
    helpall = Activity(
        code="GG_HELPALL",
        label="GG Helpall",
        area=granngarden,
        business=business,
        kpi_process_name="Full_Manual_Buffer",
    )
    person = Person(
        name="Mohammed Seido",
        noman="MOH",
        business=business,
        home_area=autostore,
        created_at=datetime(2026, 6, 1, 8, 0),
    )
    db.add_all([business, autostore, granngarden, helpall, person])
    db.flush()
    db.add(
        ScheduleCell(
            year=2026,
            week=24,
            weekday=1,
            hour=7,
            minute_start=0,
            minute_end=60,
            person_id=person.id,
            activity_id=helpall.id,
        )
    )
    db.commit()
    files = {
        "pick": write(
            tmp_path / "pick.csv",
            """
Zon\tPlockat\tAnvÃ¤ndare\tÃ„ndrad\tLokation\tBolag\tLager
H\t1\tMOH\t2026-06-08 07:10:00\tBUFF01\tGG\t404
""",
        ),
        "trans": empty_file(tmp_path, "trans.csv", "Typ\tTill\tAntal\tAnvÃ¤ndare\tTimestamp\tBolag\tLager"),
        "pallet": empty_file(tmp_path, "pallet.csv", "Typ\tAnvÃ¤ndare\tÃ„ndrad\tBolag\tLager"),
        "receive": empty_file(tmp_path, "receive.csv", "Typ\tStatus\tAnvÃ¤ndare\tTimestamp\tBolag\tLager"),
        "sort": empty_file(tmp_path, "sort.csv", "SSCC\tAnvÃ¤ndare\tTimestamp\tSÃ¤ndningsnr"),
        "kpi": base_kpi_file(tmp_path),
    }

    report = build_person_productivity_report_from_files(
        db,
        files,
        report_date=date(2026, 6, 8),
        business_id=business.id,
    )
    mohammed = next(item for item in report["people"] if item["name"] == "Mohammed Seido")
    cell = mohammed["time_cells"][0]

    assert mohammed["home_area"] == "Autostore"
    assert cell["activity_label"] == "GG Helpall"
    assert cell["activity_area_name"] == "GranngÃ¥rden"
    assert cell["activity_area_code"] == "GG"
    assert cell["points"] == 100


def test_diff_points_count_and_create_notice(tmp_path):
    db = make_session()
    data = seed_people_and_activities(db)
    files = {
        "pick": empty_file(tmp_path, "pick.csv", "Zon\tPlockat\tAnvÃ¤ndare\tÃ„ndrad\tLokation\tBolag\tLager"),
        "trans": write(
            tmp_path / "trans.csv",
            """
Typ\tTill\tAntal\tAnvÃ¤ndare\tTimestamp\tBolag\tLager
26\tAS100\t20\tALV94\t2026-06-08 07:10:00\tGG\t404
""",
        ),
        "pallet": empty_file(tmp_path, "pallet.csv", "Typ\tAnvÃ¤ndare\tÃ„ndrad\tBolag\tLager"),
        "receive": empty_file(tmp_path, "receive.csv", "Typ\tStatus\tAnvÃ¤ndare\tTimestamp\tBolag\tLager"),
        "sort": empty_file(tmp_path, "sort.csv", "SSCC\tAnvÃ¤ndare\tTimestamp\tSÃ¤ndningsnr"),
        "kpi": base_kpi_file(tmp_path),
    }

    report = build_person_productivity_report_from_files(
        db,
        files,
        report_date="2026-06-08",
        business_id=data["business"].id,
    )
    alvin = next(person for person in report["people"] if person["name"] == "Alvin")

    assert alvin["kpi_points"] == 100
    assert alvin["diffs"][0]["scheduled_display"] == "Manual_Pick"
    assert alvin["diffs"][0]["actual_process"] == "Decanting"
    diff_cell = next(cell for cell in alvin["time_cells"] if cell["start"] == "07:00")
    assert diff_cell["points"] == 100
    assert diff_cell["diff_count"] == 1
    assert diff_cell["diffs"][0]["actual_process"] == "Decanting"
    assert report["summary"]["diff_count"] == 1


def test_productivity_snapshot_sync_is_half_hourly_and_atomic(monkeypatch, tmp_path):
    source_calls = []

    def fake_sources_available(_keys):
        return True

    def fake_fetch(source_key, filters=None):
        source_calls.append((source_key, filters))
        path = tmp_path / f"{source_key}.csv"
        write(path, "col\nvalue")
        return path, WorkflowSourceEntry(key=source_key, label=source_key, view=f"v_{source_key}", status="api", row_count=1)

    monkeypatch.setattr(productivity_sync, "sources_available", fake_sources_available)
    monkeypatch.setattr(productivity_sync, "fetch_source_to_temp", fake_fetch)

    result = productivity_sync.sync_productivity_snapshot(date(2026, 6, 8), reference_dir=tmp_path)

    assert result["status"] == "ok"
    assert productivity_sync.next_productivity_sync_at(datetime(2026, 6, 8, 10, 1, tzinfo=productivity_sync.LOCAL_TZ)).minute == 30
    assert productivity_sync.next_productivity_sync_at(datetime(2026, 6, 8, 10, 31, tzinfo=productivity_sync.LOCAL_TZ)).minute == 0
    assert all(filters for source, filters in source_calls if source != "kpi")
    first_pick = gzip.open(
        productivity_sync.productivity_snapshot_source_path(date(2026, 6, 8), "pick", tmp_path),
        "rt",
        encoding="utf-8",
    ).read()

    def failing_fetch(source_key, filters=None):
        if source_key == "trans":
            raise RuntimeError("boom")
        path = tmp_path / f"failed-{source_key}.csv"
        write(path, "col\nnew")
        return path, WorkflowSourceEntry(key=source_key, label=source_key, view=f"v_{source_key}", status="api", row_count=1)

    monkeypatch.setattr(productivity_sync, "fetch_source_to_temp", failing_fetch)
    try:
        productivity_sync.sync_productivity_snapshot(date(2026, 6, 8), reference_dir=tmp_path)
    except productivity_sync.ProductivitySyncError:
        pass

    second_pick = gzip.open(
        productivity_sync.productivity_snapshot_source_path(date(2026, 6, 8), "pick", tmp_path),
        "rt",
        encoding="utf-8",
    ).read()
    assert second_pick == first_pick


def test_productivity_snapshot_history_bootstraps_13_days_and_preserves_old_days(monkeypatch, tmp_path):
    source_calls = []
    version = {"value": "first"}

    def fake_sources_available(_keys):
        return True

    def fake_fetch(source_key, filters=None):
        source_calls.append((source_key, filters))
        filter_date = "target"
        if filters:
            filter_date = str(filters[0]["value"][0])[:10]
        path = tmp_path / f"{source_key}-{filter_date}-{version['value']}.csv"
        write(path, f"col\n{source_key}-{filter_date}-{version['value']}")
        return path, WorkflowSourceEntry(key=source_key, label=source_key, view=f"v_{source_key}", status="api", row_count=1)

    monkeypatch.setattr(productivity_sync, "sources_available", fake_sources_available)
    monkeypatch.setattr(productivity_sync, "fetch_source_to_temp", fake_fetch)

    result = productivity_sync.ensure_productivity_snapshot_history(
        date(2026, 6, 9),
        reference_dir=tmp_path,
    )

    assert result["status"] == "ok"
    assert result["dates"][0] == "2026-05-27"
    assert result["dates"][-1] == "2026-06-09"
    assert len(result["dates"]) == 14
    assert productivity_sync.productivity_snapshot_source_path(date(2026, 5, 27), "pick", tmp_path).is_file()
    yesterday_pick_before = gzip.open(
        productivity_sync.productivity_snapshot_source_path(date(2026, 6, 8), "pick", tmp_path),
        "rt",
        encoding="utf-8",
    ).read()

    version["value"] = "second"
    source_calls.clear()
    productivity_sync.sync_productivity_snapshot(date(2026, 6, 9), reference_dir=tmp_path)

    today_pick_after = gzip.open(
        productivity_sync.productivity_snapshot_source_path(date(2026, 6, 9), "pick", tmp_path),
        "rt",
        encoding="utf-8",
    ).read()
    yesterday_pick_after = gzip.open(
        productivity_sync.productivity_snapshot_source_path(date(2026, 6, 8), "pick", tmp_path),
        "rt",
        encoding="utf-8",
    ).read()

    assert "pick-2026-06-09-second" in today_pick_after
    assert yesterday_pick_after == yesterday_pick_before
    assert {str(filters[0]["value"][0])[:10] for source, filters in source_calls if source != "kpi"} == {"2026-06-09"}


def test_productivity_historical_backfill_fetches_one_older_day_per_run_day(monkeypatch, tmp_path):
    source_calls = []

    def fake_sources_available(_keys):
        return True

    def fake_fetch(source_key, filters=None):
        source_calls.append((source_key, filters))
        filter_date = "target"
        if filters:
            filter_date = str(filters[0]["value"][0])[:10]
        path = tmp_path / f"{source_key}-{filter_date}.csv"
        write(path, f"col\n{source_key}-{filter_date}")
        return path, WorkflowSourceEntry(key=source_key, label=source_key, view=f"v_{source_key}", status="api", row_count=1)

    monkeypatch.delenv("PRODUCTIVITY_HISTORY_START_DATE", raising=False)
    monkeypatch.setattr(productivity_sync, "sources_available", fake_sources_available)
    monkeypatch.setattr(productivity_sync, "fetch_source_to_temp", fake_fetch)

    productivity_sync.sync_productivity_snapshot(date(2026, 6, 8), reference_dir=tmp_path)
    source_calls.clear()

    first = productivity_sync.ensure_productivity_historical_backfill(
        now=datetime(2026, 6, 9, 10, 0, tzinfo=productivity_sync.LOCAL_TZ),
        reference_dir=tmp_path,
    )
    second = productivity_sync.ensure_productivity_historical_backfill(
        now=datetime(2026, 6, 9, 11, 0, tzinfo=productivity_sync.LOCAL_TZ),
        reference_dir=tmp_path,
    )
    third = productivity_sync.ensure_productivity_historical_backfill(
        now=datetime(2026, 6, 10, 10, 0, tzinfo=productivity_sync.LOCAL_TZ),
        reference_dir=tmp_path,
    )

    assert first["status"] == "ok"
    assert first["dates"] == ["2026-06-07"]
    assert second["skipped"] is True
    assert third["dates"] == ["2026-06-06"]
    assert productivity_sync.productivity_snapshot_source_path(date(2026, 6, 7), "pick", tmp_path).is_file()
    assert productivity_sync.productivity_snapshot_source_path(date(2026, 6, 6), "pick", tmp_path).is_file()
    assert {str(filters[0]["value"][0])[:10] for source, filters in source_calls if source != "kpi"} == {
        "2026-06-07",
        "2026-06-06",
    }


def test_productivity_snapshot_uses_coredata_kpi_when_kpi_api_is_forbidden(monkeypatch, tmp_path):
    kpi_path = write(tmp_path / "local-kpi.csv", "Bolag\tProcessnamn\tRader\nMG\tManual_Pick\t1")

    def fake_sources_available(_keys):
        return True

    def fake_fetch(source_key, filters=None):
        if source_key == "kpi":
            raise WorkflowDataError("Extern datakÃ¤lla svarade med HTTP 403.")
        path = tmp_path / f"{source_key}.csv"
        write(path, "col\nvalue")
        return path, WorkflowSourceEntry(key=source_key, label=source_key, view=f"v_{source_key}", status="api", row_count=1)

    monkeypatch.setattr(productivity_sync, "sources_available", fake_sources_available)
    monkeypatch.setattr(productivity_sync, "fetch_source_to_temp", fake_fetch)
    monkeypatch.setattr(productivity_sync, "find_kpi_file", lambda *_args, **_kwargs: kpi_path)

    result = productivity_sync.sync_productivity_snapshot(
        date(2026, 6, 9),
        reference_dir=tmp_path,
        business_code="STIGAMO",
    )

    assert result["status"] == "ok"
    assert result["sources"][-1]["key"] == "kpi"
    assert result["sources"][-1]["status"] == "coredata_fallback"
    assert "HTTP 403" in result["sources"][-1]["fallback_reason"]
    kpi_snapshot = gzip.open(
        productivity_sync.productivity_snapshot_source_path(date(2026, 6, 9), "kpi", tmp_path),
        "rt",
        encoding="utf-8",
    ).read()
    assert "Manual_Pick" in kpi_snapshot
