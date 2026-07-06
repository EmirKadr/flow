"""Filtypsdetektering och CLI-tabelläsning."""
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
    ORDER_SCHEMA,
)
from .io_utils import (
    _clean_columns,
    find_col,
    read_campaign_xlsx,
    read_prognos_xlsx,
)
from .ordersaldo import (
    _find_lyx_max_csv,
)

def detect_file_type(path: str) -> str | None:
    """Försök avgöra vilken sorts fil det är (orders, buffer, automation, item, prognos, campaign).
    Returnerar en sträng med typen eller None om okänd.
    """
    import os
    import pandas as _pd
    ext = os.path.splitext(path)[1].lower().lstrip('.')
    base_name = os.path.basename(path).lower()
    wms_name_hints = {
        "v_ask_receive_log": "wms_receive",
        "v_ask_booking_putaway": "wms_booking",
        "v_ask_article_buffertpallet": "buffer",
        "v_ask_trans_log": "wms_trans",
        "v_ask_pick_log_full": "wms_pick",
        "v_ask_correct_log": "wms_correct",
    }
    for hint, file_type in wms_name_hints.items():
        if hint in base_name:
            return file_type
    # Filename hint fallback for buffer exports with varying schemas.
    generic_buffer_name_hints = (
        "buffertpall",
        "buffertpallet",
        "buffert_pall",
        "bufferpall",
        "bufferpallet",
        "buffer_pallet",
    )
    if any(hint in base_name for hint in generic_buffer_name_hints):
        return "buffer"
    if ext in ("xlsx", "xlsm", "xls"):
        try:
            df_c = read_campaign_xlsx(path)
            if isinstance(df_c, _pd.DataFrame) and not df_c.empty and list(df_c.columns) == ["Artikelnummer", "Antal styck"]:
                return "campaign"
        except Exception:
            pass
        try:
            df_p = read_prognos_xlsx(path)
            if isinstance(df_p, _pd.DataFrame) and not df_p.empty and len(df_p.columns) >= 3 and any(str(c).strip().lower() in ("antal styck", "quantity", "qty") for c in df_p.columns):
                return "prognos"
        except Exception:
            pass
        return None
    try:
        df = _pd.read_csv(path, dtype=str, nrows=50, sep=None, engine="python", encoding="utf-8-sig")
        if df.shape[1] == 1:
            df = _pd.read_csv(path, dtype=str, nrows=50, sep="\t", engine="python", encoding="utf-8-sig")
    except Exception:
        try:
            df = _pd.read_csv(path, dtype=str, nrows=50, sep="\t", engine="python", encoding="utf-8-sig")
        except Exception:
            return None
    cols = [str(c).strip().lower() for c in df.columns]
    has_art = any(c in ("artikel", "artikelnummer", "artnr", "art.nr", "sku", "article") for c in cols)
    has_qty = any(c in ("beställt", "antal", "qty", "quantity", "bestalld", "order qty", "antal styck") for c in cols)
    has_ord = any(c in ("ordernr", "order nr", "order number", "kund", "kundnr", "order id") for c in cols)
    has_rad = any(c in ("radnr", "rad nr", "line id", "rad", "struktur", "radsnr") for c in cols)
    if has_art and has_qty and (has_ord or has_rad):
        return "orders"
    has_lagerplats = any("lagerplats" in c or "plats" == c or "location" == c or "bin" == c for c in cols)
    has_pallid = any(c in ("pallid", "pall id", "id", "sscc", "etikett", "batch") for c in cols)
    has_status = any(c == "status" for c in cols)
    has_inkop = any("inköpsnr" in c or "inkopsnr" in c for c in cols)
    has_mottaget = any("mottaget" in c for c in cols)
    has_pallnr = any("pall nr" in c or "pallnr" in c for c in cols)
    has_till = any(c == "till" or c.endswith(" till") or c.startswith("till ") for c in cols)
    has_fran = any("från" in c or "fran" in c for c in cols)
    has_plockat = any("plockat" in c for c in cols)
    has_anledning = any("anledning" in c for c in cols)

    if has_inkop and has_art and has_pallid and has_mottaget:
        return "wms_receive"
    if has_inkop and (has_pallnr or has_pallid) and not has_mottaget and not has_plockat:
        return "wms_booking"
    if has_lagerplats and has_pallid and has_inkop:
        return "buffer"
    if has_pallid and has_till and has_fran:
        return "wms_trans"
    if has_pallid and has_plockat and has_ord:
        return "wms_pick"
    if has_anledning and has_qty:
        return "wms_correct"

    if has_art and has_qty and has_lagerplats:
        return "buffer"
    # Buffer exports can include saldo-like columns. Keep buffer precedence.
    buffer_marker_count = sum(
        1 for flag in (has_lagerplats, has_pallid, has_status, has_inkop, has_mottaget, has_pallnr) if flag
    )
    if has_art and (has_qty or has_pallid) and buffer_marker_count >= 2:
        return "buffer"
    has_pack = any("pack klass" in c or "staplingsbar" in c for c in cols)
    # Om filen innehåller pack‑relaterade kolumner ("pack klass" eller "staplingsbar"),
    # kontrollera först om den också motsvarar en dispatchfil. Dispatchfiler har
    # plockpallskolumn samt både ordernummer och sändningsinformation. Utan denna
    # kontroll klassificerades dispatchpallar felaktigt som item.
    if has_pack:
        # dispatch‑indikatorer
        has_plockpall = any("plockpall" in c for c in cols)
        has_dispatch_order = any(c in ("ordernr", "order nr", "order number", "ordernummer") for c in cols)
        has_dispatch_ship = any(
            ("sändnings" in c) or ("sandnings" in c) or ("sändningsnr" in c) or ("sandningsnr" in c) or ("sändningsnr." in c) or ("sandningsnr." in c)
            for c in cols
        )
        # om dispatchindikatorer hittas, återgå "dispatch" istället för "item"
        if has_plockpall and has_dispatch_order and has_dispatch_ship:
            return "dispatch"
        return "item"
    # Ny detektering för orderöversikt (overview)
    has_ordernr = any(c in ("ordernr", "order nr", "order number") for c in cols)
    has_orderdatum = any("orderdatum" in c for c in cols)
    has_sandning = any("sändningsnr" in c or "sandningsnr" in c or "sändningsnr." in c or "sandnr" in c for c in cols)
    has_ordertyp = any("ordertyp" in c for c in cols)
    has_multi = any("multi" == c for c in cols)
    # kräver flera av dessa kolumner för att identifiera en orderöversikt
    if has_ordernr and has_orderdatum and has_sandning and has_ordertyp:
        return "overview"
    # Ny detektering för dispatchpallar (dispatch)
    has_plockpall = any("plockpall" in c for c in cols)
    has_dispatch_order = any(c in ("ordernr", "order nr", "order number", "ordernummer") for c in cols)
    has_dispatch_ship = any(
        ("sändnings" in c) or ("sandnings" in c) or ("sändningsnr" in c) or ("sandningsnr" in c) or ("sändningsnr." in c) or ("sandningsnr." in c)
        for c in cols
    )
    if has_plockpall and has_dispatch_order and has_dispatch_ship:
        return "dispatch"
    has_robot = any(c == "robot" for c in cols)
    has_saldo = any(("saldo autoplock" in c) or (c == "plocksaldo") or (c == "plock saldo") for c in cols)
    if has_art and (has_robot or has_saldo):
        return "automation"
    return None

def _read_cli_table(path: str) -> pd.DataFrame:
    """Las en tabellfil for CLI-kommandon och normalisera kolumnnamn."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Filen finns inte: {target}")

    suffix = target.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return _clean_columns(pd.read_excel(target, dtype=str))

    try:
        df = pd.read_csv(target, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        if df.shape[1] == 1 and len(df):
            first = str(df.iloc[0, 0])
            if "\t" in first:
                df = pd.read_csv(target, dtype=str, sep="\t", engine="python", encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(target, dtype=str, sep="\t", engine="python", encoding="utf-8-sig")
    return _clean_columns(df)

def _df_with_named_index(df: pd.DataFrame, index_name: str) -> pd.DataFrame:
    out = df.copy()
    out.index = out.index.map(lambda value: str(value).strip())
    return out.reset_index().rename(columns={"index": index_name})

def _merge_item_flags(result_df: pd.DataFrame, item_norm: pd.DataFrame | None) -> pd.DataFrame:
    if not isinstance(result_df, pd.DataFrame) or result_df.empty:
        return result_df

    result = result_df.copy()
    if not isinstance(item_norm, pd.DataFrame) or item_norm.empty:
        if "Ej Staplingsbar" not in result.columns:
            result["Ej Staplingsbar"] = ""
        cols = [c for c in result.columns if c != "Ej Staplingsbar"] + ["Ej Staplingsbar"]
        return result[cols]

    art_col_res = find_col(result, ORDER_SCHEMA["artikel"], required=True)
    merged = result.merge(item_norm, how="left", left_on=art_col_res, right_on="Artikel", suffixes=("", "_item"))
    if "Artikel_item" in merged.columns:
        merged.drop(columns=["Artikel_item"], inplace=True, errors=False)
    if "Artikel_y" in merged.columns:
        merged.drop(columns=["Artikel_y"], inplace=True, errors=False)
    if "Ej Staplingsbar_y" in merged.columns:
        merged["Ej Staplingsbar"] = merged["Ej Staplingsbar_y"].fillna("")
    elif "Ej Staplingsbar_x" in merged.columns:
        merged["Ej Staplingsbar"] = merged["Ej Staplingsbar_x"].fillna("")
    elif "Ej Staplingsbar" not in merged.columns:
        merged["Ej Staplingsbar"] = ""
    for col in ["Ej Staplingsbar_x", "Ej Staplingsbar_y"]:
        if col in merged.columns:
            merged.drop(columns=[col], inplace=True)
    cols = [c for c in merged.columns if c != "Ej Staplingsbar"] + ["Ej Staplingsbar"]
    return merged[cols]

def _resolve_max_csv_path(explicit_path: Optional[str]) -> Path:
    if explicit_path:
        target = Path(explicit_path)
        if not target.exists():
            raise FileNotFoundError(f"Filen finns inte: {target}")
        return target

    found = _find_lyx_max_csv()
    if found is None:
        raise FileNotFoundError("Kunde inte hitta lowfreqdata/buffertpall/artikel_max.csv.")
    return found

def _read_cli_text_lines(path: str) -> list[str]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Filen finns inte: {target}")
    try:
        text = target.read_text(encoding="utf-8-sig")
    except Exception:
        text = target.read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]
