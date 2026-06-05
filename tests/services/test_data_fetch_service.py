import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from fastapi import HTTPException
from openpyxl import load_workbook
import pytest
import requests

from app.backend import data_fetch_service as service
from app.backend.config import settings
from app.backend.external_data_client import ExternalDataClient, ExternalDataClientError
from app.backend.models import AuditLog
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
