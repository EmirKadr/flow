"""Forecast, ytgenerering och order/yta-importen."""
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
    _find_table_column,
    _split_order_numbers,
    _tsv_content,
)

ORDER_SET_AREA_IMPORT_KEY = "order_set_area_import"

ORDER_SET_AREA_IMPORT_LABEL = "ASK-import order/yta"

ORDER_SET_AREA_IMPORT_FILENAME = "v_ask_order_overview_order_set_area_execute_command.csv"

ORDER_SET_AREA_IMPORT_COLUMNS = ["area_num", "company", "order_num", "pick_zone"]

YTGENERERING_UTL_MIN_PARAM = "__ytgenerering_utl_min"

YTGENERERING_UTL_MAX_PARAM = "__ytgenerering_utl_max"

YTGENERERING_UTL_DEFAULT_MIN = 1

YTGENERERING_UTL_DEFAULT_MAX = 652

@lru_cache(maxsize=32)
def _prepared_locations_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return prepare_locations(shared._read(Path(path)))

def _read_prepared_locations(path: Path) -> pd.DataFrame:
    source = Path(path).resolve()
    stat = source.stat()
    return _prepared_locations_cached(str(source), stat.st_size, stat.st_mtime_ns)

def clear_prepared_location_cache() -> None:
    _prepared_locations_cached.cache_clear()

def warm_prepared_locations(path: str | Path) -> None:
    _read_prepared_locations(Path(path))

def _ytgenerering_utl_number(value: object, fallback: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        number = fallback
    return max(YTGENERERING_UTL_DEFAULT_MIN, min(YTGENERERING_UTL_DEFAULT_MAX, number))

def _ytgenerering_utl_range(params: dict) -> tuple[int, int]:
    min_number = _ytgenerering_utl_number(params.get(YTGENERERING_UTL_MIN_PARAM), YTGENERERING_UTL_DEFAULT_MIN)
    max_number = _ytgenerering_utl_number(params.get(YTGENERERING_UTL_MAX_PARAM), YTGENERERING_UTL_DEFAULT_MAX)
    if min_number > max_number:
        min_number, max_number = max_number, min_number
    return min_number, max_number

def _filter_ytgenerering_locations(locations: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, str]:
    min_number, max_number = _ytgenerering_utl_range(params)
    filtered = locations[
        locations["_location_number"].between(min_number, max_number)
    ].copy()
    if filtered.empty:
        raise ValueError(f"Ytgenerering saknar giltiga ytor i UTL{min_number}-UTL{max_number}.")
    return filtered, f"Ytgenerering använder UTL{min_number}-UTL{max_number}."

def build_order_set_area_import(forecast_df: pd.DataFrame, assignments_df: pd.DataFrame) -> tuple[pd.DataFrame | None, str | None]:
    forecast_shipment_col = _find_table_column(forecast_df, ("Sändningsnr", "Sandningsnr", "Grupp", "Shipment"))
    order_col = _find_table_column(forecast_df, ("Ordernummer", "Ordernr", "order_num"))
    company_col = _find_table_column(forecast_df, ("Bolag", "Company", "company"))
    assignment_shipment_col = _find_table_column(assignments_df, ("Sändningsnr", "Sandningsnr", "Grupp", "Shipment"))
    location_col = _find_table_column(assignments_df, ("Lagerplats", "Location", "area_num"))

    if forecast_shipment_col is None:
        return None, "ASK-importfil skapades inte: Forecast saknar sändningsnummer."
    if order_col is None:
        return None, "ASK-importfil skapades inte: Forecast saknar kolumnen Ordernummer."
    if company_col is None:
        return None, "ASK-importfil skapades inte: Forecast saknar kolumnen Bolag."
    if assignment_shipment_col is None or location_col is None:
        return None, "ASK-importfil skapades inte: Ytgenerering saknar sändning/yta-placering."
    if assignments_df.empty:
        return None, "ASK-importfil skapades inte: inga sändningar placerades på yta."

    surfaces_by_shipment: dict[str, str] = {}
    for shipment, group in assignments_df.groupby(assignment_shipment_col, sort=False):
        shipment_key = _clean_cell(shipment)
        surfaces = [_clean_cell(value) for value in group[location_col].tolist()]
        surfaces = [value for value in surfaces if value]
        if shipment_key and surfaces:
            surfaces_by_shipment[shipment_key] = ", ".join(surfaces)

    orders_by_shipment: dict[str, list[str]] = {}
    companies_by_shipment_order: dict[str, dict[str, str]] = {}
    for _, forecast_row in forecast_df.iterrows():
        shipment_key = _clean_cell(forecast_row.get(forecast_shipment_col))
        if not shipment_key:
            continue
        order_numbers = _split_order_numbers(forecast_row.get(order_col))
        if order_numbers:
            orders_by_shipment.setdefault(shipment_key, []).extend(order_numbers)
            company = _clean_cell(forecast_row.get(company_col)).upper()
            if company:
                company_lookup = companies_by_shipment_order.setdefault(shipment_key, {})
                for order_number in order_numbers:
                    company_lookup.setdefault(order_number, company)

    rows: list[dict[str, str]] = []
    missing_order_shipments: list[str] = []
    missing_company_orders: list[str] = []
    for shipment_key, area_num in surfaces_by_shipment.items():
        order_numbers = orders_by_shipment.get(shipment_key, [])
        if not order_numbers:
            missing_order_shipments.append(shipment_key)
            continue
        company_lookup = companies_by_shipment_order.get(shipment_key, {})
        for order_num in order_numbers:
            company = company_lookup.get(order_num, "")
            if not company:
                missing_company_orders.append(order_num)
                continue
            rows.append(
                {
                    "area_num": area_num,
                    "company": company,
                    "order_num": order_num,
                    "pick_zone": "A",
                }
            )

    if missing_order_shipments:
        sample = ", ".join(missing_order_shipments[:5])
        return None, f"ASK-importfil skapades inte: {len(missing_order_shipments)} placerade sändningar saknar ordernummer ({sample})."
    if missing_company_orders:
        sample = ", ".join(missing_company_orders[:5])
        return None, f"ASK-importfil skapades inte: {len(missing_company_orders)} orderrader saknar bolag ({sample})."
    if not rows:
        return None, "ASK-importfil skapades inte: inga placerade ordernummer hittades."
    return pd.DataFrame(rows, columns=ORDER_SET_AREA_IMPORT_COLUMNS), None

FORECAST_FILE_LABELS = {
    "orders": "v_ask_customer_order_details_all",
    "overview": "v_ask_order_overview",
    "buffer": "v_ask_article_buffertpallet",
    "custom": "custom",
    "item": "item",
    "item_alias": "item_alias",
    "dimension": "dimension",
    "pallet_type": "pallet_type",
    "item_option": "item_option",
    "trans_agency": "transportorer",
}

def _require_files(files: dict, required: list[str]) -> None:
    missing = [FORECAST_FILE_LABELS.get(key, key) for key in required if key not in files]
    if missing:
        raise ValueError("Saknar filer: " + ", ".join(missing))

def flow_forecast(files: dict, params: dict) -> dict:
    required = [
        "orders",
        "overview",
        "buffer",
        "custom",
        "item",
        "item_alias",
        "dimension",
        "pallet_type",
        "item_option",
    ]
    _require_files(files, required)

    from ..mg_forecast import forecast as mg_forecast

    file_map = {
        "orders": Path(files["orders"]),
        "overview": Path(files["overview"]),
        "buffert": Path(files["buffer"]),
        "custom": Path(files["custom"]),
        "item": Path(files["item"]),
        "item_alias": Path(files["item_alias"]),
        "dimension": Path(files["dimension"]),
        "pallet_type": Path(files["pallet_type"]),
        "item_option": Path(files["item_option"]),
    }

    try:
        with tempfile.TemporaryDirectory(prefix="flow_forecast_") as tmp:
            fore_dir = mg_forecast.stage_support_files(file_map, tmp)
            forecast_df, raw_summary = mg_forecast.run_forecast(file_map["orders"], data_fore=fore_dir)
    except ImportError as exc:
        raise RuntimeError(
            "Forecast kräver ML-beroenden. Kör installation från app/requirements.txt och prova igen."
        ) from exc

    summary = {
        "Sändningar": int(raw_summary.get("antal_grupper", len(forecast_df))),
        "Predikterade pallplatser": raw_summary.get("summa_pallplatser", 0),
        "Medel pallplatser": raw_summary.get("medel_pallplatser", 0),
        "Max pallplatser": raw_summary.get("max_pallplatser", 0),
    }
    artifacts = {}
    carrier_clusters = None
    log = [
        "Forecast körd fristående i Flow.",
        "Forecast sparad som session-tabell för Ytgenerering.",
    ]
    if "trans_agency" in files:
        carrier_clusters = read_carrier_clusters(Path(files["trans_agency"]))
        artifacts["carrier_clusters"] = carrier_clusters
        log.append(
            f"Transportörskluster inlästa från kärnfil: {len(carrier_clusters.get('rows') or [])} transportörsrader."
        )
    return {
        "summary": summary,
        "tables": [("forecast", "Forecast", forecast_df)],
        "artifacts": artifacts,
        "carrier_clusters": carrier_clusters,
        "log": log,
    }

def _forecast_dataframe_from_params(params: dict) -> pd.DataFrame | None:
    forecast_df = params.get("__forecast_df")
    if forecast_df is not None and not isinstance(forecast_df, pd.DataFrame):
        return pd.DataFrame(forecast_df)
    if forecast_df is not None:
        return forecast_df

    raw_forecast = params.get("__forecast_json")
    if not raw_forecast:
        return None
    payload = json.loads(raw_forecast)
    rows = payload.get("rows") or []
    columns = payload.get("columns") or None
    return pd.DataFrame(rows, columns=columns)

def _forecast_dataframe_from_result(result: dict) -> pd.DataFrame:
    for key, _label, table in result.get("tables") or []:
        if key == "forecast":
            if isinstance(table, pd.DataFrame):
                return table
            return pd.DataFrame(table)
    raise ValueError("Forecast-resultatet saknar tabellen Forecast.")

def _flow_ytgenerering_from_forecast_df(forecast_df: pd.DataFrame, files: dict, params: dict) -> dict:
    if "location" not in files:
        raise ValueError("Saknar kärnfilen location/lagerplatser.")
    locations_df = _read_prepared_locations(Path(files["location"]))
    map_locations = normalize_map_location_rows(params.get("__ytgenerering_map_locations_json"))
    locations_df, added_map_locations = extend_locations_with_map_layout(locations_df, map_locations)
    locations_df, area_log = _filter_ytgenerering_locations(locations_df, params)
    carrier_clusters = normalize_carrier_cluster_payload(params.get("__carrier_clusters_json"))
    result = generate_surface_plan(forecast_df, locations_df, carrier_clusters=carrier_clusters)
    map_payload = build_ytgenerering_map_payload(result.assignments, result.unplaced, locations_df, forecast_df, map_locations)

    tables = [
        ("ytgenerering", "Ytgenerering", result.assignments),
        ("transportorer", "Transportörsöversikt", result.carrier_overview),
    ]
    if not result.unplaced.empty:
        tables.append(("ej_placerade", "Ej placerade", result.unplaced))

    log = [
        "Lagerplatser filtrerade på Typ U, UTL-nummer 1-652 och Max pall > 0.",
        "Sändningar placerade en och en. Transportörskluster styr sortering och UTL-område när kluster finns.",
    ]
    if area_log:
        log.insert(1, area_log)
    if added_map_locations:
        log.append(f"Ytkartsinställningar lade till {added_map_locations} ytor som saknades i location-underlaget.")
    if carrier_clusters and carrier_clusters.get("rows"):
        log.append(f"Transportörskluster använda: {len(carrier_clusters['rows'])} rader.")
    download_files: dict[str, dict[str, str]] = {}
    auto_downloads: list[dict[str, str]] = []
    if result.unplaced.empty:
        import_df, import_log = build_order_set_area_import(forecast_df, result.assignments)
        if import_df is not None:
            tables.append((ORDER_SET_AREA_IMPORT_KEY, ORDER_SET_AREA_IMPORT_LABEL, import_df))
            download_files[ORDER_SET_AREA_IMPORT_KEY] = {
                "filename": ORDER_SET_AREA_IMPORT_FILENAME,
                "content": _tsv_content(import_df),
                "media_type": "text/csv",
            }
            auto_downloads.append(
                {
                    "key": ORDER_SET_AREA_IMPORT_KEY,
                    "filename": ORDER_SET_AREA_IMPORT_FILENAME,
                }
            )
            log.append(f"ASK-importfil skapad: {len(import_df)} orderrader.")
        elif import_log:
            log.append(import_log)
    else:
        log.append("ASK-importfil skapades inte: Ytgenerering har ej placerade sändningar.")

    summary = {
        "Sändningar": result.summary["antal_sändningar"],
        "Använda lagerplatser": result.summary["använda_lagerplatser"],
        "Placerade pallplatser": result.summary["placerade_pallplatser"],
        "Ej placerade pallplatser": result.summary["ej_placerade_pallplatser"],
    }
    return {
        "summary": summary,
        "tables": tables,
        "maps": [map_payload],
        "download_files": download_files,
        "auto_downloads": auto_downloads,
        "log": log,
    }

def flow_ytgenerering(files: dict, params: dict) -> dict:
    forecast_df = _forecast_dataframe_from_params(params)
    if forecast_df is not None:
        return _flow_ytgenerering_from_forecast_df(forecast_df, files, params)

    forecast_result = flow_forecast(files, params)
    forecast_df = _forecast_dataframe_from_result(forecast_result)
    if "location" not in files:
        log = list(forecast_result.get("log") or [])
        log.append("Location/lagerplatser saknas eller kunde inte hämtas - visar endast Forecast.")
        return {**forecast_result, "log": log, "maps": [], "download_files": {}, "auto_downloads": []}

    ytgenerering_params = dict(params)
    carrier_clusters = forecast_result.get("carrier_clusters")
    if carrier_clusters and "__carrier_clusters_json" not in ytgenerering_params:
        ytgenerering_params["__carrier_clusters_json"] = json.dumps(carrier_clusters, ensure_ascii=False)
    ytgenerering_result = _flow_ytgenerering_from_forecast_df(forecast_df, files, ytgenerering_params)

    summary = dict(forecast_result.get("summary") or {})
    summary.update(ytgenerering_result.get("summary") or {})
    return {
        "summary": summary,
        "tables": list(forecast_result.get("tables") or []) + list(ytgenerering_result.get("tables") or []),
        "artifacts": forecast_result.get("artifacts") or {},
        "maps": ytgenerering_result.get("maps") or [],
        "download_files": ytgenerering_result.get("download_files") or {},
        "auto_downloads": ytgenerering_result.get("auto_downloads") or [],
        "carrier_clusters": carrier_clusters,
        "log": list(forecast_result.get("log") or []) + list(ytgenerering_result.get("log") or []),
    }

shared.register_runtime_caches([_prepared_locations_cached], clear_prepared_location_cache)
