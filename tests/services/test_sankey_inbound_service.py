import csv
import gzip
from datetime import date

import pytest

from app.backend import sankey_inbound_service as sis
from app.backend.sankey_inbound import build as sankey_build
from app.backend.sankey_inbound import fetch as sankey_fetch
from app.backend.sankey_inbound import service as sankey_service
from app.backend.sankey_inbound import trace as sankey_trace
from app.backend.external_data_client import ExternalDataClientError
from app.backend.sankey_inbound_service import (
    _load_kpi_fallback_rows,
    _process_points_from_kpi,
    build_sankey_inbound_payload,
)


class _FakeClient:
    def __init__(self, fail_views, rows_by_view=None):
        self.fail_views = set(fail_views)
        self.rows_by_view = rows_by_view or {}
        self.calls = []

    def fetch_all(self, view, filters=None):
        self.calls.append(view)
        if view in self.fail_views:
            raise ExternalDataClientError("Extern datakälla svarade med HTTP 403.")
        return list(self.rows_by_view.get(view, []))


class _SnapshotClient:
    def __init__(self, per_company, cap_rows):
        self.per_company = per_company
        self.cap_rows = cap_rows
        self.calls = []

    def fetch_all(self, view, filters=None):
        self.calls.append((view, filters))
        operator = None
        company = None
        for flt in filters or []:
            if flt.get("id") == "company":
                operator = flt.get("operator")
                company = flt.get("value")
        if operator == "Terms":
            return [{"c": "mixed"}] * self.cap_rows
        if operator == "EQ":
            return [{"c": company}] * self.per_company.get(company, 0)
        return []


@pytest.fixture(autouse=True)
def _disable_productivity_snapshot_reuse(monkeypatch):
    monkeypatch.setattr(sankey_fetch, "PRODUCTIVITY_SNAPSHOT_REUSE_SOURCE_KEYS", set())


def _write_snapshot_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_snapshot_chunks_by_company_when_cap_hit(monkeypatch):
    monkeypatch.setattr(sis.settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 3, raising=False)
    client = _SnapshotClient(per_company={"GG": 2, "MG": 2}, cap_rows=3)

    rows, statuses, warnings = sis._fetch_snapshot_rows(
        client,
        key="buffer",
        view_id="v_ask_article_buffertpallet",
        company_codes=["GG", "MG"],
        company_filter=None,
    )

    assert len(rows) == 4  # 2 (GG) + 2 (MG), inte trunkerat till 3
    assert any(w["code"] == "snapshot_chunked_by_company" for w in warnings)
    assert any(s.get("segment") == "snapshot:GG" for s in statuses)


def test_snapshot_warns_when_single_company_still_capped(monkeypatch):
    monkeypatch.setattr(sis.settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 3, raising=False)
    # Ett enda bolag vars EQ-hämtning ändå slår i taket – inget mer att dela på.
    client = _SnapshotClient(per_company={"GG": 3}, cap_rows=3)

    rows, statuses, warnings = sis._fetch_snapshot_rows(
        client,
        key="buffer",
        view_id="v_ask_article_buffertpallet",
        company_codes=["GG"],
        company_filter="GG",
    )

    assert len(rows) == 3
    assert any(w["code"] == "snapshot_truncated" for w in warnings)


def test_fetch_view_rows_reuses_productivity_snapshots_when_range_is_ready(monkeypatch, tmp_path):
    first = tmp_path / "2026-06-01" / "receive.csv.gz"
    second = tmp_path / "2026-06-02" / "receive.csv.gz"
    _write_snapshot_rows(first, [{"rowid": "snap-1", "timestamp": "2026-06-01T08:00:00", "company": "GG"}])
    _write_snapshot_rows(second, [{"rowid": "snap-2", "timestamp": "2026-06-02T08:00:00", "company": "GG"}])
    monkeypatch.setattr(sankey_fetch, "PRODUCTIVITY_SNAPSHOT_REUSE_SOURCE_KEYS", {"receive"})
    monkeypatch.setattr(sankey_fetch, "productivity_snapshot_status", lambda _day: {"ready": True})
    monkeypatch.setattr(
        sankey_fetch,
        "productivity_snapshot_source_path",
        lambda day, key: tmp_path / day.isoformat() / f"{key}.csv.gz",
    )
    monkeypatch.setattr(
        sankey_fetch,
        "_fetch_segment_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("external API should not be called")),
    )

    rows, statuses, warnings = sis._fetch_view_rows(
        _FakeClient(fail_views=set()),
        key="receive",
        view_id="v_ask_receive_log",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 2),
        company_codes=["GG"],
        company_filter="GG",
        today=date(2026, 6, 30),
    )

    assert [row["rowid"] for row in rows] == ["snap-1", "snap-2"]
    assert warnings == []
    assert statuses == [
        {
            "key": "receive",
            "view": "v_ask_receive_log",
            "segment": "productivity_snapshot",
            "status": "productivity_snapshot",
            "rows": 2,
            "start": "2026-06-01",
            "end": "2026-06-02",
            "days": 2,
        }
    ]


def test_fetch_view_rows_uses_api_when_productivity_snapshot_range_is_incomplete(monkeypatch):
    client = _FakeClient(fail_views=set(), rows_by_view={"v_ask_receive_log": [{"rowid": "api"}]})
    monkeypatch.setattr(sankey_fetch, "PRODUCTIVITY_SNAPSHOT_REUSE_SOURCE_KEYS", {"receive"})
    monkeypatch.setattr(sankey_fetch, "productivity_snapshot_status", lambda day: {"ready": day != date(2026, 6, 2)})
    monkeypatch.setattr(sankey_fetch, "_date_filter_for_view", lambda *_args, **_kwargs: None)

    rows, statuses, warnings = sis._fetch_view_rows(
        client,
        key="receive",
        view_id="v_ask_receive_log",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 2),
        company_codes=["GG"],
        company_filter="GG",
        today=date(2026, 6, 30),
    )

    assert rows == [{"rowid": "api"}]
    assert client.calls == ["v_ask_receive_log"]
    assert statuses[0]["status"] == "api"
    assert warnings == []


def test_pick_source_does_not_reuse_productivity_snapshots(monkeypatch):
    client = _FakeClient(fail_views=set(), rows_by_view={"v_ask_pick_log_full": [{"rowid": "api"}]})
    monkeypatch.setattr(sankey_fetch, "PRODUCTIVITY_SNAPSHOT_REUSE_SOURCE_KEYS", {"receive", "trans"})
    monkeypatch.setattr(sankey_fetch, "productivity_snapshot_status", lambda _day: {"ready": True})
    monkeypatch.setattr(sankey_fetch, "_date_filter_for_view", lambda *_args, **_kwargs: None)

    rows, statuses, warnings = sis._fetch_view_rows(
        client,
        key="pick",
        view_id="v_ask_pick_log_full",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 1),
        company_codes=["GG"],
        company_filter="GG",
        today=date(2026, 6, 30),
    )

    assert rows == [{"rowid": "api"}]
    assert client.calls == ["v_ask_pick_log_full"]
    assert statuses[0]["status"] == "api"
    assert warnings == []


def test_live_failure_falls_back_to_dblog_archive(monkeypatch):
    monkeypatch.setattr(sankey_fetch, "_date_filter_for_view", lambda *a, **k: None)
    client = _FakeClient(fail_views={"v_ask_trans_log"}, rows_by_view={"dblog_trans_log": [{"x": 1}]})

    rows, statuses, warnings = sis._fetch_view_rows(
        client,
        key="trans",
        view_id="v_ask_trans_log",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 10),
        company_codes=["GG"],
        company_filter=None,
        today=date(2026, 6, 24),
    )

    assert rows == [{"x": 1}]
    assert "dblog_trans_log" in client.calls
    assert any(w["code"] == "archive_fallback_used" for w in warnings)
    assert any(s.get("segment") == "arkiv (fallback)" for s in statuses)


def test_dispatch_source_uses_dispatch_pallet_log_and_archive(monkeypatch):
    live_date_filter = sis._date_filter_for_view("dispatch_pallet_log", date(2026, 6, 1), date(2026, 6, 24))
    archive_date_filter = sis._date_filter_for_view("dblog_dispatch_pallet_log", date(2026, 6, 1), date(2026, 6, 24))
    assert live_date_filter["id"] == "created"
    assert archive_date_filter["id"] == "created"

    monkeypatch.setattr(sankey_fetch, "_date_filter_for_view", lambda *a, **k: None)
    client = _FakeClient(
        fail_views=set(),
        rows_by_view={
            "dblog_dispatch_pallet_log": [{"rowid": "old"}],
            "dispatch_pallet_log": [{"rowid": "new"}],
        },
    )

    rows, statuses, warnings = sis._fetch_view_rows(
        client,
        key="dispatch",
        view_id=sis.SANKEY_SOURCE_VIEWS["dispatch"],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 24),
        company_codes=["GG"],
        company_filter=None,
        today=date(2026, 6, 24),
    )

    assert sis.SANKEY_SOURCE_VIEWS["dispatch"] == "dispatch_pallet_log"
    assert sis.LIVE_ARCHIVE_PAIRS["dispatch_pallet_log"] == (14, "dblog_dispatch_pallet_log")
    assert rows == [{"rowid": "old"}, {"rowid": "new"}]
    assert client.calls == ["dblog_dispatch_pallet_log", "dispatch_pallet_log"]
    assert any(w["code"] == "archive_retention_used" and w["archive_view"] == "dblog_dispatch_pallet_log" for w in warnings)
    assert [status["view"] for status in statuses] == ["dblog_dispatch_pallet_log", "dispatch_pallet_log"]


def test_live_segment_uses_topped_up_local_archive_prefix(monkeypatch):
    client = _FakeClient(fail_views=set(), rows_by_view={"v_ask_trans_log": [{"rowid": "live-today"}]})

    monkeypatch.setattr(sis.local_archive_store, "is_enabled", lambda: True)
    monkeypatch.setattr(
        sis.local_archive_store,
        "ingested_range",
        lambda tenant, view: (date(2024, 4, 22), date(2026, 6, 30)),
    )
    # covered_range är seamen som _fetch_view_rows faktiskt använder; utan patch
    # läser den maskinens riktiga arkivstate och testet blir miljöberoende.
    monkeypatch.setattr(
        sis.local_archive_store,
        "covered_range",
        lambda tenant, view: (date(2024, 4, 22), date(2026, 6, 30)),
    )
    monkeypatch.setattr(
        sankey_fetch,
        "_query_local_archive_segment",
        lambda **kwargs: [{"rowid": f"cached-{kwargs['segment_start']}-{kwargs['segment_end']}"}],
    )

    rows, statuses, warnings = sis._fetch_view_rows(
        client,
        key="trans",
        view_id="v_ask_trans_log",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 7, 1),
        company_codes=["GG"],
        company_filter=None,
        today=date(2026, 7, 1),
        tenant="frey",
    )

    assert rows == [{"rowid": "cached-2026-06-01-2026-06-30"}, {"rowid": "live-today"}]
    assert client.calls == ["v_ask_trans_log"]
    assert statuses[0] == {
        "key": "trans",
        "view": "dblog_trans_log",
        "live_view": "v_ask_trans_log",
        "segment": "lokal_cache",
        "status": "local_archive",
        "rows": 1,
        "start": "2026-06-01",
        "end": "2026-06-30",
    }
    assert statuses[1]["view"] == "v_ask_trans_log"
    assert statuses[1]["status"] == "api"
    assert statuses[1]["start"] == "2026-07-01"
    assert statuses[1]["end"] == "2026-07-01"
    assert warnings == []


def test_dblog_segment_status_marks_local_archive_hit(monkeypatch):
    client = _FakeClient(fail_views=set(), rows_by_view={"dblog_pick_log": [{"rowid": "api"}]})
    monkeypatch.setattr(sis.local_archive_store, "is_enabled", lambda: True)
    monkeypatch.setattr(sis.local_archive_store, "query_rows", lambda *_args, **_kwargs: [{"rowid": "cached"}])

    rows, statuses, warnings = sis._fetch_view_rows(
        client,
        key="pick",
        view_id="v_ask_pick_log_full",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 2),
        company_codes=["GG"],
        company_filter=None,
        today=date(2026, 7, 1),
        tenant="frey",
    )

    assert rows == [{"rowid": "cached"}]
    assert client.calls == []
    assert statuses[0]["view"] == "dblog_pick_log"
    assert statuses[0]["status"] == "local_archive"
    assert warnings and warnings[0]["code"] == "archive_retention_used"


def test_item_alias_uses_local_snapshot_when_available(monkeypatch):
    client = _FakeClient(fail_views=set(), rows_by_view={"item_alias": [{"rowid": "api"}]})
    seen = {}

    def fake_query_snapshot(tenant, view_id, filters=None):
        seen["tenant"] = tenant
        seen["view_id"] = view_id
        seen["filters"] = filters
        return [{"rowid": "cached-alias", "company": "GG"}]

    monkeypatch.setattr(sis.local_archive_store, "is_enabled", lambda: True)
    monkeypatch.setattr(sis.local_archive_store, "query_snapshot_rows", fake_query_snapshot)

    rows, statuses, warnings = sis._fetch_view_rows(
        client,
        key="item_alias",
        view_id="item_alias",
        period_start=None,
        period_end=None,
        company_codes=["GG", "MG"],
        company_filter="GG",
        today=date(2026, 7, 1),
        tenant="frey",
    )

    assert rows == [{"rowid": "cached-alias", "company": "GG"}]
    assert client.calls == []
    assert statuses[0]["status"] == "local_snapshot"
    assert seen["tenant"] == "frey"
    assert seen["view_id"] == "item_alias"
    assert warnings == []


def test_buffer_snapshot_source_stays_live_api(monkeypatch):
    client = _FakeClient(
        fail_views=set(),
        rows_by_view={"v_ask_article_buffertpallet": [{"rowid": "live-buffer"}]},
    )

    monkeypatch.setattr(sis.local_archive_store, "is_enabled", lambda: True)
    monkeypatch.setattr(
        sis.local_archive_store,
        "query_snapshot_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("buffer must stay live")),
    )

    rows, statuses, warnings = sis._fetch_view_rows(
        client,
        key="buffer",
        view_id="v_ask_article_buffertpallet",
        period_start=None,
        period_end=None,
        company_codes=["GG"],
        company_filter=None,
        today=date(2026, 7, 1),
        tenant="frey",
    )

    assert rows == [{"rowid": "live-buffer"}]
    assert client.calls == ["v_ask_article_buffertpallet"]
    assert statuses[0]["status"] == "api"
    assert warnings == []


def test_required_source_failure_raises_detailed_message(monkeypatch):
    monkeypatch.setattr(sankey_fetch, "_date_filter_for_view", lambda *a, **k: None)
    client = _FakeClient(fail_views={"v_ask_trans_log", "dblog_trans_log"})

    with pytest.raises(sis.SankeyInboundError) as excinfo:
        sis._fetch_view_rows(
            client,
            key="trans",
            view_id="v_ask_trans_log",
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 10),
            company_codes=["GG"],
            company_filter="GG",
            today=date(2026, 6, 24),
        )

    message = str(excinfo.value)
    assert "Translogg" in message
    assert "v_ask_trans_log" in message
    assert "dblog_trans_log" in message
    assert "HTTP 403" in message
    assert "2026-06-01" in message
    # Detaljerna ska följa med i source_status för auditloggen.
    assert excinfo.value.source_status
    assert excinfo.value.source_status[-1].get("message")


def test_pick_archive_failure_degrades_instead_of_failing(monkeypatch):
    monkeypatch.setattr(sankey_fetch, "_date_filter_for_view", lambda *a, **k: None)
    client = _FakeClient(fail_views={"dblog_pick_log"})

    rows, statuses, warnings = sis._fetch_view_rows(
        client,
        key="pick",
        view_id="v_ask_pick_log_full",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 5, 14),
        company_codes=["GG"],
        company_filter=None,
        today=date(2026, 6, 24),
    )

    assert rows == []
    assert any(s.get("view") == "dblog_pick_log" and s.get("status") == "error" for s in statuses)
    assert any(w.get("code") == "degraded_source_segment_unavailable" and w.get("source") == "pick" for w in warnings)


def finance(price=10, purchase_line_price=0):
    return {
        "invoice_rows_by_company": {
            "GG": [
                {
                    "id": "inbound_labels",
                    "price": price,
                },
                {
                    "id": "inbound_article_rows",
                    "price": purchase_line_price,
                },
            ]
        }
    }


def finance_for_companies(*companies, price=10, purchase_line_price=0):
    return {
        "invoice_rows_by_company": {
            company: [
                {"id": "inbound_labels", "price": price},
                {"id": "inbound_article_rows", "price": purchase_line_price},
            ]
            for company in companies
        }
    }


def receive(
    rowid,
    pall,
    qty=10,
    type="11",
    timestamp="2026-06-01T08:00:00",
    company="GG",
    item="A1",
    book="PO1",
    line="1",
    **extra,
):
    return {
        "rowid": rowid,
        "type": type,
        "company": company,
        "wareh_num": "WH",
        "item_num": item,
        "pall_num": pall,
        "qty_suf": qty,
        "book_num": book,
        "line_num": line,
        "timestamp": timestamp,
        **extra,
    }


def trans(pall, type, loc_to, qty=10, timestamp="2026-06-01T09:00:00", company="GG", item="A1", **extra):
    return {
        "type": type,
        "company": company,
        "wareh_num": "WH",
        "item_num": item,
        "pall_num": pall,
        "loc_to": loc_to,
        "qty": qty,
        "timestamp": timestamp,
        **extra,
    }


def pick(location, qty, timestamp="2026-06-01T11:00:00", company="GG", item="A1"):
    return {
        "company": company,
        "wareh_num": "WH",
        "item_num": item,
        "location": location,
        "qty_suf": qty,
        "timestamp": timestamp,
    }


def outbound_pick(rowid, order, zone, qty, timestamp="2026-06-01T11:00:00", company="GG", item="A1"):
    return {
        "rowid": rowid,
        "company": company,
        "wareh_num": "WH",
        "item_num": item,
        "order_num": order,
        "pick_zone": zone,
        "qty_suf": qty,
        "timestamp": timestamp,
    }


def dispatch(rowid, parent="", timestamp="2026-06-01T12:00:00", company="GG", order="TO100", pick_pall="PP1"):
    return {
        "rowid": rowid,
        "company": company,
        "order_num": order,
        "pick_pall_num": pick_pall,
        "parent_pick_pall_num": parent,
        "timestamp": timestamp,
    }


def build(rows, *, only_consumed=False, price=10, purchase_line_price=0, points=None):
    return build_sankey_inbound_payload(
        source_rows={
            "receive": rows.get("receive", []),
            "trans": rows.get("trans", []),
            "pick": rows.get("pick", []),
            "dispatch": rows.get("dispatch", []),
            "buffer": rows.get("buffer", []),
            "kpi": rows.get("kpi", []),
        },
        finance_settings=finance(price, purchase_line_price),
        company_codes=["GG"],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 1),
        follow_until=date(2026, 6, 24),
        only_consumed=only_consumed,
        process_points=points or {
            "RECEIVING": 2.5,
            "HBW": 1.25,
            "DECANTING": 1.0,
            "PUTAWAY_PICK": 1.0,
            "BUFFER_UPDATE": 1.0,
        },
    )


def process_revenue(payload, process_key):
    for row in payload["processes"]:
        if row["process_key"] == process_key:
            return row["revenue"]
    return 0


def test_outbound_flow_counts_store_and_ecommerce_invoice_branches():
    finance_settings = {
        "invoice_rows_by_company": {
            "GG": [
                {"id": "inbound_labels", "price": 0},
                {"id": "inbound_article_rows", "price": 0},
                {"id": "store_picked_orders", "price": 10},
                {"id": "store_picked_rows", "price": 2},
                {"id": "store_picked_pcs", "price": 4},
                {"id": "store_full_pallets", "price": 5},
                {"id": "store_loaded_pallets", "price": 7},
                {"id": "ecom_picked_orders", "price": 11},
                {"id": "ecom_picked_rows", "price": 3},
                {"id": "ecom_picked_pcs", "price": 5},
                {"id": "ecom_pallet", "price": 6},
            ]
        }
    }
    payload = build_sankey_inbound_payload(
        source_rows={
            "receive": [],
            "trans": [],
            "pick": [
                outbound_pick("store-row-1", "TO100", "A", 12, item="A1"),
                outbound_pick("store-row-2", "TO100", "B", 2, item="B1"),
                outbound_pick("store-pallet", "TO200", "H", 1),
                outbound_pick("store-zero", "TO300", "A", 0),
                outbound_pick("ecom-row", "PR100", "A", 11, item="A1"),
                outbound_pick("ecom-pallet", "PR101", "H", 2),
                outbound_pick("ecom-zero", "PR102", "A", 0),
                outbound_pick("ignored", "SO100", "A", 1),
            ],
            "dispatch": [
                dispatch("loaded", parent="", pick_pall="PP1"),
                dispatch("parented", parent="PARENT", pick_pall="PP2"),
            ],
            "item_alias": [
                {"item_num": "A1", "company": "GG", "unit": "KRT", "conversion_factor": 10},
                {"item_num": "A1", "company": "GG", "unit": "ST", "conversion_factor": 1},
            ],
        },
        finance_settings=finance_settings,
        company_codes=["GG"],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 1),
        follow_until=date(2026, 6, 24),
        process_points={"RECEIVING": 2.5},
    )

    metrics = {row["metric_id"]: row for row in payload["outbound_metrics"] if row["company"] == "GG"}
    assert metrics["store_picked_orders"]["count"] == 2
    assert metrics["store_picked_rows"]["count"] == 2
    assert metrics["store_picked_pcs"]["count"] == 5
    assert metrics["store_full_pallets"]["count"] == 1
    assert metrics["store_loaded_pallets"]["count"] == 1
    assert metrics["ecom_picked_orders"]["count"] == 2
    assert metrics["ecom_picked_rows"]["count"] == 1
    assert metrics["ecom_picked_pcs"]["count"] == 2
    assert metrics["ecom_pallet"]["count"] == 1
    assert payload["summary"]["outbound_picked_pcs"] == 7
    assert payload["summary"]["outbound_store_income"] == 56
    assert payload["summary"]["outbound_ecom_income"] == 41
    assert payload["summary"]["outbound_income"] == 97
    assert payload["summary"]["gross_income"] == 97
    labels = {node["label"] for node in payload["nodes"]}
    assert {"Outbound", "Butik", "E-handel", "Utlastade pallar"}.issubset(labels)
    outbound_traces = [row for row in payload["trace_rows"] if row.get("trace_type") == "outbound"]
    assert len(outbound_traces) == 13
    assert any(row["status"] == "outbound:store_loaded_pallets" and row["current_pall"] == "PP1" for row in outbound_traces)
    assert any(row["status"] == "outbound:store_picked_pcs" and row["source_row_id"] == "store-row-1" and row["qty_remaining"] == 3 and row["revenue"] == 12 for row in outbound_traces)
    assert any(row["status"] == "outbound:ecom_picked_pcs" and row["source_row_id"] == "ecom-row" and row["qty_remaining"] == 2 and row["revenue"] == 10 for row in outbound_traces)


def test_receive_filter_excludes_types_zero_qty_and_type_100_zeroed_pallets():
    payload = build(
        {
            "receive": [
                receive("ok", "P1"),
                receive("excluded-type", "P2", type="23"),
                receive("zero", "P3", qty=0),
                receive("zeroed", "P4", timestamp="2026-06-01T08:00:00"),
                receive("type100", "P4", type="100", timestamp="2026-06-01T09:00:00"),
            ]
        }
    )

    assert payload["summary"]["labels_received"] == 1
    assert payload["summary"]["gross_income"] == 10
    assert any(warning["code"] == "type_100_zeroed_receipts" for warning in payload["warnings"])


def test_process_revenue_uses_points_share_for_receiving_and_hbw():
    payload = build(
        {
            "receive": [receive("ok", "P1")],
            "trans": [trans("P1", "111", "HBW01")],
        },
        price=10,
        points={"RECEIVING": 2.5, "HBW": 1.25},
    )

    assert process_revenue(payload, "RECEIVING") == 6.67
    assert process_revenue(payload, "HBW") == 3.33


def test_buffer_update_falls_back_to_pallet_when_pick_location_key_misses():
    payload = build(
        {
            "receive": [
                receive("ok", "P1"),
                receive("buffer-update", "P1", type="91", timestamp="2026-06-01T10:00:00", location="WRONG"),
            ],
            "trans": [trans("P1", "21", "A101", timestamp="2026-06-01T09:00:00")],
        },
        price=18,
        points={"RECEIVING": 2.0, "PUTAWAY_PICK": 1.0, "BUFFER_UPDATE": 1.0},
    )

    assert process_revenue(payload, "BUFFER_UPDATE") == 4.5
    assert any(row["process_key"] == "BUFFER_UPDATE" for row in payload["processes"])
    assert any(row["status"] == "open_buffer" and "Buffer Update" in row["path"] for row in payload["trace_rows"])


def test_purchase_line_revenue_is_deduplicated_and_distributed_with_process_points():
    payload = build(
        {
            "receive": [
                receive("p1", "P1", book="PO1", line="10"),
                receive("p2", "P2", book="PO1", line="10", timestamp="2026-06-01T08:05:00"),
            ],
            "trans": [trans("P1", "111", "HBW01")],
        },
        price=10,
        purchase_line_price=4,
        points={"RECEIVING": 2.5, "HBW": 1.25},
    )

    assert payload["summary"]["gross_income"] == 24
    assert payload["summary"]["gross_income_labels"] == 20
    assert payload["summary"]["gross_income_purchase_lines"] == 4
    assert payload["summary"]["purchase_lines_received"] == 1
    assert process_revenue(payload, "RECEIVING") == 20
    assert process_revenue(payload, "HBW") == 4


def test_purchase_line_revenue_uses_same_receive_filters_as_labels():
    payload = build(
        {
            "receive": [
                receive("ok", "P1", book="PO1", line="1"),
                receive("duplicate-line", "P2", book="PO1", line="1", timestamp="2026-06-01T08:05:00"),
                receive("excluded-type", "P3", type="23", book="PO2", line="1"),
                receive("zero", "P4", qty=0, book="PO3", line="1"),
                receive("zeroed", "P5", timestamp="2026-06-01T08:00:00", book="PO4", line="1"),
                receive("type100", "P5", type="100", timestamp="2026-06-01T09:00:00", book="PO4", line="1"),
            ]
        },
        price=10,
        purchase_line_price=5,
    )

    assert payload["summary"]["labels_received"] == 2
    assert payload["summary"]["purchase_lines_received"] == 1
    assert payload["summary"]["gross_income"] == 25
    assert payload["summary"]["gross_income_purchase_lines"] == 5


def test_process_points_are_loaded_from_productivity_kpi_target_rows():
    payload = build_sankey_inbound_payload(
        source_rows={
            "receive": [receive("ok", "P1")],
            "trans": [trans("P1", "111", "HBW01")],
            "kpi": [
                {"company": "GG", "action_id": "Receiving", "loaded_rows": "2.5"},
                {"company": "GG", "action_id": "HBW", "loaded_pallets": "1.25"},
            ],
        },
        finance_settings=finance(10),
        company_codes=["GG"],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 1),
        follow_until=date(2026, 6, 24),
    )

    assert process_revenue(payload, "RECEIVING") == 6.67
    assert process_revenue(payload, "HBW") == 3.33
    assert payload["summary"]["unallocated_revenue"] == 0
    assert not [warning for warning in payload["warnings"] if warning["code"] == "missing_process_points"]


def test_autostore_split_uses_equal_branch_revenue_and_keeps_remaining_original_branch():
    payload = build(
        {
            "receive": [receive("ok", "P1", qty=30)],
            "trans": [
                trans("P1", "26", "AS1000160101", qty=10, timestamp="2026-06-01T09:00:00"),
                trans("P1", "26", "AS1000160102", qty=10, timestamp="2026-06-01T09:01:00"),
            ],
        },
        price=9,
    )

    terminal_values = {node["key"]: node["value"] for node in payload["nodes"] if node["type"] == "terminal"}
    terminal_revenues = {node["key"]: node["revenue"] for node in payload["nodes"] if node["type"] == "terminal"}

    assert payload["summary"]["branches"] == 3
    assert terminal_values["terminal:open_autostore"] == 6
    assert terminal_values["terminal:open_not_putaway"] == 3
    assert terminal_revenues["terminal:open_autostore"] == 0
    assert terminal_revenues["terminal:open_not_putaway"] == 0
    assert any(warning["code"] == "equal_split_applied" for warning in payload["warnings"])


def test_terminal_labels_use_swedish_characters():
    payload = build(
        {
            "receive": [
                receive("pick", "P1"),
                receive("unknown", "P2", timestamp="2026-06-01T08:05:00"),
            ],
            "trans": [trans("P1", "21", "A101", timestamp="2026-06-01T09:00:00")],
        }
    )

    labels = {node["key"]: node["label"] for node in payload["nodes"] if node["type"] == "terminal"}

    assert labels["terminal:open_pick_location"] == "Kvar på plockplats"
    assert labels["terminal:open_not_putaway"] == "Ej inlagrad / okänd"


def test_trace_rows_include_pallet_ids_purchase_key_and_path_membership():
    payload = build(
        {
            "receive": [receive("pick", "P1", book="PO77", line="9")],
            "trans": [trans("P1", "21", "A101", timestamp="2026-06-01T09:00:00")],
        }
    )

    trace = payload["trace_rows"][0]

    assert trace["origin_pall"] == "P1"
    assert trace["current_pall"] == "P1"
    assert trace["purchase_number"] == "PO77"
    assert trace["purchase_line"] == "9"
    assert trace["received_date"] == "2026-06-01"
    assert trace["source_row_id"] == "pick"
    assert trace["status_label"] == "Kvar på plockplats"
    assert trace["step_1"] == "Mottagning P1"
    assert trace["step_2"] == "Receiving"
    assert trace["step_3"] == "Plockplats"
    assert trace["step_4"] == "Kvar på plockplats"
    assert trace["path"] == "Mottagning P1 -> Receiving -> Plockplats -> Kvar på plockplats"
    assert "GG:start" in trace["node_ids"]
    assert "GG:process:PUTAWAY_PICK" in trace["node_ids"]
    assert "GG:terminal:open_pick_location" in trace["node_ids"]
    assert "GG:process:RECEIVING->GG:process:PUTAWAY_PICK" in trace["link_keys"]


def test_trace_rows_show_current_location_status_from_buffer_snapshot():
    payload = build(
        {
            "receive": [receive("hbw", "P1", book="PO88", line="2")],
            "buffer": [{"company": "GG", "pall_num": "P1", "location": "HBW99"}],
        }
    )

    trace = payload["trace_rows"][0]

    assert trace["origin_pall"] == "P1"
    assert trace["current_location"] == "HBW99"
    assert trace["status"] == "open_hbw"
    assert trace["status_label"] == "Kvar i HBW"
    assert trace["path"] == "Mottagning P1 -> Receiving -> Kvar i HBW"
    assert "GG:terminal:open_hbw" in trace["node_ids"]
    assert "GG:process:RECEIVING->GG:terminal:open_hbw" in trace["link_keys"]


def test_only_consumed_filters_open_branches():
    rows = {
        "receive": [
            receive("consumed", "P1"),
            receive("open", "P2", timestamp="2026-06-01T08:05:00"),
        ],
        "trans": [
            trans("P1", "21", "A101", timestamp="2026-06-01T09:00:00"),
        ],
        "pick": [pick("A101", 10, timestamp="2026-06-01T10:00:00")],
    }

    all_payload = build(rows)
    consumed_payload = build(rows, only_consumed=True)

    assert all_payload["summary"]["gross_income"] == 20
    assert all_payload["summary"]["labels_open"] == 1
    assert all_payload["client_filters"]["only_consumed"]["summary"]["gross_income"] == 10
    assert all_payload["client_filters"]["only_consumed"]["summary"] == consumed_payload["summary"]
    assert all_payload["client_filters"]["only_consumed"]["nodes"] == consumed_payload["nodes"]
    assert all_payload["client_filters"]["only_consumed"]["links"] == consumed_payload["links"]
    assert consumed_payload["summary"]["gross_income"] == 10
    assert consumed_payload["client_filters"]["all"]["summary"] == all_payload["summary"]
    assert consumed_payload["summary"]["labels_open"] == 0
    assert consumed_payload["summary"]["labels_consumed"] == 1


def test_outbound_precompute_excludes_empty_and_out_of_window_timestamps():
    """Guardrail for outbound-forberakningen (#39, build_outbound.py pick_meta/
    dispatch_meta).

    Forr scannades varje pick/dispatch-rad PER vy och parsade bolag + tidsstampel
    per rad; nu forberaknas (row, bolag, datum-eller-None) EN gang per payload.
    None-fallan: en rad utan tolkbar tidsstampel far day=None och MASTE
    exkluderas FORE fonster-jamforelsen - 'view_period_start <= None' ar
    TypeError. Detta test har outbound-rader med giltig / tom / utanfor-fonstret
    tidsstampel och kraver att de tva sistnamnda ar osynliga, exakt som den gamla
    _is_in_date_window-scannen. Den befintliga golden (ovan) saknar outbound-
    rader och exercerade darfor aldrig denna vag.
    """
    valid_pick = outbound_pick("op1", "SO100", "PLOCK", 5, timestamp="2026-06-01T11:00:00")
    empty_pick = outbound_pick("op2", "SO101", "PLOCK", 7, timestamp="")
    outside_pick = outbound_pick("op3", "SO102", "PLOCK", 9, timestamp="2026-05-01T11:00:00")
    valid_disp = dispatch("od1", timestamp="2026-06-01T12:00:00")
    empty_disp = dispatch("od2", timestamp="")
    outside_disp = dispatch("od3", timestamp="2026-05-01T12:00:00")

    # Tom tidsstampel far inte krascha bygget (None-fallan), och edge-raderna
    # ska vara osynliga -> hela payloaden identisk med bara-giltiga-rader-bygget.
    full = build(
        {
            "pick": [valid_pick, empty_pick, outside_pick],
            "dispatch": [valid_disp, empty_disp, outside_disp],
        }
    )
    valid_only = build({"pick": [valid_pick], "dispatch": [valid_disp]})

    assert full["summary"] == valid_only["summary"]
    assert full["nodes"] == valid_only["nodes"]
    assert full["links"] == valid_only["links"]
    assert full["client_filters"]["views"] == valid_only["client_filters"]["views"]


def test_client_filter_views_include_company_and_day_variants():
    payload = build_sankey_inbound_payload(
        source_rows={
            "receive": [
                receive("gg-day1", "P1", company="GG", timestamp="2026-06-01T08:00:00"),
                receive("mg-day2", "P2", company="MG", timestamp="2026-06-02T08:00:00"),
            ],
            "kpi": [],
        },
        finance_settings=finance_for_companies("GG", "MG", price=10),
        company_codes=["GG", "MG"],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        follow_until=date(2026, 6, 24),
        period_type="month",
        period_label="Månad",
        process_points={"RECEIVING": 2.5},
    )

    views = payload["client_filters"]["views"]
    month_mg_key = sis._client_filter_view_key("month", date(2026, 6, 1), "MG", False)
    day_gg_key = sis._client_filter_view_key("day", date(2026, 6, 1), "GG", False)
    day_mg_key = sis._client_filter_view_key("day", date(2026, 6, 2), "MG", False)

    assert payload["summary"]["gross_income"] == 20
    assert views[month_mg_key]["summary"]["gross_income"] == 10
    assert views[month_mg_key]["filters"]["company"] == "MG"
    assert views[day_gg_key]["summary"]["labels_received"] == 1
    assert views[day_gg_key]["period"]["type"] == "day"
    assert views[day_gg_key]["trace_rows"][0]["received_date"] == "2026-06-01"
    assert set(views[day_gg_key]["trace_rows"][0]) == {"trace_type", "company", "received_date", "consumed", "node_ids", "link_keys"}
    assert views[day_mg_key]["companies"][0]["company"] == "MG"


def test_month_client_filter_views_are_prebuilt_even_when_source_rows_are_large(monkeypatch):
    monkeypatch.setattr(sankey_build, "CLIENT_FILTER_PREBUILD_MAX_SOURCE_ROWS", 0)
    payload = build_sankey_inbound_payload(
        source_rows={
            "receive": [receive("large", "P1", timestamp="2026-06-01T08:00:00")],
            "kpi": [],
        },
        finance_settings=finance_for_companies("GG", price=10),
        company_codes=["GG"],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        follow_until=date(2026, 6, 30),
        period_type="month",
        period_label="MÃ¥nad",
        process_points={"RECEIVING": 2.5},
    )

    client_filters = payload["client_filters"]
    assert payload["summary"]["gross_income"] == 10
    assert client_filters["prebuilt"] is True
    assert client_filters["views"]
    assert "only_consumed" in client_filters
    assert "omitted_reason" not in client_filters


def test_year_client_filter_views_keep_company_and_consumed_filters_when_source_rows_are_large(monkeypatch):
    monkeypatch.setattr(sankey_build, "CLIENT_FILTER_PREBUILD_MAX_SOURCE_ROWS", 0)
    payload = build_sankey_inbound_payload(
        source_rows={
            "receive": [
                receive("gg-june", "P1", company="GG", timestamp="2026-06-15T08:00:00"),
                receive("mg-july", "P2", company="MG", timestamp="2026-07-02T08:00:00"),
            ],
            "trans": [trans("P1", "21", "A101", company="GG", timestamp="2026-06-15T09:00:00")],
            "pick": [pick("A101", 10, company="GG", timestamp="2026-06-15T10:00:00")],
            "kpi": [],
        },
        finance_settings=finance_for_companies("GG", "MG", price=10),
        company_codes=["GG", "MG"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        follow_until=date(2026, 12, 31),
        period_type="year",
        period_label="Ar",
        process_points={"RECEIVING": 2.5, "PUTAWAY_PICK": 1.0},
    )

    client_filters = payload["client_filters"]
    views = client_filters["views"]
    year_gg_key = sis._client_filter_view_key("year", date(2026, 1, 1), "GG", False)
    consumed_gg_key = sis._client_filter_view_key("year", date(2026, 1, 1), "GG", True)
    july_mg_key = sis._client_filter_view_key("month", date(2026, 7, 1), "MG", False)

    assert client_filters["prebuilt"] is True
    assert client_filters["estimated_views"] <= sankey_build.CLIENT_FILTER_PREBUILD_MAX_VIEWS
    assert "omitted_reason" not in client_filters
    assert views[year_gg_key]["filters"]["company"] == "GG"
    assert views[year_gg_key]["summary"]["labels_received"] == 1
    assert views[consumed_gg_key]["filters"]["only_consumed"] is True
    assert views[consumed_gg_key]["summary"]["labels_consumed"] == 1
    assert views[july_mg_key]["period"]["type"] == "month"
    assert views[july_mg_key]["summary"]["labels_received"] == 1


def test_client_filter_views_are_not_prebuilt_when_view_count_is_too_large(monkeypatch):
    monkeypatch.setattr(sankey_build, "CLIENT_FILTER_PREBUILD_MAX_VIEWS", 0)
    payload = build_sankey_inbound_payload(
        source_rows={
            "receive": [receive("large", "P1", timestamp="2026-06-01T08:00:00")],
            "kpi": [],
        },
        finance_settings=finance_for_companies("GG", price=10),
        company_codes=["GG"],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        follow_until=date(2026, 6, 30),
        period_type="month",
        period_label="MÃƒÂ¥nad",
        process_points={"RECEIVING": 2.5},
    )

    client_filters = payload["client_filters"]
    assert payload["summary"]["gross_income"] == 10
    assert client_filters["prebuilt"] is False
    assert client_filters["views"] == {}
    assert client_filters["omitted_reason"] == "too_many_views"
    assert "only_consumed" not in client_filters


def test_client_filter_views_include_month_variants_for_year_payload():
    payload = build_sankey_inbound_payload(
        source_rows={
            "receive": [
                receive("june", "P1", timestamp="2026-06-15T08:00:00"),
                receive("july", "P2", timestamp="2026-07-02T08:00:00"),
            ],
            "kpi": [],
        },
        finance_settings=finance_for_companies("GG", price=10),
        company_codes=["GG"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        follow_until=date(2026, 12, 31),
        period_type="year",
        period_label="År",
        process_points={"RECEIVING": 2.5},
    )

    views = payload["client_filters"]["views"]
    june_key = sis._client_filter_view_key("month", date(2026, 6, 1), "ALL", False)
    july_key = sis._client_filter_view_key("month", date(2026, 7, 1), "ALL", False)

    assert views[june_key]["summary"]["labels_received"] == 1
    assert views[june_key]["trace_rows"][0]["received_date"] == "2026-06-15"
    assert views[july_key]["summary"]["labels_received"] == 1
    assert views[july_key]["period"]["type"] == "month"


def test_pick_location_fifo_consumes_prior_unknown_balance_before_owned_branch():
    payload = build(
        {
            "receive": [receive("ok", "P1", qty=10)],
            "trans": [trans("P1", "21", "A101", qty=10, qty_pre=14)],
            "pick": [pick("A101", 20)],
        }
    )

    assert payload["summary"]["labels_consumed"] == 0
    assert payload["summary"]["labels_open"] == 1
    assert any(node["key"] == "terminal:open_pick_location" for node in payload["nodes"])


def test_kpi_coredata_fallback_reads_targets_when_live_view_unavailable(tmp_path, monkeypatch):
    kpi_file = tmp_path / "kpi.tsv"
    kpi_file.write_text(
        "Bolag\tProcessnamn\tRader\tPallar\n"
        "GG\tReceiving\t40\t0\n"
        "GG\tHBW\t0\t80\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sankey_fetch, "find_kpi_file", lambda *args, **kwargs: kpi_file)

    rows, status, warnings = _load_kpi_fallback_rows(business_code="GG", db=None)

    assert len(rows) == 2
    assert status[0]["status"] == "coredata_primary"
    assert warnings[0]["code"] == "kpi_coredata_fallback"

    points = _process_points_from_kpi(rows)
    assert points[("GG", "RECEIVING")] == 2.5
    assert points[("GG", "HBW")] == 1.25


def test_sankey_kpi_fetch_uses_coredata_without_external_api(monkeypatch):
    progress = []

    def fail_external_fetch(*args, **kwargs):
        raise AssertionError("KPI ska inte hämtas via extern API-vy")

    monkeypatch.setattr(sankey_fetch, "SANKEY_SOURCE_VIEWS", {"kpi": "v_ask_kpi_target"})
    monkeypatch.setattr(sankey_fetch, "CURRENT_STATE_SOURCE_KEYS", {"kpi"})
    monkeypatch.setattr(sankey_fetch, "_fetch_view_rows", fail_external_fetch)
    monkeypatch.setattr(
        sankey_fetch,
        "_load_kpi_fallback_rows",
        lambda **_kwargs: (
            [{"company": "GG", "action_id": "Receiving", "loaded_rows": "2.5"}],
            [{"key": "kpi", "view": "v_ask_kpi_target", "status": "coredata_primary", "rows": 1}],
            [{"code": "kpi_coredata_fallback", "source": "kpi", "message": "fallback"}],
        ),
    )

    rows, status, warnings = sis.fetch_sankey_inbound_sources(
        period_start=date(2026, 6, 1),
        follow_until=date(2026, 6, 24),
        company_codes=["GG"],
        progress_callback=progress.append,
    )

    assert rows["kpi"][0]["action_id"] == "Receiving"
    assert status[0]["status"] == "coredata_primary"
    assert warnings[0]["code"] == "kpi_coredata_fallback"
    assert progress[-1]["key"] == "kpi"
    assert progress[-1]["done"] is True


def test_only_consumed_toggle_reuses_cached_sources(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(**kwargs):
        calls["n"] += 1
        return ({"receive": [], "trans": [], "pick": [], "buffer": [], "kpi": []}, [], [])

    monkeypatch.setattr(sankey_fetch, "fetch_sankey_inbound_sources", fake_fetch)
    sis._SOURCE_CACHE.clear()

    common = dict(
        finance_settings=finance(10),
        company_codes=["GG"],
        period="day",
        selected_date=date(2026, 6, 1),
        business_id=1,
        company_filter=None,
        tenant=None,
    )
    first = sis.load_sankey_inbound_payload(only_consumed=False, **common)
    second = sis.load_sankey_inbound_payload(only_consumed=True, **common)

    assert calls["n"] == 1  # andra anropet återanvänder cachade källrader
    assert first["filters"]["only_consumed"] is False
    assert second["filters"]["only_consumed"] is True


def test_load_payload_moves_trace_rows_to_token(monkeypatch):
    trace_rows = [
        {
            "company": "GG",
            "received_date": "2026-06-01",
            "origin_pall": "P1",
            "node_ids": ["GG:start", "GG:process:RECEIVING"],
            "link_keys": ["GG:start->GG:process:RECEIVING"],
            "consumed": True,
        },
        {
            "company": "MG",
            "received_date": "2026-06-02",
            "origin_pall": "P2",
            "node_ids": ["MG:start"],
            "link_keys": [],
            "consumed": False,
        },
    ]
    variant_rows = [trace_rows[0]]

    monkeypatch.setattr(
        sankey_fetch,
        "fetch_sankey_inbound_sources",
        lambda **_kwargs: ({"receive": [], "trans": [], "pick": [], "buffer": [], "kpi": []}, [], []),
    )
    monkeypatch.setattr(
        sankey_build,
        "build_sankey_inbound_payload",
        lambda **_kwargs: {
            "period": {},
            "filters": {"company": "ALL", "only_consumed": False},
            "summary": {},
            "source_status": [],
            "warnings": [],
            "trace_rows": list(trace_rows),
            "client_filters": {
                "schema": "views_v1",
                "prebuilt": True,
                "views": {
                    "day|2026-06-01|GG|1": {
                        "period": {"type": "day", "start_date": "2026-06-01", "end_date": "2026-06-01"},
                        "filters": {"company": "GG", "only_consumed": True},
                        "trace_rows": list(variant_rows),
                    }
                },
                "only_consumed": {
                    "period": {"type": "day", "start_date": "2026-06-01", "end_date": "2026-06-01"},
                    "filters": {"company": "ALL", "only_consumed": True},
                    "trace_rows": list(variant_rows),
                },
            },
        },
    )
    sis._CACHE.clear()
    sis._SOURCE_CACHE.clear()
    sis._TRACE_CACHE.clear()

    payload = sis.load_sankey_inbound_payload(
        finance_settings=finance(10),
        company_codes=["GG"],
        period="day",
        selected_date=date(2026, 6, 1),
        business_id=1,
        company_filter=None,
        tenant=None,
    )

    assert "trace_rows" not in payload
    assert payload["trace_total"] == 2
    assert payload["trace_counts"]["nodes"]["GG:start"] == 1
    assert payload["trace_counts"]["nodes"]["MG:start"] == 1
    assert payload["trace_counts"]["nodes"]["GG:process:RECEIVING"] == 1
    assert payload["trace_counts"]["links"]["GG:start->GG:process:RECEIVING"] == 1
    assert payload["trace_filter"]["company"] == "ALL"
    assert sis.get_trace_rows(payload["trace_token"]) == trace_rows
    view = payload["client_filters"]["views"]["day|2026-06-01|GG|1"]
    assert "trace_rows" not in view
    assert view["trace_token"] == payload["trace_token"]
    assert view["trace_total"] == 1
    assert view["trace_filter"] == {
        "company": "GG",
        "start_date": "2026-06-01",
        "end_date": "2026-06-01",
        "only_consumed": True,
    }
    assert "trace_rows" not in payload["client_filters"]["only_consumed"]


def test_load_payload_trace_token_uses_all_variant_rows_for_consumed_initial_view(monkeypatch):
    all_rows = [
        {"origin_pall": "P1", "company": "GG", "received_date": "2026-06-01", "consumed": True, "node_ids": ["N1"], "link_keys": []},
        {"origin_pall": "P2", "company": "GG", "received_date": "2026-06-01", "consumed": False, "node_ids": ["N2"], "link_keys": []},
    ]

    monkeypatch.setattr(
        sankey_fetch,
        "fetch_sankey_inbound_sources",
        lambda **_kwargs: ({"receive": [], "trans": [], "pick": [], "buffer": [], "kpi": []}, [], []),
    )
    monkeypatch.setattr(
        sankey_build,
        "build_sankey_inbound_payload",
        lambda **_kwargs: {
            "period": {"type": "day", "start_date": "2026-06-01", "end_date": "2026-06-01"},
            "filters": {"company": "GG", "only_consumed": True},
            "summary": {},
            "source_status": [],
            "warnings": [],
            "trace_rows": [all_rows[0]],
            "client_filters": {
                "schema": "views_v1",
                "prebuilt": True,
                "views": {},
                "all": {
                    "period": {"type": "day", "start_date": "2026-06-01", "end_date": "2026-06-01"},
                    "filters": {"company": "GG", "only_consumed": False},
                    "trace_rows": list(all_rows),
                },
            },
        },
    )
    sis._CACHE.clear()
    sis._SOURCE_CACHE.clear()
    sis._TRACE_CACHE.clear()

    payload = sis.load_sankey_inbound_payload(
        finance_settings=finance(10),
        company_codes=["GG"],
        period="day",
        selected_date=date(2026, 6, 1),
        business_id=1,
        company_filter="GG",
        tenant=None,
        only_consumed=True,
    )

    assert payload["trace_total"] == 1
    assert sis.get_trace_rows(payload["trace_token"]) == all_rows
    assert "trace_rows" not in payload["client_filters"]["all"]
    assert payload["client_filters"]["all"]["trace_total"] == 2


def test_kpi_coredata_fallback_returns_empty_when_file_missing(monkeypatch):
    from app.backend.productivity_service import ProductivitySourceError

    def _raise(*args, **kwargs):
        raise ProductivitySourceError("saknar fil")

    monkeypatch.setattr(sankey_fetch, "find_kpi_file", _raise)

    rows, status, warnings = _load_kpi_fallback_rows(business_code="GG", db=None)

    assert rows == []
    assert status == []
    assert warnings == []


def test_missing_inbound_label_price_warns_and_returns_zero_revenue():
    payload = build_sankey_inbound_payload(
        source_rows={"receive": [receive("ok", "P1")]},
        finance_settings={"invoice_rows_by_company": {"GG": []}},
        company_codes=["GG"],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 1),
        follow_until=date(2026, 6, 24),
        process_points={"RECEIVING": 2.5},
    )

    assert payload["summary"]["gross_income"] == 0
    assert payload["summary"]["labels_received"] == 1
    assert any(warning["code"] == "missing_inbound_label_price" for warning in payload["warnings"])
