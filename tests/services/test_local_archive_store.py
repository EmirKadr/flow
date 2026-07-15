import subprocess
import sys
import textwrap
from datetime import date, timedelta

import pytest

from app.backend import local_archive_store as store
from app.backend.config import settings


TENANT = "frey"
VIEW = "dblog_pick_log"


@pytest.fixture()
def enabled_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_DIR", str(tmp_path / "archive_cache"))
    return store


def _pick_row(order_num, day, company="GG", qty="1"):
    return {
        "order_num": order_num,
        "company": company,
        "qty_suf": qty,
        "time_stamp_int": day.strftime("%Y%m%d"),
    }


def _alias_row(item, company="GG", unit="KRT", factor="10"):
    return {
        "item_num": item,
        "company": company,
        "unit": unit,
        "conversion_factor": factor,
        "timestamp": "2026-06-01T00:00:00",
    }


def _between(start, end):
    return [
        {
            "id": "time_stamp_int",
            "operator": "Between",
            "value": [int(start.strftime("%Y%m%d")), int(end.strftime("%Y%m%d"))],
        }
    ]


def test_append_and_query_roundtrip(enabled_store):
    rows = [
        _pick_row("A1", date(2026, 3, 15), "GG", "5"),
        _pick_row("A2", date(2026, 3, 15), "MG", "3"),
        _pick_row("A3", date(2026, 3, 16), "GG", "9"),
    ]
    written = store.append_rows_by_date(TENANT, VIEW, rows)
    assert written == {date(2026, 3, 15): 2, date(2026, 3, 16): 1}
    assert store.ingested_range(TENANT, VIEW) == (date(2026, 3, 15), date(2026, 3, 16))

    filters = [
        {"id": "time_stamp_int", "operator": "Between", "value": [20260315, 20260316]},
        {"id": "company", "operator": "EQ", "value": "GG"},
    ]
    result = store.query_rows(TENANT, VIEW, filters)
    assert result is not None
    assert {row["order_num"] for row in result} == {"A1", "A3"}


def test_append_day_is_idempotent(enabled_store):
    day = date(2026, 3, 15)
    rows = [_pick_row("A1", day), _pick_row("A2", day)]
    store.append_day(TENANT, VIEW, day, rows)
    store.append_day(TENANT, VIEW, day, rows)  # samma dag igen
    filters = [{"id": "time_stamp_int", "operator": "Between", "value": [20260315, 20260315]}]
    result = store.query_rows(TENANT, VIEW, filters)
    assert result is not None
    assert len(result) == 2  # inga dubletter


def test_append_day_only_stores_matching_date(enabled_store):
    # Rader vars datum inte matchar dagen ignoreras.
    store.append_day(TENANT, VIEW, date(2026, 3, 15), [_pick_row("A1", date(2026, 3, 16))])
    assert store.ingested_range(TENANT, VIEW) == (None, None)


def test_append_rows_by_date_idempotent_single_connection(enabled_store):
    rows = [
        _pick_row("A1", date(2026, 3, 15)),
        _pick_row("A2", date(2026, 3, 15)),
        _pick_row("A3", date(2026, 3, 16)),
    ]
    first = store.append_rows_by_date(TENANT, VIEW, rows)
    assert first == {date(2026, 3, 15): 2, date(2026, 3, 16): 1}
    store.append_rows_by_date(TENANT, VIEW, rows)  # samma chunk igen -> ersätter, inga dubletter
    result = store.query_rows(
        TENANT, VIEW, [{"id": "time_stamp_int", "operator": "Between", "value": [20260315, 20260316]}]
    )
    assert result is not None and len(result) == 3


def test_query_returns_none_when_window_not_covered(enabled_store):
    store.append_rows_by_date(TENANT, VIEW, [_pick_row("A1", date(2026, 3, 15))])
    # Fönster som sträcker sig utanför ingestat intervall -> fallback (None).
    filters = [{"id": "time_stamp_int", "operator": "Between", "value": [20260101, 20260110]}]
    assert store.query_rows(TENANT, VIEW, filters) is None


def test_mark_covered_range_allows_empty_window_without_rows(enabled_store):
    start = date(2026, 3, 1)
    end = date(2026, 3, 31)

    store.mark_covered_range(TENANT, VIEW, start, end, detail="empty test")

    assert store.ingested_range(TENANT, VIEW) == (None, None)
    assert store.covered_range(TENANT, VIEW) == (start, end)
    assert store.query_rows(TENANT, VIEW, _between(start, end)) == []
    assert store.query_rows(TENANT, VIEW, _between(date(2026, 2, 28), start)) is None


def test_covered_range_merges_empty_prefix_with_actual_rows(enabled_store):
    start = date(2026, 3, 1)
    row_day = date(2026, 3, 15)
    store.mark_covered_range(TENANT, VIEW, start, row_day - timedelta(days=1), detail="empty prefix")
    store.append_rows_by_date(TENANT, VIEW, [_pick_row("A1", row_day)])

    assert store.covered_range(TENANT, VIEW) == (start, row_day)
    result = store.query_rows(TENANT, VIEW, _between(start, row_day))
    assert result is not None
    assert [row["order_num"] for row in result] == ["A1"]


def test_query_returns_none_for_unseeded_view(enabled_store):
    store.append_rows_by_date(TENANT, VIEW, [_pick_row("A1", date(2026, 3, 15))])
    filters = [{"id": "time_stamp_int", "operator": "Between", "value": [20260315, 20260315]}]
    assert store.query_rows(TENANT, "dblog_trans_log", filters) is None


def test_query_returns_none_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_DIR", str(tmp_path / "archive_cache"))
    store.append_rows_by_date(TENANT, VIEW, [_pick_row("A1", date(2026, 3, 15))])
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_ENABLED", False)
    filters = [{"id": "time_stamp_int", "operator": "Between", "value": [20260315, 20260315]}]
    assert store.query_rows(TENANT, VIEW, filters) is None


def test_replace_and_query_snapshot_rows(enabled_store):
    first = [_alias_row("A1", "GG"), _alias_row("A2", "MG")]
    assert store.replace_snapshot_rows(TENANT, "item_alias", first) == 2

    result = store.query_snapshot_rows(
        TENANT,
        "item_alias",
        [{"id": "company", "operator": "EQ", "value": "GG"}],
    )

    assert result is not None
    assert [row["item_num"] for row in result] == ["A1"]
    status = store.snapshot_status(TENANT, "item_alias")
    assert status["ready"] is True
    assert status["rows"] == 2

    assert store.replace_snapshot_rows(TENANT, "item_alias", [_alias_row("A3", "GG")]) == 1
    replaced = store.query_snapshot_rows(TENANT, "item_alias")
    assert replaced is not None
    assert [row["item_num"] for row in replaced] == ["A3"]


def test_query_snapshot_returns_none_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_DIR", str(tmp_path / "archive_cache"))
    store.replace_snapshot_rows(TENANT, "item_alias", [_alias_row("A1")])
    monkeypatch.setattr(settings, "ARCHIVE_CACHE_ENABLED", False)
    assert store.query_snapshot_rows(TENANT, "item_alias") is None


def test_query_applies_terms_and_ne_operators(enabled_store):
    store.append_rows_by_date(
        TENANT,
        VIEW,
        [
            _pick_row("A1", date(2026, 3, 15), "GG"),
            _pick_row("A2", date(2026, 3, 15), "MG"),
            _pick_row("A3", date(2026, 3, 15), "R3"),
        ],
    )
    window = {"id": "time_stamp_int", "operator": "Between", "value": [20260315, 20260315]}

    terms = store.query_rows(TENANT, VIEW, [window, {"id": "company", "operator": "Terms", "value": ["GG", "R3"]}])
    assert {row["order_num"] for row in terms} == {"A1", "A3"}

    ne = store.query_rows(TENANT, VIEW, [window, {"id": "company", "operator": "NE", "value": "MG"}])
    assert {row["order_num"] for row in ne} == {"A1", "A3"}


def test_duckdb_file_lock_blocks_a_second_process(tmp_path):
    """_LOCKS är PROCESSLOKALT. Medan en skrivare håller filen kan en annan
    process inte ens öppna den read_only — den får duckdb.IOException. Det är
    blockeraren för `uvicorn --workers > 1` (se DEPLOY.md, avsnitt
    'Leveransoptimering och workers'). Går detta test rött har DuckDB bytt
    semantik och DEPLOY.md måste omprövas."""
    pytest.importorskip("duckdb")
    path = tmp_path / "t.duckdb"
    child = textwrap.dedent(
        f'''
        import duckdb
        try:
            duckdb.connect(r"{path}", read_only=True).close()
            print("OPENED")
        except duckdb.IOException:
            print("LOCKED")
        '''
    )
    with store._connection(path, read_only=False) as con:
        con.execute("CREATE TABLE t(a VARCHAR)")
        result = subprocess.run(
            [sys.executable, "-c", child], capture_output=True, text=True, timeout=60
        )
    assert result.stdout.strip() == "LOCKED", result.stdout + result.stderr
