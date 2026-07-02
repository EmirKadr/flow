from datetime import date, timedelta

import pytest

from app.backend import archive_cache_cli as cli
from app.backend import archive_cache_sync as sync
from app.backend import local_archive_store as store
from app.backend.config import settings


TENANT = "frey"
VIEW = "dblog_pick_log"          # retention 40 dgr
LIVE = "v_ask_pick_log_full"
SEED_DAYS = 90
CHUNK_DAYS = 30


@pytest.fixture()
def enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_DIR", str(tmp_path / "archive_cache"))
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_SEED_DAYS", SEED_DAYS)
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_CHUNK_DAYS", CHUNK_DAYS)
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_EMPTY_STOP_DAYS", 300)


def _days(start, end):
    out = []
    day = start
    while day <= end:
        out.append(day)
        day += timedelta(days=1)
    return out


def _row(day):
    return {"order_num": f"O{day.isoformat()}", "company": "GG", "qty_suf": "1", "time_stamp_int": day.strftime("%Y%m%d")}


class _FetchCalls(list):
    pass


def _prepopulate(days):
    store.append_rows_by_date(TENANT, VIEW, [_row(d) for d in days])


def _install_fake_fetch(monkeypatch):
    calls = _FetchCalls()
    snapshot_calls = []

    def fake_fetch(tenant, view_id, start, end):
        calls.append((view_id, start, end))
        return [_row(d) for d in _days(start, end)]

    def fake_snapshot(tenant, view_id, today):
        snapshot_calls.append((view_id, today))
        return [{"item_num": "A1", "company": "GG", "timestamp": today.isoformat()}]

    monkeypatch.setattr(sync, "_fetch", fake_fetch)
    monkeypatch.setattr(sync, "_fetch_snapshot", fake_snapshot)
    calls.snapshot_calls = snapshot_calls
    return calls


def _view_by_day(calls):
    """Karta dag -> vy den hämtades från, expanderat ur alla (vy, start, slut)-anrop."""
    mapping = {}
    for view_id, start, end in calls:
        for day in _days(start, end):
            mapping[day] = view_id
    return mapping


def test_initial_fill_covers_full_range_split_dblog_and_live(enabled, monkeypatch):
    calls = _install_fake_fetch(monkeypatch)
    today = date(2026, 6, 1)
    cutoff = today - timedelta(days=40)
    target_start = today - timedelta(days=SEED_DAYS)
    target_end = today - timedelta(days=1)

    res = sync.run_view(TENANT, VIEW, today=today)

    vbd = _view_by_day(calls)
    for day in _days(target_start, target_end):
        assert day in vbd, f"dag {day} hämtades aldrig"
        assert vbd[day] == (VIEW if day < cutoff else LIVE)
    assert store.ingested_range(TENANT, VIEW) == (target_start, target_end)
    assert res["fully_covered"] and res["newly_complete"]


def test_fill_is_chunked(enabled, monkeypatch):
    calls = _install_fake_fetch(monkeypatch)
    sync.run_view(TENANT, VIEW, today=date(2026, 6, 1))
    # 90 dagar i 30-dagarschunkar -> klart fler än ett anrop (inte en jättehämtning).
    assert len(calls) >= 3


def test_deep_seed_stops_after_empty_history_threshold(enabled, monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_SEED_DAYS", 1000)
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_CHUNK_DAYS", 100)
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_EMPTY_STOP_DAYS", 300)
    calls = _FetchCalls()
    today = date(2026, 6, 1)
    target_start = today - timedelta(days=1000)
    target_end = today - timedelta(days=1)
    first_data = target_end - timedelta(days=50)

    def fake_fetch(tenant, view_id, start, end):
        calls.append((view_id, start, end))
        if end < first_data:
            return []
        return [_row(d) for d in _days(max(start, first_data), end)]

    monkeypatch.setattr(sync, "_fetch", fake_fetch)

    res = sync.run_view(TENANT, VIEW, today=today)

    assert res["fully_covered"] is True
    assert res["empty_stopped"] is True
    assert min(start for _view, start, _end in calls) > target_start
    assert store.ingested_range(TENANT, VIEW) == (first_data, target_end)
    assert store.covered_range(TENANT, VIEW) == (target_start, target_end)
    coverage = sync.view_coverage(TENANT, VIEW, today=today)
    assert coverage["fully_covered"] is True
    assert coverage["ingested_start"] == first_data.isoformat()
    assert coverage["covered_start"] == target_start.isoformat()
    assert any(entry["source"] == "empty_stop" for entry in store.read_sync_log(TENANT, limit=200))
    old_end = target_start + timedelta(days=10)
    old_filter = [
        {
            "id": "time_stamp_int",
            "operator": "Between",
            "value": [int(target_start.strftime("%Y%m%d")), int(old_end.strftime("%Y%m%d"))],
        }
    ]
    assert store.query_rows(TENANT, VIEW, old_filter) == []


def test_second_run_same_day_fetches_nothing(enabled, monkeypatch):
    calls = _install_fake_fetch(monkeypatch)
    today = date(2026, 6, 1)
    sync.run_view(TENANT, VIEW, today=today)
    calls.clear()
    sync.run_view(TENANT, VIEW, today=today)
    assert calls == []  # allt redan cachat -> inga API-anrop


def test_resume_only_fills_missing_deep_history(enabled, monkeypatch):
    today = date(2026, 6, 1)
    target_start = today - timedelta(days=SEED_DAYS)
    target_end = today - timedelta(days=1)
    existing_start = date(2026, 5, 1)  # simulerar avbruten seed: bara nyaste blocket finns
    _prepopulate(_days(existing_start, target_end))

    calls = _install_fake_fetch(monkeypatch)
    sync.run_view(TENANT, VIEW, today=today)

    vbd = _view_by_day(calls)
    for day in _days(existing_start, target_end):
        assert day not in vbd, f"redan lagrad dag {day} hämtades om"
    for day in _days(target_start, existing_start - timedelta(days=1)):
        assert day in vbd, f"saknad djuphistorik-dag {day} fylldes inte på"
    assert store.ingested_range(TENANT, VIEW) == (target_start, target_end)


def test_forward_topup_only_new_day_from_live(enabled, monkeypatch):
    today0 = date(2026, 6, 1)
    _prepopulate(_days(today0 - timedelta(days=SEED_DAYS), today0 - timedelta(days=1)))

    calls = _install_fake_fetch(monkeypatch)
    sync.run_view(TENANT, VIEW, today=today0 + timedelta(days=1))

    vbd = _view_by_day(calls)
    assert set(vbd) == {today0}          # bara den nya dagen
    assert vbd[today0] == LIVE           # och den finns fortfarande i live-vyn


def test_forward_topup_empty_day_marks_covered(enabled, monkeypatch):
    today0 = date(2026, 6, 1)
    target_start = today0 - timedelta(days=SEED_DAYS)
    target_end = today0 - timedelta(days=1)
    _prepopulate(_days(target_start, target_end))
    calls = _FetchCalls()

    def fake_fetch(tenant, view_id, start, end):
        calls.append((view_id, start, end))
        return []

    monkeypatch.setattr(sync, "_fetch", fake_fetch)

    res = sync.run_view(TENANT, VIEW, today=today0 + timedelta(days=1))

    assert res["fully_covered"] is True
    assert store.ingested_range(TENANT, VIEW) == (target_start, target_end)
    assert store.covered_range(TENANT, VIEW) == (target_start, today0)
    assert sync.missing_window(TENANT, VIEW, today=today0 + timedelta(days=1)) is None
    assert calls == [(LIVE, today0, today0)]


def test_gap_beyond_retention_uses_dblog_and_live(enabled, monkeypatch):
    today0 = date(2026, 6, 1)
    _prepopulate(_days(today0 - timedelta(days=SEED_DAYS), today0 - timedelta(days=1)))

    calls = _install_fake_fetch(monkeypatch)
    today1 = today0 + timedelta(days=50)   # ingen synk på 50 dgr > retention 40
    sync.run_view(TENANT, VIEW, today=today1)

    vbd = _view_by_day(calls)
    cutoff1 = today1 - timedelta(days=40)
    for day in _days(today0, today1 - timedelta(days=1)):
        assert day in vbd
        assert vbd[day] == (VIEW if day < cutoff1 else LIVE)


def test_sync_log_records_plan_source_and_complete(enabled, monkeypatch):
    _install_fake_fetch(monkeypatch)
    sync.run_view(TENANT, VIEW, today=date(2026, 6, 1))
    sources = {entry["source"] for entry in store.read_sync_log(TENANT, limit=200)}
    assert "plan" in sources          # vilka dagar som skulle hämtas loggades
    assert "complete" in sources      # klarmarkering när hela intervallet var hämtat
    assert {"dblog", "live"} & sources  # minst en datakälla loggades per chunk


def test_deep_seed_false_skips_unseeded_view(enabled, monkeypatch):
    calls = _install_fake_fetch(monkeypatch)
    res = sync.run_view(TENANT, VIEW, today=date(2026, 6, 1), deep_seed=False)
    assert calls == []                                   # serverstart drar inget tungt
    assert res["skipped"] is True
    assert store.ingested_range(TENANT, VIEW) == (None, None)


def test_deep_seed_false_tops_up_already_seeded_view(enabled, monkeypatch):
    today0 = date(2026, 6, 1)
    _prepopulate(_days(today0 - timedelta(days=SEED_DAYS), today0 - timedelta(days=1)))
    calls = _install_fake_fetch(monkeypatch)
    sync.run_view(TENANT, VIEW, today=today0 + timedelta(days=1), deep_seed=False)
    vbd = _view_by_day(calls)
    assert set(vbd) == {today0} and vbd[today0] == LIVE  # bara nya dagen, framåt


def test_seed_all_fills_all_views_parallel(enabled, monkeypatch):
    _install_fake_fetch(monkeypatch)
    res = sync.seed_all([TENANT], today=date(2026, 6, 1), max_workers=3)
    assert res["status"] == "ok"
    assert {r["view"] for r in res["results"]} == set(sync.SYNC_CACHE_VIEWS)
    assert all(r["fully_covered"] for r in res["results"])


def test_seed_all_can_target_single_view(enabled, monkeypatch):
    calls = _install_fake_fetch(monkeypatch)
    res = sync.seed_all([TENANT], today=date(2026, 6, 1), max_workers=3, view_ids=["dblog_dispatch_pallet_log"])
    assert res["status"] == "ok"
    assert {r["view"] for r in res["results"]} == {"dblog_dispatch_pallet_log"}
    assert {view_id for view_id, _start, _end in calls} <= {"dblog_dispatch_pallet_log", "dispatch_pallet_log"}


def test_cli_default_includes_archive_and_snapshot_views(monkeypatch, capsys):
    captured = {}

    def fake_seed_all(tenants, *, max_workers=None, progress=None, view_ids=None):
        captured["tenants"] = tenants
        captured["max_workers"] = max_workers
        captured["view_ids"] = view_ids
        return {"status": "ok", "results": [{"view": "item_alias", "fully_covered": True}]}

    monkeypatch.setattr(cli.store, "is_enabled", lambda: True)
    monkeypatch.setattr(cli.sync, "seed_all", fake_seed_all)

    assert cli.main(["--tenant", "frey"]) == 0
    assert captured["tenants"] == ["frey"]
    assert captured["view_ids"] is None  # seed_all default = SYNC_CACHE_VIEWS.
    assert "DuckDB-cache" in capsys.readouterr().out


def test_cli_can_run_snapshots_only(monkeypatch):
    captured = {}

    def fake_seed_all(tenants, *, max_workers=None, progress=None, view_ids=None):
        captured["view_ids"] = view_ids
        return {"status": "ok", "results": [{"view": "item_alias", "snapshot": True, "fully_covered": True}]}

    monkeypatch.setattr(cli.store, "is_enabled", lambda: True)
    monkeypatch.setattr(cli.sync, "seed_all", fake_seed_all)

    assert cli.main(["--snapshots-only"]) == 0
    assert captured["view_ids"] == list(sync.SYNC_SNAPSHOT_VIEWS)


def test_cli_productivity_only_fetches_range_and_skips_archive(monkeypatch):
    captured = {}

    class FakeDb:
        def close(self):
            captured["closed"] = True

    def fail_store_enabled():
        raise AssertionError("productivity-only ska inte krava arkivcache")

    def fail_seed_all(*args, **kwargs):
        raise AssertionError("archive seed ska inte koras")

    def fake_history(end_date, *, days_back, business_code, db, warm_cache):
        captured["end_date"] = end_date
        captured["days_back"] = days_back
        captured["business_code"] = business_code
        captured["db"] = db
        captured["warm_cache"] = warm_cache
        return {"status": "ok", "dates": ["2025-01-01", "2025-12-31"], "errors": []}

    monkeypatch.setattr(cli.store, "is_enabled", fail_store_enabled)
    monkeypatch.setattr(cli.sync, "seed_all", fail_seed_all)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(cli, "sync_productivity_snapshot_history", fake_history)

    assert cli.main([
        "--productivity-only",
        "--productivity-start",
        "2025-01-01",
        "--productivity-end",
        "2025-12-31",
        "--productivity-chunk-days",
        "999",
        "--business-code",
        "STIGAMO",
    ]) == 0
    assert captured["end_date"] == date(2025, 12, 31)
    assert captured["days_back"] == 364
    assert captured["business_code"] == "STIGAMO"
    assert captured["warm_cache"] is True
    assert captured["closed"] is True


def test_cli_productivity_start_defaults_end_to_yesterday(monkeypatch):
    captured = {}

    class FakeDb:
        def close(self):
            captured["closed"] = True

    def fake_seed_all(tenants, *, max_workers=None, progress=None, view_ids=None):
        captured["archive_tenants"] = tenants
        captured["archive_view_ids"] = view_ids
        return {"status": "ok", "results": [{"view": "item_alias", "fully_covered": True}]}

    def fake_history(end_date, *, days_back, business_code, db, warm_cache):
        captured["end_date"] = end_date
        captured["days_back"] = days_back
        captured["business_code"] = business_code
        captured["db"] = db
        captured["warm_cache"] = warm_cache
        return {"status": "ok", "dates": ["2025-01-01", "2026-07-01"], "errors": []}

    monkeypatch.setattr(cli.store, "is_enabled", lambda: True)
    monkeypatch.setattr(cli.sync, "seed_all", fake_seed_all)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(cli, "sync_productivity_snapshot_history", fake_history)
    monkeypatch.setattr(cli, "_default_productivity_end", lambda: date(2026, 7, 1))

    assert cli.main([
        "--tenant",
        "frey",
        "--with-productivity",
        "--productivity-start",
        "2025-01-01",
        "--productivity-chunk-days",
        "999",
        "--business-code",
        "STIGAMO",
    ]) == 0
    assert captured["archive_tenants"] == ["frey"]
    assert captured["archive_view_ids"] is None
    assert captured["end_date"] == date(2026, 7, 1)
    assert captured["days_back"] == 546
    assert captured["business_code"] == "STIGAMO"
    assert captured["warm_cache"] is True
    assert captured["closed"] is True


def test_cli_productivity_range_is_chunked(monkeypatch):
    captured = {"calls": []}

    class FakeDb:
        def close(self):
            captured["closed"] = True

    def fake_history(end_date, *, days_back, business_code, db, warm_cache):
        captured["calls"].append((end_date, days_back, business_code, warm_cache))
        return {"status": "ok", "dates": [end_date.isoformat()], "errors": []}

    monkeypatch.setattr(cli.store, "is_enabled", lambda: False)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(cli, "sync_productivity_snapshot_history", fake_history)

    assert cli.main([
        "--productivity-only",
        "--productivity-start",
        "2025-01-01",
        "--productivity-end",
        "2025-02-05",
        "--productivity-chunk-days",
        "31",
    ]) == 0
    assert captured["calls"] == [
        (date(2025, 1, 31), 30, "STIGAMO", True),
        (date(2025, 2, 5), 4, "STIGAMO", True),
    ]
    assert captured["closed"] is True


def test_cli_with_productivity_without_dates_runs_archive_then_prebuild(monkeypatch):
    captured = {}

    class FakeDb:
        def close(self):
            captured["closed"] = True

    def fake_seed_all(tenants, *, max_workers=None, progress=None, view_ids=None):
        captured["archive_tenants"] = tenants
        captured["archive_view_ids"] = view_ids
        return {"status": "ok", "results": [{"view": "item_alias", "fully_covered": True}]}

    def fake_prebuild(*, business_code, db, force):
        captured["business_code"] = business_code
        captured["force"] = force
        return {"status": "ok", "dates": ["2025-01-01"], "errors": []}

    monkeypatch.setattr(cli.store, "is_enabled", lambda: True)
    monkeypatch.setattr(cli.sync, "seed_all", fake_seed_all)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(cli, "prebuild_ready_productivity_days", fake_prebuild)

    assert cli.main([
        "--tenant",
        "frey",
        "--with-productivity",
        "--business-code",
        "STIGAMO",
        "--force-productivity-prebuild",
    ]) == 0
    assert captured["archive_tenants"] == ["frey"]
    assert captured["archive_view_ids"] is None
    assert captured["business_code"] == "STIGAMO"
    assert captured["force"] is True
    assert captured["closed"] is True


def test_cli_productivity_date_can_skip_prebuild(monkeypatch):
    captured = {}

    class FakeDb:
        def close(self):
            captured["closed"] = True

    def fake_snapshot(snapshot_date, *, business_code, db, warm_cache):
        captured["snapshot_date"] = snapshot_date
        captured["business_code"] = business_code
        captured["warm_cache"] = warm_cache
        return {"status": "ok", "date": snapshot_date.isoformat(), "errors": []}

    monkeypatch.setattr(cli.store, "is_enabled", lambda: False)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(cli, "sync_productivity_snapshot", fake_snapshot)

    assert cli.main([
        "--productivity-only",
        "--productivity-date",
        "2025-05-01",
        "--productivity-no-prebuild",
    ]) == 0
    assert captured["snapshot_date"] == date(2025, 5, 1)
    assert captured["business_code"] == "STIGAMO"
    assert captured["warm_cache"] is False
    assert captured["closed"] is True


def test_cli_productivity_prebuild_requires_reachable_database(monkeypatch, capsys):
    captured = {}

    class BrokenDb:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("db offline")

        def rollback(self):
            captured["rollback"] = True

        def close(self):
            captured["closed"] = True

    def fail_history(*_args, **_kwargs):
        raise AssertionError("ska inte hamta produktivitet nar prebuild-db saknas")

    monkeypatch.setattr(cli.store, "is_enabled", lambda: False)
    monkeypatch.setattr(cli, "SessionLocal", lambda: BrokenDb())
    monkeypatch.setattr(cli, "sync_productivity_snapshot_history", fail_history)

    assert cli.main([
        "--productivity-only",
        "--productivity-start",
        "2025-01-01",
        "--productivity-end",
        "2025-01-01",
    ]) == 1
    out = capsys.readouterr().out
    assert "person_productivity_daily" in out
    assert "--productivity-no-prebuild" in out
    assert captured["rollback"] is True
    assert captured["closed"] is True


def test_sync_archive_views_include_sankey_dispatch_log():
    assert "dblog_dispatch_pallet_log" in sync.SYNC_ARCHIVE_VIEWS


def test_sync_snapshot_views_include_alias_not_buffer():
    assert "item_alias" in sync.SYNC_SNAPSHOT_VIEWS
    assert "v_ask_article_buffertpallet" not in sync.SYNC_SNAPSHOT_VIEWS


def test_run_snapshot_view_replaces_item_alias(enabled, monkeypatch):
    calls = _install_fake_fetch(monkeypatch)
    res = sync.run_snapshot_view(TENANT, "item_alias", today=date(2026, 6, 1))

    assert res["snapshot"] is True
    assert res["rows"] == 1
    assert calls.snapshot_calls == [("item_alias", date(2026, 6, 1))]
    cached = store.query_snapshot_rows(TENANT, "item_alias")
    assert cached is not None
    assert cached[0]["item_num"] == "A1"
    assert store.read_sync_log(TENANT, limit=5)[0]["source"] == "snapshot"


def test_run_view_emits_progress_events(enabled, monkeypatch):
    _install_fake_fetch(monkeypatch)
    events: list[dict] = []
    sync.run_view(TENANT, VIEW, today=date(2026, 6, 1), progress=events.append)
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "done"
    chunks = [e for e in events if e["type"] == "chunk"]
    assert chunks, "minst ett chunk-event"
    assert chunks[-1]["done_days"] == chunks[-1]["total_days"]  # slutar på 100%


def test_coverage_report_shows_missing_days_after_downtime(enabled, monkeypatch):
    _install_fake_fetch(monkeypatch)
    today0 = date(2026, 6, 1)
    sync.run_view(TENANT, VIEW, today=today0)

    later = today0 + timedelta(days=5)   # "servern var nere i flera nätter"
    cov = sync.view_coverage(TENANT, VIEW, today=later)
    assert cov["seeded"] is True
    assert cov["fully_covered"] is False
    assert cov["missing_days"] == 5

    report = sync.coverage_report(tenant=TENANT, today=later)
    assert report["enabled"] is True
    assert report["tenants"][0]["views"][0]["missing_days"] == 5
    assert "snapshots" in report["tenants"][0]
