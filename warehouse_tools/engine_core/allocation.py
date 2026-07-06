"""Allokering, pallplatser, refill och prognos-vs-autoplock."""
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

from .constants import (
    ALLOC_BUFFER_STATUSES,
    BUFFER_SCHEMA,
    INVALID_LOC_EXACT,
    INVALID_LOC_PREFIXES,
    NEAR_MISS_PCT,
    NOT_PUTAWAY_SCHEMA,
    ORDER_MAX_ALLOCATABLE_STATUS,
    ORDER_SCHEMA,
    REFILL_BUFFER_STATUSES,
    RF_PALLPLATS_EXCLUDE_ARTICLES,
)
from .io_utils import (
    find_col,
    normalize_saldo,
    smart_to_datetime,
    to_num,
)

def compute_pallet_spaces(result_df: pd.DataFrame) -> pd.DataFrame:
    """
    Beräkna pallplatsbehov per kund baserat på allokeringsresultatet.

    Parametrar:
        result_df: DataFrame med allokerade orderrader efter saldofil-omklassificering och item/ej staplingsbar-sammanfogning.

    Returnerar:
        Ett DataFrame med pallplatser per kund, inklusive separata delkolumner for t.ex. Plockpall, autostore och HIB.
        Om nödvändiga kolumner saknas returneras ett tomt DataFrame.
    """
    if result_df is None or result_df.empty:
        return pd.DataFrame(columns=["Kund", "Kund1", "Botten Pallar", "Topp Pallar", "Totalt Pallar", "Pallplatser"])
    df = result_df.copy()
    try:
        kund_col = find_col(df, ["kund", "customer", "kundnr", "kund nr", "kundnummer", "kund-id", "kundid"], required=True)
    except Exception:
        print(f"[compute_pallet_spaces] Kunde inte hitta kund-kolumn. Tillgängliga: {list(df.columns)}")
        return pd.DataFrame(columns=["Kund", "Kund1", "Botten Pallar", "Topp Pallar", "Totalt Pallar", "Pallplatser"])
    try:
        kund1_col = find_col(df, ["kund1", "kund 1", "customer1", "kund.1"], required=False, default=None)
    except Exception:
        kund1_col = None

    # Fallback: om primär kund-kolumn är helt tom men Kund.1 har värden, använd Kund.1 istället
    if kund_col and kund_col in df.columns:
        non_empty = df[kund_col].fillna("").astype(str).str.strip().ne("").sum()
        if non_empty == 0 and kund1_col and kund1_col in df.columns:
            kund_col, kund1_col = kund1_col, None

    zone_col = "Zon (beräknad)" if "Zon (beräknad)" in df.columns else None
    stack_col = None
    try:
        stack_col = find_col(df, ["ej staplingsbar", "ejstaplingsbar", "staplingsbar", "staplings bar"], required=False, default=None)
    except Exception:
        stack_col = None
    palltyp_col = "Palltyp (matchad)" if "Palltyp (matchad)" in df.columns else None
    if zone_col is None or palltyp_col is None:
        print(f"[compute_pallet_spaces] Saknar kolumn: zone_col={zone_col}, palltyp_col={palltyp_col}. Tillgängliga: {list(df.columns)}")
        return pd.DataFrame(columns=["Kund", "Kund1", "Botten Pallar", "Topp Pallar", "Totalt Pallar", "Pallplatser"])

    df[zone_col] = df[zone_col].fillna("").astype(str).str.strip().str.upper()
    if stack_col:
        df[stack_col] = df[stack_col].fillna("").astype(str).str.strip().str.upper()
    else:
        df["_stack_tmp"] = ""
        stack_col = "_stack_tmp"
    df[palltyp_col] = df[palltyp_col].fillna("").astype(str).str.strip().str.upper()

    art_col_ps = None
    try:
        art_col_ps = find_col(df, ORDER_SCHEMA["artikel"], required=False, default=None)
    except Exception:
        art_col_ps = None
    if kund1_col is None:
        groups = df.groupby(kund_col)
    else:
        groups = df.groupby([kund_col, kund1_col])
    records: list[dict] = []
    import math
    for keys, sub in groups:
        if kund1_col is None:
            kund_val = keys
            kund1_val = ""
        else:
            kund_val, kund1_val = keys
        mask_bottom = (sub[zone_col] == "H") & ((sub[stack_col] == "N") | (sub[stack_col] == ""))
        B = int(mask_bottom.sum())
        rows_A = int((sub[zone_col] == "A").sum())
        if rows_A > 0:
            top_A = math.ceil(rows_A / 20.0)
        else:
            top_A = 0
        mask_topH = (sub[zone_col] == "H") & (sub[stack_col] == "Y") & (sub[palltyp_col] != "SJÖ")
        top_H = int(mask_topH.sum())
        rows_F = int((sub[zone_col] == "F").sum())
        if rows_F > 0:
            top_F = math.ceil(rows_F / 20.0)
        else:
            top_F = 0
        mask_rf = sub[zone_col] == "R"
        if art_col_ps and art_col_ps in sub.columns:
            mask_rf = mask_rf & ~sub[art_col_ps].astype(str).str.strip().isin(RF_PALLPLATS_EXCLUDE_ARTICLES)
        rows_R = int(mask_rf.sum())
        if rows_R < 27:
            top_R = 0
        elif rows_R <= 96:
            top_R = 1
        elif rows_R <= 163:
            top_R = 2
        elif rows_R <= 204:
            top_R = 3
        else:
            top_R = 4
        rows_S = int((sub[zone_col] == "S").sum())
        if rows_S == 0:
            top_S = 0
        elif rows_S <= 10:
            top_S = 1
        elif rows_S <= 15:
            top_S = 2
        elif rows_S <= 20:
            top_S = 3
        elif rows_S <= 26:
            top_S = 4
        else:
            top_S = 5
        mask_sjo = (sub[zone_col] == "H") & (sub[palltyp_col] == "SJÖ")
        S_rows = int(mask_sjo.sum())
        T = top_A + top_H + top_R + top_S + top_F
        half_sum = (B + T) / 2.0
        P_component = math.ceil(half_sum)
        max_val = T if T > P_component else P_component
        P = max_val + 2 * S_rows
        total_pallar = B + T + S_rows
        helpall_stapelbar = B
        helpall_ej_stapelbar = top_H
        sjo_pall = S_rows
        skrymme_pallar = top_S
        plockpall = top_A
        autostore_pallar = top_R
        hib_pallar = top_F
        record = {
            "Kund": kund_val,
            "Kund1": kund1_val,
            "hellpall stapelbar": helpall_stapelbar,
            "hellpall ej stapelbar": helpall_ej_stapelbar,
            "Sjö pall": sjo_pall,
            "Skrymme": skrymme_pallar,
            "Plockpall": plockpall,
            "autostore": autostore_pallar,
            "HIB": hib_pallar,
            "Botten Pallar": B,
            "Topp Pallar": T,
            "Totalt Pallar": total_pallar,
            "Pallplatser": P
        }
        records.append(record)
    return pd.DataFrame(records)

def _safe_str_series(s: pd.Series) -> pd.Series:
    """
    Returnera en strängserie där varje värde är trimmat och NaN ersätts med tom sträng.
    """
    return s.fillna("").astype(str).str.strip()

def _str_to_num(x) -> float:
    """
    Extrahera första numeriska värdet ur ett godtyckligt objekt/sträng och returnera som float.
    Saknas numeriskt värde → 0.0.
    """
    import re
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    s = str(x).replace(" ", "").replace(",", ".")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    return float(m.group()) if m else 0.0

def _num_series(s: pd.Series) -> pd.Series:
    """
    Konvertera en Serie till numeriska värden med hjälp av _str_to_num. NaN ersätts med 0.
    """
    return pd.to_numeric(s.map(_str_to_num), errors="coerce").fillna(0)

def _collect_exclude_source_ids(allocated_df: Optional[pd.DataFrame]) -> set[str]:
    """
    Samla ihop de käll-ID:n från en allokerad DataFrame som motsvarar HELPALL-rader.
    Dessa ID används för att exkludera källor i refill/FIFO-beräkningen.
    """
    exclude: set[str] = set()
    if isinstance(allocated_df, pd.DataFrame) and not allocated_df.empty:
        if "Källtyp" in allocated_df.columns and "Källa" in allocated_df.columns:
            mask = _safe_str_series(allocated_df["Källtyp"]) == "HELPALL"
            vals = _safe_str_series(allocated_df.loc[mask, "Källa"]).replace("", pd.NA).dropna().unique().tolist()
            exclude = set(vals)
    return exclude

def build_prognos_vs_autoplock_report(
    prognos_df: pd.DataFrame,
    saldo_norm_df: Optional[pd.DataFrame] = None,
    buffer_df: Optional[pd.DataFrame] = None,
    *,
    exclude_source_ids: Optional[set[str]] = None,
    allocated_df: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Bygg en rapport som jämför prognosens behov med saldo i autoplock och buffertpallar (FIFO‑baserad
    pallberäkning). Kolumnen för ej inlagrade artiklar (E) har tagits bort.
    Returnerar ett DataFrame med kolumnerna A–D samt F och en meta‑dikt som anger om rapporten är
    partiell och eventuella notes om vad som saknas.
    """
    meta: Dict[str, str] = {"partial": "no", "missing": "", "note": ""}
    missing: List[str] = []
    if not isinstance(prognos_df, pd.DataFrame) or prognos_df.empty:
        empty = pd.DataFrame(columns=[
            "Artikelnummer",
            "Behov i prognosen (antal styck)",
            "Saldo i autoplock",
            "Behov efter saldo",
            "Summa antal i ej inlagrade artiklar",
            "FIFO-baserad beräkning (antal pall)",
        ])
        meta.update({"partial": "yes", "missing": "prognos", "note": "Ingen prognos inläst."})
        return empty, meta
    pr = prognos_df.copy()
    if "Artikelnummer" not in pr.columns or "Antal styck" not in pr.columns:
        rename_map: Dict[str, str] = {}
        for col in pr.columns:
            lc = str(col).strip().lower()
            if lc in ("product code", "artikelnummer", "artnr", "sku", "article"):
                rename_map[col] = "Artikelnummer"
            elif lc in ("antal styck", "antal", "qty", "quantity"):
                rename_map[col] = "Antal styck"
        if rename_map:
            pr = pr.rename(columns=rename_map)
    pr["Artikelnummer"] = _safe_str_series(pr.get("Artikelnummer", ""))
    pr["Antal styck"] = _num_series(pr.get("Antal styck", 0))
    if isinstance(saldo_norm_df, pd.DataFrame) and not saldo_norm_df.empty:
        orig_cols = [str(c).strip().lower() for c in saldo_norm_df.columns]
        has_robot_col = any("robot" == c for c in orig_cols)
        if not has_robot_col:
            missing.append("saldo")
            pr["Robot"] = "N"
            pr["Saldo i autoplock"] = 0.0
        else:
            s = saldo_norm_df.copy()
            if "Artikel" not in s.columns:
                for c in s.columns:
                    lc = str(c).strip().lower()
                    if lc in ("artikel", "artikelnummer", "sku", "artnr", "art.nr", "article"):
                        s = s.rename(columns={c: "Artikel"})
                        break
            if "Robot" not in s.columns:
                s["Robot"] = "N"
            if "Saldo autoplock" not in s.columns:
                s["Saldo autoplock"] = 0.0
            s["Artikel"] = _safe_str_series(s["Artikel"])
            s["Robot"] = _safe_str_series(s["Robot"]).str.upper().map(lambda x: "Y" if x == "Y" else "N")
            s["Saldo autoplock"] = _num_series(s["Saldo autoplock"])
            pr = pr.merge(s[["Artikel", "Robot", "Saldo autoplock"]], left_on="Artikelnummer", right_on="Artikel", how="left")
            pr = pr.drop(columns=["Artikel"], errors="ignore")
            pr["Robot"] = pr["Robot"].fillna("N")
            pr["Saldo i autoplock"] = pr["Saldo autoplock"].fillna(0.0)
    else:
        missing.append("saldo")
        pr["Robot"] = "N"
        pr["Saldo i autoplock"] = 0.0
    pr["Behov i prognosen (antal styck)"] = _num_series(pr["Antal styck"])
    pr["Saldo i autoplock"] = _num_series(pr["Saldo i autoplock"])
    pr["Behov efter saldo"] = (pr["Behov i prognosen (antal styck)"] - pr["Saldo i autoplock"]).clip(lower=0)
    pr["Summa antal i ej inlagrade artiklar"] = 0.0
    shortage = pr["Behov efter saldo"].copy()
    if exclude_source_ids is None and isinstance(allocated_df, pd.DataFrame):
        exclude_source_ids = _collect_exclude_source_ids(allocated_df)
    if not exclude_source_ids:
        exclude_source_ids = None
    if isinstance(buffer_df, pd.DataFrame) and not buffer_df.empty:
        buf = buffer_df.copy()
        try:
            buf.rename(columns=lambda c: str(c).replace("\ufeff", "").strip(), inplace=True)
        except Exception:
            pass
        try:
            art_col = find_col(buf, BUFFER_SCHEMA["artikel"], required=True)
            qty_col = find_col(buf, BUFFER_SCHEMA["qty"], required=True)
            dt_col = find_col(buf, BUFFER_SCHEMA["dt"], required=False, default=None)
            status_col = find_col(buf, BUFFER_SCHEMA["status"], required=False, default=None)
            id_col = find_col(buf, BUFFER_SCHEMA["id"], required=False, default=None)
        except Exception:
            missing.append("buffert")
            pr["FIFO-baserad beräkning (antal pall)"] = np.nan
            pr["Buffertsaldo (status 29,30)"] = 0.0
        if status_col and status_col in buf.columns:
            s_str = _safe_str_series(buf[status_col])
            s_num = pd.to_numeric(s_str.str.extract(r"(-?\d+)")[0], errors="coerce")
            allowed_str = {str(x) for x in REFILL_BUFFER_STATUSES}
            mask_status = s_str.isin(allowed_str) | s_num.isin(REFILL_BUFFER_STATUSES)
            buf = buf.loc[mask_status].copy()
        if exclude_source_ids:
            if id_col and id_col in buf.columns:
                buf["_source_id"] = _safe_str_series(buf[id_col])
            else:
                buf["_source_id"] = "SRC-" + buf.index.astype(str)
            buf = buf[~buf["_source_id"].isin(exclude_source_ids)].copy()
        buf["__qty__"] = _num_series(buf[qty_col])
        prefix_dict: Dict[str, np.ndarray] = {}
        if dt_col and dt_col in buf.columns:
            buf = buf.sort_values([art_col, dt_col], kind="mergesort", na_position="last")
        for art, group in buf.groupby(buf[art_col]):
            qty_vals = group["__qty__"].to_numpy()
            if qty_vals.size == 0:
                continue
            prefix = np.cumsum(qty_vals)
            prefix_dict[str(art)] = prefix

        buffer_sum_series = buf.groupby(buf[art_col])["__qty__"].sum()
        buffer_sum_dict = {str(k): v for k, v in buffer_sum_series.items()}
        pr["Buffertsaldo (status 29,30)"] = pr["Artikelnummer"].map(lambda x: buffer_sum_dict.get(str(x), 0.0))
        def calc_pallar(art: Any, need: float) -> float:
            if need <= 0:
                return 0.0
            pref = prefix_dict.get(str(art))
            if pref is None:
                return 0.0
            idx = np.searchsorted(pref, float(need), side="left")
            if idx >= len(pref):
                return float(len(pref))
            else:
                return float(idx + 1)
        pr["FIFO-baserad beräkning (antal pall)"] = [calc_pallar(a, n) for a, n in zip(pr["Artikelnummer"], shortage)]
    else:
        missing.append("buffert")
        pr["FIFO-baserad beräkning (antal pall)"] = np.nan
        pr["Buffertsaldo (status 29,30)"] = 0.0
    pr = pr.loc[(pr["Robot"].astype(str).str.upper() == "Y") & (pr["Behov efter saldo"] > 0)].copy()
    out_cols = [
        "Artikelnummer",
        "Behov i prognosen (antal styck)",
        "Saldo i autoplock",
        "Behov efter saldo",
        "Buffertsaldo (status 29,30)",
        "FIFO-baserad beräkning (antal pall)",
    ]
    for c in out_cols:
        if c not in pr.columns:
            pr[c] = np.nan if c.startswith("FIFO") else 0.0
    report = pr[out_cols].reset_index(drop=True)
    if missing:
        notes: List[str] = []
        if "saldo" in missing:
            notes.append("Saldo saknas → Saldo i autoplock antas 0 (C=0, D=B).")
        if "buffert" in missing:
            notes.append("Buffert saknas → F kan inte beräknas.")
        meta = {
            "partial": "yes",
            "missing": ",".join(sorted(set(missing))),
            "note": " ".join(notes),
        }
    else:
        meta = {"partial": "no", "missing": "", "note": ""}
    return report, meta

def allocate(orders_raw: pd.DataFrame, buffer_raw: pd.DataFrame, log=None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Allokera beställningsrader mot buffert enligt HELPALL→AUTOSTORE→HUVUDPLOCK.
    - Buffert filter: status {29,30,32} + platsfilter (ej AA*, TRANSIT, TRANSIT_ERROR, MISSING, UT2).
    - Ignorera orderrader med Status > 33.
    Returnerar (allocated_df, near_miss_df).
    """
    def _log(msg: str):
        if log:
            log(msg)

    order_article_col = find_col(orders_raw, ORDER_SCHEMA["artikel"])
    order_qty_col     = find_col(orders_raw, ORDER_SCHEMA["qty"])
    order_id_col      = find_col(orders_raw, ORDER_SCHEMA["ordid"], required=False, default=None)
    order_line_col    = find_col(orders_raw, ORDER_SCHEMA["radid"], required=False, default=None)
    order_status_col  = find_col(orders_raw, ORDER_SCHEMA["status"], required=False, default=None)

    buff_article_col  = find_col(buffer_raw, BUFFER_SCHEMA["artikel"])
    buff_qty_col      = find_col(buffer_raw, BUFFER_SCHEMA["qty"])
    buff_loc_col      = find_col(buffer_raw, BUFFER_SCHEMA["loc"])
    buff_dt_col       = find_col(buffer_raw, BUFFER_SCHEMA["dt"], required=False, default=None)
    buff_id_col       = find_col(buffer_raw, BUFFER_SCHEMA["id"], required=False, default=None)
    buff_status_col   = find_col(buffer_raw, BUFFER_SCHEMA["status"], required=False, default=None)
    try:
        buff_type_col = find_col(buffer_raw, [
            "palltyp", "pall typ", "pall type"
        ], required=False, default=None)
    except Exception:
        buff_type_col = None

    _log(f"Order-kolumner: Artikel='{order_article_col}', Antal='{order_qty_col}', OrderId='{order_id_col}', Rad='{order_line_col}', Status='{order_status_col}'")
    _log(f"Buffert-kolumner: Artikel='{buff_article_col}', Antal='{buff_qty_col}', Lagerplats='{buff_loc_col}', Tid='{buff_dt_col}', ID='{buff_id_col}', Status='{buff_status_col}'")

    orders = orders_raw.copy()
    orders["_artikel"] = orders[order_article_col].astype(str).str.strip()
    orders["_qty"] = orders[order_qty_col].map(to_num).astype(float)
    orders["_order_id"] = orders[order_id_col].astype(str) if order_id_col and order_id_col in orders.columns else ""
    orders["_order_line"] = orders[order_line_col].astype(str) if order_line_col and order_line_col in orders.columns else orders.index.astype(str)

    if order_status_col and order_status_col in orders.columns:
        _status_str = orders[order_status_col].astype(str).str.strip()
        _status_num = pd.to_numeric(_status_str.str.extract(r"(-?\d+)")[0], errors="coerce")
        _before = len(orders)
        orders = orders[~(_status_num > ORDER_MAX_ALLOCATABLE_STATUS)].copy()
        _removed = _before - len(orders)
        if _removed:
            _log(f"Ignorerar {_removed} orderrad(er) pga Status > {ORDER_MAX_ALLOCATABLE_STATUS}.")
    else:
        _log(f"OBS: Ingen order-statuskolumn hittad; kan inte filtrera Status > {ORDER_MAX_ALLOCATABLE_STATUS}.")

    buffer_df = buffer_raw.copy()
    buffer_df["_artikel"] = buffer_df[buff_article_col].astype(str).str.strip()
    buffer_df["_qty"] = buffer_df[buff_qty_col].map(to_num).astype(float)
    buffer_df["_loc"] = buffer_df[buff_loc_col].astype(str).str.strip()
    buffer_df["_received"] = smart_to_datetime(buffer_df[buff_dt_col]) if buff_dt_col and buff_dt_col in buffer_df.columns else pd.NaT
    buffer_df["_source_id"] = buffer_df[buff_id_col].astype(str) if buff_id_col and buff_id_col in buffer_df.columns else "SRC-" + buffer_df.index.astype(str)
    if buff_type_col and buff_type_col in buffer_df.columns:
        tmp_palltyp = buffer_df[buff_type_col].fillna("").astype(str).str.strip()
        buffer_df["_palltyp"] = tmp_palltyp.replace({"nan": "", "": ""})
    else:
        buffer_df["_palltyp"] = ""

    if buff_status_col and buff_status_col in buffer_df.columns:
        status_series = buffer_df[buff_status_col].astype(str).str.strip()
        status_num = pd.to_numeric(status_series.str.extract(r"(-?\d+)")[0], errors="coerce")
        allowed_str = {str(x) for x in ALLOC_BUFFER_STATUSES}
        mask_allowed = status_series.isin(allowed_str) | status_num.isin(ALLOC_BUFFER_STATUSES)
        removed = int((~mask_allowed).sum())
        if removed:
            _log(f"Filtrerar bort {removed} buffertpall(ar) pga Status ej i {sorted(ALLOC_BUFFER_STATUSES)}.")
        buffer_df = buffer_df[mask_allowed].copy()
    else:
        _log("OBS: Hittade ingen statuskolumn; ingen statusfiltrering tillämpas.")

    loc_upper = buffer_df["_loc"].str.upper()
    mask_exclude = loc_upper.str.startswith(INVALID_LOC_PREFIXES, na=False) | loc_upper.isin(INVALID_LOC_EXACT)
    excluded_count = int(mask_exclude.sum())
    if excluded_count:
        _log(f"Filtrerar bort {excluded_count} rad(er) från bufferten pga lagerplats-regler ({INVALID_LOC_PREFIXES}*, {', '.join(sorted(INVALID_LOC_EXACT))}).")
    buffer_df = buffer_df[~mask_exclude].copy()

    try:
        buffer_df["_artikel"] = buffer_df["_artikel"].astype("category")
    except Exception:
        pass

    buffer_df["_is_autostore"] = buffer_df["_loc"].str.contains("AUTOSTORE", case=False, na=False)
    buffer_df = buffer_df[buffer_df["_qty"] > 0].copy()

    far_future = pd.Timestamp("2262-04-11")
    buffer_df["_received_ord"] = buffer_df["_received"].fillna(far_future)

    pallets = buffer_df[~buffer_df["_is_autostore"]].copy().sort_values(by=["_artikel", "_received_ord", "_source_id"])
    bins = buffer_df[buffer_df["_is_autostore"]].copy().sort_values(by=["_artikel", "_received_ord", "_source_id"])

    pallet_queues: Dict[str, Deque[dict]] = defaultdict(deque)
    for _, r in pallets.iterrows():
        pallet_queues[str(r["_artikel"]).strip()].append({
            "source_id": r["_source_id"],
            "qty": float(r["_qty"]),
            "loc": r["_loc"],
            "received": r["_received"],
            "palltyp": (r.get("_palltyp", "") if pd.notna(r.get("_palltyp", "")) else "")
        })

    bin_queues: Dict[str, Deque[dict]] = defaultdict(deque)
    for _, r in bins.iterrows():
        bin_queues[str(r["_artikel"]).strip()].append({
            "source_id": r["_source_id"],
            "qty": float(r["_qty"]),
            "loc": r["_loc"],
            "received": r["_received"],
            "palltyp": (r.get("_palltyp", "") if pd.notna(r.get("_palltyp", "")) else "")
        })

    allocated_rows: List[dict] = []
    near_miss_rows: List[dict] = []
    near_miss_article_set: set[str] = set()

    def clone_row(orow: pd.Series) -> dict:
        return orow.to_dict()

    def record_near_miss(orow: pd.Series, pal: dict, need: float) -> None:
        """
        Record a near-miss event when a pallet is up to the configured NEAR_MISS_PCT larger than the
        remaining need for an article. To prevent excessive logging when the same article triggers
        multiple near-miss events across many order lines, this function will only record the first
        near-miss for each unique article. Additional near misses for the same article are ignored.
        """
        if need <= 0:
            return
        diff = pal["qty"] - need
        if diff <= 0:
            return
        pct = diff / need
        if pct <= NEAR_MISS_PCT:
            art_id = str(orow["_artikel"]).strip()
            if art_id in near_miss_article_set:
                return
            near_miss_article_set.add(art_id)
            near_miss_rows.append({
                "Artikel": art_id,
                "OrderID": str(orow["_order_id"]),
                "OrderRad": str(orow["_order_line"]),
                "PallID": str(pal["source_id"]),
                "Källplats": str(pal["loc"]),
                "Mottagen": pal["received"],
                "Behov_vid_tillfället": need,
                "Pall_kvantitet": pal["qty"],
                "Skillnad": diff,
                "Procentuell skillnad (%)": pct * 100.0,
                "Anledning": f"Pallen var ≤{int(NEAR_MISS_PCT * 100)}% större än återstående behov (kan ej brytas)",
                "Gäller (INSTEAD R/A)": None
            })

    for _, orow in orders.iterrows():
        art = str(orow["_artikel"]).strip()
        need = float(orow["_qty"])
        if need <= 0:
            continue

        pq = pallet_queues.get(art, deque())
        new_pq = deque()
        tmp = deque(pq)
        any_helpall = False
        while tmp and need > 0:
            pal = tmp.popleft()
            pal_qty = pal["qty"]
            if pal_qty <= need:
                sub = clone_row(orow)
                sub[order_qty_col] = pal_qty
                sub["Zon (beräknad)"] = "H"
                sub["Källtyp"] = "HELPALL"
                sub["Källa"] = pal["source_id"]
                sub["Källplats"] = pal["loc"]
                paltyp_val = pal.get("palltyp", "")
                if not paltyp_val or str(paltyp_val).lower() == "nan":
                    paltyp_val = ""
                sub["Palltyp (matchad)"] = paltyp_val
                allocated_rows.append(sub)
                need -= pal_qty
                any_helpall = True
            else:
                record_near_miss(orow, pal, need)
                new_pq.append(pal)
        while tmp:
            new_pq.append(tmp.popleft())
        pallet_queues[art] = new_pq

        any_autostore = False
        bq = bin_queues.get(art, deque())
        new_bq = deque()
        while bq and need > 0:
            binr = bq.popleft()
            take = min(binr["qty"], need)
            if take > 0:
                sub = clone_row(orow)
                sub[order_qty_col] = take
                sub["Zon (beräknad)"] = "R"
                sub["Källtyp"] = "AUTOSTORE"
                sub["Källa"] = binr["source_id"]
                sub["Källplats"] = binr["loc"]
                bin_palltyp_val = binr.get("palltyp", "")
                if not bin_palltyp_val or str(bin_palltyp_val).lower() == "nan":
                    bin_palltyp_val = ""
                sub["Palltyp (matchad)"] = bin_palltyp_val
                allocated_rows.append(sub)
                binr["qty"] -= take
                need -= take
                any_autostore = True
            if binr["qty"] > 0:
                new_bq.append(binr)
        while bq:
            new_bq.append(bq.popleft())
        bin_queues[art] = new_bq

        any_mainpick = False
        if need > 0:
            sub = clone_row(orow)
            sub[order_qty_col] = need
            sub["Zon (beräknad)"] = "A"
            sub["Källtyp"] = "HUVUDPLOCK"
            sub["Källa"] = ""
            sub["Källplats"] = ""
            sub["Palltyp (matchad)"] = ""
            allocated_rows.append(sub)
            any_mainpick = True
            need = 0.0

        if not any_helpall and (any_autostore or any_mainpick):
            for r in near_miss_rows:
                if r["OrderID"] == str(orow["_order_id"]) and r["OrderRad"] == str(orow["_order_line"]):
                    r["Gäller (INSTEAD R/A)"] = True
        else:
            for r in near_miss_rows:
                if r["OrderID"] == str(orow["_order_id"]) and r["OrderRad"] == str(orow["_order_line"]):
                    r["Gäller (INSTEAD R/A)"] = False

    allocated_df = pd.DataFrame(allocated_rows)

    try:
        if not allocated_df.empty and ("Källtyp" in allocated_df.columns):
            if "Zon (beräknad)" not in allocated_df.columns:
                allocated_df["Zon (beräknad)"] = ""
            low = {c.lower(): c for c in allocated_df.columns}
            art_col_res = None
            for n in ["artikel", "article", "artnr", "art.nr", "artikelnummer", "_artikel"]:
                if n.lower() in low:
                    art_col_res = low[n.lower()]
                    break
            if art_col_res:
                auto_arts = set(allocated_df.loc[allocated_df["Källtyp"].astype(str) == "AUTOSTORE", art_col_res].astype(str).str.strip())
                if auto_arts:
                    mask_same = allocated_df[art_col_res].astype(str).str.strip().isin(auto_arts)
                    mask_change = mask_same & (allocated_df["Källtyp"].astype(str) != "HELPALL")
                    allocated_df.loc[mask_change, "Källtyp"] = "AUTOSTORE"
                    allocated_df.loc[mask_change, "Zon (beräknad)"] = "R"
    except Exception:
        pass

    added_cols = ["Zon (beräknad)", "Källtyp", "Källa", "Källplats", "Palltyp (matchad)"]
    ordered_cols = [c for c in orders_raw.columns] + [c for c in added_cols if c not in orders_raw.columns]
    if not allocated_df.empty:
        allocated_df = allocated_df[ordered_cols]
    else:
        allocated_df = pd.DataFrame(columns=ordered_cols)

    near_miss_df = pd.DataFrame(near_miss_rows)
    return allocated_df, near_miss_df

def calculate_refill(allocated_df: pd.DataFrame,
                     buffer_raw: pd.DataFrame,
                     saldo_df: pd.DataFrame | None = None,
                     not_putaway_df: pd.DataFrame | None = None
                     ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Beräkna påfyllningspallar.
    - HP-blad inkluderar både HUVUDPLOCK (A) och SKRYMMANDE (S).
    - Plocksaldo dras en gång per artikel och fördelas proportionerligt mellan A och S.
    - 0-rader tas bort.
    - AUTOSTORE-blad (R) oförändrat, men 0-rader tas också bort.
    - Buffert filtreras till status {29,30}. HELPALL-pallar som redan används exkluderas alltid.
    """

    result = allocated_df.copy()
    buff = buffer_raw.copy()

    art_col_res = find_col(result, ORDER_SCHEMA["artikel"])
    qty_col_res = find_col(result, ORDER_SCHEMA["qty"])

    art_col_buf = find_col(buff, BUFFER_SCHEMA["artikel"])
    qty_col_buf = find_col(buff, BUFFER_SCHEMA["qty"])
    dt_col_buf  = find_col(buff, BUFFER_SCHEMA["dt"], required=False, default=None)
    id_col_buf  = find_col(buff, BUFFER_SCHEMA["id"], required=False, default=None)
    status_col_buf = find_col(buff, BUFFER_SCHEMA["status"], required=False, default=None)

    b = buff.copy()
    b["_artikel"] = b[art_col_buf].astype(str).str.strip()
    b["_qty"] = b[qty_col_buf].map(to_num).astype(float)
    b["_received"] = smart_to_datetime(b[dt_col_buf]) if dt_col_buf and dt_col_buf in b.columns else pd.NaT
    b["_source_id"] = b[id_col_buf].astype(str) if id_col_buf and id_col_buf in b.columns else "SRC-" + b.index.astype(str)

    if status_col_buf and status_col_buf in b.columns:
        _s = b[status_col_buf].astype(str).str.strip()
        _snum = pd.to_numeric(_s.str.extract(r"(-?\d+)")[0], errors="coerce")
        allowed_str = {str(x) for x in REFILL_BUFFER_STATUSES}
        b = b[_s.isin(allowed_str) | _snum.isin(REFILL_BUFFER_STATUSES)].copy()

    used_help_ids: set[str] = set()
    if "Källtyp" in result.columns and "Källa" in result.columns:
        used_help_ids = set(result[result["Källtyp"].astype(str) == "HELPALL"]["Källa"].dropna().astype(str).tolist())

    saldo_sum: Dict[str, float] = {}
    plockplats_by_art: Dict[str, str] = {}
    if isinstance(saldo_df, pd.DataFrame) and not saldo_df.empty:
        try:
            s_norm = normalize_saldo(saldo_df)
            for _, r in s_norm.iterrows():
                art = str(r["Artikel"]).strip()
                saldo_sum[art] = float(saldo_sum.get(art, 0.0) + float(r.get("Plocksaldo", 0.0)))
                pp_raw = r.get("Plockplats", "")
                # NaN ar truthy: utan denna vakt blir tom plockplats strangen "nan"
                # i refill-tabellerna (pandas 2.2.x laser tomma celler som NaN).
                pp = "" if pd.isna(pp_raw) else str(pp_raw).strip()
                if pp and art not in plockplats_by_art:
                    plockplats_by_art[art] = pp
        except Exception:
            saldo_sum = {}
            plockplats_by_art = {}

    npu_sum: Dict[str, float] = {}
    if isinstance(not_putaway_df, pd.DataFrame) and not not_putaway_df.empty:
        try:
            npu = not_putaway_df.copy()
            npu_art_col = find_col(npu, NOT_PUTAWAY_SCHEMA["artikel"])
            npu_qty_col = find_col(npu, NOT_PUTAWAY_SCHEMA["antal"])
            grp = npu.groupby(npu[npu_art_col].astype(str).str.strip())[npu_qty_col].apply(lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0).sum()))
            npu_sum = {str(k): float(v) for k, v in grp.to_dict().items()}
        except Exception:
            npu_sum = {}

    def fifo_for_art(art_key: str) -> pd.DataFrame:
        d = b[b["_artikel"] == art_key].copy()
        if not d.empty and used_help_ids:
            d = d[~d["_source_id"].astype(str).isin(used_help_ids)].copy()
        return d.sort_values("_received")

    hp_like = result[result.get("Källtyp", "").isin(["HUVUDPLOCK", "SKRYMMANDE", "HIB", "EHANDEL"])].copy()
    rows_hp: List[dict] = []
    if not hp_like.empty:
        hp_like["_zon"] = hp_like["Källtyp"].astype(str).map({"SKRYMMANDE": "S", "HIB": "F"}).fillna("A")
        needs = (hp_like
                 .assign(_art=hp_like[art_col_res].astype(str).str.strip(),
                         _qty=pd.to_numeric(hp_like[qty_col_res], errors="coerce").fillna(0.0))
                 .groupby(["_art", "_zon"], as_index=False)["_qty"].sum())

        for art_key, grp_art in needs.groupby("_art"):
            total_need = float(grp_art["_qty"].sum())
            if total_need <= 0:
                continue
            adjusted_total = max(0.0, round(total_need) - float(saldo_sum.get(art_key, 0.0)))

            if adjusted_total <= 0:
                continue  # 0-rad; hoppa över helt

            parts = []
            allocated_sum = 0
            for _, r in grp_art.iterrows():
                zone = str(r["_zon"])
                part = (float(r["_qty"]) / total_need) * adjusted_total if total_need > 0 else 0.0
                val = int(round(part))
                parts.append([zone, val])
                allocated_sum += val
            diff = int(adjusted_total) - int(allocated_sum)
            if parts:
                parts[0][1] += diff

            fifo_df = fifo_for_art(art_key)
            tillgangligt = float(pd.to_numeric(fifo_df["_qty"], errors="coerce").sum()) if not fifo_df.empty else 0.0

            for zone, behov_int in parts:
                behov_int = int(max(0, behov_int))
                if behov_int <= 0:
                    continue  # 0-rad → bort
                behov_kvar = float(behov_int)
                pall_count = 0
                for q in (fifo_df["_qty"].astype(float) if not fifo_df.empty else []):
                    if behov_kvar <= 0:
                        break
                    pall_count += 1
                    behov_kvar -= float(q)

                rows_hp.append({
                    "Artikel": art_key,
                    "Zon": zone,  # A eller S
                    "Behov (kolli)": behov_int,
                    "FIFO-baserad beräkning": int(pall_count),
                    "Tillräckligt tillgängligt saldo i buffert": "Ja" if tillgangligt >= behov_int else "Nej",
                    "Plockplats": plockplats_by_art.get(art_key, ""),
                    "Ej inlagrade (antal)": int(round(npu_sum.get(art_key, 0.0)))
                })

    refill_hp_df = pd.DataFrame(rows_hp)
    if not refill_hp_df.empty:
        refill_hp_df = refill_hp_df.sort_values(["Zon", "FIFO-baserad beräkning"], ascending=[True, False])

    refill_autostore_df = pd.DataFrame()
    try:
        as_df = result.copy()
        if not as_df.empty:
            mask_autostore = as_df["Källtyp"].astype(str) == "AUTOSTORE" if "Källtyp" in as_df.columns else pd.Series(False, index=as_df.index)
            k_blank = as_df["Källa"].isna() | (as_df["Källa"].astype(str).str.strip() == "") if "Källa" in as_df.columns else pd.Series(True, index=as_df.index)
            as_df = as_df[mask_autostore & k_blank].copy()
        if not as_df.empty:
            art_col_res_as = find_col(as_df, ORDER_SCHEMA["artikel"])
            qty_col_res_as = find_col(as_df, ORDER_SCHEMA["qty"])
            behov_per_art_as = as_df.groupby(as_df[art_col_res_as].astype(str).str.strip())[qty_col_res_as] \
                                   .apply(lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0).sum())) \
                                   .to_dict()

            rows_as: List[dict] = []
            for art, behov in behov_per_art_as.items():
                art_key = str(art).strip()
                fifo_df = fifo_for_art(art_key)
                tillgangligt = float(pd.to_numeric(fifo_df["_qty"], errors="coerce").sum()) if not fifo_df.empty else 0.0
                behov_int = int(max(0, round(behov) - float(saldo_sum.get(art_key, 0.0))))
                if behov_int <= 0:
                    continue  # 0-rad bort
                remaining = float(behov_int)
                pall_count = 0
                for q in (fifo_df["_qty"].astype(float) if not fifo_df.empty else []):
                    if remaining <= 0:
                        break
                    pall_count += 1
                    remaining -= float(q)

                rows_as.append({
                    "Artikel": art_key,
                    "Behov (kolli)": behov_int,
                    "FIFO-baserad beräkning": int(pall_count),
                    "Tillräckligt tillgängligt saldo i buffert": "Ja" if tillgangligt >= behov_int else "Nej",
                    "Plockplats": plockplats_by_art.get(art_key, ""),
                    "Ej inlagrade (antal)": int(round(npu_sum.get(art_key, 0.0)))
                })

            refill_autostore_df = pd.DataFrame(rows_as)
            if not refill_autostore_df.empty:
                refill_autostore_df = refill_autostore_df.sort_values("FIFO-baserad beräkning", ascending=False)
    except Exception:
        refill_autostore_df = pd.DataFrame()

    return refill_hp_df, refill_autostore_df
