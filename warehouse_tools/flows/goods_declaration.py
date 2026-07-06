"""Farligt gods-deklarationen (ADR/LQ/sjo, Gotland)."""
from __future__ import annotations

import io
import json
import tempfile
import time
import unicodedata
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from ..carrier_clusters import normalize_carrier_cluster_payload, read_carrier_clusters
from ..engine import engine as E
from ..surface_generation import generate_surface_plan, prepare_locations
from ..ytgenerering_map import (
    build_ytgenerering_map_payload,
    extend_locations_with_map_layout,
    normalize_map_location_rows,
)

from . import shared
from .shared import (
    _clean_cell,
    _find_required_column,
    _find_table_column,
    _normalize_lookup_value,
)

GOTLAND_POSTCODE_MIN = 62000

GOTLAND_POSTCODE_MAX = 62499

GOTLAND_POSTCODE_ROWS = [
    {"Postnummer": "620 00-620 99", "Exempel": "Burgsvik, Havdhem, Hemse, Stånga, Ljugarn, Klintehamn, Romakloster, Slite"},
    {"Postnummer": "621 00-621 99", "Exempel": "Visby"},
    {"Postnummer": "622 00-622 99", "Exempel": "Visby, Västerhejde, Tofta, Romakloster"},
    {"Postnummer": "623 00-623 99", "Exempel": "Hemse, Klintehamn, Burgsvik, Stånga, Ljugarn"},
    {"Postnummer": "624 00-624 99", "Exempel": "Slite, Lärbro, Tingstäde, Fårösund, Fårö"},
]

def _dangerous_goods_level(value: object) -> str:
    text = _clean_cell(value).upper()
    if "DG" in text:
        return "DG"
    if "LQ" in text:
        return "LQ"
    return ""

def _postcode_digits(value: object) -> str:
    return "".join(ch for ch in _clean_cell(value) if ch.isdigit())

def _is_gotland_postcode(value: object) -> bool:
    digits = _postcode_digits(value)
    if len(digits) < 5:
        return False
    try:
        number = int(digits[:5])
    except ValueError:
        return False
    return GOTLAND_POSTCODE_MIN <= number <= GOTLAND_POSTCODE_MAX

def _security_levels_by_item(security_df: pd.DataFrame) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    item_col = _find_required_column(security_df, ("Artikel", "Artikelnummer", "Item", "Item Num"), "Artikel Säkerhetsinformation")
    company_col = _find_table_column(security_df, ("Bolag", "Company"))
    level_col = _find_required_column(
        security_df,
        ("Farligt gods nivå", "Farligt gods niva", "Farligt gods niv", "Farliggods", "Dangerous goods level"),
        "Artikel Säkerhetsinformation",
    )
    priority = {"": 0, "LQ": 1, "DG": 2}
    by_item_company: dict[tuple[str, str], str] = {}
    by_item: dict[str, str] = {}
    for _, row in security_df.iterrows():
        item = _normalize_lookup_value(row.get(item_col))
        if not item:
            continue
        company = _normalize_lookup_value(row.get(company_col)).upper() if company_col else ""
        level = _dangerous_goods_level(row.get(level_col))
        if not level:
            continue
        key = (item, company)
        if priority[level] > priority.get(by_item_company.get(key, ""), 0):
            by_item_company[key] = level
        if priority[level] > priority.get(by_item.get(item, ""), 0):
            by_item[item] = level
    return by_item_company, by_item

def _address_sea_lookup(custom_adr_df: pd.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    customer_col = _find_required_column(custom_adr_df, ("Kund", "Kundnr", "Custom Num"), "Alternativ Leveransadress")
    post_col = _find_required_column(custom_adr_df, ("Post nr", "Postnummer", "Post Num", "Post No"), "Alternativ Leveransadress")
    adr_col = _find_table_column(custom_adr_df, ("Adr num", "Alt adress", "Custom Adr Num", "Custom_Adr_Num"))
    if adr_col is None:
        raise ValueError("Alternativ Leveransadress saknar kolumn: Adr num")
    address_by_customer_adr: dict[tuple[str, str], dict[str, object]] = {}

    for _, row in custom_adr_df.iterrows():
        customer = _normalize_lookup_value(row.get(customer_col))
        adr_num = _normalize_lookup_value(row.get(adr_col))
        if not customer or not adr_num:
            continue
        post_code = _clean_cell(row.get(post_col))
        address_by_customer_adr[(customer, adr_num)] = {
            "post_code": post_code,
            "is_gotland": _is_gotland_postcode(post_code),
        }
    return address_by_customer_adr

def _overview_address_lookup(overview_df: pd.DataFrame) -> dict[str, tuple[str, str]]:
    order_col = _find_required_column(overview_df, ("Ordernr", "Order nr", "Order Num", "order_num"), "Orderöversikt")
    customer_col = _find_required_column(overview_df, ("Kund nr", "Kundnr", "Custom Num", "Kund"), "Orderöversikt")
    adr_col = _find_required_column(overview_df, ("Alt adress", "Adr num", "Custom Adr Num", "Custom_Adr_Num"), "Orderöversikt")
    lookup: dict[str, tuple[str, str]] = {}
    for _, row in overview_df.iterrows():
        order_num = _normalize_lookup_value(row.get(order_col))
        customer = _normalize_lookup_value(row.get(customer_col))
        adr_num = _normalize_lookup_value(row.get(adr_col))
        if order_num and order_num not in lookup:
            lookup[order_num] = (customer, adr_num)
    return lookup

def _order_address_column(orders_df: pd.DataFrame) -> str | None:
    return _find_table_column(orders_df, ("Adr num", "Alt adress", "Custom Adr Num", "Kund Adr", "Custom_Adr_Num"))

def _lq_sea_status(customer: str, adr_num: str, by_customer_adr: dict[tuple[str, str], dict[str, object]]) -> tuple[bool, str, str, str]:
    if not adr_num or adr_num == "0":
        return False, "LQ ej klar: ordern saknar alternativt adressnummer", "", ""
    if not customer:
        return False, "LQ ej klar: kundnummer saknas för adressmatchning", adr_num, ""
    address = by_customer_adr.get((customer, adr_num))
    if address is None:
        return False, "LQ ej klar: adressnumret hittades inte i Alternativ Leveransadress", adr_num, ""
    post_code = _clean_cell(address.get("post_code"))
    if bool(address.get("is_gotland")):
        return True, "LQ Gotland", adr_num, post_code
    return False, f"LQ ej Gotland ({post_code})" if post_code else "LQ ej Gotland", adr_num, post_code

def flow_goods_declaration(files: dict, params: dict) -> dict:
    orders_df = shared._read(files["orders"])
    overview_df = shared._read(files["overview"])
    custom_adr_df = shared._read(files["custom_adr"])
    security_df = shared._read(files["item_security_info"])

    order_col = _find_required_column(orders_df, ("Order nr", "Ordernr", "Order Num", "order_num"), "Detalj Kundorder")
    item_col = _find_required_column(orders_df, ("Artikel", "Artikelnummer", "Item", "Item Num"), "Detalj Kundorder")
    company_col = _find_table_column(orders_df, ("Bolag", "Company"))
    customer_col = _find_table_column(orders_df, ("Kund", "Kundnr", "Custom Num"))
    customer_name_col = _find_table_column(orders_df, ("Kund.1", "Kund namn", "Custom Desc"))
    item_name_col = _find_table_column(orders_df, ("Artikel.1", "Artikel namn", "Item Desc"))
    line_col = _find_table_column(orders_df, ("Rad", "Radnr", "Line Num", "line_num"))
    address_col = _order_address_column(orders_df)

    by_item_company, by_item = _security_levels_by_item(security_df)
    address_by_customer_adr = _address_sea_lookup(custom_adr_df)
    order_address_lookup = _overview_address_lookup(overview_df)

    rows: list[dict[str, object]] = []
    clear_orders: list[str] = []
    seen_orders: set[str] = set()
    for _, row in orders_df.iterrows():
        item = _normalize_lookup_value(row.get(item_col))
        company = _normalize_lookup_value(row.get(company_col)).upper() if company_col else ""
        level = by_item_company.get((item, company)) or by_item.get(item) or ""
        if level not in {"DG", "LQ"}:
            continue
        order_num = _normalize_lookup_value(row.get(order_col))
        clear = False
        reason = ""
        adr_num = ""
        post_code = ""
        if level == "DG":
            clear = True
            reason = "DG"
        else:
            address_customer = _normalize_lookup_value(row.get(customer_col)) if customer_col else ""
            adr_num = _normalize_lookup_value(row.get(address_col)) if address_col else ""
            overview_customer, overview_adr_num = order_address_lookup.get(order_num, ("", ""))
            if overview_adr_num:
                address_customer = overview_customer or address_customer
                adr_num = overview_adr_num
            clear, reason, adr_num, post_code = _lq_sea_status(address_customer, adr_num, address_by_customer_adr)
        if clear and order_num and order_num not in seen_orders:
            seen_orders.add(order_num)
            clear_orders.append(order_num)
        rows.append(
            {
                "Klar": "Ja" if clear else "Nej",
                "Orsak": reason,
                "Farligt gods nivå": level,
                "Ordernr": order_num,
                "Rad": _clean_cell(row.get(line_col)) if line_col else "",
                "Kund": _clean_cell(row.get(customer_col)) if customer_col else "",
                "Kundnamn": _clean_cell(row.get(customer_name_col)) if customer_name_col else "",
                "Artikel": item,
                "Artikelbenämning": _clean_cell(row.get(item_name_col)) if item_name_col else "",
                "Bolag": company,
                "Adr num": adr_num,
                "Post nr": post_code,
            }
        )

    result_df = pd.DataFrame(rows)
    if result_df.empty:
        result_df = pd.DataFrame(
            columns=[
                "Klar",
                "Orsak",
                "Farligt gods nivå",
                "Ordernr",
                "Rad",
                "Kund",
                "Kundnamn",
                "Artikel",
                "Artikelbenämning",
                "Bolag",
                "Adr num",
                "Post nr",
            ]
        )
    clear_lines_df = result_df[result_df["Klar"].eq("Ja")].reset_index(drop=True)
    review_df = result_df[(result_df["Farligt gods nivå"].eq("LQ")) & result_df["Klar"].ne("Ja")].reset_index(drop=True)
    clear_orders_df = pd.DataFrame({"Ordernr": clear_orders})
    postcode_df = pd.DataFrame(GOTLAND_POSTCODE_ROWS)

    lq_rows = result_df[result_df["Farligt gods nivå"].eq("LQ")]
    log = [
        f"Artikel Säkerhetsinformation: {len(by_item)} artiklar med DG/LQ.",
        f"Gotland räknas som postnummer {GOTLAND_POSTCODE_MIN // 100}-{GOTLAND_POSTCODE_MAX // 100}.",
    ]
    log.append("Adressmatchning: Detalj Kundorder.Order nr -> Orderöversikt.Alt adress -> Alternativ Leveransadress.Adr num.")

    return {
        "summary": {
            "DG-rader": int(result_df["Farligt gods nivå"].eq("DG").sum()),
            "LQ-rader": int(len(lq_rows)),
            "LQ sjö/hav": int(lq_rows["Klar"].eq("Ja").sum()) if not lq_rows.empty else 0,
            "Klara ordernummer": len(clear_orders_df),
            "Ej klara LQ": len(review_df),
        },
        "tables": [
            ("clear_orders", "Klara ordernummer", clear_orders_df),
            ("clear_lines", "Klara rader", clear_lines_df),
            ("review_lq", "LQ ej klara", review_df),
            ("gotland_postcodes", "Gotland postnummer", postcode_df),
        ],
        "log": log,
    }
