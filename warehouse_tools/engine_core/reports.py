"""CLI-resultatbyggare för Bearbeta-flödena (rapporter och checkar)."""
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

from ..vendor.app_info import APP_VERSION
from ..vendor.update_service import check_for_update, download_update_installer
from .allocation import (
    build_prognos_vs_autoplock_report,
)
from .constants import (
    VECKA27_ROOF_TO_MOWERS,
)
from .filetypes import (
    _read_cli_table,
)
from .io_utils import (
    _clean_columns,
    read_campaign_xlsx,
    read_prognos_xlsx,
    to_num,
)
from .observations import (
    _artikel_max_change_summary,
    _read_artikel_max,
    _read_observations,
    business_artikel_max_path,
    business_observations_path,
    fetch_observations_from_github,
    push_new_observations_to_github,
    update_observations_from_buffer,
)
from .ordersaldo import (
    _find_ordersaldo_columns,
)

@dataclass
class OverviewCheckResult:
    shipment_df: pd.DataFrame
    hib_df: pd.DataFrame
    missing_hib_cols: list[str]
    log_lines: list[str]

@dataclass
class DispatchCheckResult:
    diff_df: pd.DataFrame
    log_lines: list[str]

@dataclass
class Vecka27CheckResult:
    deviations: list[str]
    report_text: str
    report_df: pd.DataFrame
    log_lines: list[str]

@dataclass
class PrognosReportResult:
    combined_df: pd.DataFrame
    report_df: pd.DataFrame
    meta: dict[str, str]
    log_lines: list[str]

@dataclass
class ChunkedValuesResult:
    report_df: pd.DataFrame
    value_count: int
    chunk_count: int
    chunk_size: int

@dataclass
class ObservationsUpdateResult:
    new_rows_df: pd.DataFrame
    new_row_count: int
    github_sent_rows: int
    article_max_rows: int
    article_max_changed_rows: int
    article_max_increased_rows: int
    article_max_decreased_rows: int
    article_max_new_rows: int
    article_max_removed_rows: int
    article_max_changed_examples: List[Dict[str, str]]
    pushed_to_github: bool
    observations_path: str
    article_max_path: str

@dataclass
class ObservationsSyncResult:
    fetched_rows: int
    pushed_rows: int
    total_observations: int
    article_max_rows: int
    observations_path: str
    article_max_path: str

@dataclass
class UpdateCheckCliResult:
    has_update: bool
    current_version: str
    latest_version: str
    release_url: str
    installer_name: str
    downloaded_path: str

def _vecka27_fmt_qty_value(q: float) -> str:
    try:
        f = float(q)
    except Exception:
        return str(q)
    return str(int(f)) if f.is_integer() else str(f)

def _find_keywords_column(df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
    for keyword in keywords:
        keyword_norm = keyword.lower().replace(" ", "")
        for col in df.columns:
            if str(col).lower().replace(" ", "") == keyword_norm:
                return str(col)
    for keyword in keywords:
        keyword_lower = keyword.lower()
        for col in df.columns:
            if keyword_lower in str(col).lower():
                return str(col)
    return None

def _find_customer_name_column(df: pd.DataFrame, exclude: Optional[set[str]] = None) -> Optional[str]:
    excluded = exclude or set()
    for col in df.columns:
        if col in excluded:
            continue
        col_norm = str(col).lower().replace(" ", "")
        if "kund" in col_norm and not col_norm.endswith("nr") and not col_norm.endswith("nummer"):
            return str(col)
    return None

def _status_to_int(value: object) -> Optional[int]:
    try:
        raw = str(value).strip().replace(",", ".")
        if not raw:
            return None
        return int(float(raw))
    except Exception:
        return None

def _build_order_to_customer_map(
    details_df: Optional[pd.DataFrame],
    overview_df: pd.DataFrame,
    overview_order_col: Optional[str],
    overview_customer_col: Optional[str],
) -> Dict[str, str]:
    order_to_customer: Dict[str, str] = {}

    if isinstance(details_df, pd.DataFrame) and not details_df.empty:
        details = _clean_columns(details_df.copy())
        details_order_col = _find_keywords_column(details, ["order nr", "ordernr", "ordernummer", "order number", "orderid"])
        details_customer_col = _find_customer_name_column(details, exclude={details_order_col} if details_order_col else set())
        if details_order_col and details_customer_col:
            try:
                order_to_customer = (
                    details.groupby(details_order_col)[details_customer_col]
                    .first()
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .to_dict()
                )
            except Exception:
                order_to_customer = {}

    if order_to_customer or not overview_order_col or not overview_customer_col:
        return order_to_customer

    try:
        return (
            overview_df.groupby(overview_order_col)[overview_customer_col]
            .first()
            .fillna("")
            .astype(str)
            .str.strip()
            .to_dict()
        )
    except Exception:
        return {}

def _empty_prognos_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["Artikelnummer", "Beskrivning", "Antal styck", "Antal rader", "Antal butiker"]
    )

def _normalize_prognos_cli_table(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _empty_prognos_df()

    work = _clean_columns(df.copy())
    col_map: dict[str, str] = {}
    for col in work.columns:
        col_norm = str(col).strip().lower()
        if col_norm in {"product code", "produktkod", "artikelnummer", "artikelnr", "artnr", "sku", "article"}:
            col_map[col] = "Artikelnummer"
        elif col_norm in {"product name", "produktnamn", "produktnam", "name", "benämning", "benamning", "beskrivning"}:
            col_map[col] = "Beskrivning"
        elif col_norm in {"antal styck", "antal", "projicerat antal", "qty", "quantity"}:
            col_map[col] = "Antal styck"
        elif col_norm in {"antal rader", "rows", "number of rows"}:
            col_map[col] = "Antal rader"
        elif col_norm in {"antal butiker", "stores", "butiker", "number of stores"}:
            col_map[col] = "Antal butiker"
    if col_map:
        work = work.rename(columns=col_map)

    out = _empty_prognos_df()
    for column_name in out.columns:
        if column_name in work.columns:
            out[column_name] = work[column_name]
    out["Artikelnummer"] = out["Artikelnummer"].fillna("").astype(str).str.strip()
    out["Beskrivning"] = out["Beskrivning"].fillna("").astype(str).str.strip()
    for num_col in ["Antal styck", "Antal rader", "Antal butiker"]:
        out[num_col] = pd.to_numeric(out[num_col], errors="coerce").fillna(0).astype(int)
    out = out.loc[out["Artikelnummer"].str.len().gt(0) | out["Beskrivning"].str.len().gt(0)].reset_index(drop=True)
    return out

def _normalize_campaign_cli_table(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["Artikelnummer", "Antal styck"])

    work = _clean_columns(df.copy())
    col_map: dict[str, str] = {}
    for col in work.columns:
        col_norm = str(col).strip().lower()
        if col_norm in {"artikelnummer", "artikelnr", "artnr", "sku", "article", "product code"}:
            col_map[col] = "Artikelnummer"
        elif col_norm in {"antal styck", "antal", "qty", "quantity"}:
            col_map[col] = "Antal styck"
    if col_map:
        work = work.rename(columns=col_map)

    if "Artikelnummer" not in work.columns or "Antal styck" not in work.columns:
        return pd.DataFrame(columns=["Artikelnummer", "Antal styck"])

    out = work[["Artikelnummer", "Antal styck"]].copy()
    out["Artikelnummer"] = out["Artikelnummer"].fillna("").astype(str).str.strip()
    out["Antal styck"] = pd.to_numeric(out["Antal styck"], errors="coerce").fillna(0).astype(int)
    out = out.loc[out["Artikelnummer"].str.len().gt(0)].reset_index(drop=True)
    return out

def _load_prognos_cli_source(path: str) -> pd.DataFrame:
    suffix = Path(path).suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return read_prognos_xlsx(path)
    return _normalize_prognos_cli_table(_read_cli_table(path))

def _load_campaign_cli_source(path: str) -> pd.DataFrame:
    suffix = Path(path).suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return read_campaign_xlsx(path)
    return _normalize_campaign_cli_table(_read_cli_table(path))

def _combine_prognos_and_campaign(
    prognos_df: Optional[pd.DataFrame],
    campaign_df: Optional[pd.DataFrame],
    saldo_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    has_prognos = isinstance(prognos_df, pd.DataFrame) and not prognos_df.empty
    has_campaign = isinstance(campaign_df, pd.DataFrame) and not campaign_df.empty
    if not has_prognos and not has_campaign:
        raise ValueError("Välj och läs in antingen prognosfilen eller kampanjvolymerna först.")

    if has_prognos:
        combined_df = _normalize_prognos_cli_table(prognos_df)
    else:
        combined_df = _empty_prognos_df()

    if not has_campaign:
        return combined_df

    camp_df = _normalize_campaign_cli_table(campaign_df)
    if camp_df.empty:
        return combined_df

    if isinstance(saldo_df, pd.DataFrame) and not saldo_df.empty:
        saldo_work = _clean_columns(saldo_df.copy())
        art_col_sal = None
        robot_col_sal = None
        for col in saldo_work.columns:
            col_norm = str(col).strip().lower()
            if not art_col_sal and col_norm in {"artikel", "artikelnummer", "artnr", "art.nr", "sku", "article"}:
                art_col_sal = str(col)
            if not robot_col_sal and col_norm == "robot":
                robot_col_sal = str(col)
        if art_col_sal and robot_col_sal:
            saldo_work = saldo_work[[art_col_sal, robot_col_sal]].copy()
            saldo_work.columns = ["Artikelnummer", "Robot"]
            saldo_work["Artikelnummer"] = saldo_work["Artikelnummer"].astype(str).str.strip()
            saldo_work["Robot"] = saldo_work["Robot"].astype(str).str.upper().str.strip()
            saldo_work = saldo_work.loc[saldo_work["Robot"] == "Y"]
            if not saldo_work.empty:
                camp_df = camp_df.merge(saldo_work[["Artikelnummer"]], on="Artikelnummer", how="inner")
            else:
                camp_df = camp_df.iloc[0:0]
        else:
            camp_df = camp_df.iloc[0:0]

    if camp_df.empty:
        return combined_df

    vol_by_art = camp_df.groupby("Artikelnummer")["Antal styck"].sum().to_dict()
    combined_df["Artikelnummer"] = combined_df["Artikelnummer"].astype(str).str.strip()
    combined_df["Antal styck"] = pd.to_numeric(
        combined_df.get("Antal styck", 0), errors="coerce"
    ).fillna(0).astype(int)
    existing_arts = set(combined_df["Artikelnummer"].astype(str))
    for art, vol in vol_by_art.items():
        if art in existing_arts:
            mask = combined_df["Artikelnummer"] == art
            combined_df.loc[mask, "Antal styck"] = (
                combined_df.loc[mask, "Antal styck"].astype(int) + int(vol)
            ).astype(int)
        else:
            combined_df = pd.concat(
                [
                    combined_df,
                    pd.DataFrame(
                        {
                            "Artikelnummer": [art],
                            "Beskrivning": [None],
                            "Antal styck": [int(vol)],
                            "Antal rader": [0],
                            "Antal butiker": [0],
                        }
                    ),
                ],
                ignore_index=True,
            )
    return combined_df.reset_index(drop=True)

def _validate_prognos_report_saldo(saldo_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if not isinstance(saldo_df, pd.DataFrame) or saldo_df.empty:
        raise ValueError("Ladda eller ange Saldo inkl. automation forst. Prognosrapporten filtrerar pa Robot=Y.")

    saldo_work = _clean_columns(saldo_df.copy())
    has_robot_col = any(str(col).strip().lower() == "robot" for col in saldo_work.columns)
    if not has_robot_col:
        raise ValueError("Saldofilen saknar kolumnen Robot. Prognosrapporten filtrerar pa Robot=Y.")
    return saldo_work

def build_prognos_report_result(
    prognos_df: Optional[pd.DataFrame] = None,
    campaign_df: Optional[pd.DataFrame] = None,
    saldo_df: Optional[pd.DataFrame] = None,
    buffer_df: Optional[pd.DataFrame] = None,
) -> PrognosReportResult:
    combined_df = _combine_prognos_and_campaign(prognos_df, campaign_df, saldo_df)
    saldo_df = _validate_prognos_report_saldo(saldo_df)
    report_df, meta = build_prognos_vs_autoplock_report(
        prognos_df=combined_df,
        saldo_norm_df=saldo_df,
        buffer_df=buffer_df,
        exclude_source_ids=None,
        allocated_df=None,
    )
    log_lines = [f"Prognosrapport skapad ({len(report_df)} rader)."]
    if isinstance(meta, dict) and meta.get("partial") == "yes":
        missing = str(meta.get("missing", "")).replace(",", ", ").strip()
        if missing:
            log_lines.append(f"PARTIELL: saknar {missing}.")
        note = str(meta.get("note", "")).strip()
        if note:
            log_lines.append(note)
    return PrognosReportResult(combined_df, report_df, meta, log_lines)

def build_chunked_values_result(values: list[str], chunk_size: int = 2000) -> ChunkedValuesResult:
    cleaned_values = [str(value).strip() for value in values if str(value).strip()]
    if not cleaned_values:
        raise ValueError("Klistra in värden först (en per rad).")
    try:
        chunk_size_int = int(chunk_size)
    except Exception as exc:
        raise ValueError("Antal per kolumn måste vara ett heltal > 0.") from exc
    if chunk_size_int <= 0:
        raise ValueError("Antal per kolumn måste vara ett heltal > 0.")

    chunks = [
        cleaned_values[start:start + chunk_size_int]
        for start in range(0, len(cleaned_values), chunk_size_int)
    ]
    out_cols: dict[str, pd.Series] = {}
    for idx, chunk in enumerate(chunks, start=1):
        out_cols[f"Kolumn {idx}"] = pd.Series([str(value) for value in chunk], dtype="string")
    report_df = pd.DataFrame(out_cols).fillna("")
    return ChunkedValuesResult(report_df, len(cleaned_values), len(chunks), chunk_size_int)

def build_observations_update_result(
    buffer_df: pd.DataFrame,
    observations_path: Optional[str] = None,
    artikel_max_out: Optional[str] = None,
    push_to_github: bool = False,
    business_code: Optional[str] = None,
) -> ObservationsUpdateResult:
    obs_path = Path(observations_path) if observations_path else business_observations_path(business_code)
    max_path = Path(artikel_max_out) if artikel_max_out else business_artikel_max_path(business_code)
    article_max_before = _read_artikel_max(max_path)
    new_row_count, new_rows_df = update_observations_from_buffer(
        buffer_df,
        observations_path=obs_path,
        artikel_max_path=max_path,
    )
    pushed = bool(
        push_to_github
        and new_row_count
        and push_new_observations_to_github(new_rows_df, business_code=business_code)
    )
    github_sent_rows = int(new_row_count) if pushed else 0
    article_max_after = _read_artikel_max(max_path)
    max_changes = _artikel_max_change_summary(article_max_before, article_max_after)
    article_max_rows = 0
    if max_path.exists() and max_path.stat().st_size > 0:
        try:
            article_max_rows = int(len(pd.read_csv(max_path, dtype=str, encoding="utf-8-sig")))
        except Exception:
            article_max_rows = 0
    return ObservationsUpdateResult(
        new_rows_df=new_rows_df,
        new_row_count=int(new_row_count),
        github_sent_rows=github_sent_rows,
        article_max_rows=article_max_rows,
        article_max_changed_rows=int(max_changes["changed_rows"]),
        article_max_increased_rows=int(max_changes["increased_rows"]),
        article_max_decreased_rows=int(max_changes["decreased_rows"]),
        article_max_new_rows=int(max_changes["new_article_rows"]),
        article_max_removed_rows=int(max_changes["removed_article_rows"]),
        article_max_changed_examples=list(max_changes["examples"]),
        pushed_to_github=pushed,
        observations_path=str(obs_path.resolve()),
        article_max_path=str(max_path.resolve()),
    )

def build_observations_sync_result(
    observations_path: Optional[str] = None,
    artikel_max_out: Optional[str] = None,
    remote_file: Optional[str] = None,
    push_orphaned: bool = True,
    business_code: Optional[str] = None,
) -> ObservationsSyncResult:
    obs_path = Path(observations_path) if observations_path else business_observations_path(business_code)
    max_path = Path(artikel_max_out) if artikel_max_out else business_artikel_max_path(business_code)
    fetched_rows, pushed_rows = fetch_observations_from_github(
        observations_path=obs_path,
        artikel_max_path=max_path,
        remote_file=remote_file,
        push_orphaned=push_orphaned,
        business_code=business_code,
    )
    total_observations = int(len(_read_observations(obs_path)))
    article_max_rows = 0
    if max_path.exists() and max_path.stat().st_size > 0:
        try:
            article_max_rows = int(len(pd.read_csv(max_path, dtype=str, encoding="utf-8-sig")))
        except Exception:
            article_max_rows = 0
    return ObservationsSyncResult(
        fetched_rows=int(fetched_rows),
        pushed_rows=int(pushed_rows),
        total_observations=total_observations,
        article_max_rows=article_max_rows,
        observations_path=str(obs_path.resolve()),
        article_max_path=str(max_path.resolve()),
    )

def _build_update_session_from_release_json(path: str):
    release_payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))

    class _StaticResponse:
        def __init__(self, data):
            self._data = data
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class _StaticSession:
        def __init__(self, data):
            self._response = _StaticResponse(data)

        def get(self, url, **kwargs):
            return self._response

    return _StaticSession(release_payload)

def build_update_check_cli_result(
    release_json_path: Optional[str] = None,
    download_dir: Optional[str] = None,
) -> UpdateCheckCliResult:
    session = _build_update_session_from_release_json(release_json_path) if release_json_path else None
    info = check_for_update(session=session)
    downloaded_path = ""
    if info and download_dir:
        downloaded_path = str(download_update_installer(info, target_dir=Path(download_dir)))
    if not info:
        return UpdateCheckCliResult(
            has_update=False,
            current_version=APP_VERSION,
            latest_version=APP_VERSION,
            release_url="",
            installer_name="",
            downloaded_path=downloaded_path,
        )
    return UpdateCheckCliResult(
        has_update=True,
        current_version=APP_VERSION,
        latest_version=info.version,
        release_url=info.release_url,
        installer_name=info.installer_name,
        downloaded_path=downloaded_path,
    )

def _build_overview_check_sheets(result: OverviewCheckResult) -> dict[str, pd.DataFrame]:
    sheets: dict[str, pd.DataFrame] = {}
    combined_parts: List[pd.DataFrame] = []

    if isinstance(result.shipment_df, pd.DataFrame) and not result.shipment_df.empty:
        shipment_df = result.shipment_df.copy()
        if "Avvikelsetyp" not in shipment_df.columns:
            shipment_df.insert(0, "Avvikelsetyp", "Sändningsnr med flera kunder/transportörer")
        sheets["Sändningskontroll"] = shipment_df.copy()
        combined_parts.append(shipment_df)

    if isinstance(result.hib_df, pd.DataFrame) and not result.hib_df.empty:
        hib_df = result.hib_df.copy()
        if "Avvikelsetyp" not in hib_df.columns:
            hib_df.insert(0, "Avvikelsetyp", "HIB över status 31 utan butikssändning")
        sheets["HIB utan butikssändning"] = hib_df.copy()
        combined_parts.append(hib_df)

    if combined_parts:
        sheets = {
            "Orderkontroll": pd.concat(combined_parts, ignore_index=True, sort=False),
            **sheets,
        }
    elif not sheets:
        sheets["Orderkontroll"] = pd.DataFrame(columns=["Avvikelsetyp"])

    return sheets

def build_overview_check_result(
    overview_df: pd.DataFrame,
    details_df: Optional[pd.DataFrame] = None,
) -> OverviewCheckResult:
    df = _clean_columns(overview_df.copy())
    if df.empty:
        return OverviewCheckResult(pd.DataFrame(), pd.DataFrame(), [], [])

    ship_col = _find_keywords_column(
        df,
        ["sändningsnr", "sändnings nr", "sändningsnummer", "sandningsnr", "sandnings nr", "sandningsnummer"],
    )
    if not ship_col:
        raise KeyError("Kunde inte identifiera sändningsnummer-kolumnen i orderöversikten.")

    cust_col = _find_keywords_column(df, ["kundnr", "kund nr", "kundnummer"])
    if not cust_col:
        cust_col = _find_customer_name_column(df, exclude={ship_col})
    if not cust_col:
        raise KeyError("Kunde inte identifiera kund-kolumnen i orderöversikten.")

    trans_col = _find_keywords_column(df, ["transportör", "transportor", "transportörsnr", "transportorsnr"])
    if not trans_col:
        trans_col = "__transport_dummy__"
        df[trans_col] = ""

    order_col = _find_keywords_column(df, ["ordernr", "order nr", "ordernummer", "order number", "orderid", "order id"])
    if not order_col:
        order_col = _find_keywords_column(df, ["order"])
    ordertype_col = _find_keywords_column(df, ["ordertyp", "ordertype"])
    status_col = _find_keywords_column(df, ["status", "orderstatus", "radstatus", "state"])
    if not status_col:
        status_col = _find_keywords_column(df, ["status"])

    df[ship_col] = df[ship_col].astype(str).str.strip()
    df[cust_col] = df[cust_col].astype(str).str.strip()
    df[trans_col] = df[trans_col].astype(str).str.strip()
    if order_col:
        df[order_col] = df[order_col].astype(str).str.strip()

    df = df[df[ship_col].astype(str).str.len() > 0].copy()
    if df.empty:
        return OverviewCheckResult(pd.DataFrame(), pd.DataFrame(), [], [])

    order_to_customer = _build_order_to_customer_map(details_df, df, order_col, cust_col)

    # Compute-then-filter: den dyra orders_list/customers/carriers-logiken nedan
    # behövs bara för sändningar som faktiskt flaggas (>1 unik kund ELLER
    # transportör). Förfiltrera vektoriserat så loopen kör bara för dessa i
    # stället för varje sändningsgrupp. Tomma strängar -> NaN så nunique(dropna)
    # räknar "antal unika icke-tomma värden" exakt som det explicita
    # [v for v in ... if v]-filtret i loopen (annars räknas "" som eget värde
    # och genererar falska avvikelserader).
    _cust_nonempty = df[cust_col].replace("", np.nan)
    _trans_nonempty = df[trans_col].replace("", np.nan)
    _cust_n = _cust_nonempty.groupby(df[ship_col]).nunique()
    _trans_n = _trans_nonempty.groupby(df[ship_col]).nunique()
    _flagged = _cust_n.index[_cust_n > 1].union(_trans_n.index[_trans_n > 1])
    _flagged_df = df[df[ship_col].isin(_flagged)]

    shipment_diff_rows: List[Dict[str, object]] = []
    for ship, group in _flagged_df.groupby(ship_col):
        try:
            customers = sorted(set(group[cust_col].dropna().astype(str).str.strip()))
            carriers = sorted(set(group[trans_col].dropna().astype(str).str.strip()))
            customers = [value for value in customers if value]
            carriers = [value for value in carriers if value]

            orders_list: List[str] = []
            if order_col:
                try:
                    order_vals = sorted(set(group[order_col].dropna().astype(str).str.strip()))
                except Exception:
                    order_vals = []
                for order_value in order_vals:
                    customer_name = order_to_customer.get(order_value, "")
                    orders_list.append(f"{order_value} ({customer_name})" if customer_name else order_value)

            if len(customers) > 1 or len(carriers) > 1:
                row: Dict[str, object] = {
                    "Avvikelsetyp": "Sändningsnr med flera kunder/transportörer",
                    "Sändningsnr": ship,
                    "Unika kunder": len(customers),
                    "Kunder": ", ".join(customers),
                    "Unika transportörer": len(carriers),
                    "Transportörer": ", ".join(carriers),
                    "Antal orderrader": int(len(group)),
                }
                if orders_list:
                    row["Ordernr (kundnamn)"] = ", ".join(orders_list)
                shipment_diff_rows.append(row)
        except Exception:
            continue

    shipment_df = pd.DataFrame(shipment_diff_rows) if shipment_diff_rows else pd.DataFrame()

    missing_hib_cols: List[str] = []
    if not order_col:
        missing_hib_cols.append("ordernummer")
    if not ordertype_col:
        missing_hib_cols.append("ordertyp")
    if not status_col:
        missing_hib_cols.append("status")

    hib_rows: List[Dict[str, object]] = []
    if not missing_hib_cols and order_col and ordertype_col and status_col:
        try:
            hib_df = df[[order_col, ship_col, cust_col, ordertype_col, status_col]].copy()
            hib_df["_ordertype_norm"] = hib_df[ordertype_col].astype(str).str.strip().str.upper()
            hib_df["_status_num"] = hib_df[status_col].apply(_status_to_int)

            store_mask = hib_df["_ordertype_norm"].eq("N") | hib_df["_ordertype_norm"].str.contains("BUTIK", na=False)
            store_ships = set(hib_df.loc[store_mask, ship_col].dropna().astype(str).str.strip().tolist())
            store_ships.discard("")

            hib_only_df = hib_df[hib_df["_ordertype_norm"].str.contains("HIB", na=False)].copy()
            for order_number, group in hib_only_df.groupby(order_col):
                order_number_str = str(order_number).strip()
                if not order_number_str:
                    continue
                status_values = [value for value in group["_status_num"].tolist() if value is not None]
                if not status_values:
                    continue
                max_status = max(status_values)
                if max_status <= 31:
                    continue
                hib_ships = sorted(set(group[ship_col].dropna().astype(str).str.strip()))
                hib_ships = [value for value in hib_ships if value]
                if not hib_ships or any(ship_value in store_ships for ship_value in hib_ships):
                    continue

                customer_name = order_to_customer.get(order_number_str, "")
                if not customer_name:
                    try:
                        customers = [value for value in group[cust_col].dropna().astype(str).str.strip().tolist() if value]
                        if customers:
                            customer_name = customers[0]
                    except Exception:
                        customer_name = ""

                row = {
                    "Ordernr": order_number_str,
                    "Sändningsnr": ", ".join(hib_ships),
                    "Ordertyp": "HIB",
                    "Status": int(max_status),
                    "Anmärkning": "HIB-order med status > 31 saknar matchande butikssändning",
                }
                if customer_name:
                    row["Kundnamn"] = customer_name
                hib_rows.append(row)
        except Exception:
            pass

    hib_result_df = pd.DataFrame(hib_rows) if hib_rows else pd.DataFrame()

    log_lines: list[str] = []
    if not shipment_df.empty:
        log_lines.append("Orderöversikt: sändningsnummer med flera kunder eller transportörer:")
        for _, row in shipment_df.iterrows():
            try:
                if int(row.get("Unika kunder", 0)) > 1:
                    log_lines.append(f"  Sändningsnr {row['Sändningsnr']} har flera kunder: {row['Kunder']}")
                if int(row.get("Unika transportörer", 0)) > 1:
                    log_lines.append(f"  Sändningsnr {row['Sändningsnr']} har flera transportörer: {row['Transportörer']}")
            except Exception:
                continue
    if not hib_result_df.empty:
        log_lines.append(f"HIB-ordrar med status > 31 utan matchande butikssändning ({len(hib_result_df)} st):")
        for _, row in hib_result_df.iterrows():
            try:
                name_part = f" ({row['Kundnamn']})" if str(row.get("Kundnamn", "")).strip() else ""
                log_lines.append(f"  Order {row['Ordernr']}{name_part}: sändning {row['Sändningsnr']} (status {row['Status']})")
            except Exception:
                continue
    if missing_hib_cols:
        log_lines.append("HIB-kontrollen kunde inte köras fullt ut (saknar kolumner: " + ", ".join(missing_hib_cols) + ").")

    return OverviewCheckResult(shipment_df, hib_result_df, missing_hib_cols, log_lines)

def build_dispatch_check_result(
    overview_df: pd.DataFrame,
    dispatch_df: pd.DataFrame,
    details_df: Optional[pd.DataFrame] = None,
) -> DispatchCheckResult:
    ov_df = _clean_columns(overview_df.copy())
    dp_df = _clean_columns(dispatch_df.copy())
    if ov_df.empty or dp_df.empty:
        return DispatchCheckResult(pd.DataFrame(), [])

    order_keywords = ["ordernr", "order nr", "ordernummer", "order number", "orderid", "order id"]
    ship_keywords = ["sändningsnr", "sändnings nr", "sändningsnummer", "sandningsnr", "sandnings nr", "sandningsnummer", "shipment"]
    plock_keywords = ["plockpallsnr", "plockpallsnr.", "plockpall", "plockpallnr", "plockpallsnummer", "plockpall nr"]

    ov_order_col = _find_keywords_column(ov_df, order_keywords)
    ov_ship_col = _find_keywords_column(ov_df, ship_keywords)
    if not ov_order_col or not ov_ship_col:
        raise KeyError("Kunde inte identifiera order- eller sändningskolumnen i orderöversikten.")

    dp_order_col = _find_keywords_column(dp_df, order_keywords)
    dp_ship_col = _find_keywords_column(dp_df, ship_keywords)
    plock_col = _find_keywords_column(dp_df, plock_keywords)
    if not dp_order_col or not dp_ship_col or not plock_col:
        raise KeyError("Kunde inte identifiera order-, sändnings- eller plockpallskolumnen i dispatchfilen.")

    ov_df[ov_order_col] = ov_df[ov_order_col].astype(str).str.strip()
    ov_df[ov_ship_col] = ov_df[ov_ship_col].astype(str).str.strip()
    dp_df[dp_order_col] = dp_df[dp_order_col].astype(str).str.strip()
    dp_df[dp_ship_col] = dp_df[dp_ship_col].astype(str).str.strip()
    dp_df[plock_col] = dp_df[plock_col].astype(str).str.strip()

    overview_customer_col = _find_customer_name_column(ov_df, exclude={ov_order_col, ov_ship_col})
    order_to_customer = _build_order_to_customer_map(details_df, ov_df, ov_order_col, overview_customer_col)

    order_to_ship: Dict[str, str] = {}
    try:
        # ov_order_col/ov_ship_col är redan astype(str).str.strip() ovan, så
        # "tom sträng" är enda saknad-markören. Filtrera bort tomma sändningsnr
        # och ta första per order — vektoriserat i stället för en Python-loop
        # som materialiserar en subframe per ordergrupp. groupby.first() ger
        # första icke-null (alla är icke-tomma strängar) i radordning = ships[0].
        _ship_nonempty = ov_df[ov_df[ov_ship_col].str.len() > 0]
        order_to_ship = _ship_nonempty.groupby(ov_order_col)[ov_ship_col].first().to_dict()
    except Exception:
        order_to_ship = {}

    # Vektoriserat i stället för dp_df.iterrows() (en Series/rad, ~50-100x
    # dyrare). Kolumnerna är redan astype(str).str.strip() ovan, så str().strip()
    # per rad är no-op. order_to_ship-värden är alltid icke-tomma, så notna()
    # motsvarar originalets truthy-koll `if expected_ship`.
    expected_ship = dp_df[dp_order_col].map(order_to_ship)
    mask = expected_ship.notna() & (expected_ship != dp_df[dp_ship_col])
    if not mask.any():
        diff_df = pd.DataFrame()
    else:
        diff_df = pd.DataFrame(
            {
                "Ordernr": dp_df.loc[mask, dp_order_col],
                "Översikt sändningsnr": expected_ship[mask],
                "Dispatch sändningsnr": dp_df.loc[mask, dp_ship_col],
                "Plockpallsnr": dp_df.loc[mask, plock_col],
                "kundnamn": dp_df.loc[mask, dp_order_col].map(order_to_customer).fillna(""),
            }
        ).reset_index(drop=True)

    log_lines: list[str] = []
    if not diff_df.empty:
        log_lines.append("Dispatchkontrollen har hittat avvikelser mellan orderöversikten och dispatchpallar:")
        for _, row in diff_df.iterrows():
            try:
                name_part = f" ({row['kundnamn']})" if str(row.get("kundnamn", "")).strip() else ""
                log_lines.append(
                    "Order "
                    f"{row['Ordernr']}{name_part} har sändningsnr {row['Översikt sändningsnr']} "
                    f"i översikten men {row['Dispatch sändningsnr']} i dispatch "
                    f"(plockpall {row['Plockpallsnr']})"
                )
            except Exception:
                continue

    return DispatchCheckResult(diff_df, log_lines)

def build_vecka27_check_result(orders_df: pd.DataFrame) -> Vecka27CheckResult:
    if not isinstance(orders_df, pd.DataFrame) or orders_df.empty:
        return Vecka27CheckResult([], "", pd.DataFrame(columns=["Avvikelse"]), [])

    work_df = _clean_columns(orders_df.copy())
    cols = _find_ordersaldo_columns(work_df)
    order_col = cols.get("order")
    article_col = cols.get("article")
    demand_col = cols.get("demand")
    if not order_col or not article_col or not demand_col:
        raise KeyError("Hittar inte order-, artikel- eller antalskolumn i beställningsfilen.")

    work = work_df[[order_col, article_col, demand_col]].copy()
    work[order_col] = work[order_col].astype(str).str.strip()
    work[article_col] = work[article_col].astype(str).str.strip()
    work[demand_col] = work[demand_col].map(to_num).astype(float)

    grouped = work.groupby([order_col, article_col])[demand_col].sum(min_count=1)
    deviations: list[str] = []
    for order_id, sub in grouped.groupby(level=0):
        if not str(order_id).upper().startswith("PR"):
            continue
        art_qty: dict[str, float] = {}
        for (_, art), qty in sub.items():
            if pd.notna(qty):
                art_qty[str(art)] = float(qty)
        for roof, mowers in VECKA27_ROOF_TO_MOWERS.items():
            roof_qty = art_qty.get(roof, 0.0)
            if roof_qty <= 0:
                continue
            mower_qty = sum(art_qty.get(mower, 0.0) for mower in mowers)
            if mower_qty < roof_qty:
                mower_list = "/".join(sorted(mowers))
                deviations.append(
                    f"Order {order_id} har {_vecka27_fmt_qty_value(roof_qty)} st av {roof} "
                    f"men endast {_vecka27_fmt_qty_value(mower_qty)} st gräsklippare av {mower_list}."
                )

    if not deviations:
        return Vecka27CheckResult([], "", pd.DataFrame(columns=["Avvikelse"]), ["Vecka 27: inga avvikelser."])

    report_text = "Hej Lina!\n" + "\n".join(deviations) + "\nHur gör vi med denna/dessa?\n"
    report_df = pd.DataFrame({"Avvikelse": deviations})
    log_lines = [f"Vecka 27: {len(deviations)} avvikelse(r).", *deviations]
    return Vecka27CheckResult(deviations, report_text, report_df, log_lines)
