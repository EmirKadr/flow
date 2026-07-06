"""Tunna handler-wrappers for rapport-/check-floden mot engine_core."""
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
    _temp,
)

def flow_hib_koppling(files: dict, params: dict) -> dict:
    details_df = shared._read(files["details"])
    overview_df = shared._read(files["overview"])
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
    overview_df = shared._read(files["overview"])
    details_df = shared._read(files["details"]) if "details" in files else None
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
    overview_df = shared._read(files["overview"])
    dispatch_df = shared._read(files["dispatch"])
    details_df = shared._read(files["details"]) if "details" in files else None
    result = E.build_dispatch_check_result(overview_df, dispatch_df, details_df=details_df)
    return {
        "summary": {"Avvikelser": len(result.diff_df)},
        "tables": [("diff", "Dispatchavvikelser", result.diff_df)],
        "log": list(result.log_lines or []),
    }

def flow_vecka27_check(files: dict, params: dict) -> dict:
    orders_df = shared._read(files["orders"])
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
    saldo_df = shared._read(files["saldo"])
    buffer_df = shared._read(files["buffer"]) if "buffer" in files else None
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
    buffer_df = shared._read(files["buffer"])
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
