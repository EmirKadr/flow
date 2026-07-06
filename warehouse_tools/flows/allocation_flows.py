"""Allokering, ordersaldo, lyx och pafyllnadsprio."""
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
    FileVersion,
    _file_version,
    _max_csv_path,
    _optional_file_version,
)

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

@lru_cache(maxsize=32)
def _normalized_saldo_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return E.normalize_saldo(shared._read(Path(path)))

def _read_normalized_saldo(version: FileVersion | None) -> pd.DataFrame | None:
    if version is None:
        return None
    return _normalized_saldo_cached(*version).copy(deep=True)

@lru_cache(maxsize=32)
def _normalized_items_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return E.normalize_items(shared._read(Path(path)))

def _read_normalized_items(version: FileVersion | None) -> pd.DataFrame | None:
    if version is None:
        return None
    return _normalized_items_cached(*version).copy(deep=True)

@lru_cache(maxsize=32)
def _normalized_not_putaway_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return E.normalize_not_putaway(shared._read(Path(path)))

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
    orders_raw = shared._read(Path(orders_version[0]))
    buffer_raw = shared._read(Path(buffer_version[0]))
    saldo_norm = _read_normalized_saldo(saldo_version)
    item_norm = _read_normalized_items(item_version)
    not_putaway_norm = _read_normalized_not_putaway(not_putaway_version)

    log: list[str] = []
    result_df, near_miss_df = E.allocate(orders_raw, buffer_raw, log=log.append)
    result_df = E.reclassify_skrymmande(result_df, saldo_norm)
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
    orders_df = shared._read(files["orders"])
    column_names = E._find_ordersaldo_columns(orders_df)
    utbest_map = E.utbest_per_article(shared._read(files["saldo"])) if "saldo" in files else {}
    complete_orders, shortage_df = E.compute_ordersaldo_data(
        orders_df, utbest_map=utbest_map, column_names=column_names,
    )
    log: list[str] = []
    try:
        max_path = _max_csv_path(files, params)
        shortage_df = add_ordersaldo_helpall_count(shortage_df, shared._read(Path(max_path)))
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
    saldo_df = shared._read(files["saldo"])
    max_path = _max_csv_path(files, params)
    max_df = shared._read(Path(max_path))
    articles, filtered_rows = E.compute_lyx_articles(saldo_df, max_df)
    return {
        "summary": {"LYX-artiklar": len(articles), "Filtrerade rader": filtered_rows},
        "tables": [("articles", "LYX-artiklar", pd.DataFrame({"Artikel": articles}))],
        "log": [],
    }

def flow_pafyllnadsprio(files: dict, params: dict) -> dict:
    orders_df = shared._read(files["orders"])
    column_names = E._find_ordersaldo_columns(orders_df)
    utbest_map = E.utbest_per_article(shared._read(files["saldo"])) if "saldo" in files else {}
    _, shortage_df = E.compute_ordersaldo_data(
        orders_df, utbest_map=utbest_map, column_names=column_names,
    )
    max_path = _max_csv_path(files, params)
    max_df = shared._read(Path(max_path))

    log: list[str] = []
    window_map_df = None
    mode = "fallback"
    if "overview" in files:
        try:
            overview_df = shared._read(files["overview"])
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

shared.register_runtime_caches(
    [
        _normalized_saldo_cached,
        _normalized_items_cached,
        _normalized_not_putaway_cached,
        _allocation_outputs_cached,
    ],
    clear_allocation_cache,
)
