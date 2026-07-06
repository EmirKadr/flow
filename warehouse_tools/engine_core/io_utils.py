"""Inläsning och normalisering av prognos-/kampanj-/saldo-/artikeltabeller."""
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
    ITEM_SCHEMA,
    NOT_PUTAWAY_SCHEMA,
    SALDO_SCHEMA,
)

def read_prognos_xlsx(path: str) -> pd.DataFrame:
    """
    Läser en prognos (XLSX) och returnerar ett normaliserat DataFrame.
    Steg:
      1) Ta bort de tre första raderna (index 0,1,3) om de finns.
      2) Ta bort kolumn A (första kolumnen).
      3) Använd första kvarvarande rad som rubriker och plocka ut relevanta kolumner.

    Returnerar DataFrame med kolumner:
      - Artikelnummer (str)
      - Beskrivning (str)
      - Antal styck (int)
      - Antal rader (int)
      - Antal butiker (int)
    """
    df = pd.read_excel(path, header=None, dtype=str, engine="openpyxl")
    if df.empty:
        return pd.DataFrame(columns=["Artikelnummer", "Beskrivning", "Antal styck", "Antal rader", "Antal butiker"])
    drop_idx = [i for i in (0, 1, 3) if i < len(df.index)]
    df = df.drop(index=drop_idx, errors="ignore").reset_index(drop=True)
    if df.shape[1] > 0:
        df = df.drop(columns=[df.columns[0]]).reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=["Artikelnummer", "Beskrivning", "Antal styck", "Antal rader", "Antal butiker"])
    header = df.iloc[0].astype(str).str.strip().tolist()
    df = df.iloc[1:].reset_index(drop=True)
    df.columns = header
    def _ci_match(name: str) -> str:
        return "".join(c.lower() for c in str(name).strip() if c.isalnum())
    def _pick_col(cols: List[str], candidates: List[str]) -> str | None:
        s_cols = { _ci_match(c): c for c in cols }
        for cand in candidates:
            key = _ci_match(cand)
            if key in s_cols:
                return s_cols[key]
        return None
    need_map: Dict[str, List[str]] = {
        "Artikelnummer": ["Product code", "SKU", "Artikelnr", "Artikelnummer"],
        "Beskrivning":   ["Product name", "Name", "Benämning", "Beskrivning"],
        "Antal styck":   ["Antal styck", "Antal stycken", "Qty", "Quantity"],
        "Antal rader":   ["Antal rader", "Rows", "Number of rows"],
        "Antal butiker": ["Antal butiker", "Stores", "Butiker", "Number of stores"],
    }
    picked: Dict[str, str] = {}
    for out_name, candidates in need_map.items():
        col = _pick_col(list(df.columns), candidates)
        if col:
            picked[out_name] = col
    out = pd.DataFrame()
    for out_name in ["Artikelnummer", "Beskrivning", "Antal styck", "Antal rader", "Antal butiker"]:
        if out_name in picked:
            out[out_name] = df[picked[out_name]]
        else:
            out[out_name] = pd.Series([None] * len(df), dtype=object)
    out["Artikelnummer"] = out["Artikelnummer"].astype(str).str.strip()
    out["Beskrivning"]   = out["Beskrivning"].astype(str).str.strip()
    for num_col in ["Antal styck", "Antal rader", "Antal butiker"]:
        out[num_col] = pd.to_numeric(out[num_col], errors="coerce").fillna(0).astype(int)
    mask_keep = out["Artikelnummer"].str.len().gt(0) | out["Beskrivning"].str.len().gt(0)
    out = out.loc[mask_keep].reset_index(drop=True)
    return out

def read_campaign_xlsx(path: str) -> pd.DataFrame:
    """
    Läs och normalisera en kampanjvolymfil (XLSX) enligt en fördefinierad sekvens av borttagningar av rader och kolumner.
    Returnerar ett DataFrame med kolumnerna:
      - Artikelnummer (str)
      - Antal styck (int)
    """
    df = pd.read_excel(path, header=None, dtype=str, engine="openpyxl")
    if df.empty:
        return pd.DataFrame(columns=["Artikelnummer", "Antal styck"])
    if len(df.index) > 4:
        df = df.drop(index=[4])
    drop_idx = [i for i in (0, 1, 2) if i < len(df.index)]
    df = df.drop(index=drop_idx)
    df = df.reset_index(drop=True)
    keep_cols = [c for c in df.columns if c <= 6]
    df = df.loc[:, keep_cols]
    if 5 in df.columns:
        df = df.drop(columns=[5])
    if 4 in df.columns:
        df = df.drop(columns=[4])
    if 3 in df.columns:
        df = df.drop(columns=[3])
    if 1 in df.columns:
        df = df.drop(columns=[1])
    if 0 in df.columns:
        df = df.drop(columns=[0])
    if df.shape[1] != 2:
        return pd.DataFrame(columns=["Artikelnummer", "Antal styck"])
    df = df.reset_index(drop=True)
    df.columns = ["Artikelnummer", "Antal styck"]
    df["Artikelnummer"] = df["Artikelnummer"].astype(str).str.strip()
    df["Antal styck"] = pd.to_numeric(df["Antal styck"], errors="coerce").fillna(0).astype(int)
    df = df.loc[df["Artikelnummer"].astype(str).str.len().gt(0)].reset_index(drop=True)
    if not df.empty and str(df.loc[0, "Artikelnummer"]).lower() in ("produktkod", "#"):
        df = df.drop(index=[0]).reset_index(drop=True)
    return df

def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ta bort BOM/whitespace i kolumnnamn för robustare kolumnmatchning."""
    try:
        df.rename(columns=lambda c: str(c).replace("\ufeff", "").strip(), inplace=True)
    except Exception:
        pass
    return df

def smart_to_datetime(s) -> pd.Series:
    """Robust datumtolkning (ISO→dayfirst=False, annars True; fallback tvärtom)."""
    try:
        ser = pd.Series(s) if not isinstance(s, pd.Series) else s
        vals = ser.dropna().astype(str).str.strip()
        sample = vals.head(50)
        numeric_like = (sample.str.match(r"^\d{8}$").sum() >= max(1, int(len(sample) * 0.6)))
        if numeric_like:
            dt = pd.to_datetime(ser, format="%Y%m%d", errors="coerce")
            if not dt.isna().all():
                return dt
        iso_like = (sample.str.match(r"^\d{4}-\d{2}-\d{2}").sum() >= max(1, int(len(sample) * 0.6)))
        primary_dayfirst = False if iso_like else True
        dt = pd.to_datetime(ser, errors="coerce", dayfirst=primary_dayfirst)
        if hasattr(dt, "isna") and getattr(dt, "isna")().all():
            dt = pd.to_datetime(ser, errors="coerce", dayfirst=not primary_dayfirst)
        return dt
    except Exception:
        try: return pd.to_datetime(s, errors="coerce", dayfirst=True)
        except Exception: return pd.to_datetime(s, errors="coerce", dayfirst=False)

def to_num(x) -> float:
    if pd.isna(x): return 0.0
    s = str(x).replace(" ", "").replace(",", ".")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    return float(m.group()) if m else 0.0

def find_col(df: pd.DataFrame, candidates: List[str], required: bool = True, default=None) -> str:
    """Hitta en kolumn genom exakt eller substring-match mot kandidatnamn (case-insensitive)."""
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols: return cols[cand.lower()]
    for key, orig in cols.items():
        for cand in candidates:
            if cand.lower() in key: return orig
    if required and default is None:
        raise KeyError(f"Hittar inte kolumnerna {candidates} i {list(df.columns)}")
    return default

def normalize_not_putaway(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Mappa 'Ej inlagrade' till enkel struktur. Ingen påverkan på allokering/refill."""
    df = df_raw.copy()
    def col(key: str, required: bool, default=None) -> str:
        return find_col(df, NOT_PUTAWAY_SCHEMA[key], required=required, default=default)
    art_col  = col("artikel", True)
    name_col = col("namn", False, default=None)
    qty_col  = col("antal", True)
    st_col   = col("status", False, default=None)
    pall_col = col("pallnr", False, default=None)
    sscc_col = col("sscc", False, default=None)
    chg_col  = col("andrad", False, default=None)
    exp_col  = col("utgang", False, default=None)
    out = pd.DataFrame({
        "Artikel": df[art_col].astype(str).str.strip(),
        "Namn":    df[name_col].astype(str).str.strip() if name_col else "",
        "Antal":   df[qty_col].map(to_num).astype(float),
        "Status":  pd.to_numeric(df[st_col], errors="coerce") if st_col else pd.Series([np.nan]*len(df)),
        "Pall nr": df[pall_col].astype(str) if pall_col else "",
        "SSCC":    df[sscc_col].astype(str) if sscc_col else "",
        "Ändrad":  smart_to_datetime(df[chg_col]) if chg_col else pd.NaT,
        "Utgång":  smart_to_datetime(df[exp_col]) if exp_col else pd.NaT,
    })
    for c in ["Namn","Pall nr","SSCC"]:
        if c in out.columns: out[c] = out[c].fillna("").astype(str).str.strip()
    return out

def normalize_saldo(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Mappa saldofil till struktur per artikel: Plocksaldo (sum) + Plockplats (första icke-tom)."""
    df = _clean_columns(df_raw.copy())
    def col(key: str, required: bool, default=None) -> str:
        return find_col(df, SALDO_SCHEMA[key], required=required, default=default)
    art_col   = col("artikel", True)
    saldo_col = col("plocksaldo", False, default=None)
    plats_col = col("plockplats", False, default=None)

    if saldo_col is None:
        return pd.DataFrame(columns=["Artikel", "Plocksaldo", "Plockplats"])

    out = pd.DataFrame({
        "Artikel": df[art_col].astype(str).str.strip(),
        "Plocksaldo": pd.to_numeric(df[saldo_col].map(to_num), errors="coerce").fillna(0.0),
        "Plockplats": (df[plats_col].astype(str).str.strip() if plats_col else pd.Series([""]*len(df))),
    })
    agg = (out.groupby("Artikel", as_index=False)
              .agg({"Plocksaldo":"sum","Plockplats":lambda s: next((x for x in s if isinstance(x,str) and x.strip()), "")}))
    return agg

def normalize_items(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalisera item-fil för att extrahera artikelnummer och staplingsbar-flagga.
    Returnerar DataFrame med kolumner ["Artikel", "Staplingsbar"].

    Parametrar:
        df_raw: O-normaliserad DataFrame från item-CSV.
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=["Artikel", "Staplingsbar"])
    df = df_raw.copy()
    df = _clean_columns(df)
    try:
        art_col = find_col(df, ITEM_SCHEMA["artikel"], required=True)
    except Exception:
        art_col = None
    try:
        stap_col = find_col(df, ITEM_SCHEMA["staplingsbar"], required=False, default=None)
    except Exception:
        stap_col = None
    if not art_col:
        return pd.DataFrame(columns=["Artikel", "Staplingsbar"])
    if not stap_col or stap_col not in df.columns:
        tmp = df[[art_col]].copy()
        tmp.columns = ["Artikel"]
        tmp["Ej Staplingsbar"] = ""
        return tmp.drop_duplicates(subset=["Artikel"]).reset_index(drop=True)
    tmp = df[[art_col, stap_col]].copy()
    tmp.columns = ["Artikel", "Ej Staplingsbar"]
    tmp["Artikel"] = tmp["Artikel"].astype(str).str.strip()
    tmp["Ej Staplingsbar"] = tmp["Ej Staplingsbar"].fillna("").astype(str).str.strip()
    return tmp.drop_duplicates(subset=["Artikel"]).reset_index(drop=True)

def reclassify_skrymmande(result_df: pd.DataFrame, saldo_norm: pd.DataFrame | None) -> pd.DataFrame:
    """
    Omklassificera rader utifrån orderfilens zonkod.

    Efter att HELPALL‑ och AUTOSTORE‑allokeringar är bestämda (dvs. Källtyp
    "HELPALL" respektive "AUTOSTORE"), sätts Källtyp och "Zon (beräknad)"
    för övriga rader baserat på den befintliga "Zon"‑kolumnen i
    beställningsfilen. Följande mappning används (zon → (källtyp, zon)):

      * "S" → ("SKRYMMANDE",   "S")
      * "E" → ("EHANDEL",      "E")
      * "A" → ("HUVUDPLOCK",   "A")
      * "Q" → ("EHANDEL",      "Q")
      * "O" → ("SKRYMMANDE",   "O")
      * "F" → ("HIB",          "F")

    Rader vars Källtyp redan är "HELPALL" eller "AUTOSTORE" lämnas
    oförändrade. Om ingen "Zon"‑kolumn hittas returneras oförändrat DataFrame.
    Den medskickade saldofil används inte i denna metod.
    """
    if result_df is None or result_df.empty:
        return result_df
    res = result_df.copy()
    zon_col = None
    for c in res.columns:
        if str(c).strip().lower() == "zon":
            zon_col = c
            break
    if not zon_col:
        return res
    if "Zon (beräknad)" not in res.columns:
        res["Zon (beräknad)"] = ""
    ktyp_series = res.get("Källtyp", pd.Series("", index=res.index)).astype(str)
    mask_to_change = ~(ktyp_series.isin(["HELPALL", "AUTOSTORE"]))
    if not mask_to_change.any():
        return res
    mapping: Dict[str, Tuple[str, str]] = {
        "S": ("SKRYMMANDE",   "S"),
        "E": ("EHANDEL",      "E"),
        "A": ("HUVUDPLOCK",   "A"),
        "Q": ("EHANDEL",      "Q"),
        "O": ("SKRYMMANDE",   "O"),
        "F": ("HIB",          "F"),
        "D": ("DISPLAY",      "D"),
    }
    zones = res.loc[mask_to_change, zon_col].astype(str).str.strip().str.upper()
    for zone_code, (ktyp_val, zon_val) in mapping.items():
        idx = res.loc[mask_to_change].index[zones == zone_code]
        if len(idx) > 0:
            res.loc[idx, "Källtyp"] = ktyp_val
            res.loc[idx, "Zon (beräknad)"] = zon_val
    return res
