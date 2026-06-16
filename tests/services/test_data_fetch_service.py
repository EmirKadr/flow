import asyncio
from datetime import date, datetime, timezone
import json
from types import SimpleNamespace

from fastapi import HTTPException
from openpyxl import load_workbook
import pytest
import requests

from app.backend import data_fetch_service as service
from app.backend.config import settings
from app.backend.external_data_client import (
    ExternalDataClient,
    ExternalDataClientError,
    data_source_base_url_for_tenant,
    fetch_all_rows,
)
from app.backend.models import AuditLog, Business
from app.backend.routers import data_fetch


@pytest.fixture(autouse=True)
def clear_data_fetch_sessions():
    for session in data_fetch.DATA_FETCH_SESSIONS.values():
        data_fetch._remove_data_fetch_session(session)
    data_fetch.DATA_FETCH_SESSIONS.clear()
    yield
    for session in data_fetch.DATA_FETCH_SESSIONS.values():
        data_fetch._remove_data_fetch_session(session)
    data_fetch.DATA_FETCH_SESSIONS.clear()


SAMPLE_CATALOG = {
    "version": 1,
    "views": [
        {
            "id": "dblog_count_log",
            "label_en": "Activity Log",
            "label_sv": "Aktivitetslogg",
            "columns": [
                {"id": "type", "order": 1, "label_en": "Type", "label_sv": "Typ"},
                {"id": "item_num", "order": 2, "label_en": "Item Num", "label_sv": "Artikel"},
                {"id": "created_at", "order": 3, "label_en": "Created At", "label_sv": "Skapad"},
            ],
        }
    ],
}
PICK_LOG_CATALOG = {
    "version": 1,
    "views": [
        {
            "id": "v_ask_pick_log_full",
            "label_en": "Pick Log Full",
            "label_sv": "Plocklogg Full",
            "columns": [
                {"id": "order_num", "order": 1, "label_en": "Order Num", "label_sv": "Ordernr"},
                {"id": "time_stamp_int", "order": 2, "label_en": "Time Stamp Int", "label_sv": "Datum"},
                {"id": "item_num", "order": 3, "label_en": "Item Num", "label_sv": "Artikel"},
                {"id": "company", "order": 4, "label_en": "Company", "label_sv": "Bolag"},
                {"id": "pick_zone", "order": 5, "label_en": "Pick Zone", "label_sv": "Zon"},
                {"id": "qty_suf", "order": 6, "label_en": "Qty Suf", "label_sv": "Plockat"},
            ],
        }
    ],
}
TRANS_LOG_CATALOG = {
    "version": 1,
    "views": [
        {
            "id": "v_ask_trans_log",
            "label_en": "Trans Log",
            "label_sv": "Translogg",
            "columns": [
                {"id": "type", "order": 1, "label_en": "Type", "label_sv": "Typ"},
                {"id": "timestamp", "order": 2, "label_en": "Timestamp", "label_sv": "Timestamp"},
                {"id": "company", "order": 3, "label_en": "Company", "label_sv": "Bolag"},
            ],
        }
    ],
}
RECEIVE_LOG_CATALOG = {
    "version": 1,
    "views": [
        {
            "id": "v_ask_receive_log",
            "label_en": "Receive log",
            "label_sv": "Varumottagningslogg",
            "columns": [
                {"id": "type", "order": 1, "label_en": "Type", "label_sv": "Typ"},
                {"id": "book_num", "order": 2, "label_en": "Book Num", "label_sv": "Inköpsnr"},
                {"id": "item_num", "order": 3, "label_en": "Item Num", "label_sv": "Artikel"},
                {"id": "qty_suf", "order": 4, "label_en": "Qty Suf", "label_sv": "Mottaget"},
                {"id": "timestamp", "order": 5, "label_en": "Timestamp", "label_sv": "Ändrad"},
                {"id": "company", "order": 6, "label_en": "Company", "label_sv": "Bolag"},
            ],
        }
    ],
}


def fake_user():
    return SimpleNamespace(id=1, username="emikad", display_name="Emir")


class FakeAuditDb:
    def __init__(self):
        self.items = []
        self.committed = False
        self.rolled_back = False

    def add(self, item):
        self.items.append(item)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_minimax_payload_never_contains_external_connection_details(monkeypatch):
    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://secret.example/api/")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY", "very-secret-key")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT", "secret-client")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY_HEADER", "secret-key-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT_HEADER", "secret-client-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "secret/path/{view}/data")
    catalog = service.catalog_from_payload(SAMPLE_CATALOG)

    context = service.build_catalog_context("Aktivitetslogg typ korrigering", catalog)
    payload = service.build_data_fetch_minimax_payload("Hämta aktivitetslogg", context)
    text = json.dumps(payload, ensure_ascii=False)

    assert "dblog_count_log" in text
    assert "Aktivitetslogg" in text
    assert "https://secret.example" not in text
    assert "very-secret-key" not in text
    assert "secret-client" not in text
    assert "secret-key-header" not in text
    assert "secret/path" not in text
    assert "count_distinct" in text
    assert "Använd aldrig identifiers för dubletter" in text


def test_validate_plan_normalizes_columns_and_filters():
    catalog = service.catalog_from_payload(SAMPLE_CATALOG)
    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "dblog_count_log",
            "output_columns": ["type", "item_num"],
            "filters": [{"field": "type", "operator": "eq", "value": "korrigering"}],
        },
        catalog,
    )

    assert plan["view_label"] == "Aktivitetslogg"
    assert plan["output_column_labels"]["type"] == "Typ"
    assert plan["filters"] == [{"id": "type", "operator": "EQ", "value": "korrigering"}]


def test_validate_plan_supports_calculation_and_expands_exclusions():
    catalog = service.catalog_from_payload(RECEIVE_LOG_CATALOG)

    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_receive_log",
            "output_columns": ["book_num", "item_num"],
            "filters": [{"field": "type", "operator": "NE", "value": [45, 91, 100]}],
            "calculation": {
                "metric": "count_distinct",
                "distinct_by": ["book_num", "item_num"],
            },
        },
        catalog,
    )

    assert plan["filters"] == [
        {"id": "type", "operator": "NE", "value": 45},
        {"id": "type", "operator": "NE", "value": 91},
        {"id": "type", "operator": "NE", "value": 100},
    ]
    assert service.external_filters_for_api(plan["filters"]) == []
    assert service.apply_local_filters(
        [
            {"type": 10, "book_num": "PO1", "item_num": "A1"},
            {"type": 45, "book_num": "PO2", "item_num": "A2"},
            {"type": "91", "book_num": "PO3", "item_num": "A3"},
            {"type": 100, "book_num": "PO4", "item_num": "A4"},
        ],
        plan["filters"],
    ) == [{"type": 10, "book_num": "PO1", "item_num": "A1"}]
    assert plan["calculation"] == {
        "metric": "count_distinct",
        "field": None,
        "distinct_by": ["book_num", "item_num"],
        "group_by": [],
        "sort_by": None,
        "limit": None,
    }


def test_identifier_column_list_becomes_count_distinct_calculation():
    catalog = service.catalog_from_payload(RECEIVE_LOG_CATALOG)

    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_receive_log",
            "output_columns": ["book_num", "item_num"],
            "identifiers": ["book_num", "item_num"],
        },
        catalog,
    )

    assert plan["identifiers"] == []
    assert plan["calculation"]["metric"] == "count_distinct"
    assert plan["calculation"]["distinct_by"] == ["book_num", "item_num"]


def test_execute_calculation_counts_distinct_purchase_item_pairs():
    catalog = service.catalog_from_payload(RECEIVE_LOG_CATALOG)
    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_receive_log",
            "output_columns": ["book_num", "item_num"],
            "calculation": {
                "metric": "count_distinct",
                "distinct_by": ["book_num", "item_num"],
            },
        },
        catalog,
    )
    rows = [
        {"book_num": "PO1", "item_num": "A1"},
        {"book_num": "PO1", "item_num": "A1"},
        {"book_num": "PO1", "item_num": "A2"},
        {"book_num": "PO2", "item_num": "A1"},
    ]

    result = service.execute_calculation(rows, plan)

    assert result["value"] == 3
    assert result["label"] == "Antal unika Inköpsnr + Artikel"
    assert service.calculation_query_text(plan) == (
        "SELECT COUNT(DISTINCT (book_num, item_num)) AS value FROM v_ask_receive_log;"
    )


def test_execute_calculation_groups_sorts_and_limits():
    catalog = service.catalog_from_payload(RECEIVE_LOG_CATALOG)
    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_receive_log",
            "output_columns": ["item_num", "qty_suf"],
            "calculation": {
                "metric": "sum",
                "field": "qty_suf",
                "group_by": ["item_num"],
                "sort_by": {"field": "value", "direction": "desc"},
                "limit": 2,
            },
        },
        catalog,
    )
    rows = [
        {"item_num": "A1", "qty_suf": "2,5"},
        {"item_num": "A1", "qty_suf": 3},
        {"item_num": "A2", "qty_suf": 10},
        {"item_num": "A3", "qty_suf": 1},
    ]

    result = service.execute_calculation(rows, plan)

    assert result["value"] == 16.5
    assert result["rows"] == [
        {"item_num": "A2", "value": 10},
        {"item_num": "A1", "value": 5.5},
    ]
    assert service.calculation_query_text(plan) == (
        "SELECT item_num, SUM(qty_suf) AS value FROM v_ask_receive_log "
        "GROUP BY item_num ORDER BY value DESC LIMIT 2;"
    )


def test_prefix_filter_counts_unique_order_numbers():
    catalog = service.catalog_from_payload(PICK_LOG_CATALOG)
    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_pick_log_full",
            "output_columns": ["order_num"],
            "filters": [{"field": "order_num", "operator": "StartsWith", "value": "TO"}],
            "calculation": {
                "metric": "count_distinct",
                "distinct_by": ["order_num"],
            },
        },
        catalog,
    )
    rows = [
        {"order_num": "TO100"},
        {"order_num": "TO100"},
        {"order_num": "TP100"},
        {"order_num": "to200"},
    ]

    filtered_rows = service.apply_local_filters(rows, plan["filters"])
    result = service.execute_calculation(filtered_rows, plan)

    assert service.external_filters_for_api(plan["filters"]) == []
    assert [row["order_num"] for row in filtered_rows] == ["TO100", "TO100", "to200"]
    assert result["value"] == 2
    assert service.calculation_query_text(plan) == (
        "SELECT COUNT(DISTINCT order_num) AS value FROM v_ask_pick_log_full "
        "WHERE order_num LIKE 'TO%';"
    )


def test_like_filter_accepts_sql_wildcard_pattern():
    catalog = service.catalog_from_payload(PICK_LOG_CATALOG)
    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_pick_log_full",
            "output_columns": ["order_num"],
            "filters": [{"field": "order_num", "operator": "Like", "value": "TO_"}],
        },
        catalog,
    )
    rows = [
        {"order_num": "TO1"},
        {"order_num": "TO12"},
        {"order_num": "TP1"},
    ]

    assert service.apply_local_filters(rows, plan["filters"]) == [{"order_num": "TO1"}]


def test_range_and_exclusion_filters_are_applied_locally_after_stable_api_filters():
    catalog = service.catalog_from_payload(PICK_LOG_CATALOG)
    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_pick_log_full",
            "output_columns": ["order_num", "pick_zone", "qty_suf"],
            "filters": [
                {"field": "pick_zone", "operator": "NE", "value": "H"},
                {"field": "qty_suf", "operator": "GTE", "value": 1},
                {"field": "time_stamp_int", "operator": "Between", "value": [20260501, 20260531]},
                {"field": "company", "operator": "EQ", "value": "GG"},
            ],
            "calculation": {"metric": "count"},
        },
        catalog,
    )
    rows = [
        {"order_num": "O1", "pick_zone": "A", "qty_suf": 1, "time_stamp_int": 20260501, "company": "GG"},
        {"order_num": "O2", "pick_zone": "H", "qty_suf": 2, "time_stamp_int": 20260502, "company": "GG"},
        {"order_num": "O3", "pick_zone": "A", "qty_suf": 0, "time_stamp_int": 20260503, "company": "GG"},
        {"order_num": "O4", "pick_zone": "A", "qty_suf": "1,5", "time_stamp_int": 20260504, "company": "GG"},
        {"order_num": "O5", "pick_zone": "A", "qty_suf": 2, "time_stamp_int": 20260601, "company": "GG"},
        {"order_num": "O6", "pick_zone": "A", "qty_suf": 2, "time_stamp_int": 20260505, "company": "MG"},
    ]

    assert service.external_filters_for_api(plan["filters"]) == [
        {"id": "time_stamp_int", "operator": "Between", "value": [20260501, 20260531]},
        {"id": "company", "operator": "EQ", "value": "GG"},
    ]
    filtered_rows = service.apply_local_filters(rows, plan["filters"])

    assert [row["order_num"] for row in filtered_rows] == ["O1", "O4"]
    assert service.execute_calculation(filtered_rows, plan)["value"] == 2
    assert service.calculation_query_text(plan) == (
        "SELECT COUNT(*) AS value FROM v_ask_pick_log_full "
        "WHERE pick_zone <> 'H' AND qty_suf >= 1 "
        "AND time_stamp_int BETWEEN 20260501 AND 20260531 AND company = 'GG';"
    )


def test_blank_max_rows_means_all_rows(monkeypatch):
    monkeypatch.setattr(settings, "DATA_SOURCE_MAX_ROWS", 1)
    rows = [
        {"type": "korrigering", "item_num": "A1"},
        {"type": "korrigering", "item_num": "A2"},
        {"type": "korrigering", "item_num": "A3"},
    ]

    request = data_fetch.DataFetchRunRequest(plan={"status": "ok"})

    assert request.max_rows is None
    assert data_fetch._max_rows(None) is None
    assert data_fetch._max_rows(5) == 1
    assert service.project_rows(rows, ["type"], None) == [
        {"type": "korrigering"},
        {"type": "korrigering"},
        {"type": "korrigering"},
    ]
    assert service.project_rows(rows, ["type"], 2) == [
        {"type": "korrigering"},
        {"type": "korrigering"},
    ]


def test_catalog_context_includes_month_period_hint_for_date_columns():
    catalog = service.catalog_from_payload(PICK_LOG_CATALOG)

    context = service.build_catalog_context("hamta plocklogg full for apil 2026", catalog)

    assert context["detected_period"]["start_yyyymmdd"] == 20260401
    assert context["detected_period"]["end_yyyymmdd"] == 20260430
    assert context["detected_period"]["preferred_date_columns"] == {
        "v_ask_pick_log_full": "time_stamp_int"
    }


def test_catalog_context_sends_current_app_clock(monkeypatch):
    monkeypatch.setattr(
        service,
        "_app_now",
        lambda: datetime(2026, 5, 22, 9, 30, tzinfo=timezone.utc),
    )
    catalog = service.catalog_from_payload(TRANS_LOG_CATALOG)

    context = service.build_catalog_context("hamta translogg med dagens timestamp", catalog)

    assert context["current_date"] == "2026-05-22"
    assert context["current_datetime"].startswith("2026-05-22T09:30:00")
    assert context["detected_period"]["preferred_date_columns"] == {"v_ask_trans_log": "timestamp"}


def test_prompt_period_hint_replaces_misread_order_filter():
    catalog = service.catalog_from_payload(PICK_LOG_CATALOG)
    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_pick_log_full",
            "output_columns": ["order_num", "time_stamp_int"],
            "filters": [{"field": "order_num", "operator": "EQ", "value": "apil 2026"}],
        },
        catalog,
    )

    repaired = service.apply_prompt_period_hint(
        plan,
        "hamta plocklogg full for apil 2026",
        catalog,
    )

    assert repaired["filters"] == [
        {"id": "time_stamp_int", "operator": "Between", "value": [20260401, 20260430]}
    ]


def test_prompt_period_hint_uses_app_clock_for_today_and_normalizes_company(monkeypatch):
    monkeypatch.setattr(
        service,
        "_app_now",
        lambda: datetime(2026, 5, 22, 9, 30, tzinfo=timezone.utc),
    )
    catalog = service.catalog_from_payload(TRANS_LOG_CATALOG)
    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_trans_log",
            "output_columns": ["type", "timestamp", "company"],
            "filters": [
                {"field": "company", "operator": "EQ", "value": "gg"},
                {
                    "field": "timestamp",
                    "operator": "Between",
                    "value": ["2026-04-09T00:00:00", "2026-04-09T23:59:59"],
                },
            ],
        },
        catalog,
    )

    repaired = service.apply_prompt_period_hint(
        plan,
        "hamta translogg for bolag gg med dagens timestamp",
        catalog,
    )

    assert repaired["filters"] == [
        {"id": "company", "operator": "EQ", "value": "GG"},
        {
            "id": "timestamp",
            "operator": "Between",
            "value": ["2026-05-22T00:00:00", "2026-05-22T23:59:59"],
        },
    ]


def test_relative_days_period_uses_app_clock(monkeypatch):
    monkeypatch.setattr(
        service,
        "_app_now",
        lambda: datetime(2026, 5, 22, 9, 30, tzinfo=timezone.utc),
    )
    catalog = service.catalog_from_payload(PICK_LOG_CATALOG)
    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_pick_log_full",
            "output_columns": ["order_num", "time_stamp_int", "company"],
            "filters": [{"field": "company", "operator": "EQ", "value": "gg"}],
        },
        catalog,
    )

    repaired = service.apply_prompt_period_hint(
        plan,
        "hamta plocklogg full for bolag gg senaste 5 dagarna",
        catalog,
    )

    assert repaired["filters"] == [
        {"id": "company", "operator": "EQ", "value": "GG"},
        {"id": "time_stamp_int", "operator": "Between", "value": [20260518, 20260522]},
    ]


def test_validate_plan_rejects_unknown_column():
    catalog = service.catalog_from_payload(SAMPLE_CATALOG)

    with pytest.raises(service.DataFetchPlanError):
        service.validate_plan_payload(
            {
                "status": "ok",
                "view": "dblog_count_log",
                "output_columns": ["does_not_exist"],
            },
            catalog,
        )


def test_run_data_fetch_uses_validated_llm_plan_and_projects_rows(monkeypatch):
    captured = {}
    db = FakeAuditDb()

    class FakeExternalDataClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def fetch_data(self, view, filters=None, identifiers=None):
            captured["view"] = view
            captured["filters"] = filters
            captured["identifiers"] = identifiers
            return [
                {"type": "korrigering", "item_num": "A1", "created_at": "2026-05-21", "extra": "x"},
                {"type": "korrigering", "item_num": "A2", "created_at": "2026-05-21", "extra": "y"},
            ]

    monkeypatch.setattr(settings, "DATA_SOURCE_CATALOG_JSON", json.dumps(SAMPLE_CATALOG))
    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://secret.example/api/")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY", "secret-key")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT", "secret-client")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY_HEADER", "secret-key-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT_HEADER", "secret-client-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "secret/path/{view}/data")
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "minimax-key")
    service.clear_catalog_cache()
    monkeypatch.setattr(
        data_fetch,
        "_call_minimax",
        lambda _payload: json.dumps(
            {
                "status": "ok",
                "view": "dblog_count_log",
                "output_columns": ["type", "item_num"],
                "filters": [{"field": "type", "operator": "EQ", "value": "korrigering"}],
            }
        ),
    )
    monkeypatch.setattr(data_fetch, "ExternalDataClient", FakeExternalDataClient)

    result = asyncio.run(
        data_fetch.run_data_fetch(
            data_fetch.DataFetchRunRequest(prompt="Hämta Aktivitetslogg där typ är korrigering"),
            current_user=fake_user(),
            db=db,
        )
    )

    assert captured["view"] == "dblog_count_log"
    assert captured["filters"] == [{"id": "type", "operator": "EQ", "value": "korrigering"}]
    assert captured["client_kwargs"]["base_url"] == "https://secret.example/api/"
    assert result["columns"] == [
        {"id": "type", "label": "Typ"},
        {"id": "item_num", "label": "Artikel"},
    ]
    assert result["rows"] == [
        {"type": "korrigering", "item_num": "A1"},
        {"type": "korrigering", "item_num": "A2"},
    ]
    assert result["session_id"]
    session = data_fetch.DATA_FETCH_SESSIONS[result["session_id"]]
    assert session["user_key"] == "1"
    assert "rows" not in session
    assert data_fetch._read_data_fetch_rows(session) == result["rows"]
    assert db.committed is True
    assert len(db.items) == 1
    assert isinstance(db.items[0], AuditLog)
    assert db.items[0].entity_type == "data_fetch"
    assert db.items[0].action == "fetch_success"
    assert db.items[0].new_value["view"] == "dblog_count_log"
    assert db.items[0].new_value["total_rows"] == 2


def test_excel_export_session_is_bound_to_user():
    session_id = "session-for-user-1"
    data_fetch.DATA_FETCH_SESSIONS[session_id] = {
        "user_key": "1",
        "plan": {"view": "dblog_count_log", "view_label": "Aktivitetslogg"},
        "columns": [{"id": "type", "label": "Typ"}],
        "rows": [{"type": "korrigering"}],
        "total_rows": 1,
    }

    try:
        with pytest.raises(HTTPException) as exc_info:
            data_fetch.export_data_fetch_excel(session_id, current_user=SimpleNamespace(id=2))
        assert getattr(exc_info.value, "status_code", None) == 404
    finally:
        data_fetch.DATA_FETCH_SESSIONS.pop(session_id, None)


def test_run_data_fetch_uses_business_tenant_for_api_base_url(monkeypatch):
    captured = {}

    class TenantAuditDb(FakeAuditDb):
        def __init__(self):
            super().__init__()
            self.business = Business(id=42, code="T3", name="T3", tenant="itworks")

        def get(self, model, object_id):
            if model is Business and int(object_id) == self.business.id:
                return self.business
            return None

    class FakeExternalDataClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def fetch_data(self, view, filters=None, identifiers=None):
            captured["view"] = view
            return [{"type": "korrigering", "item_num": "A1"}]

    monkeypatch.setattr(settings, "DATA_SOURCE_CATALOG_JSON", json.dumps(SAMPLE_CATALOG))
    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://data-frey.example.test/api/")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY", "secret-key")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT", "secret-client")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY_HEADER", "secret-key-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT_HEADER", "secret-client-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "secret/path/{view}/data")
    service.clear_catalog_cache()
    monkeypatch.setattr(data_fetch, "ExternalDataClient", FakeExternalDataClient)
    db = TenantAuditDb()

    result = asyncio.run(
        data_fetch.run_data_fetch(
            data_fetch.DataFetchRunRequest(
                business_id=42,
                plan={
                    "status": "ok",
                    "view": "dblog_count_log",
                    "output_columns": ["type", "item_num"],
                    "filters": [],
                },
            ),
            current_user=fake_user(),
            db=db,
        )
    )

    assert captured["client_kwargs"]["base_url"] == "https://data-itworks.example.test/api/"
    assert captured["view"] == "dblog_count_log"
    assert result["rows"] == [{"type": "korrigering", "item_num": "A1"}]
    assert db.items[0].business_id == 42


def test_run_data_fetch_returns_calculation_result(monkeypatch):
    captured = {}

    class FakeExternalDataClient:
        def __init__(self, **_kwargs):
            pass

        def fetch_data(self, view, filters=None, identifiers=None):
            captured["filters"] = filters
            return [
                {"book_num": "PO1", "item_num": "A1", "type": 10},
                {"book_num": "PO1", "item_num": "A1", "type": 10},
                {"book_num": "PO1", "item_num": "A2", "type": 10},
                {"book_num": "PO2", "item_num": "A1", "type": 10},
                {"book_num": "PO9", "item_num": "A9", "type": 45},
                {"book_num": "PO9", "item_num": "A8", "type": "91"},
                {"book_num": "PO8", "item_num": "A7", "type": 100},
            ]

    monkeypatch.setattr(settings, "DATA_SOURCE_CATALOG_JSON", json.dumps(RECEIVE_LOG_CATALOG))
    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://secret.example/api/")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY", "secret-key")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT", "secret-client")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY_HEADER", "secret-key-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT_HEADER", "secret-client-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "secret/path/{view}/data")
    service.clear_catalog_cache()
    monkeypatch.setattr(data_fetch, "ExternalDataClient", FakeExternalDataClient)

    result = asyncio.run(
        data_fetch.run_data_fetch(
            data_fetch.DataFetchRunRequest(
                plan={
                    "status": "ok",
                    "view": "v_ask_receive_log",
                    "output_columns": ["book_num", "item_num"],
                    "filters": [{"id": "type", "operator": "NE", "value": [45, 91, 100]}],
                    "calculation": {
                        "metric": "count_distinct",
                        "distinct_by": ["book_num", "item_num"],
                    },
                },
            ),
            current_user=fake_user(),
            db=FakeAuditDb(),
        )
    )

    assert captured["filters"] is None
    assert result["calculation"]["value"] == 3
    assert result["calculation"]["distinct_by"] == ["book_num", "item_num"]
    assert result["calculation_query"] == (
        "SELECT COUNT(DISTINCT (book_num, item_num)) AS value FROM v_ask_receive_log "
        "WHERE type <> 45 AND type <> 91 AND type <> 100;"
    )


def test_run_data_fetch_applies_prefix_filter_after_external_fetch(monkeypatch):
    captured = {}

    class FakeExternalDataClient:
        def __init__(self, **_kwargs):
            pass

        def fetch_data(self, view, filters=None, identifiers=None):
            captured["view"] = view
            captured["filters"] = filters
            captured["identifiers"] = identifiers
            return [
                {"order_num": "TO100", "time_stamp_int": 20260102},
                {"order_num": "TO100", "time_stamp_int": 20260103},
                {"order_num": "TP100", "time_stamp_int": 20260104},
                {"order_num": "to200", "time_stamp_int": 20260105},
            ]

    monkeypatch.setattr(settings, "DATA_SOURCE_CATALOG_JSON", json.dumps(PICK_LOG_CATALOG))
    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://secret.example/api/")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY", "secret-key")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT", "secret-client")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY_HEADER", "secret-key-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT_HEADER", "secret-client-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "secret/path/{view}/data")
    service.clear_catalog_cache()
    monkeypatch.setattr(data_fetch, "ExternalDataClient", FakeExternalDataClient)

    result = asyncio.run(
        data_fetch.run_data_fetch(
            data_fetch.DataFetchRunRequest(
                plan={
                    "status": "ok",
                    "view": "v_ask_pick_log_full",
                    "output_columns": ["order_num"],
                    "filters": [
                        {"field": "time_stamp_int", "operator": "Between", "value": [20260101, 20260131]},
                        {"field": "order_num", "operator": "StartsWith", "value": "TO"},
                    ],
                    "calculation": {
                        "metric": "count_distinct",
                        "distinct_by": ["order_num"],
                    },
                },
            ),
            current_user=fake_user(),
            db=FakeAuditDb(),
        )
    )

    assert captured["view"] == "v_ask_pick_log_full"
    assert captured["filters"] == [
        {"id": "time_stamp_int", "operator": "Between", "value": [20260101, 20260131]}
    ]
    assert captured["identifiers"] is None
    assert result["rows"] == [
        {"order_num": "TO100"},
        {"order_num": "TO100"},
        {"order_num": "to200"},
    ]
    assert result["calculation"]["value"] == 2
    assert result["calculation_query"] == (
        "SELECT COUNT(DISTINCT order_num) AS value FROM v_ask_pick_log_full "
        "WHERE time_stamp_int BETWEEN 20260101 AND 20260131 AND order_num LIKE 'TO%';"
    )


def test_excel_export_writes_data_and_metadata(tmp_path):
    session = {
        "plan": {"view": "dblog_count_log", "view_label": "Aktivitetslogg"},
        "columns": [{"id": "type", "label": "Typ"}, {"id": "item_num", "label": "Artikel"}],
        "rows": [{"type": "korrigering", "item_num": "A1"}],
        "total_rows": 1,
    }

    path = data_fetch._write_excel(session)
    workbook = load_workbook(path)

    assert workbook["Data"]["A1"].value == "Typ"
    assert workbook["Data"]["B2"].value == "A1"
    assert workbook["Fråga"]["B2"].value == "dblog_count_log"


def test_health_reports_missing_catalog_without_spending_ai(monkeypatch):
    monkeypatch.setattr(data_fetch, "load_catalog", lambda: (_ for _ in ()).throw(service.DataFetchConfigError("saknas")))
    for setting_name in data_fetch.REQUIRED_API_SETTINGS:
        monkeypatch.setattr(settings, setting_name, "")
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "minimax-key")

    result = data_fetch.data_fetch_health(fake_user())

    assert result["ok"] is False
    assert result["catalog_configured"] is False
    assert result["api_configured"] is False
    assert result["api_missing"] == list(data_fetch.REQUIRED_API_SETTINGS)
    assert result["minimax_configured"] is True
    assert result["catalog"] == {"views": 0, "columns": 0}


def test_api_client_reports_exact_missing_settings(monkeypatch):
    for setting_name in data_fetch.REQUIRED_API_SETTINGS:
        monkeypatch.setattr(settings, setting_name, "")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://secret.example/api/")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "secret/path/{view}/data")

    with pytest.raises(HTTPException) as exc_info:
        data_fetch._api_client_or_503()

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert "DATA_SOURCE_API_KEY" in detail
    assert "DATA_SOURCE_API_CLIENT" in detail
    assert "DATA_SOURCE_API_KEY_HEADER" in detail
    assert "DATA_SOURCE_API_CLIENT_HEADER" in detail
    assert "DATA_SOURCE_API_BASE_URL" not in detail
    assert "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE" not in detail


def test_external_data_client_wraps_connection_errors():
    class BrokenSession:
        headers = {}

        def post(self, *_args, **_kwargs):
            raise requests.ConnectionError("connection reset")

    client = ExternalDataClient(
        base_url="https://secret.example/api/",
        view_data_path_template="views/{view}/data",
        session=BrokenSession(),
    )

    with pytest.raises(ExternalDataClientError) as exc_info:
        client.fetch_data("dblog_count_log")

    assert "Extern datakälla kunde inte nås" in str(exc_info.value)


def test_external_data_client_builds_path_and_passes_tls_verify():
    captured = {}

    class OkResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"rows": []}

    class FakeSession:
        headers = {}

        def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return OkResponse()

    client = ExternalDataClient(
        base_url="https://secret.example",
        view_data_path_template="/api/integration/views/{view}/data",
        verify_ssl=False,
        session=FakeSession(),
    )

    rows = client.fetch_data("v_ask_pick_log_full")

    assert rows == []
    assert captured["url"] == "https://secret.example/api/integration/views/v_ask_pick_log_full/data"
    assert captured["verify"] is False


def test_data_source_base_url_can_be_tenant_scoped():
    assert (
        data_source_base_url_for_tenant("https://data-frey.example.test/api/", "itworks")
        == "https://data-itworks.example.test/api/"
    )
    assert (
        data_source_base_url_for_tenant("https://data-{tenant}.example.test/api/", "itworks")
        == "https://data-itworks.example.test/api/"
    )


def test_api_client_passes_tls_settings(monkeypatch):
    captured = {}

    class FakeExternalDataClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://secret.example/")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY", "secret-key")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT", "secret-client")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY_HEADER", "secret-key-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT_HEADER", "secret-client-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "/api/integration/views/{view}/data")
    monkeypatch.setattr(settings, "DATA_SOURCE_VERIFY_SSL", False)
    monkeypatch.setattr(settings, "DATA_SOURCE_CA_BUNDLE", "")
    monkeypatch.setattr(data_fetch, "ExternalDataClient", FakeExternalDataClient)

    data_fetch._api_client_or_503()

    assert captured["verify_ssl"] is False
    assert captured["ca_bundle"] is None


def test_run_data_fetch_returns_logged_external_error(monkeypatch):
    db = FakeAuditDb()

    class FailingExternalDataClient:
        def __init__(self, **_kwargs):
            pass

        def fetch_data(self, *_args, **_kwargs):
            raise ExternalDataClientError("Extern datakälla kunde inte nås.")

    monkeypatch.setattr(settings, "DATA_SOURCE_CATALOG_JSON", json.dumps(SAMPLE_CATALOG))
    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://secret.example/api/")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY", "secret-key")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT", "secret-client")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY_HEADER", "secret-key-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT_HEADER", "secret-client-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "secret/path/{view}/data")
    service.clear_catalog_cache()
    monkeypatch.setattr(data_fetch, "ExternalDataClient", FailingExternalDataClient)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            data_fetch.run_data_fetch(
                data_fetch.DataFetchRunRequest(
                    plan={
                        "status": "ok",
                        "view": "dblog_count_log",
                        "output_columns": ["type", "item_num"],
                        "filters": [{"field": "type", "operator": "EQ", "value": "korrigering"}],
                    }
                ),
                current_user=fake_user(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["message"] == "Extern datakälla kunde inte nås."
    assert exc_info.value.detail["view"] == "dblog_count_log"
    assert exc_info.value.detail["error_id"]
    assert db.committed is True
    assert len(db.items) == 1
    assert db.items[0].entity_type == "data_fetch"
    assert db.items[0].action == "fetch_failed"
    assert db.items[0].new_value["status_code"] == 502
    assert db.items[0].new_value["error_id"] == exc_info.value.detail["error_id"]


class _WindowedClient:
    """Fake källa som respekterar ett radtak och filtrerar på Between-datumfönstret."""

    def __init__(self, rows, cap, date_field="ts"):
        self.rows = rows
        self.cap = cap
        self.date_field = date_field
        self.calls = []

    def fetch_data(self, view, filters=None, identifiers=None):
        between = next(
            (item for item in (filters or []) if item.get("operator") == "Between"),
            None,
        )
        if between is None:
            window = list(self.rows)
        else:
            low, high = between["value"]
            window = [row for row in self.rows if low <= row[self.date_field] <= high]
        self.calls.append((view, between["value"] if between else None))
        return window[: self.cap]


def test_fetch_external_rows_splits_date_window_when_response_capped(monkeypatch):
    monkeypatch.setattr(settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 3)
    all_rows = [
        {"id": f"{day}-{n}", "ts": 20260500 + day}
        for day in range(1, 5)
        for n in range(2)
    ]
    client = _WindowedClient(all_rows, cap=3)
    external_filters = [{"id": "ts", "operator": "Between", "value": [20260501, 20260504]}]

    rows = data_fetch._fetch_external_rows(client, "v_test", external_filters, None)

    assert len(rows) == len(all_rows)
    assert {row["id"] for row in rows} == {row["id"] for row in all_rows}
    # Varje delfönster ligger under taket -> inga rader tappas och inget överlapp.
    assert all(len(call_value or []) == 2 for _view, call_value in client.calls if call_value)


def test_fetch_external_rows_returns_capped_without_date_filter(monkeypatch):
    monkeypatch.setattr(settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 3)
    all_rows = [{"id": idx, "ts": 20260501} for idx in range(10)]
    client = _WindowedClient(all_rows, cap=3)

    rows = data_fetch._fetch_external_rows(client, "v_test", [], None)

    # Utan datumfilter att dela på kan vi inte gå runt taket – men vi kraschar inte.
    assert len(rows) == 3
    assert len(client.calls) == 1


def test_fetch_external_rows_raises_when_single_day_exceeds_cap(monkeypatch):
    monkeypatch.setattr(settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 3)
    all_rows = [{"id": idx, "ts": 20260501} for idx in range(10)]
    client = _WindowedClient(all_rows, cap=3)
    external_filters = [{"id": "ts", "operator": "Between", "value": [20260501, 20260501]}]

    with pytest.raises(ExternalDataClientError) as exc_info:
        data_fetch._fetch_external_rows(client, "v_test", external_filters, None)

    assert "2026-05-01" in str(exc_info.value)


def test_fetch_external_rows_splits_iso_datetime_window(monkeypatch):
    monkeypatch.setattr(settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 3)
    all_rows = [
        {"id": f"{day}-{n}", "ts": f"2026-05-0{day}T12:00:00"}
        for day in range(1, 5)
        for n in range(2)
    ]
    client = _WindowedClient(all_rows, cap=3)
    external_filters = [
        {"id": "ts", "operator": "Between", "value": ["2026-05-01T00:00:00", "2026-05-04T23:59:59"]}
    ]

    rows = data_fetch._fetch_external_rows(client, "v_test", external_filters, None)

    assert {row["id"] for row in rows} == {row["id"] for row in all_rows}


# --- Delad fetch_all_rows / ExternalDataClient.fetch_all -----------------------

def test_fetch_all_rows_no_cap_returns_everything_without_windowing():
    all_rows = [{"id": idx, "ts": 20260501} for idx in range(10)]
    client = _WindowedClient(all_rows, cap=3)
    # response_row_cap=0 stänger av uppdelning -> en enda hämtning, inga fönster
    rows = fetch_all_rows(client.fetch_data, "v_test", None, response_row_cap=0)
    assert rows == client.fetch_data("v_test")  # samma som rå-hämtning
    assert len(client.calls) >= 1
    assert all(call_value is None for _view, call_value in client.calls)


# --- Förpacknings-uppdelning (package_breakdown) ------------------------------

PACKAGE_PICK_CATALOG = {
    "version": 1,
    "views": [
        {
            "id": "v_ask_pick_log_full",
            "label_en": "Pick Log Full",
            "label_sv": "Plocklogg Full",
            "columns": [
                {"id": "item_num", "order": 1, "label_en": "Item Num", "label_sv": "Artikelnr"},
                {"id": "company", "order": 2, "label_en": "Company", "label_sv": "Bolag"},
                {"id": "qty_pre", "order": 3, "label_en": "Qty Pre", "label_sv": "Beställt"},
                {"id": "pick_zone", "order": 4, "label_en": "Pick Zone", "label_sv": "Zon"},
                {"id": "rel_num", "order": 5, "label_en": "Rel Num", "label_sv": "Relnr"},
            ],
        }
    ],
}


def test_split_quantity_into_packages_is_greedy_largest_first():
    ladder = [("DFP", 10), ("ST", 1)]
    assert service.split_quantity_into_packages(15, ladder) == {"DFP": 1, "ST": 5}
    assert service.split_quantity_into_packages(30, ladder) == {"DFP": 3}
    assert service.split_quantity_into_packages(0, ladder) == {}
    assert service.split_quantity_into_packages(-4, ladder) == {}


def test_build_package_ladders_sorts_desc_and_guarantees_base_unit():
    ladders = service.build_package_ladders(
        [
            {"item_num": "A1", "company": "GG", "unit": "DFP", "conversion_factor": 10},
            {"item_num": "A1", "company": "GG", "unit": "KRT", "conversion_factor": 4},
            # ingen faktor-1-rad: en bas-enhet ska ändå läggas till
            {"item_num": "A2", "company": "GG", "unit": "RULLE", "conversion_factor": 240},
        ]
    )
    assert ladders[("A1", "GG")] == [("DFP", 10), ("KRT", 4), ("ST", 1)]
    assert ladders[("A2", "GG")] == [("RULLE", 240), ("ST", 1)]


def test_execute_package_breakdown_splits_per_row_not_grouped():
    # Användarens exempel: två orderrader á 15. Uppdelning per rad ger 12 (2 DFP +
    # 10 ST), inte 3 som en hopslagen total (30 / 10) hade gett.
    pick_rows = [
        {"order_num": "1", "item_num": "ART1", "company": "GG", "qty_pre": 15},
        {"order_num": "2", "item_num": "ART1", "company": "GG", "qty_pre": 15},
    ]
    alias_rows = [
        {"item_num": "ART1", "company": "GG", "unit": "ST", "conversion_factor": 1},
        {"item_num": "ART1", "company": "GG", "unit": "DFP", "conversion_factor": 10},
    ]
    plan = {"calculation": {"metric": "package_breakdown", "field": "qty_pre", "group_by": ["item_num"]}}

    result = service.execute_package_breakdown(pick_rows, alias_rows, plan)

    assert result["value"] == 12
    assert result["unit_totals"] == {"ST": 10, "DFP": 2}
    by_unit = {(row["item_num"], row["unit"]): row["value"] for row in result["rows"]}
    assert by_unit == {("ART1", "DFP"): 2, ("ART1", "ST"): 10}


def test_execute_package_breakdown_falls_back_to_base_unit_without_alias():
    pick_rows = [{"item_num": "MISSING", "company": "GG", "qty_pre": 7}]
    plan = {"calculation": {"metric": "package_breakdown", "field": "qty_pre", "group_by": ["item_num"]}}

    result = service.execute_package_breakdown(pick_rows, [], plan)

    assert result["value"] == 7
    assert result["unit_totals"] == {"ST": 7}


def test_validate_plan_requires_field_for_package_breakdown():
    catalog = service.catalog_from_payload(PACKAGE_PICK_CATALOG)
    with pytest.raises(service.DataFetchPlanError):
        service.validate_plan_payload(
            {
                "status": "ok",
                "view": "v_ask_pick_log_full",
                "output_columns": ["item_num"],
                "calculation": {"metric": "package_breakdown", "group_by": ["item_num"]},
            },
            catalog,
        )

    plan = service.validate_plan_payload(
        {
            "status": "ok",
            "view": "v_ask_pick_log_full",
            "output_columns": ["item_num"],
            "calculation": {"metric": "förpackningar", "field": "qty_pre", "group_by": ["item_num"]},
        },
        catalog,
    )
    assert plan["calculation"]["metric"] == "package_breakdown"
    assert plan["calculation"]["field"] == "qty_pre"


def test_run_data_fetch_package_breakdown_fetches_alias_and_splits(monkeypatch):
    calls = []
    pick_rows = [
        {"item_num": "ART1", "company": "GG", "qty_pre": 15, "pick_zone": "A", "rel_num": 0},
        {"item_num": "ART1", "company": "GG", "qty_pre": 15, "pick_zone": "A", "rel_num": 0},
    ]
    alias_rows = [
        {"item_num": "ART1", "company": "GG", "unit": "ST", "conversion_factor": 1},
        {"item_num": "ART1", "company": "GG", "unit": "DFP", "conversion_factor": 10},
    ]

    class FakeExternalDataClient:
        def __init__(self, **_kwargs):
            pass

        def fetch_data(self, view, filters=None, identifiers=None):
            calls.append((view, filters))
            return alias_rows if view == "asw_item_alias" else pick_rows

    monkeypatch.setattr(settings, "DATA_SOURCE_CATALOG_JSON", json.dumps(PACKAGE_PICK_CATALOG))
    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://secret.example/api/")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY", "secret-key")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT", "secret-client")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY_HEADER", "secret-key-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT_HEADER", "secret-client-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "secret/path/{view}/data")
    service.clear_catalog_cache()
    monkeypatch.setattr(data_fetch, "ExternalDataClient", FakeExternalDataClient)

    result = asyncio.run(
        data_fetch.run_data_fetch(
            data_fetch.DataFetchRunRequest(
                plan={
                    "status": "ok",
                    "view": "v_ask_pick_log_full",
                    "output_columns": ["item_num"],
                    "filters": [
                        {"field": "pick_zone", "operator": "NE", "value": "H"},
                        {"field": "rel_num", "operator": "EQ", "value": 0},
                        {"field": "company", "operator": "EQ", "value": "GG"},
                    ],
                    "calculation": {"metric": "package_breakdown", "field": "qty_pre", "group_by": ["item_num"]},
                },
            ),
            current_user=fake_user(),
            db=FakeAuditDb(),
        )
    )

    assert result["calculation"]["value"] == 12
    assert result["calculation"]["unit_totals"] == {"ST": 10, "DFP": 2}
    # Alias-vyn hämtades, filtrerad på samma bolag som plockplanen.
    alias_calls = [filters for view, filters in calls if view == "asw_item_alias"]
    assert alias_calls and {"id": "company", "operator": "EQ", "value": "GG"} in alias_calls[0]
    assert "package_breakdown" in result["calculation"]["metric"]


def test_fetch_all_rows_windows_when_capped():
    all_rows = [{"id": f"{day}-{n}", "ts": 20260500 + day} for day in range(1, 5) for n in range(2)]
    client = _WindowedClient(all_rows, cap=3)
    filters = [{"id": "ts", "operator": "Between", "value": [20260501, 20260504]}]
    rows = fetch_all_rows(client.fetch_data, "v_test", filters, response_row_cap=3)
    assert {row["id"] for row in rows} == {row["id"] for row in all_rows}


def test_external_client_fetch_all_uses_shared_windowing():
    all_rows = [{"id": f"{day}-{n}", "ts": 20260500 + day} for day in range(1, 5) for n in range(2)]
    windowed = _WindowedClient(all_rows, cap=3)
    client = ExternalDataClient(base_url="http://example.test", response_row_cap=3)
    client.fetch_data = windowed.fetch_data  # type: ignore[assignment]
    filters = [{"id": "ts", "operator": "Between", "value": [20260501, 20260504]}]
    rows = client.fetch_all("v_test", filters=filters)
    assert {row["id"] for row in rows} == {row["id"] for row in all_rows}
    assert len(windowed.calls) > 1  # delades upp i fönster


# --- Retention: live/archive auto-byte och merge -------------------------------

def _date_col(order):
    return {"id": "time_stamp_int", "order": order, "label_en": "Time Stamp Int", "label_sv": "Datum"}


RETENTION_CATALOG = service.catalog_from_payload({
    "version": 1,
    "views": [
        {
            "id": "v_ask_pick_log_full",
            "label_en": "Pick Log Full",
            "label_sv": "Plocklogg Full",
            "columns": [
                {"id": "order_num", "order": 1, "label_en": "Order Num", "label_sv": "Ordernr"},
                _date_col(2),
                {"id": "company", "order": 3, "label_en": "Company", "label_sv": "Bolag"},
                {"id": "qty_suf", "order": 4, "label_en": "Qty Suf", "label_sv": "Plockat"},
            ],
        },
        {
            "id": "dblog_pick_log",
            "label_en": "Archive Pick Log",
            "label_sv": "Arkiv Plocklogg",
            "columns": [
                {"id": "order_num", "order": 1, "label_en": "Order Num", "label_sv": "Ordernr"},
                _date_col(2),
                {"id": "company", "order": 3, "label_en": "Company", "label_sv": "Bolag"},
            ],
        },
    ],
})
TODAY = date(2026, 6, 15)  # cutoff för 40d retention = 2026-05-06


def _pick_plan(view, start_int, end_int):
    return {
        "status": "ok",
        "view": view,
        "output_columns": ["order_num", "time_stamp_int", "company"],
        "filters": [
            {"id": "company", "operator": "EQ", "value": "GG"},
            {"id": "time_stamp_int", "operator": "Between", "value": [start_int, end_int]},
        ],
        "identifiers": [],
        "calculation": None,
    }


def test_retention_live_only_when_period_within_active_window():
    plan = _pick_plan("v_ask_pick_log_full", 20260609, 20260615)
    assert service.build_retention_segments(plan, RETENTION_CATALOG, TODAY) is None


def test_retention_redirects_old_period_to_archive():
    plan = _pick_plan("v_ask_pick_log_full", 20260101, 20260131)
    result = service.build_retention_segments(plan, RETENTION_CATALOG, TODAY)
    assert result is not None
    assert [seg["view"] for seg in result["segments"]] == ["dblog_pick_log"]
    assert result["fetched_views"] == ["dblog_pick_log"]
    assert "Arkiv Plocklogg" in result["notice"]
    # company-filtret behålls, datumfiltret pekar på arkivets datumkolumn
    segment = result["segments"][0]
    company = [f for f in segment["filters"] if f["id"] == "company"]
    between = [f for f in segment["filters"] if f["operator"] == "Between"]
    assert company and company[0]["value"] == "GG"
    assert between and between[0]["value"] == [20260101, 20260131]


def test_retention_spanning_period_fetches_both_and_splits_at_cutoff():
    plan = _pick_plan("v_ask_pick_log_full", 20260420, 20260610)
    result = service.build_retention_segments(plan, RETENTION_CATALOG, TODAY)
    assert result is not None
    assert [seg["view"] for seg in result["segments"]] == ["v_ask_pick_log_full", "dblog_pick_log"]
    live_between = [f for f in result["segments"][0]["filters"] if f["operator"] == "Between"][0]
    archive_between = [f for f in result["segments"][1]["filters"] if f["operator"] == "Between"][0]
    assert live_between["value"] == [20260506, 20260610]      # från cutoff
    assert archive_between["value"] == [20260420, 20260505]    # till cutoff-1


def test_retention_archive_request_with_active_dates_also_fetches_live():
    plan = _pick_plan("dblog_pick_log", 20260610, 20260614)
    result = service.build_retention_segments(plan, RETENTION_CATALOG, TODAY)
    assert result is not None
    assert [seg["view"] for seg in result["segments"]] == ["dblog_pick_log", "v_ask_pick_log_full"]
    assert "v_ask_pick_log_full" in result["fetched_views"]
    assert "Plocklogg Full" in result["notice"]


def test_retention_archive_request_with_old_dates_stays_archive_only():
    plan = _pick_plan("dblog_pick_log", 20260101, 20260131)
    assert service.build_retention_segments(plan, RETENTION_CATALOG, TODAY) is None


def test_retention_ignored_for_unmapped_view():
    plan = _pick_plan("v_ask_trans_log", 20260101, 20260131)
    plan["view"] = "v_ask_some_unmapped_view"
    assert service.build_retention_segments(plan, RETENTION_CATALOG, TODAY) is None
