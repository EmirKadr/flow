from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from .business_scope import default_business
from .models import AppSetting
from .user_access import normalize_role_view_access_ids, normalize_role_view_id


LOCK_FOREIGN_SCHEDULE_CELLS_KEY = "lock_foreign_schedule_cells"
SIDEBAR_LAYOUT_KEY = "sidebar_layout"
ROLE_VIEW_ACCESS_KEY = "role_view_access"
ALLOCATION_PROCESS_MATRIX_KEY = "allocation_process_matrix"
STAFFING_HISTORY_HOURS_KEY = "staffing_history_hours"
STAFFING_ACTIVITY_CAPACITY_ACTIVITY_IDS_KEY = "staffing_activity_capacity_activity_ids"
STAFFING_HISTORY_HOURS_DEFAULT = 40.0
STAFFING_HISTORY_HOURS_MIN = 1.0
STAFFING_HISTORY_HOURS_MAX = 240.0
PRODUCTIVITY_FINANCE_KEY = "productivity_finance"
PRODUCTIVITY_FINANCE_HOURLY_COST_DEFAULT = 0.0
PRODUCTIVITY_FINANCE_AMOUNT_MIN = 0.0
PRODUCTIVITY_FINANCE_AMOUNT_MAX = 10000000.0
PRODUCTIVITY_FINANCE_COLLAR_TYPES = ("blue_collar", "white_collar")
PRODUCTIVITY_FINANCE_DEFAULT_COLLAR_TYPE = "blue_collar"
PRODUCTIVITY_FINANCE_VAS_RATE_TYPES = ("normal", "ot_50", "ob1_40", "ob2_70", "ob3_100")
PRODUCTIVITY_FINANCE_DEFAULT_VAS_RATE_TYPE = "normal"
# OBS: Default-priserna är medvetet 0.0 i koden. Riktiga (hemliga) priser ligger
# ALDRIG i repot – de läses från den gitignore:ade lokala filen
# data/productivity_finance_prices.local.json (se _local_invoice_prices) eller
# matas in i UI:t och sparas per verksamhet i databasen.
PRODUCTIVITY_FINANCE_INVOICE_PRICE_KEYS = (
    "inbound_container_unloading",
    "inbound_labels",
    "inbound_article_rows",
    "store_picked_orders",
    "store_picked_rows",
    "store_picked_pcs",
    "store_full_pallets",
    "store_loaded_pallets",
    "ecom_picked_orders",
    "ecom_picked_rows",
    "ecom_picked_pcs",
    "ecom_pallet",
    "vas_blue_normal",
    "vas_blue_ot_50",
    "vas_blue_ob1_40",
    "vas_blue_ob2_70",
    "vas_blue_ob3_100",
    "vas_white_normal",
    "vas_white_ot_50",
    "vas_white_ob1_40",
    "vas_white_ob2_70",
    "vas_white_ob3_100",
    "it_hourly",
    "dc_function",
    "pallet_automation",
    "box_automation",
    "other_investments",
    "other_costs",
    "rent_index_kpi_2501",
    "outdoor_storage_facade_chilled",
    "racking_complement",
    "rent_addendum_ii",
    "autostore_store_box",
    "driver_trucks",
)
PRODUCTIVITY_FINANCE_GG_INVOICE_PRICES = {key: 0.0 for key in PRODUCTIVITY_FINANCE_INVOICE_PRICE_KEYS}
PRODUCTIVITY_FINANCE_MG_INVOICE_PRICES = {
    key: 0.0 for key in PRODUCTIVITY_FINANCE_INVOICE_PRICE_KEYS if key.startswith("vas_")
}
PRODUCTIVITY_FINANCE_MG_INVOICE_PRICES["it_hourly"] = 0.0

# Gitignore:ad lokal fil med riktiga priser per bolag, t.ex. {"GG": {...}, "MG": {...}}.
PRODUCTIVITY_FINANCE_LOCAL_PRICES_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "productivity_finance_prices.local.json"
)


def _local_invoice_prices(company_code: str) -> dict:
    """Riktiga priser från den lokala (gitignore:ade) filen, om den finns. Annars tomt."""
    try:
        if not PRODUCTIVITY_FINANCE_LOCAL_PRICES_PATH.is_file():
            return {}
        data = json.loads(PRODUCTIVITY_FINANCE_LOCAL_PRICES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    prices = data.get(str(company_code or "").strip().upper())
    return {k: v for k, v in prices.items() if isinstance(v, (int, float))} if isinstance(prices, dict) else {}
PRODUCTIVITY_FINANCE_GG_INVOICE_CALCULATIONS = {
    "inbound_labels": {
        "calculation_prompt": "antal poster i varumottagningslogg\nexkludera typ 45, 91 & 100",
        "calculation_plan": {
            "status": "ok",
            "view": "v_ask_receive_log",
            "view_label": "Varumottagningslogg",
            "output_columns": ["rowid"],
            "filters": [
                {"id": "type", "operator": "NE", "value": "45"},
                {"id": "type", "operator": "NE", "value": "91"},
                {"id": "type", "operator": "NE", "value": "100"},
                {"id": "timestamp", "operator": "Between", "value": ["2026-05-01T00:00:00", "2026-05-31T23:59:59"]},
                {"id": "company", "operator": "EQ", "value": "GG"},
            ],
            "calculation": {"metric": "count", "field": None, "distinct_by": [], "group_by": [], "sort_by": None, "limit": None},
        },
        "calculation_sql": "SELECT COUNT(*) AS st_antal FROM v_ask_receive_log WHERE type <> '45' AND type <> '91' AND type <> '100' AND timestamp BETWEEN '2026-05-01T00:00:00' AND '2026-05-31T23:59:59' AND company = 'GG';",
    },
    "store_picked_orders": {
        "calculation_prompt": "antal unika ordernummer i plocklogg full som börjar på TO",
        "calculation_plan": {
            "status": "ok",
            "view": "v_ask_pick_log_full",
            "view_label": "Plocklogg Full",
            "output_columns": ["order_num"],
            "filters": [
                {"id": "order_num", "operator": "StartsWith", "value": "TO"},
                {"id": "time_stamp_int", "operator": "Between", "value": [20260501, 20260531]},
                {"id": "company", "operator": "EQ", "value": "GG"},
            ],
            "calculation": {"metric": "count_distinct", "field": None, "distinct_by": ["order_num"], "group_by": [], "sort_by": None, "limit": None},
        },
        "calculation_sql": "SELECT COUNT(DISTINCT order_num) AS value FROM v_ask_pick_log_full WHERE order_num LIKE 'TO%' AND time_stamp_int BETWEEN 20260501 AND 20260531 AND company = 'GG';",
    },
    "store_picked_rows": {
        "calculation_prompt": "antal poster i plocklogg full\ninkludera endast ordernummer som börjar på TO\nexkludera poster med zon = H\nexkludera rader med <1 i kolumn plockat",
        "calculation_plan": {
            "status": "ok",
            "view": "v_ask_pick_log_full",
            "view_label": "Plocklogg Full",
            "output_columns": ["rowid"],
            "filters": [
                {"id": "order_num", "operator": "StartsWith", "value": "TO"},
                {"id": "pick_zone", "operator": "NE", "value": "H"},
                {"id": "qty_suf", "operator": "GTE", "value": 1},
                {"id": "time_stamp_int", "operator": "Between", "value": [20260501, 20260531]},
                {"id": "company", "operator": "EQ", "value": "GG"},
            ],
            "calculation": {"metric": "count", "field": None, "distinct_by": [], "group_by": [], "sort_by": None, "limit": None},
        },
        "calculation_sql": "SELECT COUNT(*) AS value FROM v_ask_pick_log_full WHERE order_num LIKE 'TO%' AND pick_zone <> 'H' AND qty_suf >= 1 AND time_stamp_int BETWEEN 20260501 AND 20260531 AND company = 'GG';",
    },
    "store_full_pallets": {
        "calculation_prompt": "antal poster i plocklogg full med zon = H\nexkludera rader med <1 i kolumn plockat\ninkludera endast ordernummer som börjar på TO",
        "calculation_plan": {
            "status": "ok",
            "view": "v_ask_pick_log_full",
            "view_label": "Plocklogg Full",
            "output_columns": ["rowid"],
            "filters": [
                {"id": "pick_zone", "operator": "EQ", "value": "H"},
                {"id": "qty_suf", "operator": "GTE", "value": 1},
                {"id": "order_num", "operator": "StartsWith", "value": "TO"},
                {"id": "time_stamp_int", "operator": "Between", "value": [20260601, 20260630]},
                {"id": "company", "operator": "EQ", "value": "GG"},
            ],
            "calculation": {"metric": "count", "field": None, "distinct_by": [], "group_by": [], "sort_by": None, "limit": None},
        },
        "calculation_sql": "SELECT COUNT(*) AS value FROM v_ask_pick_log_full WHERE pick_zone = 'H' AND qty_suf >= '1' AND order_num LIKE 'TO%' AND time_stamp_int BETWEEN 20260601 AND 20260630 AND company = 'GG';",
    },
    "store_loaded_pallets": {
        "calculation_prompt": "antal poster i dispatchpallar utan värde i kolumnen pappapallsnr",
        "calculation_plan": {
            "status": "ok",
            "view": "v_ask_dispatch_pallet",
            "view_label": "Dispatchpallar",
            "output_columns": ["parent_pick_pall_num"],
            "filters": [
                {"id": "parent_pick_pall_num", "operator": "NE", "value": ""},
                {"id": "timestamp", "operator": "Between", "value": ["2026-05-01T00:00:00", "2026-05-31T23:59:59"]},
                {"id": "company", "operator": "EQ", "value": "GG"},
            ],
            "calculation": {"metric": "count", "field": None, "distinct_by": [], "group_by": [], "sort_by": None, "limit": None},
        },
        "calculation_sql": "SELECT COUNT(*) AS value FROM v_ask_dispatch_pallet WHERE parent_pick_pall_num <> '' AND timestamp BETWEEN '2026-05-01T00:00:00' AND '2026-05-31T23:59:59' AND company = 'GG';",
    },
    "inbound_article_rows": {
        "calculation_prompt": "kolla i varumottagningslogg\nexkludera typ 45, 91 & 100\nsedan ta antal rader om vi tar bort dubletter för artikelnummer per inköpsnummer",
        "calculation_plan": {
            "status": "ok",
            "view": "v_ask_receive_log",
            "view_label": "Varumottagningslogg",
            "output_columns": ["book_num", "item_num"],
            "filters": [
                {"id": "type", "operator": "NE", "value": 45},
                {"id": "type", "operator": "NE", "value": 91},
                {"id": "type", "operator": "NE", "value": 100},
                {"id": "timestamp", "operator": "Between", "value": ["2026-05-01T00:00:00", "2026-05-31T23:59:59"]},
                {"id": "company", "operator": "EQ", "value": "GG"},
            ],
            "calculation": {"metric": "count_distinct", "field": None, "distinct_by": ["book_num", "item_num"], "group_by": [], "sort_by": None, "limit": None},
        },
        "calculation_sql": "SELECT COUNT(DISTINCT (book_num, item_num)) AS value FROM v_ask_receive_log WHERE type <> 45 AND type <> 91 AND type <> 100 AND timestamp BETWEEN '2026-05-01T00:00:00' AND '2026-05-31T23:59:59' AND company = 'GG';",
    },
}


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "ja"}


def _parse_float(value: str | None, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def _clamp_float(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def clean_productivity_finance_company_code(value: object) -> str:
    return "".join(
        char
        for char in str(value or "").strip().upper()
        if char.isalnum() or char in {"_", "-"}
    )[:40]


def _clean_company_code(value: object) -> str:
    return clean_productivity_finance_company_code(value)


def _clean_money_amount(value: object) -> float:
    try:
        parsed = float(str(value or "0").strip().replace(",", "."))
    except (TypeError, ValueError):
        parsed = 0.0
    return round(_clamp_float(
        parsed,
        minimum=PRODUCTIVITY_FINANCE_AMOUNT_MIN,
        maximum=PRODUCTIVITY_FINANCE_AMOUNT_MAX,
    ), 2)


def normalize_productivity_finance_collar_type(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "white_collar" if text == "white_collar" else PRODUCTIVITY_FINANCE_DEFAULT_COLLAR_TYPE


def normalize_productivity_finance_vas_rate_type(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "normal": "normal",
        "base": "normal",
        "ot_50": "ot_50",
        "ot1_50": "ot_50",
        "overtime_50": "ot_50",
        "öt_1_50": "ot_50",
        "ob1_40": "ob1_40",
        "ob_1_40": "ob1_40",
        "ob2_70": "ob2_70",
        "ob_2_70": "ob2_70",
        "ob3_100": "ob3_100",
        "ob_3_100": "ob3_100",
    }
    return aliases.get(text, PRODUCTIVITY_FINANCE_DEFAULT_VAS_RATE_TYPE)


def _empty_productivity_finance_vas_rate_amounts() -> dict[str, float]:
    return {rate_type: 0.0 for rate_type in PRODUCTIVITY_FINANCE_VAS_RATE_TYPES}


def _productivity_finance_vas_rate_amounts(value: object) -> dict[str, float]:
    amounts = _empty_productivity_finance_vas_rate_amounts()
    if isinstance(value, dict):
        for key, amount in value.items():
            rate_type = normalize_productivity_finance_vas_rate_type(key)
            amounts[rate_type] = _clean_money_amount(amount)
        return amounts
    amounts[PRODUCTIVITY_FINANCE_DEFAULT_VAS_RATE_TYPE] = _clean_money_amount(value)
    return amounts


def _productivity_finance_company_amounts(value: object) -> dict[str, dict[str, float]]:
    if isinstance(value, dict):
        blue_value = value.get("blue_collar", value.get("blueCollar", value.get("blue")))
        white_value = value.get("white_collar", value.get("whiteCollar", value.get("white")))
        has_collar_values = any(item is not None for item in (blue_value, white_value))
        if has_collar_values:
            return {
                "blue_collar": _productivity_finance_vas_rate_amounts(blue_value),
                "white_collar": _productivity_finance_vas_rate_amounts(white_value),
            }
        rate_amounts = _productivity_finance_vas_rate_amounts(value)
        return {collar_type: dict(rate_amounts) for collar_type in PRODUCTIVITY_FINANCE_COLLAR_TYPES}
    rate_amounts = _productivity_finance_vas_rate_amounts(value)
    return {collar_type: dict(rate_amounts) for collar_type in PRODUCTIVITY_FINANCE_COLLAR_TYPES}


def _productivity_finance_invoice_row(
    row_id: str,
    section: str,
    service: str,
    description: str,
    unit: str,
    *,
    default_price: float = 0.0,
    collar_type: str | None = None,
    vas_rate_type: str | None = None,
) -> dict:
    return {
        "id": row_id,
        "section": section,
        "service": service,
        "description": description,
        "unit": unit,
        "price": default_price,
        "quantity": 0.0,
        "calculation_prompt": "",
        "calculation_plan": None,
        "calculation_sql": "",
        "collar_type": collar_type,
        "vas_rate_type": vas_rate_type,
    }


def _productivity_finance_invoice_template_rows() -> list[dict]:
    return [
        _productivity_finance_invoice_row("inbound_container_unloading", "Inbound", "Inbound", "Containerlossning", "Per lossad m3"),
        _productivity_finance_invoice_row("inbound_labels", "Inbound", "Inbound", "Mottagna etiketter", "Per etikett eller låda"),
        _productivity_finance_invoice_row("inbound_article_rows", "Inbound", "Inbound", "Mottagna artikelrader", "Per intagen artikelrad"),
        _productivity_finance_invoice_row("store_picked_orders", "BUTIK", "Outbound", "Plockade orders", "Per order"),
        _productivity_finance_invoice_row("store_picked_rows", "BUTIK", "Outbound", "Plockade rader", "Per rad"),
        _productivity_finance_invoice_row("store_picked_pcs", "BUTIK", "Outbound", "Plockade pcs", "Per plockenhet (kartong/styck)"),
        _productivity_finance_invoice_row("store_full_pallets", "BUTIK", "Outbound", "Antal helpallar", "Helpall"),
        _productivity_finance_invoice_row("store_loaded_pallets", "BUTIK", "Outbound", "Utlastade pallar", "Per utlastad pall (helpall/plockad pall)"),
        _productivity_finance_invoice_row("ecom_picked_orders", "E-handel", "Outbound", "Plockade orders", "Per order"),
        _productivity_finance_invoice_row("ecom_picked_rows", "E-handel", "Outbound", "Plockade rader", "Per rad"),
        _productivity_finance_invoice_row("ecom_picked_pcs", "E-handel", "Outbound", "Plockade pcs", "Per plockenhet (kartong/styck)"),
        _productivity_finance_invoice_row("ecom_pallet", "E-handel", "Outbound", "Per pall", "Helpall"),
        _productivity_finance_invoice_row("vas_blue_normal", "VAS", "Blue collar VAS", "Per timme", "Normal", collar_type="blue_collar", vas_rate_type="normal"),
        _productivity_finance_invoice_row("vas_blue_ot_50", "VAS", "Blue collar VAS", "Per timme", "ÖT 1 - 50%", collar_type="blue_collar", vas_rate_type="ot_50"),
        _productivity_finance_invoice_row("vas_blue_ob1_40", "VAS", "Blue collar VAS", "Per timme", "OB1 - 40%", collar_type="blue_collar", vas_rate_type="ob1_40"),
        _productivity_finance_invoice_row("vas_blue_ob2_70", "VAS", "Blue collar VAS", "Per timme", "OB2 - 70%", collar_type="blue_collar", vas_rate_type="ob2_70"),
        _productivity_finance_invoice_row("vas_blue_ob3_100", "VAS", "Blue collar VAS", "Per timme", "OB3 - 100%", collar_type="blue_collar", vas_rate_type="ob3_100"),
        _productivity_finance_invoice_row("vas_white_normal", "VAS", "White collar VAS", "Per timme", "Normal", collar_type="white_collar", vas_rate_type="normal"),
        _productivity_finance_invoice_row("vas_white_ot_50", "VAS", "White collar VAS", "Per timme", "ÖT 1 - 50%", collar_type="white_collar", vas_rate_type="ot_50"),
        _productivity_finance_invoice_row("vas_white_ob1_40", "VAS", "White collar VAS", "Per timme", "OB1 - 40%", collar_type="white_collar", vas_rate_type="ob1_40"),
        _productivity_finance_invoice_row("vas_white_ob2_70", "VAS", "White collar VAS", "Per timme", "OB2 - 70%", collar_type="white_collar", vas_rate_type="ob2_70"),
        _productivity_finance_invoice_row("vas_white_ob3_100", "VAS", "White collar VAS", "Per timme", "OB3 - 100%", collar_type="white_collar", vas_rate_type="ob3_100"),
        _productivity_finance_invoice_row("it_hourly", "IT", "IT", "Per timme", ""),
        _productivity_finance_invoice_row("dc_function", "Övrigt", "DC-funktion", "Fast månadskostnad", "Per månad"),
        _productivity_finance_invoice_row("pallet_automation", "Övrigt", "", "Pallautomation", "Per månad"),
        _productivity_finance_invoice_row("box_automation", "Övrigt", "", "Lådautomation", "Per månad"),
        _productivity_finance_invoice_row("other_investments", "Övrigt", "", "Övriga investeringar", "Per månad"),
        _productivity_finance_invoice_row("other_costs", "Övrigt", "", "Övriga kostnader", "Per månad"),
        _productivity_finance_invoice_row("rent_index_kpi_2501", "Övrigt", "", "Hyra - index m KPI 2501", "Per månad"),
        _productivity_finance_invoice_row("outdoor_storage_facade_chilled", "Övrigt", "", "Utelagring samt Fasads kylt", "Per månad"),
        _productivity_finance_invoice_row("racking_complement", "Övrigt", "", "Komplement till ställage", "Per månad"),
        _productivity_finance_invoice_row("rent_addendum_ii", "Övrigt", "", "Hyra - Tilläggsavtal II", "Per månad"),
        _productivity_finance_invoice_row("rebilling", "Övrigt", "Vidarefakturering", "enl bifogade kopior", ""),
        _productivity_finance_invoice_row("autostore_store_box", "Övrigt", "Autostore butikslåda", "", ""),
        _productivity_finance_invoice_row("driver_trucks", "Övrigt", "Chaufförstruckar", "enl överenskommelse", ""),
    ]


def _productivity_finance_invoice_template_rows_for_company(company_code: object) -> list[dict]:
    rows = _productivity_finance_invoice_template_rows()
    if clean_productivity_finance_company_code(company_code) == "MG":
        return [
            row
            for row in rows
            if str(row.get("section") or "") in {"VAS", "IT"}
        ]
    return rows


def _productivity_finance_invoice_calculation_defaults(company_code: object, row_id: object) -> dict:
    code = clean_productivity_finance_company_code(company_code)
    if code != "GG":
        return {}
    defaults = PRODUCTIVITY_FINANCE_GG_INVOICE_CALCULATIONS.get(str(row_id or ""))
    return json.loads(json.dumps(defaults, ensure_ascii=False)) if defaults else {}


def _merge_productivity_finance_default_calculation(row: dict, default_row: dict) -> dict:
    merged = dict(row)
    for key in ("calculation_prompt", "calculation_plan", "calculation_sql"):
        if not merged.get(key) and default_row.get(key):
            merged[key] = default_row[key]
    return merged


def productivity_finance_default_invoice_rows(company_code: object) -> list[dict]:
    code = clean_productivity_finance_company_code(company_code)
    # Default-priser är 0.0 i koden; riktiga (hemliga) värden overlay:as från den
    # gitignore:ade lokala filen om den finns. MG:s vas-priser speglar GG:s.
    if code == "GG":
        defaults = {**PRODUCTIVITY_FINANCE_GG_INVOICE_PRICES, **_local_invoice_prices("GG")}
    elif code == "MG":
        gg_defaults = {**PRODUCTIVITY_FINANCE_GG_INVOICE_PRICES, **_local_invoice_prices("GG")}
        defaults = {
            **PRODUCTIVITY_FINANCE_MG_INVOICE_PRICES,
            **{key: value for key, value in gg_defaults.items() if key.startswith("vas_")},
            **_local_invoice_prices("MG"),
        }
    else:
        defaults = {}
    rows: list[dict] = []
    for row in _productivity_finance_invoice_template_rows_for_company(code):
        price = defaults.get(str(row.get("id") or ""), 0.0)
        calculation_defaults = _productivity_finance_invoice_calculation_defaults(code, row.get("id"))
        rows.append({**row, "price": _clean_money_amount(price), **calculation_defaults})
    return rows


def productivity_finance_invoice_rows_for_company(company_code: object, stored_rows: object) -> list[dict]:
    code = clean_productivity_finance_company_code(company_code)
    default_rows = productivity_finance_default_invoice_rows(code)
    cleaned_rows = clean_productivity_finance_invoice_rows(stored_rows)
    if not cleaned_rows:
        return default_rows

    cleaned_by_id = {str(row.get("id") or ""): row for row in cleaned_rows}
    default_ids = {str(row.get("id") or "") for row in default_rows}
    rows: list[dict] = []
    for default_row in default_rows:
        row_id = str(default_row.get("id") or "")
        stored_row = cleaned_by_id.get(row_id)
        if stored_row is None:
            rows.append(default_row)
            continue
        merged = {**default_row, **stored_row}
        if code == "MG" and _clean_money_amount(stored_row.get("price")) == 0.0:
            default_price = _clean_money_amount(default_row.get("price"))
            if default_price > 0.0:
                merged["price"] = default_price
        rows.append(_merge_productivity_finance_default_calculation(merged, default_row))
    if code != "MG":
        rows.extend(row for row in cleaned_rows if str(row.get("id") or "") not in default_ids)
    return rows


def _clean_productivity_finance_invoice_row(row: object) -> dict | None:
    if not isinstance(row, dict):
        return None
    row_id = str(row.get("id") or "").strip()[:80]
    section = str(row.get("section") or "").strip()[:80]
    service = str(row.get("service") or "").strip()[:120]
    description = str(row.get("description") or "").strip()[:160]
    unit = str(row.get("unit") or "").strip()[:160]
    if not row_id or not (section or service or description or unit):
        return None
    collar_type = row.get("collar_type")
    vas_rate_type = row.get("vas_rate_type")
    cleaned_collar_type = normalize_productivity_finance_collar_type(collar_type) if collar_type else None
    cleaned_vas_rate_type = normalize_productivity_finance_vas_rate_type(vas_rate_type) if vas_rate_type else None
    return {
        "id": row_id,
        "section": section,
        "service": service,
        "description": description,
        "unit": unit,
        "price": _clean_money_amount(row.get("price")),
        "quantity": _clean_money_amount(row.get("quantity")),
        "calculation_prompt": str(row.get("calculation_prompt") or "").strip()[:4000],
        "calculation_plan": row.get("calculation_plan") if isinstance(row.get("calculation_plan"), dict) else None,
        "calculation_sql": str(row.get("calculation_sql") or "").strip()[:8000],
        "collar_type": cleaned_collar_type,
        "vas_rate_type": cleaned_vas_rate_type,
    }


def clean_productivity_finance_invoice_rows(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    for item in value:
        row = _clean_productivity_finance_invoice_row(item)
        if row is None:
            continue
        row_id = str(row["id"])
        if row_id in seen:
            continue
        seen.add(row_id)
        rows.append(row)
    return rows


def productivity_finance_vas_rates_from_invoice_rows(rows: object) -> dict[str, dict[str, float]]:
    rates = {collar_type: _empty_productivity_finance_vas_rate_amounts() for collar_type in PRODUCTIVITY_FINANCE_COLLAR_TYPES}
    for row in clean_productivity_finance_invoice_rows(rows):
        collar_type = row.get("collar_type")
        vas_rate_type = row.get("vas_rate_type")
        if collar_type not in PRODUCTIVITY_FINANCE_COLLAR_TYPES or vas_rate_type not in PRODUCTIVITY_FINANCE_VAS_RATE_TYPES:
            continue
        rates[str(collar_type)][str(vas_rate_type)] = _clean_money_amount(row.get("price"))
    return rates


def _business_id(db: Session, business_id: int | None = None) -> int:
    if business_id is not None:
        return business_id
    try:
        business = default_business(db)
        return int(business.id) if business is not None else 1
    except Exception:
        return 1


def _get_setting(db: Session, key: str, business_id: int | None = None) -> AppSetting | None:
    return db.get(AppSetting, {"business_id": _business_id(db, business_id), "key": key})


def get_bool_setting(db: Session, key: str, *, default: bool = False, business_id: int | None = None) -> bool:
    row = _get_setting(db, key, business_id)
    return _parse_bool(row.value if row else None, default=default)


def set_bool_setting(
    db: Session,
    key: str,
    value: bool,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    scoped_business_id = _business_id(db, business_id)
    row = _get_setting(db, key, scoped_business_id)
    if row is None:
        row = AppSetting(business_id=scoped_business_id, key=key, value=_bool_text(value), updated_by=user_id)
        db.add(row)
    else:
        row.value = _bool_text(value)
        row.updated_by = user_id
    db.flush()
    return row


def get_float_setting(
    db: Session,
    key: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
    business_id: int | None = None,
) -> float:
    row = _get_setting(db, key, business_id)
    value = _parse_float(row.value if row else None, default=default)
    return _clamp_float(value, minimum=minimum, maximum=maximum)


def set_float_setting(
    db: Session,
    key: str,
    value: float,
    *,
    minimum: float,
    maximum: float,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    scoped_business_id = _business_id(db, business_id)
    cleaned = _clamp_float(value, minimum=minimum, maximum=maximum)
    row = _get_setting(db, key, scoped_business_id)
    text = f"{cleaned:g}"
    if row is None:
        row = AppSetting(business_id=scoped_business_id, key=key, value=text, updated_by=user_id)
        db.add(row)
    else:
        row.value = text
        row.updated_by = user_id
    db.flush()
    return row


def get_json_setting(db: Session, key: str, *, default=None, business_id: int | None = None):
    row = _get_setting(db, key, business_id)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        return default


def set_json_setting(
    db: Session,
    key: str,
    value,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    scoped_business_id = _business_id(db, business_id)
    row = _get_setting(db, key, scoped_business_id)
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if row is None:
        row = AppSetting(business_id=scoped_business_id, key=key, value=text, updated_by=user_id)
        db.add(row)
    else:
        row.value = text
        row.updated_by = user_id
    db.flush()
    return row


def get_lock_foreign_schedule_cells(db: Session, business_id: int | None = None) -> bool:
    return get_bool_setting(db, LOCK_FOREIGN_SCHEDULE_CELLS_KEY, default=False, business_id=business_id)


def set_lock_foreign_schedule_cells(
    db: Session,
    value: bool,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    return set_bool_setting(db, LOCK_FOREIGN_SCHEDULE_CELLS_KEY, value, user_id=user_id, business_id=business_id)


def get_staffing_history_hours(db: Session, business_id: int | None = None) -> float:
    return get_float_setting(
        db,
        STAFFING_HISTORY_HOURS_KEY,
        default=STAFFING_HISTORY_HOURS_DEFAULT,
        minimum=STAFFING_HISTORY_HOURS_MIN,
        maximum=STAFFING_HISTORY_HOURS_MAX,
        business_id=business_id,
    )


def set_staffing_history_hours(
    db: Session,
    value: float,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    return set_float_setting(
        db,
        STAFFING_HISTORY_HOURS_KEY,
        value,
        minimum=STAFFING_HISTORY_HOURS_MIN,
        maximum=STAFFING_HISTORY_HOURS_MAX,
        user_id=user_id,
        business_id=business_id,
    )


def get_staffing_activity_capacity_activity_ids(db: Session, business_id: int | None = None) -> list[int] | None:
    value = get_json_setting(db, STAFFING_ACTIVITY_CAPACITY_ACTIVITY_IDS_KEY, default=None, business_id=business_id)
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    ids: list[int] = []
    for item in value:
        try:
            activity_id = int(item)
        except (TypeError, ValueError):
            continue
        if activity_id > 0 and activity_id not in ids:
            ids.append(activity_id)
    return ids


def set_staffing_activity_capacity_activity_ids(
    db: Session,
    activity_ids: list[int] | None,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    if activity_ids is None:
        return set_json_setting(
            db,
            STAFFING_ACTIVITY_CAPACITY_ACTIVITY_IDS_KEY,
            None,
            user_id=user_id,
            business_id=business_id,
        )
    cleaned: list[int] = []
    for item in activity_ids:
        try:
            activity_id = int(item)
        except (TypeError, ValueError):
            continue
        if activity_id > 0 and activity_id not in cleaned:
            cleaned.append(activity_id)
    return set_json_setting(
        db,
        STAFFING_ACTIVITY_CAPACITY_ACTIVITY_IDS_KEY,
        cleaned,
        user_id=user_id,
        business_id=business_id,
    )


def normalize_productivity_finance_settings(value: object) -> dict:
    raw = value if isinstance(value, dict) else {}
    raw_invoice_rows = raw.get("invoice_rows_by_company")
    invoice_rows_by_company: dict[str, list[dict]] = {}
    if isinstance(raw_invoice_rows, dict):
        for company, rows in raw_invoice_rows.items():
            code = _clean_company_code(company)
            if not code:
                continue
            invoice_rows_by_company[code] = clean_productivity_finance_invoice_rows(rows)
    raw_rates = raw.get("vas_hourly_revenue_by_company")
    if not isinstance(raw_rates, dict):
        raw_rates = raw.get("vas_revenue_by_company")
    rates: dict[str, dict[str, dict[str, float]]] = {
        company: productivity_finance_vas_rates_from_invoice_rows(rows)
        for company, rows in invoice_rows_by_company.items()
    }
    if isinstance(raw_rates, dict):
        for company, amount in raw_rates.items():
            code = _clean_company_code(company)
            if not code:
                continue
            rates[code] = _productivity_finance_company_amounts(amount)
    return {
        "hourly_cost": _clean_money_amount(raw.get("hourly_cost")),
        "vas_hourly_revenue_by_company": rates,
        "invoice_rows_by_company": invoice_rows_by_company,
    }


def get_productivity_finance_settings(db: Session, business_id: int | None = None) -> dict:
    return normalize_productivity_finance_settings(
        get_json_setting(
            db,
            PRODUCTIVITY_FINANCE_KEY,
            default={},
            business_id=business_id,
        )
    )


def set_productivity_finance_settings(
    db: Session,
    value: dict,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    return set_json_setting(
        db,
        PRODUCTIVITY_FINANCE_KEY,
        normalize_productivity_finance_settings(value),
        user_id=user_id,
        business_id=business_id,
    )


def get_sidebar_layout(db: Session, business_id: int | None = None) -> list[dict]:
    value = get_json_setting(db, SIDEBAR_LAYOUT_KEY, default=[], business_id=business_id)
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        parent_id = item.get("parent_id")
        normalized.append({
            **item,
            "id": normalize_role_view_id(item.get("id")),
            "parent_id": normalize_role_view_id(parent_id) if parent_id else None,
        })
    return normalized


def set_sidebar_layout(
    db: Session,
    items: list[dict],
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    return set_json_setting(db, SIDEBAR_LAYOUT_KEY, items, user_id=user_id, business_id=business_id)


def get_role_view_access(db: Session, business_id: int | None = None) -> dict:
    value = get_json_setting(db, ROLE_VIEW_ACCESS_KEY, default={})
    return normalize_role_view_access_ids(value) if isinstance(value, dict) else {}


def set_role_view_access(
    db: Session,
    access: dict,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    return set_json_setting(db, ROLE_VIEW_ACCESS_KEY, access, user_id=user_id)
