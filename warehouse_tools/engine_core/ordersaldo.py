"""Ordersaldo, påfyllnadsprio, lastningsfönster och lyx-artiklar."""
from __future__ import annotations

import base64
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .allocation import (
    _safe_str_series,
)
from .constants import (
    DEFAULT_OBSERVATIONS_BUSINESS_CODE,
    LASTNINGSFONSTER_PRIO_COLUMNS,
    LASTNINGSFONSTER_UNKNOWN_LABEL,
    LASTNINGSFONSTER_UNKNOWN_SORT,
    ORDERSALDO_COLUMN_CANDIDATES,
    PAFYLLNADSPRIO_COLUMNS,
)
from .io_utils import (
    _clean_columns,
    find_col,
    to_num,
)
from .observations import (
    business_artikel_max_path,
)
from .runtime_paths import (
    _business_bufferpall_resource_path,
    _legacy_default_bufferpall_resource_path,
)

def _find_lyx_max_csv() -> Optional[Path]:
    candidates = [
        business_artikel_max_path(DEFAULT_OBSERVATIONS_BUSINESS_CODE),
        _business_bufferpall_resource_path(DEFAULT_OBSERVATIONS_BUSINESS_CODE, "artikel_max.csv"),
        _legacy_default_bufferpall_resource_path(DEFAULT_OBSERVATIONS_BUSINESS_CODE, "artikel_max.csv"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate
    return None

def _ordersaldo_norm(value: str) -> str:
    """Normalisera kolumnnamn för robust matchning."""
    txt = str(value).lower()
    txt = txt.replace("å", "a").replace("ä", "a").replace("ö", "o")
    txt = re.sub(r"[^a-z0-9]+", "", txt)
    return txt

def _ordersaldo_find_col(df: pd.DataFrame, candidates: List[str], used_cols: set[str]) -> Optional[str]:
    """Hitta kolumn via exakt/fuzzy match mot kandidater."""
    cols = [str(c) for c in df.columns]
    norm_cols = {col: _ordersaldo_norm(col) for col in cols}
    cand_norm = [_ordersaldo_norm(c) for c in candidates]
    for cand in cand_norm:
        for col, norm_col in norm_cols.items():
            if col in used_cols:
                continue
            if norm_col == cand:
                return col
    for cand in cand_norm:
        for col, norm_col in norm_cols.items():
            if col in used_cols:
                continue
            if cand and cand in norm_col:
                return col
    return None

def _find_ordersaldo_columns(
    df: pd.DataFrame,
    column_candidates: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Optional[str]]:
    candidates = column_candidates or ORDERSALDO_COLUMN_CANDIDATES
    used: set[str] = set()
    order_col = _ordersaldo_find_col(df, candidates["order"], used)
    if order_col:
        used.add(order_col)
    article_col = _ordersaldo_find_col(df, candidates["article"], used)
    if article_col:
        used.add(article_col)
    demand_col = _ordersaldo_find_col(df, candidates["demand"], used)
    if demand_col:
        used.add(demand_col)
    pick_col = _ordersaldo_find_col(df, candidates["pick"], used)
    return {
        "order": order_col,
        "article": article_col,
        "demand": demand_col,
        "pick": pick_col,
    }

def compute_ordersaldo_data(
    df: pd.DataFrame,
    utbest_map: Optional[Dict[str, float]] = None,
    column_names: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[list[str], pd.DataFrame]:
    """
    Beräkna ordersaldo-listor och underskottsdata per artikel från beställningslinjer.

    Returnerar (kompletta_ordrar, underskott_df) där underskott_df har index=artikelnummer
    och kolumnerna Total beställt, Tillgängligt saldo (Plock), Utbeställt, Underskott.
    """
    empty = pd.DataFrame(
        columns=["Total beställt", "Tillgängligt saldo (Plock)", "Utbeställt", "Underskott"]
    )
    if not isinstance(df, pd.DataFrame) or df.empty:
        return [], empty

    calc_df = _clean_columns(df.copy())
    cols = column_names or _find_ordersaldo_columns(calc_df)
    order_col = cols.get("order")
    article_col = cols.get("article")
    demand_col = cols.get("demand")
    pick_col = cols.get("pick")
    if not order_col or not article_col or not demand_col or not pick_col:
        raise KeyError("Hittar inte order-, artikel-, antal- eller plockkolumn i beställningsfilen.")

    calc_df[order_col] = calc_df[order_col].astype(str).str.strip()
    calc_df[article_col] = calc_df[article_col].astype(str).str.strip()
    calc_df[demand_col] = calc_df[demand_col].map(to_num).astype(float)
    calc_df[pick_col] = calc_df[pick_col].map(to_num).astype(float)

    calc_df["_enough_row"] = calc_df[pick_col] >= calc_df[demand_col]
    complete_mask = calc_df.groupby(order_col)["_enough_row"].all()
    complete_orders = sorted(complete_mask[complete_mask].index.astype(str).tolist())

    demand_by_art = calc_df.groupby(article_col)[demand_col].sum(min_count=1)
    stock_by_art = calc_df.groupby(article_col)[pick_col].max()
    holistic = pd.DataFrame({
        "Total beställt": demand_by_art,
        "Tillgängligt saldo (Plock)": stock_by_art,
    }).fillna(0)
    holistic.index = holistic.index.map(lambda value: str(value).strip())

    if utbest_map is None:
        utbest_map = {}
    holistic["Utbeställt"] = holistic.index.to_series().map(utbest_map).fillna(0.0)
    holistic["Underskott"] = (
        holistic["Total beställt"] + holistic["Utbeställt"] - holistic["Tillgängligt saldo (Plock)"]
    ).clip(lower=0)
    holistic_short = holistic[holistic["Underskott"] > 0].copy().sort_index()
    return complete_orders, holistic_short

def _build_article_max_map(max_df: pd.DataFrame) -> Dict[str, float]:
    max_df = _clean_columns(max_df.copy())
    max_art_col = find_col(max_df, ["artikelnummer", "artikel", "artnr", "art.nr", "sku"])
    max_val_col = find_col(max_df, ["max"])
    tmp = pd.DataFrame({
        "_art": _safe_str_series(max_df[max_art_col]),
        "_max": max_df[max_val_col].map(to_num),
    })
    tmp = tmp[tmp["_art"].ne("")].dropna(subset=["_max"])
    return tmp.drop_duplicates(subset="_art").set_index("_art")["_max"].to_dict()

def _classify_pafyllnadsprio(underskott: float, reference_value: float) -> Tuple[str, bool]:
    try:
        reference = float(reference_value)
    except Exception:
        reference = 0.0
    if pd.isna(reference) or reference <= 0:
        return "PRIO 5", True

    ratio = float(underskott) / reference
    if ratio <= 0.25:
        return "PRIO 1", False
    if ratio <= 0.40:
        return "PRIO 2", False
    if ratio <= 0.55:
        return "PRIO 3", False
    if ratio <= 0.70:
        return "PRIO 4", False
    return "PRIO 5", False

def _build_pafyllnadsprio_dataframe(groups: Dict[str, List[str]]) -> pd.DataFrame:
    max_len = max((len(values) for values in groups.values()), default=0)
    padded = {
        column: values + [""] * (max_len - len(values))
        for column, values in groups.items()
    }
    return pd.DataFrame(padded, columns=PAFYLLNADSPRIO_COLUMNS)

def build_pafyllnadsprio_report(shortage_df: pd.DataFrame, max_df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Bygg enkel fallback-rapport för Påfyllnadsprio utan lastningsfönster."""
    groups = {column: [] for column in PAFYLLNADSPRIO_COLUMNS}
    if not isinstance(shortage_df, pd.DataFrame) or shortage_df.empty:
        return pd.DataFrame(columns=PAFYLLNADSPRIO_COLUMNS), 0

    max_map = _build_article_max_map(max_df)
    missing_reference_count = 0
    work = shortage_df.copy()
    work.index = work.index.map(lambda value: str(value).strip())
    work = work[work.index != ""].sort_index()

    for article, row in work.iterrows():
        groups["ALLA"].append(article)
        reference_value = max_map.get(article, 0.0)
        prio, missing_reference = _classify_pafyllnadsprio(to_num(row.get("Underskott", 0.0)), reference_value)
        if missing_reference:
            missing_reference_count += 1
        groups[prio].append(article)

    return _build_pafyllnadsprio_dataframe(groups), missing_reference_count

def _combine_orderdatum_and_laststart(orderdatum_value: object, laststart_value: object) -> pd.Timestamp | pd.NaT:
    """Kombinera datum från Orderdatum med klockslag från Laststarttid."""
    order_ts = pd.to_datetime(orderdatum_value, errors="coerce", dayfirst=False)
    if pd.isna(order_ts):
        return pd.NaT
    match = re.search(r"(\d{1,2}):(\d{2})", str(laststart_value or "").strip())
    if not match:
        return pd.NaT
    hour = int(match.group(1))
    minute = int(match.group(2))
    try:
        return pd.Timestamp(
            year=int(order_ts.year),
            month=int(order_ts.month),
            day=int(order_ts.day),
            hour=hour,
            minute=minute,
        )
    except Exception:
        return pd.NaT

def _format_lastningsfonster_label(window_ts: pd.Timestamp) -> str:
    if pd.isna(window_ts):
        return LASTNINGSFONSTER_UNKNOWN_LABEL
    return pd.Timestamp(window_ts).strftime("%Y-%m-%d %H:%M")

def _prepare_lastningsfonster_overview(overview_df: pd.DataFrame) -> pd.DataFrame:
    """Normalisera orderöversikten till en order -> lastningsfönster-tabell."""
    overview = _clean_columns(overview_df.copy())
    order_col = find_col(overview, ["ordernr", "ordernummer", "order number", "order no", "orderid", "order"])
    orderdatum_col = find_col(overview, ["orderdatum", "order datum", "order date", "orderdate"])
    laststart_col = find_col(
        overview,
        ["laststarttid", "laststart tid", "laststart", "laststart time", "last start time"],
    )

    tmp = pd.DataFrame({
        "_order": overview[order_col].astype(str).str.strip(),
        "_orderdatum": overview[orderdatum_col],
        "_laststart": overview[laststart_col],
    })
    tmp = tmp[tmp["_order"] != ""].copy()
    if tmp.empty:
        return pd.DataFrame(columns=["_order", "_window_sort", "_window_label", "_prio", "_missing_window"])

    tmp["_window_sort"] = [
        _combine_orderdatum_and_laststart(orderdatum_value, laststart_value)
        for orderdatum_value, laststart_value in zip(tmp["_orderdatum"], tmp["_laststart"])
    ]

    rows: List[dict] = []
    for order, grp in tmp.groupby("_order", sort=True):
        valid = grp.dropna(subset=["_window_sort"]).sort_values("_window_sort")
        if not valid.empty:
            window_ts = pd.Timestamp(valid.iloc[0]["_window_sort"])
            rows.append({
                "_order": str(order).strip(),
                "_window_sort": window_ts,
                "_window_label": _format_lastningsfonster_label(window_ts),
                "_missing_window": False,
            })
        else:
            rows.append({
                "_order": str(order).strip(),
                "_window_sort": LASTNINGSFONSTER_UNKNOWN_SORT,
                "_window_label": LASTNINGSFONSTER_UNKNOWN_LABEL,
                "_missing_window": True,
            })

    out = pd.DataFrame(rows)
    valid_windows = sorted(
        {pd.Timestamp(value) for value in out.loc[~out["_missing_window"], "_window_sort"].tolist()}
    )
    prio_map: Dict[pd.Timestamp, str] = {}
    for idx, window_ts in enumerate(valid_windows):
        prio_map[window_ts] = f"PRIO {idx + 1}" if idx < 4 else "PRIO 5"
    out["_prio"] = out["_window_sort"].map(prio_map).fillna("PRIO 5")
    return out[["_order", "_window_sort", "_window_label", "_prio", "_missing_window"]]

def _build_lastningsfonster_prio_dataframe(overview_windows: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Bygg en enkel översikt över vilka lastningsfönster som motsvarar PRIO 1-4."""
    if not isinstance(overview_windows, pd.DataFrame) or overview_windows.empty:
        return pd.DataFrame(columns=LASTNINGSFONSTER_PRIO_COLUMNS), []

    prio_map = (
        overview_windows.loc[
            (~overview_windows["_missing_window"]) & (overview_windows["_prio"].isin(PAFYLLNADSPRIO_COLUMNS[1:5])),
            ["_window_sort", "_window_label", "_prio"],
        ]
        .drop_duplicates()
        .sort_values(["_window_sort", "_prio", "_window_label"])
    )
    if prio_map.empty:
        return pd.DataFrame(columns=LASTNINGSFONSTER_PRIO_COLUMNS), []

    rows: List[dict] = []
    log_lines: List[str] = []
    for _, row in prio_map.iterrows():
        prio = str(row["_prio"]).strip()
        label = str(row["_window_label"]).strip()
        rows.append({"PRIO": prio, "LASTNINGSFÖNSTER": label})
        log_lines.append(f"{prio} = {label}")

    return pd.DataFrame(rows, columns=LASTNINGSFONSTER_PRIO_COLUMNS), log_lines

def build_pafyllnadsprio_lastningsfonster_report(
    orders_df: pd.DataFrame,
    shortage_df: pd.DataFrame,
    overview_df: pd.DataFrame,
    max_df: pd.DataFrame,
    *,
    column_names: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[pd.DataFrame, set[tuple[int, int]], List[str], int, pd.DataFrame]:
    """Bygg Påfyllnadsprio med lastningsfönster där samma artikel kan ligga i flera PRIO-kolumner."""
    groups = {column: [] for column in PAFYLLNADSPRIO_COLUMNS}
    empty_window_map = pd.DataFrame(columns=LASTNINGSFONSTER_PRIO_COLUMNS)
    if not isinstance(shortage_df, pd.DataFrame) or shortage_df.empty:
        return pd.DataFrame(columns=PAFYLLNADSPRIO_COLUMNS), set(), [], 0, empty_window_map

    orders_work = _clean_columns(orders_df.copy())
    cols = column_names or _find_ordersaldo_columns(orders_work)
    order_col = cols.get("order")
    article_col = cols.get("article")
    demand_col = cols.get("demand")
    if not order_col or not article_col or not demand_col:
        raise KeyError("Hittar inte order-, artikel- eller antalskolumn i beställningsfilen.")

    overview_windows = _prepare_lastningsfonster_overview(overview_df)
    demand_rows = pd.DataFrame({
        "_order": orders_work[order_col].astype(str).str.strip(),
        "_article": orders_work[article_col].astype(str).str.strip(),
        "_qty": orders_work[demand_col].map(to_num).astype(float),
    })
    demand_rows = demand_rows[(demand_rows["_article"] != "") & (demand_rows["_qty"] > 0)].copy()
    if demand_rows.empty:
        return pd.DataFrame(columns=PAFYLLNADSPRIO_COLUMNS), set(), [], 0, empty_window_map

    demand_rows = demand_rows.merge(
        overview_windows,
        how="left",
        left_on="_order",
        right_on="_order",
    )
    demand_rows["_window_sort"] = pd.to_datetime(demand_rows["_window_sort"], errors="coerce")
    demand_rows["_window_sort"] = demand_rows["_window_sort"].fillna(LASTNINGSFONSTER_UNKNOWN_SORT)
    demand_rows["_window_label"] = demand_rows["_window_label"].fillna(LASTNINGSFONSTER_UNKNOWN_LABEL)
    demand_rows["_prio"] = demand_rows["_prio"].fillna("PRIO 5")
    demand_by_window = (
        demand_rows.groupby(["_article", "_window_sort", "_window_label", "_prio"], as_index=False)["_qty"]
        .sum()
        .sort_values(["_article", "_window_sort", "_window_label"])
    )
    window_map_df, window_map_log_lines = _build_lastningsfonster_prio_dataframe(overview_windows)

    max_map = _build_article_max_map(max_df)
    prio_counts: Dict[str, Dict[str, int]] = {prio: {} for prio in PAFYLLNADSPRIO_COLUMNS[1:]}
    log_lines: List[str] = []
    missing_reference_count = 0

    work = shortage_df.copy()
    work.index = work.index.map(lambda value: str(value).strip())
    work = work[work.index != ""].sort_index()

    for article, row in work.iterrows():
        groups["ALLA"].append(article)
        reference_value = max_map.get(article, 0.0)
        try:
            reference_float = float(reference_value)
        except Exception:
            reference_float = 0.0
        if pd.isna(reference_float) or reference_float <= 0:
            missing_reference_count += 1
            prio_counts["PRIO 5"][article] = max(prio_counts["PRIO 5"].get(article, 0), 1)
            log_lines.append(f"Artikel {article} saknar referensvärde och placerades i PRIO 5.")
            continue

        article_windows = demand_by_window[demand_by_window["_article"] == article].copy()
        if article_windows.empty:
            prio_counts["PRIO 5"][article] = max(prio_counts["PRIO 5"].get(article, 0), 1)
            log_lines.append(f"Artikel {article} saknar matchning mot lastningsfönster och placerades i PRIO 5.")
            continue

        available_start = float(to_num(row.get("Tillgängligt saldo (Plock)", 0.0))) - float(
            to_num(row.get("Utbeställt", 0.0))
        )
        cumulative_need = 0.0
        previous_total_pallets = 0
        event_found = False

        for _, window_row in article_windows.iterrows():
            qty = float(window_row["_qty"])
            if qty <= 0:
                continue
            cumulative_need += qty
            cumulative_shortage = max(0.0, cumulative_need - available_start)
            total_pallets = int(math.ceil(cumulative_shortage / reference_float)) if cumulative_shortage > 0 else 0
            new_pallets = max(0, total_pallets - previous_total_pallets)
            previous_total_pallets = total_pallets
            if new_pallets <= 0:
                continue

            event_found = True
            prio = str(window_row["_prio"])
            prio_counts[prio][article] = max(prio_counts[prio].get(article, 0), new_pallets)
            pall_text = "pall" if new_pallets == 1 else "pallar"
            log_lines.append(
                f"Artikel {article} behöver {new_pallets} {pall_text} i lastningsfönster "
                f"{window_row['_window_label']} ({prio})."
            )

        if not event_found:
            prio_counts["PRIO 5"][article] = max(prio_counts["PRIO 5"].get(article, 0), 1)
            log_lines.append(f"Artikel {article} saknar beräknat påfyllningsfönster och placerades i PRIO 5.")

    bold_cells: set[tuple[int, int]] = set()
    for col_idx, prio in enumerate(PAFYLLNADSPRIO_COLUMNS[1:], start=1):
        counts = prio_counts[prio]
        multi_articles = sorted(
            [article for article, pallet_count in counts.items() if pallet_count > 1],
            key=lambda article: (-counts[article], article),
        )
        single_articles = sorted(article for article, pallet_count in counts.items() if pallet_count <= 1)
        ordered_articles = multi_articles + single_articles
        groups[prio] = ordered_articles
        for row_idx, article in enumerate(ordered_articles):
            if counts.get(article, 0) > 1:
                bold_cells.add((row_idx, col_idx))

    if window_map_log_lines:
        log_lines.append("Lastningsfönster per prio:")
        log_lines.extend(window_map_log_lines)

    return _build_pafyllnadsprio_dataframe(groups), bold_cells, log_lines, missing_reference_count, window_map_df

def utbest_per_article(saldo_df: pd.DataFrame) -> Dict[str, float]:
    """Summera 'utbeställt' per artikel från saldofilen.

    Returnerar tom dict om artikel- eller utbest-kolumn saknas.
    Inga bolagsfilter — alla rader summeras.
    """
    df = _clean_columns(saldo_df.copy())
    art_col = find_col(df, ["artikel", "artnr", "art.nr", "artikelnummer", "sku"], required=False)
    utbest_col = find_col(df, ["utbeställt", "utbestallt"], required=False)
    if not art_col or not utbest_col:
        return {}
    tmp = pd.DataFrame({
        "_art": _safe_str_series(df[art_col]),
        "_utbest": df[utbest_col].map(to_num).fillna(0.0),
    })
    return tmp.groupby("_art")["_utbest"].sum().to_dict()

def compute_lyx_articles(saldo_df: pd.DataFrame, max_df: pd.DataFrame) -> Tuple[list[str], int]:
    """
    Returnera artikelnummer där (plocksaldo + utbeställt) är högst 20 % av
    max buffertantalet. Returvärdet är (artikellista, antal filtrerade rader).
    """
    saldo_df = _clean_columns(saldo_df.copy())
    max_df = _clean_columns(max_df.copy())

    art_col = find_col(saldo_df, ["artikel", "artnr", "art.nr", "artikelnummer", "sku"])
    saldo_col = find_col(
        saldo_df,
        ["plocksaldo", "plock saldo", "plock-saldo", "tillgängligt plock", "tillgangligt plock", "plock"],
        required=False,
    )
    plats_col = find_col(
        saldo_df,
        ["plockplats", "huvudplock", "mainpick", "hyllplats", "bin", "location", "lagerplats"],
        required=False,
    )
    bolag_col = find_col(saldo_df, ["bolag", "company", "bolagskod"], required=False)
    utbest_col = find_col(saldo_df, ["utbeställt", "utbestallt"], required=False)

    if saldo_col is None:
        raise KeyError("Kunde inte hitta plocksaldo-kolumnen i saldofilen.")

    mask = pd.Series(True, index=saldo_df.index)
    if plats_col:
        mask &= _safe_str_series(saldo_df[plats_col]).ne("")
    if bolag_col:
        mask &= _safe_str_series(saldo_df[bolag_col]).str.upper() == "MG"

    saldo_filt = saldo_df[mask].copy()
    if saldo_filt.empty:
        return [], 0

    saldo_filt["_art"] = _safe_str_series(saldo_filt[art_col])
    saldo_filt["_saldo"] = saldo_filt[saldo_col].map(to_num).fillna(0)
    if utbest_col:
        saldo_filt["_utbest"] = saldo_filt[utbest_col].map(to_num).fillna(0)
    else:
        saldo_filt["_utbest"] = 0.0
    saldo_filt["_total"] = saldo_filt["_saldo"] + saldo_filt["_utbest"]

    max_map = _build_article_max_map(max_df)

    saldo_filt["_max"] = saldo_filt["_art"].map(max_map)
    lyx_mask = saldo_filt["_max"].notna() & (saldo_filt["_total"] <= saldo_filt["_max"] * 0.20)
    lyx_arts = sorted(saldo_filt.loc[lyx_mask, "_art"].unique().tolist())
    return lyx_arts, len(saldo_filt)
