"""Delad grund for flodena: fil-lasning, runtime-cache-trim och sma hjalpare."""
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


DEFAULT_MAX_CSV_PARAM = "__default_max_csv_path"

PROCESS_AREA_FOCUS_PARAM = "__process_area_focus"

FileVersion = tuple[str, int, int]

WAREHOUSE_RUNTIME_CACHE_TTL_SECONDS = 2 * 60 * 60

WAREHOUSE_RUNTIME_CACHE_MAX_ITEMS = 48

WAREHOUSE_RUNTIME_CACHE_APPROX_BYTES_PER_ITEM = 8 * 1024 * 1024

WAREHOUSE_RUNTIME_CACHE_MAX_APPROX_BYTES = 384 * 1024 * 1024

_WAREHOUSE_RUNTIME_CACHE_CREATED_AT = time.time()

# Cache-registret fylls pa av allocation_flows/forecast_flows vid import sa
# trimlogiken slipper importera dom (ingen cirkularitet).
_RUNTIME_LRU_CACHES: list = []
_RUNTIME_CACHE_CLEARERS: list = []


def register_runtime_caches(caches, clearer) -> None:
    _RUNTIME_LRU_CACHES.extend(caches)
    _RUNTIME_CACHE_CLEARERS.append(clearer)


def _runtime_cache_info():
    return tuple(cache.cache_info() for cache in [_read_cached, *_RUNTIME_LRU_CACHES])

def _maybe_trim_runtime_caches(now: float | None = None) -> None:
    global _WAREHOUSE_RUNTIME_CACHE_CREATED_AT
    now_ts = time.time() if now is None else now
    infos = _runtime_cache_info()
    total_items = sum(info.currsize for info in infos)
    approx_bytes = total_items * WAREHOUSE_RUNTIME_CACHE_APPROX_BYTES_PER_ITEM
    if (
        now_ts - _WAREHOUSE_RUNTIME_CACHE_CREATED_AT <= WAREHOUSE_RUNTIME_CACHE_TTL_SECONDS
        and total_items <= WAREHOUSE_RUNTIME_CACHE_MAX_ITEMS
        and approx_bytes <= WAREHOUSE_RUNTIME_CACHE_MAX_APPROX_BYTES
    ):
        return
    _read_cached.cache_clear()
    for clear in _RUNTIME_CACHE_CLEARERS:
        clear()
    _WAREHOUSE_RUNTIME_CACHE_CREATED_AT = now_ts

@lru_cache(maxsize=32)
def _read_cached(path: str, size: int, mtime_ns: int) -> pd.DataFrame:
    return E._read_cli_table(path)

def _read(path: Path) -> pd.DataFrame:
    _maybe_trim_runtime_caches()
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

def _normalize_lookup_value(value: object) -> str:
    text = _clean_cell(value)
    if not text:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text.strip()

def _find_required_column(df: pd.DataFrame, aliases: tuple[str, ...], source_label: str) -> str:
    column = _find_table_column(df, aliases)
    if column is None:
        raise ValueError(f"{source_label} saknar kolumn: {aliases[0]}")
    return column
