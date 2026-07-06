"""Karakteriseringstester för warehouse_tools-flöden mot golden-snapshots.

Syfte: låsa motorns observerbara beteende. Golden-snapshotsen skapades mot den
gamla vendormotorn (vendor/allokering12.1.py) och bevisade att uppdelningen
till warehouse_tools/engine_core/ (2026-07) gav identiska utdata. Testerna kör
flödeshandlers i warehouse_tools/flows.py direkt mot realistisk lokal testdata
och jämför ett normaliserat snapshot (summary, tabellkolumner, radantal,
innehålls-hash och de fem första raderna) mot golden-filer.

Privat data: både `testdata/` och `tests/services/golden/` är gitignorade
eftersom underlaget innehåller kund-/lagerdata. I CI (där testdata saknas)
skippas hela modulen — skyddet är lokalt, där motorändringar görs.

Regenerera golden-filer avsiktligt med:

    FLOW_GOLDEN_UPDATE=1 python -m pytest tests/services/test_warehouse_flow_characterization.py

Kör aldrig med flaggan satt för att "fixa" ett rött test utan att först
förstå varför beteendet ändrades.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TESTDATA = ROOT / "testdata" / "warehouse_tools"
GOLDEN_DIR = ROOT / "tests" / "services" / "golden" / "warehouse_flows"

pytestmark = pytest.mark.skipif(
    not TESTDATA.is_dir(),
    reason="privat testdata saknas (testdata/warehouse_tools är gitignorerad)",
)


def _data(name: str) -> Path:
    path = TESTDATA / name
    if not path.is_file():
        pytest.skip(f"testdatafil saknas: {name}")
    return path


# Flöde -> files-dict (nycklar enligt FLOW_BY_ID[...]["inputs"]/["coredata"]).
# Endast flöden som går genom motorn (engine_core) och är deterministiska utan
# nätverk/GitHub/ML tas med. forecast/ytgenerering (ML), observations-*
# (GitHub/temporära filer) och update-check (nätverk) karakteriseras inte.
FLOW_INPUTS: dict[str, dict[str, str]] = {
    "allocate": {
        "orders": "v_ask_customer_order_details_all-20260519090642.csv",
        "buffer": "v_ask_article_buffertpallet-20260519090645.csv",
        "saldo": "v_ask_item_summary_stock_automation-20260519090648.csv",
        "items": "item_option-20260519090653.csv",
        "not_putaway": "v_ask_booking_putaway-20260519090707.csv",
    },
    "ordersaldo": {
        "orders": "v_ask_customer_order_details_all-20260519090642.csv",
        "saldo": "v_ask_item_summary_stock_automation-20260519090648.csv",
    },
    "lyx": {
        "saldo": "v_ask_item_summary_stock_automation-20260519090648.csv",
    },
    "pafyllnadsprio": {
        "orders": "v_ask_customer_order_details_all-20260519090642.csv",
        "saldo": "v_ask_item_summary_stock_automation-20260519090648.csv",
        "overview": "v_ask_order_overview-20260519090657.csv",
    },
    "hib-koppling": {
        "details": "v_ask_customer_order_details_all-20260519090642.csv",
        "overview": "v_ask_order_overview-20260519090657.csv",
    },
    "overview-check": {
        "overview": "v_ask_order_overview-20260519090657.csv",
        "details": "v_ask_customer_order_details_all-20260519090642.csv",
    },
    "dispatch-check": {
        "overview": "v_ask_order_overview-20260519090657.csv",
        "dispatch": "v_ask_dispatch_pallet-20260519090706.csv",
        "details": "v_ask_customer_order_details_all-20260519090642.csv",
    },
    "vecka27-check": {
        "orders": "v_ask_customer_order_details_all-20260519090642.csv",
    },
    "goods-declaration": {
        "orders": "v_ask_customer_order_details_all-20260519090642.csv",
        "overview": "v_ask_order_overview-20260519090657.csv",
        "custom_adr": "v_ask_custom_adr-20260526135512.csv",
        "item_security_info": "item_security_info-20260526135153.csv",
    },
    "prognos-report": {
        "prognos": "Prognos idag_1227934_3062311682516.xlsx",
        "campaign": "Granngården prognos kampanjplock +6v_1208059_2993592205456.xlsx",
        "saldo": "v_ask_item_summary_stock_automation-20260519090648.csv",
        "buffer": "v_ask_article_buffertpallet-20260519090645.csv",
    },
}

HEAD_ROWS = 5


def _normalize_cell(value) -> str:
    """Normalisera ett cellvärde enligt samma principer som
    tools/compare_warehouse_results.py: NaN -> "", heltalslika flyttal -> heltal."""
    import pandas as pd

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    text = str(value)
    return text


def _table_snapshot(df) -> dict:
    normalized = df.astype(object).where(df.notna(), None)
    rows = [
        [_normalize_cell(cell) for cell in row]
        for row in normalized.itertuples(index=False, name=None)
    ]
    payload = "\n".join("\x1f".join(row) for row in rows)
    return {
        "columns": [str(c) for c in df.columns],
        "rows": len(rows),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "head": rows[:HEAD_ROWS],
    }


def _result_snapshot(result: dict) -> dict:
    snapshot: dict = {
        "summary": {str(k): _normalize_cell(v) for k, v in (result.get("summary") or {}).items()},
        "tables": [
            {"key": key, "label": label, **_table_snapshot(df)}
            for key, label, df in (result.get("tables") or [])
        ],
        "log_line_count": len(result.get("log") or []),
        "has_text": bool(result.get("text")),
    }
    display = result.get("display_summary")
    if display is not None:
        snapshot["display_summary"] = json.loads(json.dumps(display, ensure_ascii=False, default=str))
    return snapshot


def _golden_path(flow_id: str) -> Path:
    return GOLDEN_DIR / f"{flow_id}.json"


def _run_flow(flow_id: str) -> dict:
    from warehouse_tools import flows

    files = {key: _data(name) for key, name in FLOW_INPUTS[flow_id].items()}
    handler = flows.FLOW_BY_ID[flow_id]["handler"]
    return handler(files, {})


@pytest.mark.parametrize("flow_id", sorted(FLOW_INPUTS))
def test_flow_matches_golden_snapshot(flow_id: str):
    result = _run_flow(flow_id)
    snapshot = _result_snapshot(result)

    golden_path = _golden_path(flow_id)
    if os.environ.get("FLOW_GOLDEN_UPDATE") == "1" or not golden_path.is_file():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if os.environ.get("FLOW_GOLDEN_UPDATE") != "1":
            pytest.skip(f"golden-fil skapad för {flow_id} - kör om testet för att jämföra")
        return

    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert snapshot == golden, (
        f"Flödet {flow_id} avviker från golden-snapshot. Om ändringen är avsiktlig: "
        "regenerera med FLOW_GOLDEN_UPDATE=1 och granska diffen."
    )
