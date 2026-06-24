from types import SimpleNamespace

from fastapi import HTTPException

from app.backend import productivity_finance_process_check as process_check
from app.backend.productivity_kpi_rules import parse_kpi_rule_rows


class FakeCatalog:
    def view(self, view_id):
        columns = [
            SimpleNamespace(id="time_stamp_int", label_en="Date", label_sv="Datum"),
            SimpleNamespace(id="company", label_en="Company", label_sv="Bolag"),
            SimpleNamespace(id="pick_zone", label_en="Zone", label_sv="Zon"),
            SimpleNamespace(id="qty_suf", label_en="Picked", label_sv="Plockat"),
            SimpleNamespace(id="order_num", label_en="Order", label_sv="Order"),
            SimpleNamespace(id="type", label_en="Type", label_sv="Typ"),
            SimpleNamespace(id="status", label_en="Status", label_sv="Status"),
            SimpleNamespace(id="wareh_num", label_en="Warehouse", label_sv="Lager"),
        ]
        return SimpleNamespace(
            id=view_id,
            label=view_id,
            columns=columns,
            column_by_id={column.id: column for column in columns},
        )


def _matches_filter(row, item):
    column = item.get("id") or item.get("field")
    operator = item.get("operator")
    value = item.get("value")
    row_value = row.get(column)
    if operator == "EQ":
        return str(row_value) == str(value)
    if operator == "NE":
        return str(row_value) != str(value)
    if operator == "StartsWith":
        return str(row_value or "").startswith(str(value or ""))
    if operator == "GTE":
        return float(row_value or 0) >= float(value or 0)
    if operator == "Between":
        start, end = value
        return int(start) <= int(row_value or 0) <= int(end)
    return True


def test_process_check_finds_missing_revenue_zone_and_duplicate_kpi(monkeypatch):
    rules = parse_kpi_rule_rows(
        [
            {"process": "GG Plock", "source": "pick", "metric": "rows", "company": "GG", "zone": "A;B;C", "positive_column": "qty_suf"},
            {"process": "GG Plock dubbel", "source": "pick", "metric": "rows", "company": "GG", "zone": "B", "positive_column": "qty_suf"},
        ]
    )
    rows = [
        {"rowid": "1", "company": "GG", "pick_zone": "A", "qty_suf": 1, "order_num": "TO1", "time_stamp_int": 20260601},
        {"rowid": "2", "company": "GG", "pick_zone": "B", "qty_suf": 1, "order_num": "TO2", "time_stamp_int": 20260601},
        {"rowid": "3", "company": "GG", "pick_zone": "C", "qty_suf": 1, "order_num": "TO3", "time_stamp_int": 20260601},
        {"rowid": "4", "company": "GG", "pick_zone": "D", "qty_suf": 1, "order_num": "TO4", "time_stamp_int": 20260601},
        {"rowid": "5", "company": "GG", "pick_zone": "H", "qty_suf": 1, "order_num": "TO5", "time_stamp_int": 20260601},
    ]

    def fake_fetch(plan, _error_id, _tenant):
        if plan.get("view") != "v_ask_pick_log_full":
            return []
        result = rows
        for item in plan.get("filters") or []:
            result = [row for row in result if _matches_filter(row, item)]
        return result

    monkeypatch.setattr(process_check, "load_catalog", lambda: FakeCatalog())
    monkeypatch.setattr(process_check, "load_kpi_rules", lambda *_args, **_kwargs: (rules, {}))

    result = process_check.build_productivity_finance_process_check(
        object(),
        business=SimpleNamespace(id=1, company_codes=["GG"]),
        finance_settings={
            "invoice_rows_by_company": {
                "GG": [
                    {
                        "id": "store_picked_rows",
                        "service": "Outbound",
                        "description": "Plockade rader",
                        "unit": "Per rad",
                        "price": 10,
                        "calculation_plan": {
                            "status": "ok",
                            "view": "v_ask_pick_log_full",
                            "view_label": "Plocklogg Full",
                            "output_columns": ["rowid"],
                            "filters": [
                                {"id": "order_num", "operator": "StartsWith", "value": "TO"},
                                {"id": "pick_zone", "operator": "NE", "value": "H"},
                                {"id": "qty_suf", "operator": "GTE", "value": 1},
                                {"id": "company", "operator": "EQ", "value": "GG"},
                            ],
                            "calculation": {
                                "metric": "count",
                                "field": None,
                                "distinct_by": [],
                                "group_by": [],
                                "sort_by": None,
                                "limit": None,
                            },
                        },
                    }
                ]
            }
        },
        month=6,
        year=2026,
        company_code="GG",
        fetch_rows=fake_fetch,
        tenant="frey",
    )

    check = result["revenue_checks"][0]

    assert check["quantity"] == 4
    assert check["revenue"] == 40
    assert check["missing_in_kpi_count"] == 1
    assert check["missing_in_kpi"][0]["values"]["pick_zone"] == "D"
    assert {item["process"] for item in check["matched_processes"]} == {"GG Plock", "GG Plock dubbel"}
    assert result["summary"]["duplicate_kpi"] == 1


def test_process_check_accepts_combined_processes_and_notes_broader_process(monkeypatch):
    rules = parse_kpi_rule_rows(
        [
            {"process": "GG Plock A-B", "source": "pick", "metric": "rows", "company": "GG", "zone": "A;B", "positive_column": "qty_suf"},
            {"process": "GG Plock C-D-H", "source": "pick", "metric": "rows", "company": "GG", "zone": "C;D;H", "positive_column": "qty_suf"},
        ]
    )
    rows = [
        {"rowid": "1", "company": "GG", "pick_zone": "A", "qty_suf": 1, "order_num": "TO1", "time_stamp_int": 20260601},
        {"rowid": "2", "company": "GG", "pick_zone": "B", "qty_suf": 1, "order_num": "TO2", "time_stamp_int": 20260601},
        {"rowid": "3", "company": "GG", "pick_zone": "C", "qty_suf": 1, "order_num": "TO3", "time_stamp_int": 20260601},
        {"rowid": "4", "company": "GG", "pick_zone": "D", "qty_suf": 1, "order_num": "TO4", "time_stamp_int": 20260601},
        {"rowid": "5", "company": "GG", "pick_zone": "H", "qty_suf": 1, "order_num": "TO5", "time_stamp_int": 20260601},
    ]

    def fake_fetch(plan, _error_id, _tenant):
        if plan.get("view") != "v_ask_pick_log_full":
            return []
        result = rows
        for item in plan.get("filters") or []:
            result = [row for row in result if _matches_filter(row, item)]
        return result

    monkeypatch.setattr(process_check, "load_catalog", lambda: FakeCatalog())
    monkeypatch.setattr(process_check, "load_kpi_rules", lambda *_args, **_kwargs: (rules, {}))

    result = process_check.build_productivity_finance_process_check(
        object(),
        business=SimpleNamespace(id=1, company_codes=["GG"]),
        finance_settings={
            "invoice_rows_by_company": {
                "GG": [
                    {
                        "id": "store_picked_rows",
                        "service": "Outbound",
                        "description": "Plockade rader",
                        "unit": "Per rad",
                        "price": 10,
                        "calculation_plan": {
                            "status": "ok",
                            "view": "v_ask_pick_log_full",
                            "view_label": "Plocklogg Full",
                            "output_columns": ["rowid"],
                            "filters": [
                                {"id": "order_num", "operator": "StartsWith", "value": "TO"},
                                {"id": "pick_zone", "operator": "NE", "value": "H"},
                                {"id": "qty_suf", "operator": "GTE", "value": 1},
                                {"id": "company", "operator": "EQ", "value": "GG"},
                            ],
                            "calculation": {"metric": "count"},
                        },
                    }
                ]
            }
        },
        month=6,
        year=2026,
        company_code="GG",
        fetch_rows=fake_fetch,
        tenant="frey",
    )

    check = result["revenue_checks"][0]

    assert check["status"] == "ok"
    assert check["missing_in_kpi_count"] == 0
    assert check["process_extra_count"] == 1
    assert check["process_extra"][0]["values"]["pick_zone"] == "H"
    assert {item["process"] for item in check["matched_processes"]} == {"GG Plock A-B", "GG Plock C-D-H"}
    assert "Flera KPI-processer verkar tillsammans täcka intäktsraden." in check["messages"]
    assert "Matchande KPI-processer räknar även rader utanför den här intäktsraden." in check["messages"]
    assert result["summary"]["matched_revenue_rows"] == 1
    assert result["summary"]["warning_revenue_rows"] == 0
    assert result["summary"]["missing_in_revenue"] == 1
    assert result["summary"]["duplicate_kpi"] == 0


def test_process_check_combines_processes_by_distinct_revenue_key(monkeypatch):
    rules = parse_kpi_rule_rows(
        [
            {"process": "Manual Pick", "source": "pick", "metric": "rows", "company": "GG", "zone": "A", "positive_column": "qty_suf"},
            {"process": "Bulky Pick", "source": "pick", "metric": "rows", "company": "GG", "zone": "S", "positive_column": "qty_suf"},
            {"process": "E Commerce", "source": "pick", "metric": "rows", "company": "GG", "zone": "E", "positive_column": "qty_suf"},
        ]
    )
    rows = [
        {"rowid": "1", "company": "GG", "pick_zone": "A", "qty_suf": 1, "order_num": "TO1", "time_stamp_int": 20260601},
        {"rowid": "2", "company": "GG", "pick_zone": "D", "qty_suf": 1, "order_num": "TO1", "time_stamp_int": 20260601},
        {"rowid": "3", "company": "GG", "pick_zone": "S", "qty_suf": 1, "order_num": "TO2", "time_stamp_int": 20260601},
        {"rowid": "4", "company": "GG", "pick_zone": "E", "qty_suf": 1, "order_num": "TO3", "time_stamp_int": 20260601},
        {"rowid": "5", "company": "GG", "pick_zone": "D", "qty_suf": 1, "order_num": "TO4", "time_stamp_int": 20260601},
        {"rowid": "6", "company": "GG", "pick_zone": "A", "qty_suf": 1, "order_num": "XX1", "time_stamp_int": 20260601},
    ]

    def fake_fetch(plan, _error_id, _tenant):
        if plan.get("view") != "v_ask_pick_log_full":
            return []
        result = rows
        for item in plan.get("filters") or []:
            result = [row for row in result if _matches_filter(row, item)]
        return result

    monkeypatch.setattr(process_check, "load_catalog", lambda: FakeCatalog())
    monkeypatch.setattr(process_check, "load_kpi_rules", lambda *_args, **_kwargs: (rules, {}))

    result = process_check.build_productivity_finance_process_check(
        object(),
        business=SimpleNamespace(id=1, company_codes=["GG"]),
        finance_settings={
            "invoice_rows_by_company": {
                "GG": [
                    {
                        "id": "store_picked_orders",
                        "service": "Outbound",
                        "description": "Plockade orders",
                        "unit": "Per order",
                        "price": 10,
                        "calculation_plan": {
                            "status": "ok",
                            "view": "v_ask_pick_log_full",
                            "view_label": "Plocklogg Full",
                            "output_columns": ["order_num"],
                            "filters": [
                                {"id": "order_num", "operator": "StartsWith", "value": "TO"},
                                {"id": "company", "operator": "EQ", "value": "GG"},
                            ],
                            "calculation": {
                                "metric": "count_distinct",
                                "field": None,
                                "distinct_by": ["order_num"],
                                "group_by": [],
                                "sort_by": None,
                                "limit": None,
                            },
                        },
                    }
                ]
            }
        },
        month=6,
        year=2026,
        company_code="GG",
        fetch_rows=fake_fetch,
        tenant="frey",
    )

    check = result["revenue_checks"][0]
    combo = check["combined_process_coverage"]

    assert check["quantity"] == 4
    assert check["row_count"] == 5
    assert check["comparison_key_columns"] == ["order_num"]
    assert check["comparison_key_count"] == 4
    assert check["missing_in_kpi_count"] == 1
    assert check["process_extra_count"] == 1
    assert combo["key_label"] == "order_num"
    assert combo["revenue_key_count"] == 4
    assert combo["covered_key_count"] == 3
    assert combo["missing_key_count"] == 1
    assert combo["extra_key_count"] == 1
    assert {item["process"] for item in combo["processes"]} == {"Manual Pick", "Bulky Pick", "E Commerce"}
    assert check["missing_in_kpi"][0]["values"]["order_num"] == "TO4"
    assert check["process_extra"][0]["values"]["order_num"] == "XX1"


def test_process_check_reuses_broad_source_for_multiple_revenue_rows(monkeypatch):
    rules = parse_kpi_rule_rows(
        [
            {"process": "GG Plock", "source": "pick", "metric": "rows", "company": "GG", "zone": "A;B", "positive_column": "qty_suf"},
        ]
    )
    rows = [
        {"rowid": "1", "company": "GG", "pick_zone": "A", "qty_suf": 1, "order_num": "TO1", "time_stamp_int": 20260601},
        {"rowid": "2", "company": "GG", "pick_zone": "B", "qty_suf": 1, "order_num": "TO2", "time_stamp_int": 20260601},
    ]
    calls = []

    def fake_fetch(plan, error_id, _tenant):
        calls.append((error_id, plan))
        if plan.get("view") != "v_ask_pick_log_full":
            return []
        result = rows
        for item in plan.get("filters") or []:
            result = [row for row in result if _matches_filter(row, item)]
        return result

    def revenue_row(row_id, zone):
        return {
            "id": row_id,
            "service": "Outbound",
            "description": f"Plock zon {zone}",
            "unit": "Per rad",
            "price": 10,
            "calculation_plan": {
                "status": "ok",
                "view": "v_ask_pick_log_full",
                "view_label": "Plocklogg Full",
                "output_columns": ["rowid"],
                "filters": [
                    {"id": "pick_zone", "operator": "EQ", "value": zone},
                    {"id": "company", "operator": "EQ", "value": "GG"},
                ],
                "calculation": {"metric": "count"},
            },
        }

    monkeypatch.setattr(process_check, "load_catalog", lambda: FakeCatalog())
    monkeypatch.setattr(process_check, "load_kpi_rules", lambda *_args, **_kwargs: (rules, {}))

    result = process_check.build_productivity_finance_process_check(
        object(),
        business=SimpleNamespace(id=1, company_codes=["GG"]),
        finance_settings={"invoice_rows_by_company": {"GG": [revenue_row("zone_a", "A"), revenue_row("zone_b", "B")]}},
        month=6,
        year=2026,
        company_code="GG",
        fetch_rows=fake_fetch,
        tenant="frey",
    )

    assert [check["status"] for check in result["revenue_checks"]] == ["ok", "ok"]
    assert [check["quantity"] for check in result["revenue_checks"]] == [1, 1]
    assert [error_id for error_id, _plan in calls] == ["finance-process-check"]


def test_process_check_explains_partial_receiving_status_gap(monkeypatch):
    rules = parse_kpi_rule_rows(
        [
            {
                "process": "Receiving",
                "source": "receive",
                "metric": "rows",
                "type": "11;12;61;62;71",
                "status": "20;30",
            },
        ]
    )
    rows = [
        {"rowid": "1", "company": "GG", "wareh_num": "404", "type": "61", "status": "20", "time_stamp_int": 20260601},
        {"rowid": "2", "company": "GG", "wareh_num": "404", "type": "61", "status": "0", "time_stamp_int": 20260601},
    ]

    def fake_fetch(plan, _error_id, _tenant):
        if plan.get("view") != "v_ask_receive_log":
            return []
        result = rows
        for item in plan.get("filters") or []:
            result = [row for row in result if _matches_filter(row, item)]
        return result

    monkeypatch.setattr(process_check, "load_catalog", lambda: FakeCatalog())
    monkeypatch.setattr(process_check, "load_kpi_rules", lambda *_args, **_kwargs: (rules, {}))

    result = process_check.build_productivity_finance_process_check(
        object(),
        business=SimpleNamespace(id=1, company_codes=["GG"]),
        finance_settings={
            "invoice_rows_by_company": {
                "GG": [
                    {
                        "id": "receive_labels",
                        "service": "Inbound",
                        "description": "Mottagna etiketter",
                        "unit": "Per etikett",
                        "price": 10,
                        "calculation_plan": {
                            "status": "ok",
                            "view": "v_ask_receive_log",
                            "view_label": "Varumottagningslogg",
                            "filters": [{"id": "company", "operator": "EQ", "value": "GG"}],
                            "calculation": {"metric": "count"},
                        },
                    }
                ]
            }
        },
        month=6,
        year=2026,
        company_code="GG",
        fetch_rows=fake_fetch,
        tenant="frey",
    )

    check = result["revenue_checks"][0]

    assert check["status"] == "warning"
    assert check["missing_in_kpi_count"] == 1
    assert check["matched_processes"][0]["process"] == "Receiving"
    assert "delvis täckt" in check["messages"][0]
    assert check["rule_gaps"] == [
        {
            "count": 1,
            "process": "Receiving",
            "process_key": "RECEIVING",
            "field": "Status",
            "expected": "20/30",
            "actual": "0",
        }
    ]


def test_process_check_reports_source_error_without_false_no_match(monkeypatch):
    rules = parse_kpi_rule_rows(
        [
            {"process": "GG Plock", "source": "pick", "metric": "rows", "company": "GG", "zone": "A", "positive_column": "qty_suf"},
        ]
    )

    def fake_fetch(_plan, _error_id, _tenant):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Extern datakälla kunde inte nås.",
                "error_id": "finance-process-check-revenue",
                "view": "v_ask_pick_log_full",
                "view_label": "Plocklogg Full",
            },
        )

    monkeypatch.setattr(process_check, "load_catalog", lambda: FakeCatalog())
    monkeypatch.setattr(process_check, "load_kpi_rules", lambda *_args, **_kwargs: (rules, {}))

    result = process_check.build_productivity_finance_process_check(
        object(),
        business=SimpleNamespace(id=1, company_codes=["GG"]),
        finance_settings={
            "invoice_rows_by_company": {
                "GG": [
                    {
                        "id": "store_picked_rows",
                        "service": "Outbound",
                        "description": "Plockade rader",
                        "unit": "Per rad",
                        "price": 10,
                        "calculation_plan": {
                            "status": "ok",
                            "view": "v_ask_pick_log_full",
                            "view_label": "Plocklogg Full",
                            "filters": [{"id": "company", "operator": "EQ", "value": "GG"}],
                            "calculation": {"metric": "count"},
                        },
                    }
                ]
            }
        },
        month=6,
        year=2026,
        company_code="GG",
        fetch_rows=fake_fetch,
        tenant="frey",
    )

    check = result["revenue_checks"][0]

    assert check["status"] == "error"
    assert result["summary"]["error_revenue_rows"] == 1
    assert result["sources"][0]["message"] == "Extern datakälla kunde inte nås."
    assert "502:" not in " ".join(check["messages"])
    assert "Ingen tydlig KPI-processmatch hittades." not in check["messages"]


def test_process_check_row_scope_lists_same_view_process_without_overlap(monkeypatch):
    rules = parse_kpi_rule_rows(
        [
            {
                "process": "Receiving",
                "source": "receive",
                "metric": "rows",
                "type": "11;12;61;62;71",
                "status": "20;30",
            },
            {"process": "GG Plock", "source": "pick", "metric": "rows", "company": "GG", "zone": "A"},
        ]
    )
    receive_rows = [
        {"rowid": "1", "company": "GG", "wareh_num": "404", "type": "61", "status": "0", "time_stamp_int": 20260601},
        {"rowid": "2", "company": "GG", "wareh_num": "404", "type": "61", "status": "0", "time_stamp_int": 20260601},
    ]
    pick_rows = [
        {"rowid": "p1", "company": "GG", "pick_zone": "A", "time_stamp_int": 20260601},
    ]
    calls = []

    def fake_fetch(plan, _error_id, _tenant):
        calls.append(plan.get("view"))
        if plan.get("view") == "v_ask_receive_log":
            result = receive_rows
        elif plan.get("view") == "v_ask_pick_log_full":
            result = pick_rows
        else:
            result = []
        for item in plan.get("filters") or []:
            result = [row for row in result if _matches_filter(row, item)]
        return result

    def revenue_row(row_id, view):
        return {
            "id": row_id,
            "service": "Inbound" if view == "v_ask_receive_log" else "Outbound",
            "description": row_id,
            "unit": "Per rad",
            "price": 10,
            "calculation_plan": {
                "status": "ok",
                "view": view,
                "view_label": view,
                "filters": [{"id": "company", "operator": "EQ", "value": "GG"}],
                "calculation": {"metric": "count"},
            },
        }

    monkeypatch.setattr(process_check, "load_catalog", lambda: FakeCatalog())
    monkeypatch.setattr(process_check, "load_kpi_rules", lambda *_args, **_kwargs: (rules, {}))

    result = process_check.build_productivity_finance_process_check(
        object(),
        business=SimpleNamespace(id=1, company_codes=["GG"]),
        finance_settings={
            "invoice_rows_by_company": {
                "GG": [
                    revenue_row("receive_labels", "v_ask_receive_log"),
                    revenue_row("pick_rows", "v_ask_pick_log_full"),
                ]
            }
        },
        month=6,
        year=2026,
        company_code="GG",
        fetch_rows=fake_fetch,
        tenant="frey",
        row_id="receive_labels",
    )

    check = result["revenue_checks"][0]

    assert result["target_row_id"] == "receive_labels"
    assert len(result["revenue_checks"]) == 1
    assert calls == ["v_ask_receive_log"]
    assert check["row_id"] == "receive_labels"
    assert check["status"] == "warning"
    assert check["matched_processes"] == []
    assert len(check["same_view_processes"]) == 1
    process = check["same_view_processes"][0]
    assert process["process"] == "Receiving"
    assert process["process_key"] == "RECEIVING"
    assert process["source"] == "receive"
    assert process["metrics"] == ["rows"]
    assert process["revenue_row_count"] == 2
    assert process["process_row_count"] == 0
    assert process["overlap_count"] == 0
    assert process["missing_from_process_count"] == 2
    assert process["extra_in_process_count"] == 0
    assert process["count_difference"] == -2
    assert "SELECT COUNT(*) AS value FROM v_ask_receive_log" in process["process_sql"]
    assert "status IN ('20', '30')" in process["process_sql"]
