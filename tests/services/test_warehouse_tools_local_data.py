from __future__ import annotations

import json
from pathlib import Path

import pytest

from warehouse_tools import flows
from warehouse_tools.carrier_clusters import read_carrier_clusters
from warehouse_tools.surface_generation import generate_surface_plan, prepare_locations
from warehouse_tools.ytgenerering_map import normalize_map_location_rows


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
    "goods-declaration",
    "vecka27-check",
    "prognos-report",
    "observations-update",
    "observations-sync",
    "split-values",
    "update-check",
)
PUBLIC_REGISTRY_FLOW_IDS = tuple(flow_id for flow_id in REGISTRY_FLOW_IDS if flow_id != "forecast")

LOCAL_DATA_FLOW_IDS = tuple(
    flow_id
    for flow_id in REGISTRY_FLOW_IDS
    if flow_id not in {"forecast", "ytgenerering", "goods-declaration", "observations-sync", "update-check"}
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


def test_goods_declaration_uses_order_overview_alt_address_for_lq_gotland(tmp_path):
    orders_path = tmp_path / "orders.csv"
    overview_path = tmp_path / "overview.csv"
    custom_adr_path = tmp_path / "custom_adr.csv"
    security_path = tmp_path / "item_security_info.csv"

    pd.DataFrame(
        [
            {"Order nr": "O-DG", "Rad": "1", "Kund": "10", "Kund.1": "DG kund", "Artikel": "A-DG", "Artikel.1": "DG vara", "Bolag": "GG", "Kund Adr": "99"},
            {"Order nr": "O-LQ-GOT", "Rad": "1", "Kund": "20", "Kund.1": "Gotland kund", "Artikel": "A-LQ", "Artikel.1": "LQ vara", "Bolag": "GG", "Kund Adr": "99"},
            {"Order nr": "O-LQ-NOT", "Rad": "1", "Kund": "30", "Kund.1": "Fastland kund", "Artikel": "A-LQ", "Artikel.1": "LQ vara", "Bolag": "GG", "Kund Adr": "99"},
            {"Order nr": "O-LQ-ZERO", "Rad": "1", "Kund": "40", "Kund.1": "Saknar alt", "Artikel": "A-LQ", "Artikel.1": "LQ vara", "Bolag": "GG", "Kund Adr": "99"},
            {"Order nr": "O-OK", "Rad": "1", "Kund": "50", "Kund.1": "Vanlig kund", "Artikel": "A-OK", "Artikel.1": "Vanlig vara", "Bolag": "GG", "Kund Adr": "5"},
        ]
    ).to_csv(orders_path, sep="\t", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {"Ordernr": "O-DG", "Kund nr": "10", "Alt adress": "1"},
            {"Ordernr": "O-LQ-GOT", "Kund nr": "20", "Alt adress": "5"},
            {"Ordernr": "O-LQ-NOT", "Kund nr": "30", "Alt adress": "7"},
            {"Ordernr": "O-LQ-ZERO", "Kund nr": "40", "Alt adress": "0"},
            {"Ordernr": "O-OK", "Kund nr": "50", "Alt adress": "5"},
        ]
    ).to_csv(overview_path, sep="\t", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {"Kund": "10", "Adr num": "1", "Post nr": "111 11", "Adress 1": "DG-gatan"},
            {"Kund": "20", "Adr num": "5", "Post nr": "620 12", "Adress 1": "Gotlandsgatan"},
            {"Kund": "30", "Adr num": "7", "Post nr": "111 22", "Adress 1": "Fastlandsgatan"},
            {"Kund": "20", "Adr num": "99", "Post nr": "111 33", "Adress 1": "Fel detaljadress"},
        ]
    ).to_csv(custom_adr_path, sep="\t", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {"Artikel": "A-DG", "Bolag": "GG", "Farligt gods niv\u00e5": "DG"},
            {"Artikel": "A-LQ", "Bolag": "GG", "Farligt gods niv\u00e5": "LQ"},
            {"Artikel": "A-OK", "Bolag": "GG", "Farligt gods niv\u00e5": ""},
        ]
    ).to_csv(security_path, sep="\t", index=False, encoding="utf-8-sig")

    result = flows.FLOW_BY_ID["goods-declaration"]["handler"](
        {
            "orders": orders_path,
            "overview": overview_path,
            "custom_adr": custom_adr_path,
            "item_security_info": security_path,
        },
        {},
    )
    tables = {key: table for key, _label, table in result["tables"]}

    assert result["summary"] == {
        "DG-rader": 1,
        "LQ-rader": 3,
        "LQ sj\u00f6/hav": 1,
        "Klara ordernummer": 2,
        "Ej klara LQ": 2,
    }
    assert tables["clear_orders"]["Ordernr"].tolist() == ["O-DG", "O-LQ-GOT"]
    assert tables["clear_lines"]["Ordernr"].tolist() == ["O-DG", "O-LQ-GOT"]
    assert tables["clear_lines"].loc[tables["clear_lines"]["Ordernr"].eq("O-LQ-GOT"), "Post nr"].iloc[0] == "620 12"
    assert tables["review_lq"]["Ordernr"].tolist() == ["O-LQ-NOT", "O-LQ-ZERO"]
    assert tables["gotland_postcodes"]["Postnummer"].tolist() == [
        "620 00-620 99",
        "621 00-621 99",
        "622 00-622 99",
        "623 00-623 99",
        "624 00-624 99",
    ]


def test_allocate_flow_reuses_cached_outputs_for_same_file_versions(monkeypatch, tmp_path):
    flows.clear_allocation_cache()
    orders_path = tmp_path / "orders.csv"
    buffer_path = tmp_path / "buffer.csv"
    orders_path.write_text("orders-v1\n", encoding="utf-8")
    buffer_path.write_text("buffer-v1\n", encoding="utf-8")
    calls = {"allocate": 0}

    monkeypatch.setattr(flows, "_read", lambda path: pd.DataFrame({"source": [Path(path).name]}))

    def fake_allocate(_orders, _buffer, log=None):
        calls["allocate"] += 1
        if log:
            log(f"allocate {calls['allocate']}")
        return pd.DataFrame({"Artikel": ["A1"], "Källtyp": ["HELPALL"]}), pd.DataFrame()

    monkeypatch.setattr(flows.E, "allocate", fake_allocate)
    monkeypatch.setattr(flows.E.App, "_reclassify_skrymmande", lambda result, _saldo: result)
    monkeypatch.setattr(flows.E, "_merge_item_flags", lambda result, _items: result)
    monkeypatch.setattr(
        flows.E,
        "calculate_refill",
        lambda _result, _buffer, saldo_df=None, not_putaway_df=None: (pd.DataFrame(), pd.DataFrame()),
    )
    monkeypatch.setattr(flows.E, "compute_pallet_spaces", lambda _result: pd.DataFrame())

    flows.FLOW_BY_ID["allocate"]["handler"]({"orders": orders_path, "buffer": buffer_path}, {})
    second = flows.FLOW_BY_ID["allocate"]["handler"]({"orders": orders_path, "buffer": buffer_path}, {})

    orders_path.write_text("orders-version-2\n", encoding="utf-8")
    flows.FLOW_BY_ID["allocate"]["handler"]({"orders": orders_path, "buffer": buffer_path}, {})

    assert calls["allocate"] == 2
    assert second["log"] == ["allocate 1"]
    flows.clear_allocation_cache()


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
    assert len(flows.public_pool()) == 11
    public_registry = flows.public_registry()
    assert [flow["id"] for flow in public_registry] == list(PUBLIC_REGISTRY_FLOW_IDS)
    assert all("handler" not in flow for flow in public_registry)
    assert flows.FLOW_BY_ID["forecast"]["hidden"] is True
    ytgenerering = next(flow for flow in public_registry if flow["id"] == "ytgenerering")
    assert [input_def["key"] for input_def in ytgenerering["inputs"]] == ["orders", "overview", "buffer"]
    assert "requiresSessionFlow" not in ytgenerering
    assert {entry["key"] for entry in ytgenerering["coredata"]} == {
        "custom",
        "item",
        "item_alias",
        "dimension",
        "pallet_type",
        "item_option",
        "trans_agency",
        "location",
    }
    assert next(entry for entry in ytgenerering["coredata"] if entry["key"] == "location")["required"] is False
    ordersaldo = next(flow for flow in public_registry if flow["id"] == "ordersaldo")
    assert any(input_def["key"] == "max_csv" for input_def in ordersaldo["inputs"])
    pafyllnadsprio = next(flow for flow in public_registry if flow["id"] == "pafyllnadsprio")
    pafyllnadsprio_inputs = {input_def["key"]: input_def for input_def in pafyllnadsprio["inputs"]}
    assert [key for key, item in pafyllnadsprio_inputs.items() if item.get("required")] == [
        "orders",
        "saldo",
        "overview",
    ]
    goods_declaration = next(flow for flow in public_registry if flow["id"] == "goods-declaration")
    assert [input_def["key"] for input_def in goods_declaration["inputs"]] == ["orders", "overview", "custom_adr"]
    assert goods_declaration["coredata"] == [
        {"key": "item_security_info", "label": "Artikel S\u00e4kerhetsinformation", "required": True}
    ]


def test_ytgenerering_combined_returns_forecast_only_when_location_missing(monkeypatch):
    forecast_df = pd.DataFrame(
        [
            {"Sändningsnr": "S-1", "Transportör": "Akeri A", "Predikterade pallplatser": 1.5},
        ]
    )

    def fake_flow_forecast(files, params):
        return {
            "summary": {"Sändningar": 1, "Predikterade pallplatser": 1.5},
            "tables": [("forecast", "Forecast", forecast_df)],
            "artifacts": {},
            "carrier_clusters": None,
            "log": ["Forecast körd."],
        }

    monkeypatch.setattr(flows, "flow_forecast", fake_flow_forecast)

    result = flows.FLOW_BY_ID["ytgenerering"]["handler"](
        {"orders": Path("orders.csv"), "overview": Path("overview.csv"), "buffer": Path("buffer.csv")},
        {},
    )

    assert [key for key, _label, _table in result["tables"]] == ["forecast"]
    assert result["maps"] == []
    assert result["download_files"] == {}
    assert result["auto_downloads"] == []
    assert any("Location/lagerplatser saknas" in line for line in result["log"])


def test_ytgenerering_combined_runs_forecast_and_surface_generation(monkeypatch, tmp_path):
    forecast_df = pd.DataFrame(
        [
            {
                "Sändningsnr": "S-1",
                "Transportör": "Akeri A",
                "Predikterade pallplatser": 1.0,
                "Ordernummer": "O-1",
            },
        ]
    )

    def fake_flow_forecast(files, params):
        return {
            "summary": {"Sändningar": 1, "Predikterade pallplatser": 1.0},
            "tables": [("forecast", "Forecast", forecast_df)],
            "artifacts": {"carrier_clusters": {"rows": []}},
            "carrier_clusters": {"rows": []},
            "log": ["Forecast körd."],
        }

    location_path = tmp_path / "location.csv"
    location_path.write_text("not used\n", encoding="utf-8")
    monkeypatch.setattr(flows, "flow_forecast", fake_flow_forecast)
    monkeypatch.setattr(
        flows,
        "_read",
        lambda path: pd.DataFrame(
            [
                {"Lagerplats": "UTL100", "Typ": "U", "Max pall": 2},
            ]
        ),
    )

    result = flows.FLOW_BY_ID["ytgenerering"]["handler"](
        {"orders": Path("orders.csv"), "overview": Path("overview.csv"), "buffer": Path("buffer.csv"), "location": location_path},
        {},
    )

    tables = {key: table for key, _label, table in result["tables"]}
    assert {"forecast", "ytgenerering", "transportorer"}.issubset(tables)
    assert list(tables["ytgenerering"]["Lagerplats"]) == ["UTL100"]
    assert result["maps"]
    assert result["carrier_clusters"] == {"rows": []}
    assert any("Forecast körd." == line for line in result["log"])


def test_ytgenerering_places_shipments_separately_and_sorts_by_carrier():
    forecast = pd.DataFrame(
        [
            {"Sändningsnr": "S1", "Transportör": "Akeri A", "Predikterade pallplatser": 2.5},
            {"Sändningsnr": "S2", "Transportör": "Akeri A", "Predikterade pallplatser": 1.0},
            {"Sändningsnr": "S3", "Transportör": "Akeri B", "Predikterade pallplatser": 2.0},
        ]
    )
    locations = pd.DataFrame(
        [
            {"Lagerplats": "UTL999", "Typ": "U", "Max pall": 10},
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


def test_prepare_locations_accepts_zero_padded_short_utl_codes():
    locations = pd.DataFrame(
        [
            {"Lagerplats": "UTL01", "Typ": "U", "Max pall": 1},
            {"Lagerplats": "UTL99", "Typ": "U", "Max pall": 2},
            {"Lagerplats": "UTL100", "Typ": "U", "Max pall": 3},
            {"Lagerplats": "UTL0", "Typ": "U", "Max pall": 1},
            {"Lagerplats": "UTL653", "Typ": "U", "Max pall": 1},
            {"Lagerplats": "UTL02", "Typ": "H", "Max pall": 1},
            {"Lagerplats": "UTL03", "Typ": "U", "Max pall": 0},
        ]
    )

    prepared = prepare_locations(locations)

    assert list(prepared["Lagerplats"]) == ["UTL01", "UTL99", "UTL100"]
    assert list(prepared["_location_number"]) == [1, 99, 100]


def test_ytgenerering_places_shipments_by_transport_cluster_ranges():
    forecast = pd.DataFrame(
        [
            {"Sändningsnr": "F-1", "Transportör": "Freja Stockholm", "Predikterade pallplatser": 1.0},
            {"Sändningsnr": "S-1", "Transportör": "Schenker", "Predikterade pallplatser": 1.0},
        ]
    )
    locations = pd.DataFrame(
        [
            {"Lagerplats": "UTL205", "Typ": "U", "Max pall": 1},
            {"Lagerplats": "UTL206", "Typ": "U", "Max pall": 1},
            {"Lagerplats": "UTL600", "Typ": "U", "Max pall": 1},
            {"Lagerplats": "UTL601", "Typ": "U", "Max pall": 1},
        ]
    )
    clusters = {
        "rows": [
            {"alias": "Schenker", "clusterGroup": "Schenker", "assignmentOrder": 0, "startSeq": 205, "endSeq": 356},
            {"alias": "Freja Stockholm", "clusterGroup": "Freja", "assignmentOrder": 9, "startSeq": 600, "endSeq": 652},
        ]
    }

    result = generate_surface_plan(forecast, locations, carrier_clusters=clusters)

    placement_by_shipment = dict(zip(result.assignments["Sändningsnr"], result.assignments["Lagerplats"]))
    assert placement_by_shipment == {"S-1": "UTL205", "F-1": "UTL600"}
    assert dict(zip(result.assignments["Sändningsnr"], result.assignments["Kluster"])) == {
        "S-1": "Schenker",
        "F-1": "Freja",
    }


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
            "trans_agency",
        )
    }
    for path in required.values():
        path.write_text("x\n", encoding="utf-8")
    required["trans_agency"].write_text(
        "agency_num,agency_desc,agency_alias,cluster_group,assignment_order,start_seq,end_seq\n"
        "79,Schenker - 11:00 - Parti,Schenker,Schenker,0,205,356\n",
        encoding="utf-8",
    )

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
    assert result["tables"][0][2].iloc[0]["Sändningsnr"] == "S-1"
    assert "forecast_json" not in result.get("artifacts", {})
    assert result["artifacts"]["carrier_clusters"]["rows"][0]["clusterGroup"] == "Schenker"
    assert result["carrier_clusters"]["source"]["name"] == "trans_agency.csv"
    assert captured["file_map"]["buffert"] == required["buffer"]
    assert captured["orders_path"] == required["orders"]


def test_trans_agency_defaults_fill_known_carriers(tmp_path):
    trans_agency = tmp_path / "trans_agency.csv"
    trans_agency.write_text(
        "agency_num,agency_desc,agency_alias,cluster_group,assignment_order,start_seq,end_seq\n"
        "39,,,,,,\n"
        "40,,,,,,\n"
        "41,,,,,,\n",
        encoding="utf-8",
    )

    rows = read_carrier_clusters(trans_agency)["rows"]
    by_num = {row["carrierNum"]: row for row in rows}

    assert by_num["39"]["clusterGroup"] == "Freja"
    assert by_num["39"]["assignmentOrder"] == 10
    assert by_num["39"]["startSeq"] == 600
    assert by_num["39"]["endSeq"] == 652
    assert by_num["39"]["color"] == "#c4b5fd"
    assert by_num["40"]["clusterGroup"] == "Freja"
    assert by_num["41"]["clusterGroup"] == ""
    assert by_num["41"]["assignmentOrder"] == 6
    assert by_num["41"]["startSeq"] == 356
    assert by_num["41"]["endSeq"] == 205


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


def test_forecast_has_packaged_calibration_artifact():
    from warehouse_tools.mg_forecast import predict

    assert predict._CALIBRATION_PATH.is_file()
    assert predict._CALIBRATION["feature_cols"]


def test_forecast_prediction_uses_boosters_without_sklearn_get_params(monkeypatch):
    from warehouse_tools.mg_forecast import predict

    def broken_wrapper(*_args, **_kwargs):
        raise AttributeError("'super' object has no attribute 'get_params'")

    calibration = predict._CALIBRATION
    monkeypatch.setattr(calibration["lgb"], "predict", broken_wrapper)
    monkeypatch.setattr(calibration["lgb"], "get_params", broken_wrapper)
    monkeypatch.setattr(calibration["xgb"], "predict", broken_wrapper)
    monkeypatch.setattr(calibration["xgb"], "get_params", broken_wrapper)

    row = {column: 0 for column in calibration["feature_cols"]}
    row.update(
        {
            "sum_vikt_brutto": 0,
            "sum_bestallt": 1,
            "n_rader": 1,
            "n_artiklar": 1,
            "order_vikt_huvud": 0,
            "order_antal_huvud": 0,
            "n_multi_huvud": 0,
            "n_ordrar": 1,
            "kund_max_hojd": 280,
            "n_skrymmande_rader": 0,
            "n_zoner": 1,
            "pall_estimate": 1.0,
            "sum_bestallt_robot": 0,
            "n_robot_rader": 0,
            "transportor": "Schenker",
            "orderdatum": pd.Timestamp("2026-06-01"),
        }
    )

    result = predict.predict(pd.DataFrame([row]))

    assert len(result) == 1
    assert result.iloc[0] >= 0


def test_forecast_inference_uses_default_transportor_when_overview_value_missing(monkeypatch, tmp_path):
    from warehouse_tools.mg_forecast import forecast as mg_forecast

    orders_path = tmp_path / "orders.csv"
    pd.DataFrame(
        [
            {
                "Bolag": "MG",
                "Kund": "50000",
                "Order nr": "O1",
                "Artikel": "A1",
                "Best\u00e4llt": "12",
                "Orderdatum": "2026-05-26",
                "Robot": "",
                "Zon": "A",
                "Pack klass": "K",
                "Status": "30",
                "\u00c4r plockad": "0",
            }
        ]
    ).to_csv(orders_path, index=False, sep="\t", encoding="utf-8-sig")

    monkeypatch.setattr(
        mg_forecast,
        "load_order_overview",
        lambda: pd.DataFrame(
            [
                {
                    "Ordernr": "O1",
                    "order_transportor": pd.NA,
                    "order_sandningsnr": "S1",
                    "order_typ": "",
                    "order_multi": False,
                    "order_multi_size": 1.0,
                    "order_volym_huvud": 0.0,
                    "order_vikt_huvud": 0.0,
                    "order_antal_huvud": 0.0,
                    "order_rader_huvud": 1.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        mg_forecast,
        "load_customers",
        lambda: pd.DataFrame(
            [
                {
                    "Kund": "50000",
                    "kund_max_hojd": 280.0,
                    "kund_postnr_prefix2": 0.0,
                    "kund_postnr_prefix3": 0.0,
                    "kund_postnr_missing": 1.0,
                    "kund_is_foreign": 0.0,
                    "kund_standard_transportornr": 0.0,
                    "kund_has_standard_transportor": 0.0,
                    "kund_requires_lift": 0.0,
                    "kund_special_delivery_text": 0.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        mg_forecast,
        "load_items",
        lambda: pd.DataFrame(
            [
                {
                    "Artikel": "A1",
                    "per_pall": 12.0,
                    "vikt_brutto": 1.0,
                    "volym": 1.0,
                    "item_palltyp": "E",
                    "item_robot": False,
                    "item_staplingsbar": True,
                    "item_pack_klass": "",
                    "item_pall_flakmeter": 0.0,
                    "item_pall_langd": 120.0,
                    "item_pall_bredd": 80.0,
                    "item_pall_hojd": 120.0,
                    "item_pall_langgods": False,
                    "item_pall_extra_lang": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        mg_forecast,
        "load_item_dimensions",
        lambda: pd.DataFrame([{"Artikel": "A1", "art_langd": 120.0, "art_bredd": 80.0, "art_hojd": 120.0}]),
    )
    monkeypatch.setattr(
        mg_forecast,
        "load_item_options",
        lambda: pd.DataFrame(
            [
                {
                    "Artikel": "A1",
                    "opt_ej_staplingsbar": False,
                    "opt_helpalls_avvikelse_pct": 0.0,
                    "opt_plockzon": "",
                    "opt_robot": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        mg_forecast,
        "load_buffert_pallets",
        lambda: pd.DataFrame([{"Artikel": "A1", "buffert_n_pallar": 1.0, "buffert_total_antal": 12.0}]),
    )

    features = mg_forecast.build_inference_features(
        orders_path,
        default_transportor="Schenker",
        data_fore=tmp_path,
    )

    assert features["transportor"].tolist() == ["Schenker"]
    assert features["transportor_result"].tolist() == ["Okänd"]
    assert features["grupp"].tolist() == ["S1"]

    monkeypatch.setattr(
        mg_forecast,
        "_predict",
        lambda forecast_features: pd.Series([1.5], index=forecast_features.index),
    )

    out, summary = mg_forecast.run_forecast(
        orders_path,
        default_transportor="Schenker",
        data_fore=tmp_path,
    )

    assert summary["antal_grupper"] == 1
    assert out["Transportör"].tolist() == ["Okänd"]
    assert "Kundnamn" in out.columns


def test_forecast_inference_ignores_overview_status_11_orders(monkeypatch, tmp_path):
    from warehouse_tools.mg_forecast import forecast as mg_forecast

    fore_dir = tmp_path / "Fore"
    fore_dir.mkdir()
    orders_path = tmp_path / "orders.csv"
    pd.DataFrame(
        [
            {
                "Bolag": "MG",
                "Kund": "50000",
                "Order nr": "O-OK",
                "Artikel": "A1",
                "Beställt": "12",
                "Orderdatum": "2026-05-26",
                "Robot": "",
                "Zon": "A",
                "Pack klass": "K",
                "Status": "30",
                "Är plockad": "0",
            },
            {
                "Bolag": "MG",
                "Kund": "50000",
                "Order nr": "O-STOP",
                "Artikel": "A1",
                "Beställt": "12",
                "Orderdatum": "2026-05-26",
                "Robot": "",
                "Zon": "A",
                "Pack klass": "K",
                "Status": "30",
                "Är plockad": "0",
            },
        ]
    ).to_csv(orders_path, index=False, sep="\t", encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "Bolag": "MG",
                "Kund nr": "50000",
                "Ordernr": "O-STOP",
                "Ordertyp": "",
                "Sändningsnr": "S-STOP",
                "Multi": "",
                "Transportör": "Schenker - 10:00 - Parti",
                "Volym": "1",
                "Vikt": "1",
                "Antal": "12",
                "Rader": "1",
                "Status": "11",
            },
        ]
    ).to_csv(fore_dir / "v_ask_order_overview-20260601000000.csv", index=False, sep="\t", encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "Bolag": "MG",
                "Kund nr": "50000",
                "Ordernr": "O-OK",
                "Ordertyp": "",
                "Sändningsnr": "S-OK",
                "Multi": "",
                "Transportör": "Schenker - 10:00 - Parti",
                "Volym": "1",
                "Vikt": "1",
                "Antal": "12",
                "Rader": "1",
                "Status": "30",
            },
            {
                "Bolag": "MG",
                "Kund nr": "50000",
                "Ordernr": "O-STOP",
                "Ordertyp": "",
                "Sändningsnr": "S-STOP",
                "Multi": "",
                "Transportör": "Schenker - 10:00 - Parti",
                "Volym": "1",
                "Vikt": "1",
                "Antal": "12",
                "Rader": "1",
                "Status": "30",
            },
        ]
    ).to_csv(fore_dir / "v_ask_order_overview-20260601000100.csv", index=False, sep="\t", encoding="utf-8-sig")

    monkeypatch.setattr(
        mg_forecast,
        "load_customers",
        lambda: pd.DataFrame(
            [
                {
                    "Kund": "50000",
                    "kund_max_hojd": 280.0,
                    "kund_postnr_prefix2": 0.0,
                    "kund_postnr_prefix3": 0.0,
                    "kund_postnr_missing": 1.0,
                    "kund_is_foreign": 0.0,
                    "kund_standard_transportornr": 0.0,
                    "kund_has_standard_transportor": 0.0,
                    "kund_requires_lift": 0.0,
                    "kund_special_delivery_text": 0.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        mg_forecast,
        "load_items",
        lambda: pd.DataFrame(
            [
                {
                    "Artikel": "A1",
                    "per_pall": 12.0,
                    "vikt_brutto": 1.0,
                    "volym": 1.0,
                    "item_palltyp": "E",
                    "item_robot": False,
                    "item_staplingsbar": True,
                    "item_pack_klass": "",
                    "item_pall_flakmeter": 0.0,
                    "item_pall_langd": 120.0,
                    "item_pall_bredd": 80.0,
                    "item_pall_hojd": 120.0,
                    "item_pall_langgods": False,
                    "item_pall_extra_lang": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        mg_forecast,
        "load_item_dimensions",
        lambda: pd.DataFrame([{"Artikel": "A1", "art_langd": 120.0, "art_bredd": 80.0, "art_hojd": 120.0}]),
    )
    monkeypatch.setattr(
        mg_forecast,
        "load_item_options",
        lambda: pd.DataFrame(
            [
                {
                    "Artikel": "A1",
                    "opt_ej_staplingsbar": False,
                    "opt_helpalls_avvikelse_pct": 0.0,
                    "opt_plockzon": "",
                    "opt_robot": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        mg_forecast,
        "load_buffert_pallets",
        lambda: pd.DataFrame([{"Artikel": "A1", "buffert_n_pallar": 1.0, "buffert_total_antal": 12.0}]),
    )

    features = mg_forecast.build_inference_features(
        orders_path,
        default_transportor="Schenker",
        data_fore=fore_dir,
    )

    assert features["ordernummer"].tolist() == ["O-OK"]
    assert features["grupp"].tolist() == ["S-OK"]
    assert features["n_rader"].tolist() == [1.0]


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
    assert "order_set_area_import" not in tables
    assert result["auto_downloads"] == []
    assert any("Forecast saknar kolumnen Ordernummer" in line for line in result["log"])


def test_ytgenerering_uses_configured_utl_range(monkeypatch, tmp_path):
    forecast_df = pd.DataFrame(
        [
            {"SÃ¤ndningsnr": "S-1", "TransportÃ¶r": "Akeri A", "Predikterade pallplatser": 2.0},
        ]
    )
    location_path = tmp_path / "location.csv"
    location_path.write_text("not used\n", encoding="utf-8")
    monkeypatch.setattr(
        flows,
        "_read",
        lambda path: pd.DataFrame(
            [
                {"Lagerplats": "UTL204", "Typ": "U", "Max pall": 10},
                {"Lagerplats": "UTL205", "Typ": "U", "Max pall": 1},
                {"Lagerplats": "UTL206", "Typ": "U", "Max pall": 1},
            ]
        ),
    )

    result = flows.FLOW_BY_ID["ytgenerering"]["handler"](
        {"location": location_path},
        {"__forecast_df": forecast_df, "__ytgenerering_utl_min": "205", "__ytgenerering_utl_max": "652"},
    )

    tables = {key: table for key, _label, table in result["tables"]}
    map_payload = result["maps"][0]
    assert list(tables["ytgenerering"]["Lagerplats"]) == ["UTL205", "UTL206"]
    assert [loc["location"] for loc in map_payload["locations"]] == ["UTL205", "UTL206"]
    assert [assignment["location"] for assignment in map_payload["assignments"]] == ["UTL205", "UTL206"]
    assert result["summary"]["Ej placerade pallplatser"] == 0
    assert any("UTL205-UTL652" in line for line in result["log"])


def test_ytgenerering_map_layout_adds_missing_location_capacity(monkeypatch, tmp_path):
    forecast_df = pd.DataFrame(
        [
            {"SÃ¤ndningsnr": "S-1", "TransportÃ¶r": "Akeri A", "Predikterade pallplatser": 2.0},
        ]
    )
    location_path = tmp_path / "location.csv"
    location_path.write_text("not used\n", encoding="utf-8")
    monkeypatch.setattr(
        flows,
        "_read",
        lambda path: pd.DataFrame(
            [
                {"Lagerplats": "UTL205", "Typ": "U", "Max pall": 1},
            ]
        ),
    )
    layout = {
        "locations": [
            {"location": "UTL206", "x": 100, "y": 100, "w": 240, "h": 80, "maxPall": 1, "loadDirection": "left"},
        ]
    }

    result = flows.FLOW_BY_ID["ytgenerering"]["handler"](
        {"location": location_path},
        {"__forecast_df": forecast_df, "__ytgenerering_map_locations_json": json.dumps(layout, ensure_ascii=False)},
    )

    tables = {key: table for key, _label, table in result["tables"]}
    assert list(tables["ytgenerering"]["Lagerplats"]) == ["UTL205", "UTL206"]
    assert [loc["location"] for loc in result["maps"][0]["locations"]] == ["UTL205", "UTL206"]
    assert result["maps"][0]["locations"][1]["maxPall"] == 1
    assert result["maps"][0]["locations"][1]["loadDirection"] == "left"
    assert any("Ytkartsinställningar lade till 1 ytor" in line for line in result["log"])


def test_ytgenerering_map_load_direction_stays_parallel_to_long_side():
    rows = normalize_map_location_rows(
        [
            {"location": "UTL600", "x": 0, "y": 0, "w": 240, "h": 80, "loadDirection": "down"},
            {"location": "UTL601", "x": 0, "y": 0, "w": 80, "h": 240, "loadDirection": "left"},
            {"location": "UTL602", "x": 0, "y": 0, "w": 240, "h": 80, "loadDirection": "left"},
            {"location": "UTL603", "x": 0, "y": 0, "w": 80, "h": 240, "loadDirection": "up"},
        ]
    )

    assert [row["loadDirection"] for row in rows] == ["right", "down", "left", "up"]


def test_ytgenerering_flow_uses_transport_cluster_json(monkeypatch, tmp_path):
    forecast_df = pd.DataFrame(
        [
            {"Sändningsnr": "F-1", "Transportör": "Freja Stockholm", "Predikterade pallplatser": 1.0},
            {"Sändningsnr": "S-1", "Transportör": "Schenker", "Predikterade pallplatser": 1.0},
        ]
    )
    clusters = {
        "rows": [
            {"alias": "Schenker", "clusterGroup": "Schenker", "assignmentOrder": 0, "startSeq": 205, "endSeq": 356},
            {"alias": "Freja Stockholm", "clusterGroup": "Freja", "assignmentOrder": 9, "startSeq": 600, "endSeq": 652},
        ]
    }
    location_path = tmp_path / "location.csv"
    location_path.write_text("not used\n", encoding="utf-8")
    monkeypatch.setattr(
        flows,
        "_read",
        lambda path: pd.DataFrame(
            [
                {"Lagerplats": "UTL205", "Typ": "U", "Max pall": 1},
                {"Lagerplats": "UTL600", "Typ": "U", "Max pall": 1},
            ]
        ),
    )

    result = flows.FLOW_BY_ID["ytgenerering"]["handler"](
        {"location": location_path},
        {"__forecast_df": forecast_df, "__carrier_clusters_json": json.dumps(clusters, ensure_ascii=False)},
    )

    tables = {key: table for key, _label, table in result["tables"]}
    assert dict(zip(tables["ytgenerering"]["Sändningsnr"], tables["ytgenerering"]["Lagerplats"])) == {
        "S-1": "UTL205",
        "F-1": "UTL600",
    }
    assert result["maps"][0]["assignments"][0]["cluster"] == "Schenker"
    assert any("Transportörskluster använda" in line for line in result["log"])


def test_ytgenerering_builds_order_set_area_import_for_multi_order_multi_surface(monkeypatch, tmp_path):
    forecast_payload = {
        "columns": ["Sändningsnr", "Ordernummer", "Transportör", "Predikterade pallplatser"],
        "rows": [
            {
                "Sändningsnr": "S-1",
                "Ordernummer": "1001, 1002",
                "Transportör": "Akeri A",
                "Predikterade pallplatser": 1.5,
            },
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
    import_table = tables["order_set_area_import"]
    assert result["maps"][0]["assignments"][0]["orderNumbers"] == ["1001", "1002"]
    assert import_table.to_dict("records") == [
        {"area_num": "UTL100, UTL101", "company": "MG", "order_num": "1001", "pick_zone": "A"},
        {"area_num": "UTL100, UTL101", "company": "MG", "order_num": "1002", "pick_zone": "A"},
    ]
    assert result["auto_downloads"] == [
        {
            "key": "order_set_area_import",
            "filename": "v_ask_order_overview_order_set_area_execute_command.csv",
        }
    ]
    assert result["download_files"]["order_set_area_import"]["content"] == (
        "area_num\tcompany\torder_num\tpick_zone\n"
        "UTL100, UTL101\tMG\t1001\tA\n"
        "UTL100, UTL101\tMG\t1002\tA\n"
    )


def test_ytgenerering_map_attaches_customer_to_assignments_and_unplaced(monkeypatch, tmp_path):
    forecast_payload = {
        "columns": ["Sändningsnr", "Kund", "Kundnamn", "Transportör", "Predikterade pallplatser"],
        "rows": [
            {"Sändningsnr": "S-1", "Kund": "10", "Kundnamn": "ICA Maxi", "Transportör": "Akeri A", "Predikterade pallplatser": 1.0},
            {"Sändningsnr": "S-2", "Kund": "20", "Kundnamn": "Coop Forum", "Transportör": "Akeri B", "Predikterade pallplatser": 1.0},
        ],
    }
    location_path = tmp_path / "location.csv"
    location_path.write_text("not used\n", encoding="utf-8")
    monkeypatch.setattr(
        flows,
        "_read",
        lambda path: pd.DataFrame([{"Lagerplats": "UTL100", "Typ": "U", "Max pall": 1}]),
    )

    result = flows.FLOW_BY_ID["ytgenerering"]["handler"](
        {"location": location_path},
        {"__forecast_json": json.dumps(forecast_payload, ensure_ascii=False)},
    )

    map_payload = result["maps"][0]
    customers = {a["location"]: a["customer"] for a in map_payload["assignments"]}
    assert customers.get("UTL100") == "ICA Maxi"
    assert map_payload["assignments"][0]["customerNum"] == "10"
    # Sändningen som inte fick plats bär kundnamnet i missing-listan.
    assert any(row.get("customer") == "Coop Forum" for row in map_payload["unplaced"])


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


def test_prepared_location_cache_uses_current_file_version(tmp_path):
    flows.clear_prepared_location_cache()
    flows._read_cached.cache_clear()
    location_path = tmp_path / "location.csv"
    location_path.write_text("Lagerplats\tTyp\tMax pall\nUTL100\tU\t1\n", encoding="utf-8")

    first = flows._read_prepared_locations(location_path)

    location_path.write_text(
        "Lagerplats\tTyp\tMax pall\nUTL100\tU\t2\nUTL101\tU\t3\n",
        encoding="utf-8",
    )
    second = flows._read_prepared_locations(location_path)

    assert list(first["Lagerplats"]) == ["UTL100"]
    assert list(second["Lagerplats"]) == ["UTL100", "UTL101"]
    assert list(second["Max pall"]) == [2, 3]


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
