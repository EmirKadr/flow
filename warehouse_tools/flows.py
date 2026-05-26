"""Flöden: ett API-handtag per CLI-kommando i allokering12.1.py.

Varje handler tar emot:
  files  - dict {input_key: Path till temporär uppladdad fil}
  params - dict {input_key: strängvärde} för text/nummer/textarea-fält

och returnerar en standarddict:
  {
    "summary": {etikett: värde, ...},   # visas som kort
    "tables":  [(key, label, DataFrame), ...],
    "text":    str | None,              # fritext-rapport (vecka27)
    "log":     [str, ...],
  }

All domänlogik kommer från motorn - inga beräkningar dupliceras här.
"""
from __future__ import annotations

import io
import json
import tempfile
import unicodedata
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from .engine import engine as E
from .surface_generation import generate_surface_plan, prepare_locations

ORDER_SET_AREA_IMPORT_KEY = "order_set_area_import"
ORDER_SET_AREA_IMPORT_LABEL = "ASK-import order/yta"
ORDER_SET_AREA_IMPORT_FILENAME = "v_ask_order_overview_order_set_area_execute_command.csv"
ORDER_SET_AREA_IMPORT_COLUMNS = ["area_num", "company", "order_num", "pick_zone"]

NEAR_MISS_COLUMNS = [
    "Artikel", "OrderID", "OrderRad", "PallID", "Kallplats", "Mottagen",
    "Behov_vid_tillfallet", "Pall_kvantitet", "Skillnad",
    "Procentuell skillnad (%)", "Anledning", "Gäller (INSTEAD R/A)",
]

ALLOCATE_DISPLAY_SUMMARY_TYPES = [
    ("Helpall", "HELPALL", "pallar"),
    ("Autostore", "AUTOSTORE", "rader"),
    ("Huvudplock", "HUVUDPLOCK", "rader"),
    ("Skrymmande", "SKRYMMANDE", "rader"),
    ("E-Handel", "EHANDEL", "rader"),
    ("HIB", "HIB", "rader"),
]

ORDERSALDO_HELPALL_COLUMN = "Antal på Helpall"


DEFAULT_MAX_CSV_PARAM = "__default_max_csv_path"
FileVersion = tuple[str, int, int]


@lru_cache(maxsize=32)
def _read_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return E._read_cli_table(path)


def _read(path: Path) -> pd.DataFrame:
    source = Path(path).resolve()
    stat = source.stat()
    return _read_cached(str(source), stat.st_size, stat.st_mtime_ns).copy(deep=True)


def _file_version(path: Path | str) -> FileVersion:
    source = Path(path).resolve()
    stat = source.stat()
    return str(source), stat.st_size, stat.st_mtime_ns


def _optional_file_version(files: dict, key: str) -> FileVersion | None:
    if key not in files:
        return None
    return _file_version(files[key])


@lru_cache(maxsize=32)
def _prepared_locations_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return prepare_locations(_read(Path(path)))


def _read_prepared_locations(path: Path) -> pd.DataFrame:
    source = Path(path).resolve()
    stat = source.stat()
    return _prepared_locations_cached(str(source), stat.st_size, stat.st_mtime_ns)


def clear_prepared_location_cache() -> None:
    _prepared_locations_cached.cache_clear()


def warm_prepared_locations(path: str | Path) -> None:
    _read_prepared_locations(Path(path))


@lru_cache(maxsize=32)
def _normalized_saldo_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return E.normalize_saldo(_read(Path(path)))


def _read_normalized_saldo(version: FileVersion | None) -> pd.DataFrame | None:
    if version is None:
        return None
    return _normalized_saldo_cached(*version).copy(deep=True)


@lru_cache(maxsize=32)
def _normalized_items_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return E.normalize_items(_read(Path(path)))


def _read_normalized_items(version: FileVersion | None) -> pd.DataFrame | None:
    if version is None:
        return None
    return _normalized_items_cached(*version).copy(deep=True)


@lru_cache(maxsize=32)
def _normalized_not_putaway_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return E.normalize_not_putaway(_read(Path(path)))


def _read_normalized_not_putaway(version: FileVersion | None) -> pd.DataFrame | None:
    if version is None:
        return None
    return _normalized_not_putaway_cached(*version).copy(deep=True)


@lru_cache(maxsize=16)
def _allocation_outputs_cached(
    orders_version: FileVersion,
    buffer_version: FileVersion,
    saldo_version: FileVersion | None,
    item_version: FileVersion | None,
    not_putaway_version: FileVersion | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    orders_raw = _read(Path(orders_version[0]))
    buffer_raw = _read(Path(buffer_version[0]))
    saldo_norm = _read_normalized_saldo(saldo_version)
    item_norm = _read_normalized_items(item_version)
    not_putaway_norm = _read_normalized_not_putaway(not_putaway_version)

    log: list[str] = []
    result_df, near_miss_df = E.allocate(orders_raw, buffer_raw, log=log.append)
    result_df = E.App._reclassify_skrymmande(result_df, saldo_norm)
    result_df = E._merge_item_flags(result_df, item_norm)
    if near_miss_df.empty and len(near_miss_df.columns) == 0:
        near_miss_df = pd.DataFrame(columns=NEAR_MISS_COLUMNS)

    refill_hp_df, refill_autostore_df = E.calculate_refill(
        result_df, buffer_raw, saldo_df=saldo_norm, not_putaway_df=not_putaway_norm,
    )
    pallet_spaces_df = E.compute_pallet_spaces(result_df)
    return result_df, near_miss_df, refill_hp_df, refill_autostore_df, pallet_spaces_df, tuple(log)


def clear_allocation_cache() -> None:
    _allocation_outputs_cached.cache_clear()
    _normalized_saldo_cached.cache_clear()
    _normalized_items_cached.cache_clear()
    _normalized_not_putaway_cached.cache_clear()


def _temp(suffix: str) -> Path:
    """En unik temporär sökväg som ännu inte finns (motorn skapar filen)."""
    return Path(tempfile.gettempdir()) / f"allok_{uuid.uuid4().hex}{suffix}"


def _max_csv_path(files: dict, params: dict) -> Path:
    if "max_csv" in files:
        return Path(files["max_csv"])
    if params.get(DEFAULT_MAX_CSV_PARAM):
        return Path(params[DEFAULT_MAX_CSV_PARAM])
    return E._resolve_max_csv_path(None)


def _column_key(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in text.strip().lower() if ch.isalnum())


def _find_table_column(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    lookup = {_column_key(column): column for column in df.columns}
    for alias in aliases:
        column = lookup.get(_column_key(alias))
        if column is not None:
            return column
    return None


def _clean_cell(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "nat", "none"} else text


def _split_order_numbers(value: object) -> list[str]:
    text = _clean_cell(value)
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _tsv_content(df: pd.DataFrame) -> str:
    output = io.StringIO()
    df.to_csv(output, sep="\t", index=False, lineterminator="\n")
    return output.getvalue()


def build_order_set_area_import(forecast_df: pd.DataFrame, assignments_df: pd.DataFrame) -> tuple[pd.DataFrame | None, str | None]:
    forecast_shipment_col = _find_table_column(forecast_df, ("Sändningsnr", "Sandningsnr", "Grupp", "Shipment"))
    order_col = _find_table_column(forecast_df, ("Ordernummer", "Ordernr", "order_num"))
    assignment_shipment_col = _find_table_column(assignments_df, ("Sändningsnr", "Sandningsnr", "Grupp", "Shipment"))
    location_col = _find_table_column(assignments_df, ("Lagerplats", "Location", "area_num"))

    if forecast_shipment_col is None:
        return None, "ASK-importfil skapades inte: Forecast saknar sändningsnummer."
    if order_col is None:
        return None, "ASK-importfil skapades inte: Forecast saknar kolumnen Ordernummer."
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
    for _, forecast_row in forecast_df.iterrows():
        shipment_key = _clean_cell(forecast_row.get(forecast_shipment_col))
        if not shipment_key:
            continue
        order_numbers = _split_order_numbers(forecast_row.get(order_col))
        if order_numbers:
            orders_by_shipment.setdefault(shipment_key, []).extend(order_numbers)

    rows: list[dict[str, str]] = []
    missing_order_shipments: list[str] = []
    for shipment_key, area_num in surfaces_by_shipment.items():
        order_numbers = orders_by_shipment.get(shipment_key, [])
        if not order_numbers:
            missing_order_shipments.append(shipment_key)
            continue
        rows.extend(
            {
                "area_num": area_num,
                "company": "MG",
                "order_num": order_num,
                "pick_zone": "A",
            }
            for order_num in order_numbers
        )

    if missing_order_shipments:
        sample = ", ".join(missing_order_shipments[:5])
        return None, f"ASK-importfil skapades inte: {len(missing_order_shipments)} placerade sändningar saknar ordernummer ({sample})."
    if not rows:
        return None, "ASK-importfil skapades inte: inga placerade ordernummer hittades."
    return pd.DataFrame(rows, columns=ORDER_SET_AREA_IMPORT_COLUMNS), None


def build_allocate_display_summary(
    result_df: pd.DataFrame,
    refill_hp_df: pd.DataFrame,
    refill_autostore_df: pd.DataFrame,
) -> dict[str, str]:
    def column_key(value: object) -> str:
        return "".join(ch for ch in str(value).strip().lower() if ch.isascii() and ch.isalnum())

    ktyp_col = None
    if isinstance(result_df, pd.DataFrame):
        for column in result_df.columns:
            if column_key(column) == "klltyp":
                ktyp_col = column
                break

    if ktyp_col is not None:
        source_counts = (
            result_df[ktyp_col]
            .astype(str)
            .str.strip()
            .str.upper()
            .value_counts()
            .to_dict()
        )
    else:
        source_counts = {}

    summary: dict[str, str] = {}
    for label, source, unit in ALLOCATE_DISPLAY_SUMMARY_TYPES:
        summary[label] = f"{int(source_counts.get(source, 0))} {unit}"
    summary["Refill Autostore"] = f"{len(refill_autostore_df)} rader"
    summary["Refill Huvudplock"] = f"{len(refill_hp_df)} rader"
    return summary


def add_ordersaldo_helpall_count(shortage_df: pd.DataFrame, max_df: pd.DataFrame | None) -> pd.DataFrame:
    result = shortage_df.copy()
    helpall_values = pd.Series("", index=result.index)
    if isinstance(max_df, pd.DataFrame) and not max_df.empty:
        try:
            max_map = E._build_article_max_map(max_df)
            helpall_values = result.index.to_series().astype(str).str.strip().map(max_map).fillna("")
        except Exception:
            helpall_values = pd.Series("", index=result.index)

    if ORDERSALDO_HELPALL_COLUMN in result.columns:
        result = result.drop(columns=[ORDERSALDO_HELPALL_COLUMN])

    insert_at = len(result.columns)
    if "Tillgängligt saldo (Plock)" in result.columns:
        insert_at = list(result.columns).index("Tillgängligt saldo (Plock)") + 1
    result.insert(insert_at, ORDERSALDO_HELPALL_COLUMN, helpall_values)
    return result


# --- Floden ------------------------------------------------------------------

def flow_allocate(files: dict, params: dict) -> dict:
    (
        result_df,
        near_miss_df,
        refill_hp_df,
        refill_autostore_df,
        pallet_spaces_df,
        log_lines,
    ) = _allocation_outputs_cached(
        _file_version(files["orders"]),
        _file_version(files["buffer"]),
        _optional_file_version(files, "saldo"),
        _optional_file_version(files, "items"),
        _optional_file_version(files, "not_putaway"),
    )
    result_df = result_df.copy(deep=True)
    near_miss_df = near_miss_df.copy(deep=True)
    refill_hp_df = refill_hp_df.copy(deep=True)
    refill_autostore_df = refill_autostore_df.copy(deep=True)
    pallet_spaces_df = pallet_spaces_df.copy(deep=True)
    log = list(log_lines)

    return {
        "summary": {
            "Resultatrader": len(result_df),
            "Near-miss": len(near_miss_df),
            "Refill Huvudplock": len(refill_hp_df),
            "Refill AutoStore": len(refill_autostore_df),
            "Pallplatser": len(pallet_spaces_df),
        },
        "display_summary": build_allocate_display_summary(result_df, refill_hp_df, refill_autostore_df),
        "tables": [
            ("result", "Allokerade pallar", result_df),
            ("near_miss", "Near-miss", near_miss_df),
            ("refill_hp", "Refill Huvudplock", refill_hp_df),
            ("refill_autostore", "Refill AutoStore", refill_autostore_df),
            ("pallet_spaces", "Pallplatser", pallet_spaces_df),
        ],
        "log": log,
    }


def flow_ordersaldo(files: dict, params: dict) -> dict:
    orders_df = _read(files["orders"])
    column_names = E._find_ordersaldo_columns(orders_df)
    utbest_map = E.utbest_per_article(_read(files["saldo"])) if "saldo" in files else {}
    complete_orders, shortage_df = E.compute_ordersaldo_data(
        orders_df, utbest_map=utbest_map, column_names=column_names,
    )
    log: list[str] = []
    try:
        max_path = _max_csv_path(files, params)
        shortage_df = add_ordersaldo_helpall_count(shortage_df, _read(Path(max_path)))
    except Exception as exc:  # noqa: BLE001
        shortage_df = add_ordersaldo_helpall_count(shortage_df, None)
        log.append(f"Kunde inte läsa artikel_max.csv för Antal på Helpall: {exc}")
    return {
        "summary": {
            "Kompletta ordrar": len(complete_orders),
            "Artiklar med underskott": len(shortage_df),
        },
        "tables": [
            ("complete", "Kompletta ordrar", pd.DataFrame({"Ordernr": complete_orders})),
            ("shortage", "Underskott", E._df_with_named_index(shortage_df, "Artikel")),
        ],
        "log": log,
    }


def flow_lyx(files: dict, params: dict) -> dict:
    saldo_df = _read(files["saldo"])
    max_path = _max_csv_path(files, params)
    max_df = _read(Path(max_path))
    articles, filtered_rows = E.compute_lyx_articles(saldo_df, max_df)
    return {
        "summary": {"LYX-artiklar": len(articles), "Filtrerade rader": filtered_rows},
        "tables": [("articles", "LYX-artiklar", pd.DataFrame({"Artikel": articles}))],
        "log": [],
    }


def flow_pafyllnadsprio(files: dict, params: dict) -> dict:
    orders_df = _read(files["orders"])
    column_names = E._find_ordersaldo_columns(orders_df)
    utbest_map = E.utbest_per_article(_read(files["saldo"])) if "saldo" in files else {}
    _, shortage_df = E.compute_ordersaldo_data(
        orders_df, utbest_map=utbest_map, column_names=column_names,
    )
    max_path = _max_csv_path(files, params)
    max_df = _read(Path(max_path))

    log: list[str] = []
    window_map_df = None
    mode = "fallback"
    if "overview" in files:
        try:
            overview_df = _read(files["overview"])
            report_df, _bold, log, missing_ref, window_map_df = (
                E.build_pafyllnadsprio_lastningsfonster_report(
                    orders_df, shortage_df, overview_df, max_df, column_names=column_names,
                )
            )
            mode = "lastningsfonster"
        except Exception as exc:  # noqa: BLE001
            log = [f"Lastningsfönster-läge misslyckades, faller tillbaka: {exc}"]
            report_df, missing_ref = E.build_pafyllnadsprio_report(shortage_df, max_df)
    else:
        report_df, missing_ref = E.build_pafyllnadsprio_report(shortage_df, max_df)

    tables = [("report", "Påfyllnadsprio", report_df)]
    if isinstance(window_map_df, pd.DataFrame):
        tables.append(("window_map", "Lastningsfönster", window_map_df))
    return {
        "summary": {
            "Läge": "Lastningsfönster" if mode == "lastningsfonster" else "Standard",
            "Rapportrader": len(report_df),
            "Saknad referens": int(missing_ref),
        },
        "tables": tables,
        "log": log,
    }


def flow_hib_koppling(files: dict, params: dict) -> dict:
    details_df = _read(files["details"])
    overview_df = _read(files["overview"])
    changes_df = E.compute_hib_koppling(details_df, overview_df)
    missed_df = E.compute_missed_departures(details_df, overview_df)
    return {
        "summary": {"Ändringar": len(changes_df), "Missade avgångar": len(missed_df)},
        "tables": [
            ("changes", "Ändringar", changes_df),
            ("missed", "Missade avgångar", missed_df),
        ],
        "log": [],
    }


def flow_overview_check(files: dict, params: dict) -> dict:
    overview_df = _read(files["overview"])
    details_df = _read(files["details"]) if "details" in files else None
    result = E.build_overview_check_result(overview_df, details_df=details_df)
    sheets = E._build_overview_check_sheets(result)
    tables = [(key.lower().replace(" ", "_"), key, df) for key, df in sheets.items()]
    return {
        "summary": {
            "Sändningsrader": len(result.shipment_df),
            "HIB-rader": len(result.hib_df),
        },
        "tables": tables,
        "log": list(result.log_lines or []),
    }


def flow_dispatch_check(files: dict, params: dict) -> dict:
    overview_df = _read(files["overview"])
    dispatch_df = _read(files["dispatch"])
    details_df = _read(files["details"]) if "details" in files else None
    result = E.build_dispatch_check_result(overview_df, dispatch_df, details_df=details_df)
    return {
        "summary": {"Avvikelser": len(result.diff_df)},
        "tables": [("diff", "Dispatchavvikelser", result.diff_df)],
        "log": list(result.log_lines or []),
    }


def flow_vecka27_check(files: dict, params: dict) -> dict:
    orders_df = _read(files["orders"])
    result = E.build_vecka27_check_result(orders_df)
    return {
        "summary": {"Avvikelser": len(result.deviations)},
        "tables": [("report", "Avvikelser", result.report_df)],
        "text": result.report_text,
        "log": list(result.log_lines or []),
    }


def flow_prognos_report(files: dict, params: dict) -> dict:
    if "prognos" not in files and "campaign" not in files:
        raise ValueError("Ange minst en prognosfil eller en kampanjfil.")
    if "saldo" not in files:
        raise ValueError("Saldo/automation krävs - rapporten filtrerar på Robot=Y.")
    prognos_df = E._load_prognos_cli_source(str(files["prognos"])) if "prognos" in files else None
    campaign_df = E._load_campaign_cli_source(str(files["campaign"])) if "campaign" in files else None
    saldo_df = _read(files["saldo"])
    buffer_df = _read(files["buffer"]) if "buffer" in files else None
    result = E.build_prognos_report_result(
        prognos_df=prognos_df, campaign_df=campaign_df, saldo_df=saldo_df, buffer_df=buffer_df,
    )
    meta = result.meta if isinstance(result.meta, dict) else {}
    return {
        "summary": {
            "Rapportrader": len(result.report_df),
            "Kombinerade rader": len(result.combined_df),
            "Partiell": "Ja" if meta.get("partial") == "yes" else "Nej",
        },
        "tables": [
            ("report", "Prognos vs Autoplock", result.report_df),
            ("combined", "Kombinerat underlag", result.combined_df),
        ],
        "log": list(result.log_lines or []),
    }


def flow_observations_update(files: dict, params: dict) -> dict:
    buffer_df = _read(files["buffer"])
    # Skriv till temporära filer - rör aldrig repo-data från demon.
    result = E.build_observations_update_result(
        buffer_df,
        observations_path=str(_temp(".csv.gz")),
        artikel_max_out=str(_temp(".csv")),
        push_to_github=False,
    )
    return {
        "summary": {
            "Nya observationer": result.new_row_count,
            "Skickade pallid": result.github_sent_rows,
            "Artikel-max-rader": result.article_max_rows,
            "Ändrade maxvärden": result.article_max_changed_rows,
        },
        "tables": [("new_rows", "Nya observationer", result.new_rows_df)],
        "log": [
            "Skrivet till temporära filer (repo-data orörd).",
            f"Nya pallid: {result.new_row_count}. Skickade till GitHub: {result.github_sent_rows}.",
            f"Artikel-max ändrade maxvärden: {result.article_max_changed_rows} "
            f"(upp: {result.article_max_increased_rows}, ned: {result.article_max_decreased_rows}, "
            f"nya artiklar: {result.article_max_new_rows}).",
            f"Observations: {result.observations_path}",
            f"Artikel-max: {result.article_max_path}",
        ],
    }


def flow_observations_sync(files: dict, params: dict) -> dict:
    result = E.build_observations_sync_result(
        observations_path=str(_temp(".csv.gz")),
        artikel_max_out=str(_temp(".csv")),
        remote_file=str(files["remote_file"]) if "remote_file" in files else None,
        push_orphaned=False,
    )
    return {
        "summary": {
            "Hämtade rader": result.fetched_rows,
            "Totalt observationer": result.total_observations,
            "Artikel-max-rader": result.article_max_rows,
        },
        "tables": [],
        "log": ["Synkat till temporära filer (repo-data orörd, ingen push)."],
    }


def flow_split_values(files: dict, params: dict) -> dict:
    if "values_file" in files:
        values = E._read_cli_text_lines(str(files["values_file"]))
    else:
        raw = params.get("values") or ""
        values = [line.strip() for line in raw.splitlines() if line.strip()]
    if not values:
        raise ValueError("Inga värden angivna - klistra in eller ladda upp en textfil.")
    try:
        chunk_size = int(params.get("chunk_size") or 2000)
    except ValueError:
        chunk_size = 2000
    result = E.build_chunked_values_result(values, chunk_size=max(1, chunk_size))
    return {
        "summary": {
            "Antal värden": result.value_count,
            "Antal kolumner": result.chunk_count,
            "Per kolumn": result.chunk_size,
        },
        "tables": [("report", "Delade värden", result.report_df)],
        "log": [],
    }


def flow_update_check(files: dict, params: dict) -> dict:
    result = E.build_update_check_cli_result()
    return {
        "summary": {
            "Ny version finns": "Ja" if result.has_update else "Nej",
            "Nuvarande version": result.current_version,
            "Senaste version": result.latest_version,
        },
        "tables": [],
        "text": (
            f"Release: {result.release_url}\nInstallerare: {result.installer_name}"
            if result.has_update
            else "Appen är uppdaterad."
        ),
        "log": [],
    }


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

    from .mg_forecast import forecast as mg_forecast

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
    artifact = {
        "columns": list(forecast_df.columns),
        "rows": forecast_df.to_dict("records"),
        "summary": summary,
    }
    return {
        "summary": summary,
        "tables": [("forecast", "Forecast", forecast_df)],
        "artifacts": {"forecast_json": artifact},
        "log": [
            "Forecast körd fristående i Flow.",
            "Forecast sparad som session-artifact för Ytgenerering.",
        ],
    }


def flow_ytgenerering(files: dict, params: dict) -> dict:
    if "location" not in files:
        raise ValueError("Saknar kärnfilen location/lagerplatser.")

    forecast_df = params.get("__forecast_df")
    if forecast_df is not None and not isinstance(forecast_df, pd.DataFrame):
        forecast_df = pd.DataFrame(forecast_df)

    raw_forecast = params.get("__forecast_json")
    if forecast_df is None and not raw_forecast:
        raise ValueError("Kör Forecast först, så Ytgenerering kan använda forecastens resultat.")

    if forecast_df is None:
        payload = json.loads(raw_forecast)
        rows = payload.get("rows") or []
        columns = payload.get("columns") or None
        forecast_df = pd.DataFrame(rows, columns=columns)
    locations_df = _read_prepared_locations(Path(files["location"]))
    result = generate_surface_plan(forecast_df, locations_df)

    tables = [
        ("ytgenerering", "Ytgenerering", result.assignments),
        ("transportorer", "Transportörsöversikt", result.carrier_overview),
    ]
    if not result.unplaced.empty:
        tables.append(("ej_placerade", "Ej placerade", result.unplaced))

    log = [
        "Lagerplatser filtrerade på Typ U, UTL1-UTL652, minst 6 tecken och Max pall > 0.",
        "Sändningar placerade en och en. Transportör används för sortering och översikt.",
    ]
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
        "download_files": download_files,
        "auto_downloads": auto_downloads,
        "log": log,
    }


# --- Registry ----------------------------------------------------------------
# Varje post: id, label, category, description, inputs[], handler.
# input.type: file | text | number | textarea
# input.detect: lista av filtyper (fran motorns _detect_file_type) som auto-routas hit.

FLOWS: list[dict] = [
    {
        "id": "allocate", "label": "Allokering", "category": "Allokering",
        "description": "Allokera kundorder mot buffertpallar (Helpall -> AutoStore -> Huvudplock, FIFO) med near-miss-loggning, refill och pallplatsberäkning.",
        "handler": flow_allocate,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "buffer", "label": "Buffertpallar", "type": "file", "required": True, "detect": ["buffer"]},
            {"key": "saldo", "label": "Saldo ink. Automation", "type": "file", "required": False, "detect": ["automation"]},
            {"key": "items", "label": "Item option", "type": "file", "required": False, "detect": ["item"]},
            {"key": "not_putaway", "label": "Ej inlagrade", "type": "file", "required": False, "detect": ["not_putaway", "wms_booking"]},
        ],
    },
    {
        "id": "forecast", "label": "Forecast", "category": "Forecast & yta",
        "description": "Prognostisera pallplatser per sändningsnr med lokala orderfiler och kärnfiler.",
        "handler": flow_forecast,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "buffer", "label": "Buffertpallar", "type": "file", "required": True, "detect": ["buffer"]},
        ],
        "coredata": [
            {"key": "custom", "label": "custom", "required": True},
            {"key": "item", "label": "item", "required": True},
            {"key": "item_alias", "label": "item_alias", "required": True},
            {"key": "dimension", "label": "dimension", "required": True},
            {"key": "pallet_type", "label": "pallet_type", "required": True},
            {"key": "item_option", "label": "item_option", "required": True},
        ],
    },
    {
        "id": "ytgenerering", "label": "Ytgenerering", "category": "Forecast & yta",
        "description": "Placera forecastens sändningar på lagerplatser utifrån Max pall och transportör.",
        "handler": flow_ytgenerering,
        "inputs": [],
        "coredata": [
            {"key": "location", "label": "Lagerplatser", "required": True},
        ],
        "requiresSessionFlow": {"flowId": "forecast", "label": "Forecast"},
    },
    {
        "id": "ordersaldo", "label": "Ordersaldo", "category": "Order & saldo",
        "description": "Beräkna kompletta ordrar och artiklar med underskott utifrån Detalj Kundorder(alla).",
        "handler": flow_ordersaldo,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "saldo", "label": "Saldo ink. Automation (Utbestallt)", "type": "file", "required": False, "detect": ["automation"]},
            {"key": "max_csv", "label": "artikel_max.csv (kärnfil)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "lyx", "label": "LYX-artiklar", "category": "Order & saldo",
        "description": "Identifiera LYX-artiklar utifrån en saldofil och artikel_max-referens.",
        "handler": flow_lyx,
        "inputs": [
            {"key": "saldo", "label": "Saldofil", "type": "file", "required": True, "detect": ["automation", "buffer"]},
            {"key": "max_csv", "label": "artikel_max.csv (kärnfil)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "pafyllnadsprio", "label": "Påfyllnadsprio", "category": "Order & saldo",
        "description": "Prioritera påfyllnad utifrån underskott. Med orderöversikt används lastningsfönster-läge.",
        "handler": flow_pafyllnadsprio,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "saldo", "label": "Saldo ink. Automation", "type": "file", "required": False, "detect": ["automation"]},
            {"key": "overview", "label": "Orderöversikt (lastningsfönster)", "type": "file", "required": False, "detect": ["overview"]},
            {"key": "max_csv", "label": "artikel_max.csv (kärnfil)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "hib-koppling", "label": "HIB-koppling", "category": "Kontroller",
        "description": "Räkna ut vilka HIB-ordrar som behöver kopplas om samt missade avgångar.",
        "handler": flow_hib_koppling,
        "inputs": [
            {"key": "details", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
        ],
    },
    {
        "id": "overview-check", "label": "Orderöversiktkontroll", "category": "Kontroller",
        "description": "Hitta sändningsnr med flera kunder/transportörer och HIB utan butikssändning.",
        "handler": flow_overview_check,
        "inputs": [
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "details", "label": "Detalj Kundorder(alla) (kundnamn)", "type": "file", "required": False, "detect": ["orders"]},
        ],
    },
    {
        "id": "dispatch-check", "label": "Dispatchkontroll", "category": "Kontroller",
        "description": "Jämför orderöversikt mot dispatchpallar och lista avvikelser.",
        "handler": flow_dispatch_check,
        "inputs": [
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "dispatch", "label": "Dispatchpallar", "type": "file", "required": True, "detect": ["dispatch"]},
            {"key": "details", "label": "Detalj Kundorder(alla) (kundnamn)", "type": "file", "required": False, "detect": ["orders"]},
        ],
    },
    {
        "id": "vecka27-check", "label": "Vecka 27-kontroll", "category": "Kontroller",
        "description": "Kontrollera orderrader mot vecka 27-reglerna.",
        "handler": flow_vecka27_check,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
        ],
    },
    {
        "id": "prognos-report", "label": "Prognosrapport", "category": "Sökning & prognos",
        "description": "Bygg prognos-/kampanjrapport mot autoplock. Saldo krävs (Robot=Y-filter).",
        "handler": flow_prognos_report,
        "inputs": [
            {"key": "prognos", "label": "Prognosfil", "type": "file", "required": False, "detect": ["prognos"]},
            {"key": "campaign", "label": "Kampanjfil", "type": "file", "required": False, "detect": ["campaign"]},
            {"key": "saldo", "label": "Saldo ink. Automation", "type": "file", "required": True, "detect": ["automation"]},
            {"key": "buffer", "label": "Buffertpallar", "type": "file", "required": False, "detect": ["buffer"]},
        ],
    },
    {
        "id": "observations-update", "label": "Observations-uppdatering", "category": "Data & verktyg",
        "description": "Lägg till nya status-30-pallar i observations och räkna om artikel_max. Skriver till temporära filer.",
        "handler": flow_observations_update,
        "inputs": [
            {"key": "buffer", "label": "Buffertpallar", "type": "file", "required": True, "detect": ["buffer"]},
        ],
    },
    {
        "id": "observations-sync", "label": "Observations-synk", "category": "Data & verktyg",
        "description": "Hämta observations från GitHub (eller en lokal fil). Ingen push, skriver till temporära filer.",
        "handler": flow_observations_sync,
        "inputs": [
            {"key": "remote_file", "label": "Lokal observationsfil (valfri)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "split-values", "label": "Dela värden", "category": "Data & verktyg",
        "description": "Dela en lång lista av värden i kolumner med valbar kolumnstorlek.",
        "handler": flow_split_values,
        "inputs": [
            {"key": "values", "label": "Värden (ett per rad)", "type": "textarea", "required": False},
            {"key": "values_file", "label": "...eller ladda upp textfil", "type": "file", "required": False, "detect": []},
            {"key": "chunk_size", "label": "Antal per kolumn", "type": "number", "required": False, "default": "2000"},
        ],
    },
    {
        "id": "update-check", "label": "Uppdateringskoll", "category": "Data & verktyg",
        "description": "Kontrollera om en nyare version av appen finns på GitHub.",
        "handler": flow_update_check,
        "inputs": [],
    },
]

FLOW_BY_ID: dict[str, dict] = {flow["id"]: flow for flow in FLOWS}

# Flöden som visas som egna vyer. Allt övrigt samlas i den kombinerade
# huvudvyn där filerna delas mellan körningarna.
SOLO_FLOWS = {
    "observations-update",
    "observations-sync",
    "split-values",
    "update-check",
}


# Gemensam datapool: combined-flöden laddar upp filerna EN gång här, och
# varje flödes filinput mappas till en pool-nyckel. Endast "details" skiljer
# sig från sin pool-nyckel (samma filformat som "orders").
DATA_POOL: list[dict] = [
    {"key": "orders", "label": "Detalj Kundorder(alla)", "detect": ["orders"]},
    {"key": "buffer", "label": "Buffertpallar", "detect": ["buffer"]},
    {"key": "saldo", "label": "Saldo ink. Automation", "detect": ["automation"]},
    {"key": "overview", "label": "Orderöversikt", "detect": ["overview"]},
    {"key": "dispatch", "label": "Dispatchpallar", "detect": ["dispatch"]},
    {"key": "items", "label": "Item option", "detect": ["item"]},
    {"key": "not_putaway", "label": "Ej inlagrade", "detect": ["not_putaway", "wms_booking"]},
    {"key": "prognos", "label": "Prognosfil", "detect": ["prognos"]},
    {"key": "campaign", "label": "Kampanjfil", "detect": ["campaign"]},
    {"key": "max_csv", "label": "artikel_max.csv", "detect": []},
]

_POOL_KEY_OVERRIDE = {"details": "orders"}


def _pool_key(input_key: str) -> str:
    return _POOL_KEY_OVERRIDE.get(input_key, input_key)


def public_registry() -> list[dict]:
    """Registret utan handler-referenser - sant till frontenden.

    Varje flöde får ett ``view``-fält: ``solo`` (egen vy) eller
    ``combined`` (delar huvudvyn med övriga combined-flöden). Filinputs i
    combined-flöden får en ``pool``-nyckel mot den gemensamma datapoolen.
    """
    result: list[dict] = []
    for flow in FLOWS:
        view = "solo" if flow["id"] in SOLO_FLOWS else "combined"
        inputs: list[dict] = []
        for inp in flow["inputs"]:
            new_inp = dict(inp)
            if view == "combined" and inp.get("type") == "file":
                new_inp["pool"] = _pool_key(inp["key"])
            inputs.append(new_inp)
        result.append({
            **{key: value for key, value in flow.items() if key != "handler"},
            "inputs": inputs,
            "view": view,
        })
    return result


def public_pool() -> list[dict]:
    """Datapoolens slots - sänt till frontenden för den kombinerade vyn."""
    return [dict(slot) for slot in DATA_POOL]
