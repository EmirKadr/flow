from __future__ import annotations

import json
from pathlib import Path

import pytest

from warehouse_tools import flows
from warehouse_tools.surface_generation import generate_surface_plan


pd = pytest.importorskip("pandas")

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE_TESTDATA = ROOT / "testdata" / "warehouse_tools"

REGISTRY_FLOW_IDS = (
    "allocate",
    "forecast",
    "ytgenerering",
    "ordersaldo",
    "lyx",
    "pafyllnadsprio",
    "hib-koppling",
    "overview-check",
    "dispatch-check",
    "vecka27-check",
    "prognos-report",
    "observations-update",
    "observations-sync",
    "split-values",
    "update-check",
)

LOCAL_DATA_FLOW_IDS = tuple(
    flow_id
    for flow_id in REGISTRY_FLOW_IDS
    if flow_id not in {"forecast", "ytgenerering", "observations-sync", "update-check"}
)

EXPECTED_SUMMARIES = {
    "allocate": {
        "Resultatrader": 12062,
        "Near-miss": 12,
        "Refill Huvudplock": 298,
        "Refill AutoStore": 7,
        "Pallplatser": 144,
    },
    "dispatch-check": {"Avvikelser": 0},
    "hib-koppling": {"Ändringar": 49, "Missade avgångar": 1},
    "lyx": {"LYX-artiklar": 264, "Filtrerade rader": 5510},
    "observations-update": {"Nya observationer": 24047, "Skickade pallid": 0, "Artikel-max-rader": 3026, "Ändrade maxvärden": 0},
    "ordersaldo": {"Kompletta ordrar": 300, "Artiklar med underskott": 3777},
    "overview-check": {"Sändningsrader": 0, "HIB-rader": 6},
    "pafyllnadsprio": {"Läge": "Lastningsfönster", "Rapportrader": 3777, "Saknad referens": 2951},
    "prognos-report": {"Rapportrader": 238, "Kombinerade rader": 1963, "Partiell": "Nej"},
    "split-values": {"Antal värden": 5, "Antal kolumner": 3, "Per kolumn": 2},
    "vecka27-check": {"Avvikelser": 0},
}

EXPECTED_TABLE_ROWS = {
    "allocate": {
        "result": 12062,
        "near_miss": 12,
        "refill_hp": 298,
        "refill_autostore": 7,
        "pallet_spaces": 144,
    },
    "dispatch-check": {"diff": 0},
    "hib-koppling": {"changes": 49, "missed": 1},
    "lyx": {"articles": 264},
    "observations-update": {"new_rows": 24047},
    "ordersaldo": {"complete": 300, "shortage": 3777},
    "overview-check": {"orderkontroll": 6, "hib_utan_butikssändning": 6},
    "pafyllnadsprio": {"report": 3777, "window_map": 4},
    "prognos-report": {"report": 238, "combined": 1963},
    "split-values": {"report": 2},
    "vecka27-check": {"report": 0},
}

EXPECTED_FIRST_VALUES = {
    "allocate": {
        "result": (0, "33"),
        "near_miss": (0, "2000051"),
        "refill_hp": (0, "1267353"),
        "refill_autostore": (0, "1179324"),
        "pallet_spaces": (0, "133343"),
    },
    "hib-koppling": {"changes": (0, "PR100500372"), "missed": (0, "324042")},
    "lyx": {"articles": (0, "10010")},
    "observations-update": {"new_rows": (0, "10001")},
    "ordersaldo": {"complete": (0, "301331"), "shortage": (0, "1000279")},
    "overview-check": {"orderkontroll": (1, "322882"), "hib_utan_butikssändning": (1, "322882")},
    "pafyllnadsprio": {"report": (0, "1000279"), "window_map": (0, "PRIO 1")},
    "prognos-report": {"report": (0, "2002903"), "combined": (0, "1169944")},
    "split-values": {"report": (0, "A")},
}

LEGACY_FIXTURE_NAMES = {
    "orders": "v_ask_customer_order_details_all-20260317145125.csv",
    "buffer": "v_ask_article_buffertpallet-20260317145136.csv",
    "saldo": "v_ask_item_summary_stock_automation-20260317145351.csv",
    "items": "item_option-20260317145203.csv",
    "overview": "v_ask_order_overview-20260317145114.csv",
    "dispatch": "v_ask_dispatch_pallet-20260316130458.csv",
    "wms_booking": "v_ask_booking_putaway-20260317145232.csv",
}


def _testdata() -> dict[str, Path]:
    missing = [filename for filename in LEGACY_FIXTURE_NAMES.values() if not (WAREHOUSE_TESTDATA / filename).is_file()]
    if missing:
        pytest.skip(f"Lokala warehouse-regressionsfiler saknas: {', '.join(missing[:3])}")
    return {
        "orders": WAREHOUSE_TESTDATA / LEGACY_FIXTURE_NAMES["orders"],
        "buffer": WAREHOUSE_TESTDATA / LEGACY_FIXTURE_NAMES["buffer"],
        "saldo": WAREHOUSE_TESTDATA / LEGACY_FIXTURE_NAMES["saldo"],
        "items": WAREHOUSE_TESTDATA / LEGACY_FIXTURE_NAMES["items"],
        "overview": WAREHOUSE_TESTDATA / LEGACY_FIXTURE_NAMES["overview"],
        "dispatch": WAREHOUSE_TESTDATA / LEGACY_FIXTURE_NAMES["dispatch"],
        "prognos": next(WAREHOUSE_TESTDATA.glob("Prognos idag_*.xlsx")),
        "campaign": next(WAREHOUSE_TESTDATA.glob("Granng*prognos*.xlsx")),
        "wms_booking": WAREHOUSE_TESTDATA / LEGACY_FIXTURE_NAMES["wms_booking"],
    }


def _scenario_payloads() -> dict[str, tuple[dict[str, Path], dict[str, str]]]:
    files = _testdata()
    return {
        "allocate": (
            {
                "orders": files["orders"],
                "buffer": files["buffer"],
                "saldo": files["saldo"],
                "items": files["items"],
            },
            {},
        ),
        "ordersaldo": ({"orders": files["orders"], "saldo": files["saldo"]}, {}),
        "lyx": ({"saldo": files["saldo"]}, {}),
        "pafyllnadsprio": (
            {"orders": files["orders"], "saldo": files["saldo"], "overview": files["overview"]},
            {},
        ),
        "hib-koppling": ({"details": files["orders"], "overview": files["overview"]}, {}),
        "overview-check": ({"overview": files["overview"], "details": files["orders"]}, {}),
        "dispatch-check": (
            {"overview": files["overview"], "dispatch": files["dispatch"], "details": files["orders"]},
            {},
        ),
        "vecka27-check": ({"orders": files["orders"]}, {}),
        "prognos-report": (
            {
                "prognos": files["prognos"],
                "campaign": files["campaign"],
                "saldo": files["saldo"],
                "buffer": files["buffer"],
            },
            {},
        ),
        "observations-update": ({"buffer": files["buffer"]}, {}),
        "split-values": ({}, {"values": "A\nB\nC\nD\nE", "chunk_size": "2"}),
    }


def _first_value(table, column_index: int) -> str:
    return str(table.iloc[0, column_index])


def test_allocate_display_summary_formats_fixed_labels_in_order():
    result_df = pd.DataFrame({
        "K\u00e4lltyp": [
            "HELPALL",
            "AUTOSTORE",
            "AUTOSTORE",
            "HUVUDPLOCK",
            "SKRYMMANDE",
            "EHANDEL",
            "HIB",
        ]
    })
    refill_hp_df = pd.DataFrame({"Artikel": ["A1", "A2"]})
    refill_autostore_df = pd.DataFrame({"Artikel": ["R1"]})

    assert flows.build_allocate_display_summary(result_df, refill_hp_df, refill_autostore_df) == {
        "Helpall": "1 pallar",
        "Autostore": "2 rader",
        "Huvudplock": "1 rader",
        "Skrymmande": "1 rader",
        "E-Handel": "1 rader",
        "HIB": "1 rader",
        "Refill Autostore": "1 rader",
        "Refill Huvudplock": "2 rader",
    }


def test_allocate_flow_ignores_order_rows_above_status_33(tmp_path):
    orders_path = tmp_path / "orders_status.csv"
    buffer_path = tmp_path / "buffer_status.csv"
    pd.DataFrame([
        {"Artikel": "A33", "Antal": 1, "Ordernr": "O33", "Radnr": "1", "Status": 33, "Zon": "A"},
        {"Artikel": "A34", "Antal": 1, "Ordernr": "O34", "Radnr": "1", "Status": 34, "Zon": "A"},
        {"Artikel": "A40", "Antal": 1, "Ordernr": "O40", "Radnr": "1", "Status": 40, "Zon": "A"},
    ]).to_csv(orders_path, index=False, encoding="utf-8-sig")
    pd.DataFrame([
        {"Artikel": "A33", "Antal": 1, "Lagerplats": "H33", "Datum/Tid": "2024-01-01 10:00", "PallID": "P33", "Status": 29},
        {"Artikel": "A34", "Antal": 1, "Lagerplats": "H34", "Datum/Tid": "2024-01-01 10:00", "PallID": "P34", "Status": 29},
        {"Artikel": "A40", "Antal": 1, "Lagerplats": "H40", "Datum/Tid": "2024-01-01 10:00", "PallID": "P40", "Status": 29},
    ]).to_csv(buffer_path, index=False, encoding="utf-8-sig")

    result = flows.FLOW_BY_ID["allocate"]["handler"]({"orders": orders_path, "buffer": buffer_path}, {})
    tables = {key: table for key, _label, table in result["tables"]}

    assert result["summary"]["Resultatrader"] == 1
    assert tables["result"]["Ordernr"].tolist() == ["O33"]
    assert tables["result"]["Artikel"].tolist() == ["A33"]
    assert any("Status > 33" in line for line in result["log"])


def test_read_cache_reuses_same_file_without_shared_dataframe_mutation(tmp_path, monkeypatch):
    source = tmp_path / "orders.csv"
    source.write_text("Artikel;Antal\nA1;2\n", encoding="utf-8")
    calls = []

    def fake_read(path: str):
        calls.append(path)
        return pd.DataFrame({"Artikel": ["A1"], "Antal": [2]})

    flows._read_cached.cache_clear()
    monkeypatch.setattr(flows.E, "_read_cli_table", fake_read)
    try:
        first = flows._read(source)
        first.loc[0, "Artikel"] = "changed"
        second = flows._read(source)
    finally:
        flows._read_cached.cache_clear()

    assert calls == [str(source.resolve())]
    assert second.iloc[0].to_dict() == {"Artikel": "A1", "Antal": 2}


@pytest.mark.filterwarnings(
    "ignore:Workbook contains no default style, apply openpyxl's default:UserWarning:openpyxl.styles.stylesheet"
)
def test_allocate_display_summary_matches_current_local_fixture_data():
    files = {
        "orders": next(iter(sorted(WAREHOUSE_TESTDATA.glob("v_ask_customer_order_details_all-*.csv"))), None),
        "buffer": next(iter(sorted(WAREHOUSE_TESTDATA.glob("v_ask_article_buffertpallet-*.csv"))), None),
        "saldo": next(iter(sorted(WAREHOUSE_TESTDATA.glob("v_ask_item_summary_stock_automation-*.csv"))), None),
        "items": next(iter(sorted(WAREHOUSE_TESTDATA.glob("item_option-*.csv"))), None),
    }
    if any(path is None for path in files.values()):
        pytest.skip("Aktuella warehouse-regressionsfiler saknas.")

    result = flows.FLOW_BY_ID["allocate"]["handler"](files, {})

    assert result["display_summary"] == {
        "Helpall": "401 pallar",
        "Autostore": "4844 rader",
        "Huvudplock": "5025 rader",
        "Skrymmande": "1382 rader",
        "E-Handel": "165 rader",
        "HIB": "245 rader",
        "Refill Autostore": "7 rader",
        "Refill Huvudplock": "298 rader",
    }


def test_pallet_spaces_counts_hib_separately_from_autostore_like_allokera():
    rows = [
        {
            "Kund": "Butik F",
            "Kund.1": "Butik F",
            "Artikel": f"F{i}",
            "Zon (ber\u00e4knad)": "F",
            "Palltyp (matchad)": "EURO",
            "Ej Staplingsbar": "",
        }
        for i in range(21)
    ]

    result = flows.E.compute_pallet_spaces(pd.DataFrame(rows))

    assert result["Kund"].tolist() == ["Butik F"]
    assert result["HIB"].tolist() == [2]
    assert result["autostore"].tolist() == [0]
    assert result["Topp Pallar"].tolist() == [2]
    assert result["Totalt Pallar"].tolist() == [2]
    assert result["Pallplatser"].tolist() == [2]


def test_ordersaldo_shortage_includes_helpall_count_from_article_max(tmp_path):
    orders_path = tmp_path / "orders.csv"
    max_path = tmp_path / "artikel_max.csv"
    pd.DataFrame([
        {"Ordernr": "O1", "Artikel": "A1", "Antal": 10, "Plock": 2},
        {"Ordernr": "O2", "Artikel": "A2", "Antal": 1, "Plock": 1},
    ]).to_csv(orders_path, index=False, encoding="utf-8-sig")
    pd.DataFrame([
        {"artikelnummer": "A1", "max": 42.0, "pallid": "P1"},
        {"artikelnummer": "A2", "max": 12.0, "pallid": "P2"},
    ]).to_csv(max_path, index=False, encoding="utf-8-sig")

    result = flows.FLOW_BY_ID["ordersaldo"]["handler"](
        {"orders": orders_path, "max_csv": max_path},
        {},
    )
    tables = {key: table for key, _label, table in result["tables"]}
    shortage = tables["shortage"]

    assert list(shortage.columns) == [
        "Artikel",
        "Total beställt",
        "Tillgängligt saldo (Plock)",
        "Antal på Helpall",
        "Utbeställt",
        "Underskott",
    ]
    assert shortage.iloc[0].to_dict() == {
        "Artikel": "A1",
        "Total beställt": 10.0,
        "Tillgängligt saldo (Plock)": 2.0,
        "Antal på Helpall": 42.0,
        "Utbeställt": 0.0,
        "Underskott": 8.0,
    }


def test_warehouse_tool_testdata_is_local_to_flow():
    if not WAREHOUSE_TESTDATA.is_dir():
        pytest.skip("Lokala warehouse-regressionsfiler saknas.")
    assert WAREHOUSE_TESTDATA.is_dir()
    assert any(WAREHOUSE_TESTDATA.glob("v_ask_pick_log_full-*.csv"))
    assert ROOT.name == "flow"


def test_warehouse_registry_is_loaded_from_flow_package():
    assert tuple(flows.FLOW_BY_ID) == REGISTRY_FLOW_IDS
    assert len(flows.public_pool()) == 10
    public_registry = flows.public_registry()
    assert [flow["id"] for flow in public_registry] == list(REGISTRY_FLOW_IDS)
    assert all("handler" not in flow for flow in public_registry)
    forecast = next(flow for flow in public_registry if flow["id"] == "forecast")
    assert {entry["key"] for entry in forecast["coredata"]} == {
        "custom",
        "item",
        "item_alias",
        "dimension",
        "pallet_type",
        "item_option",
    }
    ytgenerering = next(flow for flow in public_registry if flow["id"] == "ytgenerering")
    assert ytgenerering["requiresSessionFlow"]["flowId"] == "forecast"
    assert ytgenerering["coredata"] == [{"key": "location", "label": "Lagerplatser", "required": True}]
    ordersaldo = next(flow for flow in public_registry if flow["id"] == "ordersaldo")
    assert any(input_def["key"] == "max_csv" for input_def in ordersaldo["inputs"])


def test_ytgenerering_filters_locations_and_groups_transporters():
    forecast = pd.DataFrame(
        [
            {"Sändningsnr": "S1", "Transportör": "Akeri A", "Predikterade pallplatser": 2.5},
            {"Sändningsnr": "S2", "Transportör": "Akeri A", "Predikterade pallplatser": 1.0},
            {"Sändningsnr": "S3", "Transportör": "Akeri B", "Predikterade pallplatser": 2.0},
        ]
    )
    locations = pd.DataFrame(
        [
            {"Lagerplats": "UTL1", "Typ": "U", "Max pall": 10},
            {"Lagerplats": "UTL100", "Typ": "U", "Max pall": 1},
            {"Lagerplats": "UTL101", "Typ": "U", "Max pall": 2},
            {"Lagerplats": "UTL102", "Typ": "U", "Max pall": 1},
            {"Lagerplats": "UTL103", "Typ": "U", "Max pall": 2},
            {"Lagerplats": "UTL104", "Typ": "H", "Max pall": 2},
            {"Lagerplats": "UTL105", "Typ": "U", "Max pall": 0},
        ]
    )

    result = generate_surface_plan(forecast, locations)

    assert result.summary["ej_placerade_pallplatser"] == 0
    assert list(result.assignments["Lagerplats"]) == ["UTL100", "UTL101", "UTL102", "UTL103"]
    assert list(result.assignments["Transportör"]) == ["Akeri A", "Akeri A", "Akeri A", "Akeri B"]
    assert result.assignments["Lagerplats"].is_unique
    assert list(result.assignments["Placerade pallplatser"]) == [1.0, 1.5, 1.0, 2.0]


def test_forecast_flow_returns_table_and_json_artifact(monkeypatch, tmp_path):
    from warehouse_tools.mg_forecast import forecast as mg_forecast

    required = {
        key: tmp_path / f"{key}.csv"
        for key in (
            "orders",
            "overview",
            "buffer",
            "custom",
            "item",
            "item_alias",
            "dimension",
            "pallet_type",
            "item_option",
        )
    }
    for path in required.values():
        path.write_text("x\n", encoding="utf-8")

    captured = {}

    def fake_stage_support_files(file_map, staging_root):
        captured["file_map"] = dict(file_map)
        return Path(staging_root) / "Fore"

    def fake_run_forecast(orders_path, *, data_fore):
        captured["orders_path"] = orders_path
        captured["data_fore"] = data_fore
        return (
            pd.DataFrame(
                [
                    {
                        "Sändningsnr": "S-1",
                        "Transportör": "Akeri A",
                        "Predikterade pallplatser": 2.5,
                    }
                ]
            ),
            {
                "antal_grupper": 1,
                "summa_pallplatser": 2.5,
                "medel_pallplatser": 2.5,
                "max_pallplatser": 2.5,
            },
        )

    monkeypatch.setattr(mg_forecast, "stage_support_files", fake_stage_support_files)
    monkeypatch.setattr(mg_forecast, "run_forecast", fake_run_forecast)

    result = flows.FLOW_BY_ID["forecast"]["handler"](required, {})

    assert result["summary"] == {
        "Sändningar": 1,
        "Predikterade pallplatser": 2.5,
        "Medel pallplatser": 2.5,
        "Max pallplatser": 2.5,
    }
    assert result["tables"][0][0:2] == ("forecast", "Forecast")
    assert result["artifacts"]["forecast_json"]["rows"][0]["Sändningsnr"] == "S-1"
    assert captured["file_map"]["buffert"] == required["buffer"]
    assert captured["orders_path"] == required["orders"]


def test_forecast_stage_support_files_uses_canonical_names(tmp_path):
    from warehouse_tools.mg_forecast import forecast as mg_forecast

    file_map = {}
    for file_type in mg_forecast.SUPPORT_FILE_TYPES:
        source = tmp_path / f"flow_mg_{file_type}_temp.csv"
        source.write_text("x\n", encoding="utf-8")
        file_map[file_type] = source

    fore_dir = mg_forecast.stage_support_files(file_map, tmp_path / "stage")

    assert (fore_dir / "v_ask_order_overview-flow.csv").is_file()
    assert (fore_dir / "v_ask_article_buffertpallet-flow.csv").is_file()
    assert (fore_dir / "custom-flow.csv").is_file()
    assert (fore_dir / "item-flow.csv").is_file()
    assert (fore_dir / "item_alias-flow.csv").is_file()
    assert (fore_dir / "dimension-flow.csv").is_file()
    assert (fore_dir / "pallet_type-flow.csv").is_file()
    assert (fore_dir / "item_option-flow.csv").is_file()


def test_ytgenerering_flow_consumes_forecast_json_and_location_coredata(monkeypatch, tmp_path):
    forecast_payload = {
        "columns": ["Sändningsnr", "Transportör", "Predikterade pallplatser"],
        "rows": [
            {"Sändningsnr": "S-1", "Transportör": "Akeri A", "Predikterade pallplatser": 1.5},
        ],
    }
    location_path = tmp_path / "location.csv"
    location_path.write_text("not used\n", encoding="utf-8")
    monkeypatch.setattr(
        flows,
        "_read",
        lambda path: pd.DataFrame(
            [
                {"Lagerplats": "UTL100", "Typ": "U", "Max pall": 1},
                {"Lagerplats": "UTL101", "Typ": "U", "Max pall": 1},
            ]
        ),
    )

    result = flows.FLOW_BY_ID["ytgenerering"]["handler"](
        {"location": location_path},
        {"__forecast_json": json.dumps(forecast_payload, ensure_ascii=False)},
    )

    tables = {key: table for key, _label, table in result["tables"]}
    assert result["summary"]["Sändningar"] == 1
    assert result["summary"]["Ej placerade pallplatser"] == 0
    assert list(tables["ytgenerering"]["Lagerplats"]) == ["UTL100", "UTL101"]
    assert list(tables["ytgenerering"]["Placerade pallplatser"]) == [1.0, 0.5]


def test_ytgenerering_flow_consumes_forecast_dataframe_fast_path(monkeypatch, tmp_path):
    forecast_df = pd.DataFrame(
        [
            {"Sändningsnr": "S-1", "Transportör": "Akeri A", "Predikterade pallplatser": 1.5},
        ]
    )
    location_path = tmp_path / "location.csv"
    location_path.write_text("not used\n", encoding="utf-8")
    monkeypatch.setattr(
        flows,
        "_read",
        lambda path: pd.DataFrame(
            [
                {"Lagerplats": "UTL100", "Typ": "U", "Max pall": 1},
                {"Lagerplats": "UTL101", "Typ": "U", "Max pall": 1},
            ]
        ),
    )

    result = flows.FLOW_BY_ID["ytgenerering"]["handler"](
        {"location": location_path},
        {"__forecast_df": forecast_df},
    )

    tables = {key: table for key, _label, table in result["tables"]}
    assert result["summary"]["Ej placerade pallplatser"] == 0
    assert list(tables["ytgenerering"]["Lagerplats"]) == ["UTL100", "UTL101"]


@pytest.mark.filterwarnings(
    "ignore:Workbook contains no default style, apply openpyxl's default:UserWarning:openpyxl.styles.stylesheet"
)
def test_overview_check_preserves_avvikelse_type_column_for_allokera_parity():
    overview = next(iter(sorted(WAREHOUSE_TESTDATA.glob("v_ask_order_overview-*.csv"))), None)
    details = next(iter(sorted(WAREHOUSE_TESTDATA.glob("v_ask_customer_order_details_all-*.csv"))), None)
    if overview is None or details is None:
        pytest.skip("Aktuella orderoversiktsfiler saknas.")

    result = flows.FLOW_BY_ID["overview-check"]["handler"](
        {"overview": overview, "details": details},
        {},
    )
    tables = {key: table for key, _label, table in result["tables"]}
    expected_columns = [
        "Avvikelsetyp",
        "Ordernr",
        "S\u00e4ndningsnr",
        "Ordertyp",
        "Status",
        "Anm\u00e4rkning",
        "Kundnamn",
    ]

    for key in ("orderkontroll", "hib_utan_butikss\u00e4ndning"):
        assert list(tables[key].columns) == expected_columns

    assert set(tables["hib_utan_butikss\u00e4ndning"]["Avvikelsetyp"].astype(str)) == {
        "HIB \u00f6ver status 31 utan butikss\u00e4ndning"
    }


@pytest.mark.filterwarnings(
    "ignore:Workbook contains no default style, apply openpyxl's default:UserWarning:openpyxl.styles.stylesheet"
)
@pytest.mark.parametrize("flow_id", LOCAL_DATA_FLOW_IDS)
def test_warehouse_flows_run_against_local_fixture_data(flow_id: str):
    files, params = _scenario_payloads()[flow_id]

    result = flows.FLOW_BY_ID[flow_id]["handler"](dict(files), dict(params))
    tables = {key: table for key, _label, table in result.get("tables", [])}
    labels = {key: label for key, label, _table in result.get("tables", [])}

    assert result.get("summary") == EXPECTED_SUMMARIES[flow_id]
    assert {key: len(table) for key, table in tables.items()} == EXPECTED_TABLE_ROWS[flow_id]
    if flow_id == "allocate":
        assert labels["result"] == "Allokerade pallar"

    for table_key, (column_index, expected_prefix) in EXPECTED_FIRST_VALUES.get(flow_id, {}).items():
        assert _first_value(tables[table_key], column_index).startswith(expected_prefix)


def test_source_has_no_technical_dependency_on_old_allocation_project():
    forbidden = [
        "projects/" + "allokering",
        "projects\\" + "allokering",
        "EmirKadr/" + "allokering",
        "ALLOKERING" + "_ROOT",
        str(Path("C:/Users/emikad/OneDrive - Dole Nordic AB/Skrivbordet/projects") / "allokering"),
        "Mestergruppen " + "Prelimin" + "\u00e4r" + "bokning",
    ]
    scanned_suffixes = {
        ".bat",
        ".css",
        ".html",
        ".ini",
        ".iss",
        ".js",
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".spec",
        ".txt",
        ".yaml",
        ".yml",
    }
    skipped_dirs = {".git", ".pytest_cache", "artifacts", "build", "dist", "release", "tmp_screenshots"}
    offenders: list[str] = []

    for path in ROOT.rglob("*"):
        if any(part in skipped_dirs for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in scanned_suffixes:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)}: {needle}")

    assert offenders == []
