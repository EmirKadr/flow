import calendar
import os
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from app.backend.config import settings
from app.backend.data_fetch_service import (
    apply_local_filters,
    calculation_query_text,
    execute_calculation,
    external_filters_for_api,
)
from app.backend.external_data_client import ExternalDataClient, data_source_base_url_for_tenant


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DATA_SOURCE_INTEGRATION") != "1",
        reason="Live data source tests are opt-in. Set RUN_DATA_SOURCE_INTEGRATION=1 to run.",
    ),
]


REQUIRED_DATA_SOURCE_SETTINGS = (
    "DATA_SOURCE_API_BASE_URL",
    "DATA_SOURCE_API_KEY",
    "DATA_SOURCE_API_CLIENT",
    "DATA_SOURCE_API_KEY_HEADER",
    "DATA_SOURCE_API_CLIENT_HEADER",
    "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE",
)


def _setting(name: str) -> str:
    return str(getattr(settings, name) or "").strip()


def _require_data_source_settings() -> None:
    missing = [name for name in REQUIRED_DATA_SOURCE_SETTINGS if not _setting(name)]
    if missing:
        pytest.fail(
            "RUN_DATA_SOURCE_INTEGRATION=1 was set, but these settings are missing: "
            + ", ".join(missing)
        )


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        pytest.fail(f"{name} must be an integer, got {value!r}")
        raise exc


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return float(value.replace(",", "."))
    except ValueError as exc:
        pytest.fail(f"{name} must be a number, got {value!r}")
        raise exc


def _month_period_for_field(field: str, year: int, month: int) -> list[Any]:
    last_day = calendar.monthrange(year, month)[1]
    if field == "time_stamp_int" or field.endswith("_int"):
        return [year * 10000 + month * 100 + 1, year * 10000 + month * 100 + last_day]
    return [
        f"{year:04d}-{month:02d}-01T00:00:00",
        f"{year:04d}-{month:02d}-{last_day:02d}T23:59:59",
    ]


def _pick_log_plan() -> dict[str, Any]:
    year = _int_env("LIVE_DATA_SOURCE_YEAR", 2026)
    month = _int_env("LIVE_DATA_SOURCE_MONTH", 5)
    company = os.getenv("LIVE_DATA_SOURCE_COMPANY", "GG").strip().upper() or "GG"
    date_field = os.getenv("LIVE_DATA_SOURCE_DATE_FIELD", "time_stamp_int").strip() or "time_stamp_int"
    excluded_zone = os.getenv("LIVE_DATA_SOURCE_EXCLUDE_ZONE", "H").strip().upper() or "H"
    min_picked = _float_env("LIVE_DATA_SOURCE_MIN_PICKED", 1)
    min_picked_value: int | float = int(min_picked) if min_picked.is_integer() else min_picked
    return {
        "status": "ok",
        "view": "v_ask_pick_log_full",
        "view_label": "Plocklogg Full",
        "output_columns": ["order_num", "pick_zone", "qty_suf", date_field, "company"],
        "output_column_labels": {
            "order_num": "Ordernr",
            "pick_zone": "Zon",
            "qty_suf": "Plockat",
            date_field: "Datum",
            "company": "Bolag",
        },
        "filters": [
            {"id": "pick_zone", "operator": "NE", "value": excluded_zone},
            {"id": "qty_suf", "operator": "GTE", "value": min_picked_value},
            {"id": date_field, "operator": "Between", "value": _month_period_for_field(date_field, year, month)},
            {"id": "company", "operator": "EQ", "value": company},
        ],
        "identifiers": [],
        "calculation": {
            "metric": "count",
            "field": None,
            "distinct_by": [],
            "group_by": [],
            "sort_by": None,
            "limit": None,
        },
        "reason": "Live diagnostic for pick rows.",
    }


def _client() -> ExternalDataClient:
    _require_data_source_settings()
    tenant = os.getenv("LIVE_DATA_SOURCE_TENANT", "frey").strip() or "frey"
    base_url = data_source_base_url_for_tenant(settings.DATA_SOURCE_API_BASE_URL, tenant)
    return ExternalDataClient(
        base_url=base_url,
        api_key=settings.DATA_SOURCE_API_KEY,
        api_client=settings.DATA_SOURCE_API_CLIENT,
        api_key_header=settings.DATA_SOURCE_API_KEY_HEADER,
        api_client_header=settings.DATA_SOURCE_API_CLIENT_HEADER,
        view_data_path_template=settings.DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE,
        timeout=float(settings.DATA_SOURCE_TIMEOUT_SECONDS or 30),
        verify_ssl=bool(settings.DATA_SOURCE_VERIFY_SSL),
        ca_bundle=settings.DATA_SOURCE_CA_BUNDLE or None,
    )


def _assert_expected_count(value: int | float) -> None:
    expected = os.getenv("LIVE_DATA_SOURCE_EXPECTED_PICK_COUNT", "").strip()
    if not expected:
        return
    try:
        expected_value = int(expected)
    except ValueError as exc:
        pytest.fail(f"LIVE_DATA_SOURCE_EXPECTED_PICK_COUNT must be an integer, got {expected!r}")
        raise exc
    assert value == expected_value


def _assert_optional_sql_facit(value: int | float) -> None:
    sql_url = os.getenv("LIVE_DATA_SOURCE_SQL_URL", "").strip()
    sql_query = os.getenv("LIVE_DATA_SOURCE_SQL", "").strip()
    if not sql_url and not sql_query:
        return
    if not sql_url or not sql_query:
        pytest.fail("Set both LIVE_DATA_SOURCE_SQL_URL and LIVE_DATA_SOURCE_SQL to compare against SQL facit.")

    engine = create_engine(sql_url)
    try:
        with engine.connect() as connection:
            sql_value = connection.execute(text(sql_query)).scalar_one()
    finally:
        engine.dispose()
    assert int(value) == int(sql_value)


def test_live_pick_log_count_after_local_filters():
    plan = _pick_log_plan()
    api_filters = external_filters_for_api(plan["filters"])

    rows = _client().fetch_data(plan["view"], filters=api_filters or None, identifiers=None)
    filtered_rows = apply_local_filters(rows, plan["filters"])
    calculation = execute_calculation(filtered_rows, plan) or {"value": len(filtered_rows)}

    value = calculation["value"]
    assert isinstance(value, int)
    assert value <= len(rows)

    print(
        "\n".join(
            [
                "",
                "Live data source diagnostic:",
                f"  query: {calculation_query_text(plan)}",
                f"  api_filters: {api_filters}",
                f"  api_rows: {len(rows)}",
                f"  local_filtered_rows: {value}",
            ]
        )
    )

    _assert_expected_count(value)
    _assert_optional_sql_facit(value)
