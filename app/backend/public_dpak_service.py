from __future__ import annotations

import calendar
import math
import re
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
from psycopg import OperationalError as PsycopgOperationalError
from sqlalchemy import and_, func, or_, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code
from .config import settings
from .data_fetch_service import _date_period_payload, _period_values_for_column, _preferred_date_column, load_catalog
from .external_data_client import ExternalDataClient, ExternalDataClientError
from .models import (
    PublicDpakDataset,
    PublicDpakOrderArticleFact,
    PublicDpakOrderSupplierBoxFact,
    PublicDpakPickRow,
    PublicDpakRawItemAlias,
    PublicDpakRawItemAttribute,
    PublicDpakRawPicklog,
    PublicDpakSyncChunk,
)


PICK_FIELDS: dict[str, tuple[str, ...]] = {
    "source_rowid": ("rowid", "Radid", "Rowid"),
    "date_int": ("time_stamp_int", "Datum"),
    "order_num": ("order_num", "Ordernr"),
    "customer_num": ("custom_num", "Kundnr", "Kund"),
    "customer_desc": ("custom_desc", "Kund"),
    "line_num": ("line_num", "Linjenr", "Rad"),
    "pick_zone": ("pick_zone", "Zon", "Plockzon"),
    "location": ("location", "Lokation", "Lagerplats"),
    "item_num": ("item_num", "Artikelnr", "Artikel"),
    "item_desc": ("item_desc", "Artikel"),
    "qty_pre": ("qty_pre", "Beställt", "Bestallt"),
    "qty_suf": ("qty_suf", "Plockat"),
    "pick_pall_num": ("pick_pall_num", "Plockpallsnr", "Plockpallsnr."),
    "responsible": ("responsible", "Ansvarig inköpare", "Ansvarig inkopare"),
    "company": ("company", "Bolag"),
}

ALIAS_FIELDS: dict[str, tuple[str, ...]] = {
    "item_num": ("item_num", "Artikel"),
    "company": ("company", "Bolag"),
    "unit": ("unit", "Enhet"),
    "factor": ("conversion_factor", "Faktor"),
}

ATTRIBUTE_FIELDS: dict[str, tuple[str, ...]] = {
    "item_num": ("item_num", "Artikel"),
    "name": ("name", "Namn"),
    "value": ("value", "Värde", "Varde"),
}

MONTH_ALIASES = {
    "januari": 1,
    "jan": 1,
    "februari": 2,
    "feb": 2,
    "mars": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "maj": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "augusti": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "oktober": 10,
    "okt": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

MONTH_PATTERN = re.compile(
    r"\b("
    + "|".join(sorted((re.escape(key) for key in MONTH_ALIASES), key=len, reverse=True))
    + r")\s*(20\d{2})?\b",
    re.IGNORECASE,
)

PUBLIC_DPAK_LIVE_RETENTION_DAYS = 40
DB_WRITE_ERRORS = (OperationalError, PsycopgOperationalError)


@dataclass(frozen=True)
class DpakBuildResult:
    business_code: str
    pick_rows: int
    order_article_rows: int
    order_supplier_rows: int
    alias_rows: int
    attribute_rows: int
    coverage_start: date | None
    coverage_end: date | None


@dataclass(frozen=True)
class DpakSyncResult:
    build: DpakBuildResult
    chunks_fetched: int
    chunks_skipped: int
    rows_imported: int


@dataclass(frozen=True)
class RawCsvRows:
    source_file: str
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str


def public_dpak_business_code(value: str | None = None) -> str:
    return (
        normalize_business_code(value)
        or normalize_business_code(settings.PUBLIC_DPAK_DEFAULT_BUSINESS_CODE)
        or DEFAULT_BUSINESS_CODE
    )


def _dt(day: date | None) -> datetime | None:
    if day is None:
        return None
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _day(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).replace("\ufeff", "").strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _num(value: Any) -> float | None:
    text = _text(value)
    if text is None:
        return None
    text = text.replace(" ", "").replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _int_text(value: Any) -> int | None:
    number = _num(value)
    if number is None:
        return None
    return int(number)


def _row_get(row: dict[str, Any], names: Iterable[str]) -> Any:
    lower_map = {str(key).strip().lower(): key for key in row.keys()}
    for name in names:
        if name in row:
            return row.get(name)
        actual = lower_map.get(str(name).strip().lower())
        if actual is not None:
            return row.get(actual)
    return None


def _pick_date_from_int(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    return None


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_csv(path, sep="\t", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame.to_dict("records")


def _latest_csv(directory: Path, prefix: str) -> Path | None:
    matches = sorted(directory.glob(f"{prefix}-*.csv"))
    if not matches:
        matches = sorted(directory.glob(f"{prefix}.csv"))
    return matches[-1] if matches else None


def load_support_csvs(directory: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    alias_path = _latest_csv(directory, "item_alias")
    attribute_path = _latest_csv(directory, "item_attribute")
    if alias_path is None or attribute_path is None:
        raise FileNotFoundError("Saknar item_alias-*.csv eller item_attribute-*.csv.")
    return _read_csv_rows(alias_path), _read_csv_rows(attribute_path)


def load_support_csv_files(directory: Path) -> tuple[RawCsvRows, RawCsvRows]:
    alias_path = _latest_csv(directory, "item_alias")
    attribute_path = _latest_csv(directory, "item_attribute")
    if alias_path is None or attribute_path is None:
        raise FileNotFoundError("Saknar item_alias-*.csv eller item_attribute-*.csv.")
    return (
        RawCsvRows(source_file=alias_path.name, rows=_read_csv_rows(alias_path)),
        RawCsvRows(source_file=attribute_path.name, rows=_read_csv_rows(attribute_path)),
    )


def load_pick_csvs(directory: Path) -> list[tuple[str, list[dict[str, Any]]]]:
    sources: list[tuple[str, list[dict[str, Any]]]] = []
    for prefix, view_id in (
        ("v_ask_pick_log_full", settings.PUBLIC_DPAK_LIVE_PICK_VIEW),
        ("dblog_pick_log", settings.PUBLIC_DPAK_ARCHIVE_PICK_VIEW),
    ):
        path = _latest_csv(directory, prefix)
        if path is not None:
            sources.append((view_id, _read_csv_rows(path)))
    if not sources:
        raise FileNotFoundError("Saknar v_ask_pick_log_full-*.csv eller dblog_pick_log-*.csv.")
    return sources


def load_pick_csv_files(directory: Path) -> list[tuple[str, str, list[dict[str, Any]]]]:
    sources: list[tuple[str, str, list[dict[str, Any]]]] = []
    for prefix, view_id in (
        ("v_ask_pick_log_full", settings.PUBLIC_DPAK_LIVE_PICK_VIEW),
        ("dblog_pick_log", settings.PUBLIC_DPAK_ARCHIVE_PICK_VIEW),
    ):
        path = _latest_csv(directory, prefix)
        if path is not None:
            sources.append((view_id, path.name, _read_csv_rows(path)))
    if not sources:
        raise FileNotFoundError("Saknar v_ask_pick_log_full-*.csv eller dblog_pick_log-*.csv.")
    return sources


def _factor_by_item(alias_rows: list[dict[str, Any]]) -> dict[str, float]:
    factors: dict[str, float] = {}
    for row in alias_rows:
        item = _text(_row_get(row, ALIAS_FIELDS["item_num"]))
        factor = _num(_row_get(row, ALIAS_FIELDS["factor"]))
        unit = (_text(_row_get(row, ALIAS_FIELDS["unit"])) or "").upper()
        if not item or factor is None or factor <= 1 or unit == "PAL":
            continue
        current = factors.get(item)
        if current is None or factor < current:
            factors[item] = factor
    return factors


def _supplier_by_item(attribute_rows: list[dict[str, Any]]) -> dict[str, str]:
    suppliers: dict[str, str] = {}
    for row in attribute_rows:
        item = _text(_row_get(row, ATTRIBUTE_FIELDS["item_num"]))
        name = _text(_row_get(row, ATTRIBUTE_FIELDS["name"]))
        value = _text(_row_get(row, ATTRIBUTE_FIELDS["value"]))
        if item and value and name == "LastSupplierName" and item not in suppliers:
            suppliers[item] = value
    return suppliers


def normalize_pick_rows(
    source_view: str,
    rows: list[dict[str, Any]],
    *,
    business_code: str,
    supplier_by_item: dict[str, str],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item_num = _text(_row_get(row, PICK_FIELDS["item_num"]))
        date_int = _int_text(_row_get(row, PICK_FIELDS["date_int"]))
        pick_date = _pick_date_from_int(date_int)
        order_num = _text(_row_get(row, PICK_FIELDS["order_num"]))
        qty_suf = _num(_row_get(row, PICK_FIELDS["qty_suf"]))
        if not item_num or not order_num or pick_date is None:
            continue
        normalized.append(
            {
                "business_code": business_code,
                "source_view": source_view,
                "source_rowid": _text(_row_get(row, PICK_FIELDS["source_rowid"])),
                "pick_date": _dt(pick_date),
                "date_int": date_int,
                "order_num": order_num,
                "customer_num": _text(_row_get(row, PICK_FIELDS["customer_num"])),
                "customer_desc": _text(_row_get(row, PICK_FIELDS["customer_desc"])),
                "line_num": _text(_row_get(row, PICK_FIELDS["line_num"])),
                "pick_zone": (_text(_row_get(row, PICK_FIELDS["pick_zone"])) or "").upper() or None,
                "location": _text(_row_get(row, PICK_FIELDS["location"])),
                "item_num": item_num,
                "item_desc": _text(_row_get(row, PICK_FIELDS["item_desc"])),
                "qty_pre": _num(_row_get(row, PICK_FIELDS["qty_pre"])) or 0.0,
                "qty_suf": qty_suf or 0.0,
                "pick_pall_num": _text(_row_get(row, PICK_FIELDS["pick_pall_num"])),
                "responsible": _text(_row_get(row, PICK_FIELDS["responsible"])),
                "company": _text(_row_get(row, PICK_FIELDS["company"])),
                "supplier": supplier_by_item.get(item_num),
            }
        )
    return normalized


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        try:
            return _jsonable(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _raw_data(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key).strip(): _jsonable(value) for key, value in row.items() if str(key).strip()}


def raw_picklog_rows(
    rows: list[dict[str, Any]],
    *,
    business_code: str,
    source_view: str | None,
    source_file: str | None = None,
    chunk_start: date | None = None,
    chunk_end: date | None = None,
) -> list[dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        date_int = _int_text(_row_get(row, PICK_FIELDS["date_int"]))
        pick_date = _pick_date_from_int(date_int)
        raw_rows.append(
            {
                "business_code": business_code,
                "source_view": source_view,
                "source_file": source_file,
                "source_rowid": _text(_row_get(row, PICK_FIELDS["source_rowid"])),
                "chunk_start": _dt(chunk_start) if chunk_start else None,
                "chunk_end": _range_end_dt(chunk_end) if chunk_end else None,
                "row_index": index,
                "pick_date": _dt(pick_date),
                "date_int": date_int,
                "company": _text(_row_get(row, PICK_FIELDS["company"])),
                "zone": (_text(_row_get(row, PICK_FIELDS["pick_zone"])) or "").upper() or None,
                "order_num": _text(_row_get(row, PICK_FIELDS["order_num"])),
                "customer_num": _text(_row_get(row, PICK_FIELDS["customer_num"])),
                "customer_desc": _text(_row_get(row, PICK_FIELDS["customer_desc"])),
                "line_num": _text(_row_get(row, PICK_FIELDS["line_num"])),
                "item_num": _text(_row_get(row, PICK_FIELDS["item_num"])),
                "item_desc": _text(_row_get(row, PICK_FIELDS["item_desc"])),
                "location": _text(_row_get(row, PICK_FIELDS["location"])),
                "pick_pall_num": _text(_row_get(row, PICK_FIELDS["pick_pall_num"])),
                "qty_pre": _num(_row_get(row, PICK_FIELDS["qty_pre"])),
                "qty_suf": _num(_row_get(row, PICK_FIELDS["qty_suf"])),
                "data": _raw_data(row),
            }
        )
    return raw_rows


def raw_alias_rows(rows: list[dict[str, Any]], *, business_code: str, source_file: str | None) -> list[dict[str, Any]]:
    return [
        {
            "business_code": business_code,
            "source_file": source_file,
            "row_index": index,
            "item_num": _text(_row_get(row, ALIAS_FIELDS["item_num"])),
            "company": _text(_row_get(row, ALIAS_FIELDS["company"])),
            "alias": _text(_row_get(row, ("alias", "Alias"))),
            "unit": _text(_row_get(row, ALIAS_FIELDS["unit"])),
            "factor": _num(_row_get(row, ALIAS_FIELDS["factor"])),
            "data": _raw_data(row),
        }
        for index, row in enumerate(rows, start=1)
    ]


def raw_attribute_rows(
    rows: list[dict[str, Any]],
    *,
    business_code: str,
    source_file: str | None,
) -> list[dict[str, Any]]:
    return [
        {
            "business_code": business_code,
            "source_file": source_file,
            "row_index": index,
            "item_num": _text(_row_get(row, ATTRIBUTE_FIELDS["item_num"])),
            "company": _text(_row_get(row, ("company", "Bolag"))),
            "name": _text(_row_get(row, ATTRIBUTE_FIELDS["name"])),
            "value": _text(_row_get(row, ATTRIBUTE_FIELDS["value"])),
            "data": _raw_data(row),
        }
        for index, row in enumerate(rows, start=1)
    ]


def _dedupe_pick_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        rowid = row.get("source_rowid")
        content_key = (
            "content",
            row.get("order_num"),
            row.get("customer_num"),
            row.get("line_num"),
            row.get("item_num"),
            row.get("date_int"),
            row.get("pick_pall_num"),
            row.get("qty_suf"),
            row.get("location"),
        )
        key = content_key if any(value is not None for value in content_key[1:]) else ("rowid", rowid)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _safe_first(series: pd.Series) -> Any:
    for value in series:
        if _text(value) is not None:
            return value
    return None


def _unique_texts(series: pd.Series) -> list[str]:
    values = {_text(value) for value in series}
    return sorted(value for value in values if value)


def build_order_article_facts(
    pick_rows: list[dict[str, Any]],
    factor_by_item: dict[str, float],
    *,
    business_code: str,
) -> list[dict[str, Any]]:
    if not pick_rows:
        return []
    frame = pd.DataFrame(pick_rows)
    frame = frame[frame["qty_suf"].fillna(0) > 0].copy()
    frame["factor"] = frame["item_num"].map(factor_by_item)
    frame = frame[frame["factor"].notna() & (frame["factor"] > 1)].copy()
    if frame.empty:
        return []

    frame["whole_row"] = (frame["qty_suf"] // frame["factor"]).astype(int)
    frame["loose_row"] = (frame["qty_suf"] % frame["factor"]).astype(int)
    grouped = frame.groupby(["order_num", "item_num"], as_index=False).agg(
        qty_pre=("qty_pre", "sum"),
        qty_suf=("qty_suf", "sum"),
        whole_dpak=("whole_row", "sum"),
        loose_units=("loose_row", "sum"),
        pick_rows=("qty_suf", "size"),
        factor=("factor", "first"),
        item_desc=("item_desc", _safe_first),
        customer_num=("customer_num", _safe_first),
        customer_desc=("customer_desc", _safe_first),
        pick_date=("pick_date", "min"),
        date_int=("date_int", "min"),
        pick_zone=("pick_zone", _safe_first),
        company=("company", _safe_first),
        supplier=("supplier", _safe_first),
        responsible=("responsible", _safe_first),
        locations=("location", _unique_texts),
    )
    grouped["dpack_sold"] = (grouped["qty_suf"] // grouped["factor"]).astype(int)
    grouped["dpack_broken"] = (grouped["dpack_sold"] - grouped["whole_dpak"]).clip(lower=0).astype(int)
    grouped["unnecessary_break"] = grouped["dpack_broken"] > 0

    autostore = (
        frame.assign(_autostore=frame["location"].fillna("").str.upper().eq("AUTOSTORE"))
        .groupby(["order_num", "item_num"])["_autostore"]
        .any()
        .reset_index()
    )
    grouped = grouped.merge(autostore, on=["order_num", "item_num"], how="left")
    grouped["_autostore"] = grouped["_autostore"].fillna(False)

    records: list[dict[str, Any]] = []
    for row in grouped.to_dict("records"):
        records.append(
            {
                "business_code": business_code,
                "order_num": str(row["order_num"]),
                "item_num": str(row["item_num"]),
                "item_desc": _text(row.get("item_desc")),
                "customer_num": _text(row.get("customer_num")),
                "customer_desc": _text(row.get("customer_desc")),
                "pick_date": row.get("pick_date"),
                "date_int": int(row["date_int"]) if pd.notna(row.get("date_int")) else None,
                "pick_zone": _text(row.get("pick_zone")),
                "company": _text(row.get("company")),
                "supplier": _text(row.get("supplier")),
                "responsible": _text(row.get("responsible")),
                "qty_pre": float(row.get("qty_pre") or 0),
                "qty_suf": float(row.get("qty_suf") or 0),
                "factor": float(row.get("factor")) if pd.notna(row.get("factor")) else None,
                "whole_dpak": int(row.get("whole_dpak") or 0),
                "loose_units": int(row.get("loose_units") or 0),
                "dpack_sold": int(row.get("dpack_sold") or 0),
                "dpack_broken": int(row.get("dpack_broken") or 0),
                "unnecessary_break": bool(row.get("unnecessary_break")),
                "pick_rows": int(row.get("pick_rows") or 0),
                "locations": row.get("locations") or [],
                "has_autostore": bool(row.get("_autostore")),
            }
        )
    return records


def build_order_supplier_box_facts(
    pick_rows: list[dict[str, Any]],
    *,
    business_code: str,
) -> list[dict[str, Any]]:
    if not pick_rows:
        return []
    frame = pd.DataFrame(pick_rows)
    frame = frame[
        frame["supplier"].notna()
        & frame["pick_pall_num"].notna()
        & frame["pick_zone"].fillna("").str.upper().eq("R")
    ].copy()
    if frame.empty:
        return []
    grouped = frame.groupby(["order_num", "supplier"], as_index=False).agg(
        pick_date=("pick_date", "min"),
        date_int=("date_int", "min"),
        pick_rows=("item_num", "size"),
        article_count=("item_num", "nunique"),
        box_count=("pick_pall_num", "nunique"),
        boxes=("pick_pall_num", _unique_texts),
        has_autostore=("location", lambda values: any(str(value or "").upper() == "AUTOSTORE" for value in values)),
    )
    grouped["can_spread"] = grouped["pick_rows"] >= 2
    grouped["spread"] = grouped["can_spread"] & (grouped["box_count"] >= 2)
    return [
        {
            "business_code": business_code,
            "order_num": str(row["order_num"]),
            "supplier": str(row["supplier"]),
            "pick_date": row.get("pick_date"),
            "date_int": int(row["date_int"]) if pd.notna(row.get("date_int")) else None,
            "pick_zone": "R",
            "pick_rows": int(row["pick_rows"] or 0),
            "article_count": int(row["article_count"] or 0),
            "box_count": int(row["box_count"] or 0),
            "boxes": row.get("boxes") or [],
            "can_spread": bool(row.get("can_spread")),
            "spread": bool(row.get("spread")),
            "has_autostore": bool(row.get("has_autostore")),
        }
        for row in grouped.to_dict("records")
    ]


def _bulk_insert(
    db: Session,
    model,
    rows: list[dict[str, Any]],
    chunk_size: int | None = None,
    *,
    commit_each_batch: bool = False,
    label: str | None = None,
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> None:
    chunk_size = max(1, int(chunk_size or settings.PUBLIC_DPAK_INSERT_BATCH_SIZE or 500))
    if _copy_insert_postgres(
        db,
        model,
        rows,
        chunk_size=chunk_size,
        commit_each_batch=commit_each_batch,
        label=label,
        progress=progress,
    ):
        return
    last_reported = 0
    for index in range(0, len(rows), chunk_size):
        db.bulk_insert_mappings(model, rows[index : index + chunk_size])
        db.flush()
        if commit_each_batch:
            db.commit()
        inserted = min(index + chunk_size, len(rows))
        if progress and (inserted == len(rows) or inserted - last_reported >= max(chunk_size, 5000)):
            last_reported = inserted
            progress(
                {
                    "type": "db_insert",
                    "label": label,
                    "inserted": inserted,
                    "rows": len(rows),
                }
            )


def _copy_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "item") and callable(value.item):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, (list, dict)):
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    return value


def _quote_pg_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _copy_insert_postgres(
    db: Session,
    model,
    rows: list[dict[str, Any]],
    *,
    chunk_size: int,
    commit_each_batch: bool,
    label: str | None = None,
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> bool:
    if not rows:
        return True
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return False

    table = model.__table__
    columns = [column.name for column in table.columns if column.name != "id" and column.name in rows[0]]
    if not columns:
        return True
    table_name = _quote_pg_identifier(table.name)
    column_names = ", ".join(_quote_pg_identifier(column) for column in columns)
    copy_sql = f"COPY {table_name} ({column_names}) FROM STDIN"
    last_reported = 0

    for index in range(0, len(rows), chunk_size):
        batch = rows[index : index + chunk_size]
        connection = db.connection()
        raw_connection = connection.connection.driver_connection
        with raw_connection.cursor() as cursor:
            with cursor.copy(copy_sql) as copy:
                for row in batch:
                    copy.write_row(tuple(_copy_value(row.get(column)) for column in columns))
        db.flush()
        if commit_each_batch:
            db.commit()
        inserted = min(index + chunk_size, len(rows))
        if progress and (inserted == len(rows) or inserted - last_reported >= max(chunk_size, 5000)):
            last_reported = inserted
            progress(
                {
                    "type": "db_insert",
                    "label": label,
                    "inserted": inserted,
                    "rows": len(rows),
                }
            )
    return True


def _raw_picklog_batch_size() -> int:
    configured = int(settings.PUBLIC_DPAK_FACT_INSERT_BATCH_SIZE or settings.PUBLIC_DPAK_INSERT_BATCH_SIZE or 5000)
    return max(500, min(configured, 5000))


def replace_raw_support_rows(
    db: Session,
    *,
    business_code: str,
    alias_file: RawCsvRows,
    attribute_file: RawCsvRows,
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> tuple[int, int]:
    business = public_dpak_business_code(business_code)
    alias_raw = raw_alias_rows(alias_file.rows, business_code=business, source_file=alias_file.source_file)
    attribute_raw = raw_attribute_rows(
        attribute_file.rows,
        business_code=business,
        source_file=attribute_file.source_file,
    )
    db.query(PublicDpakRawItemAlias).filter(PublicDpakRawItemAlias.business_code == business).delete(
        synchronize_session=False
    )
    db.query(PublicDpakRawItemAttribute).filter(PublicDpakRawItemAttribute.business_code == business).delete(
        synchronize_session=False
    )
    db.flush()
    _bulk_insert(
        db,
        PublicDpakRawItemAlias,
        alias_raw,
        chunk_size=settings.PUBLIC_DPAK_FACT_INSERT_BATCH_SIZE,
        label="raw item_alias",
        progress=progress,
    )
    _bulk_insert(
        db,
        PublicDpakRawItemAttribute,
        attribute_raw,
        chunk_size=settings.PUBLIC_DPAK_FACT_INSERT_BATCH_SIZE,
        label="raw item_attribute",
        progress=progress,
    )
    return len(alias_raw), len(attribute_raw)


def _clear_derived_public_dpak_rows(db: Session, business_code: str) -> None:
    business = public_dpak_business_code(business_code)
    db.query(PublicDpakPickRow).filter(PublicDpakPickRow.business_code == business).delete(synchronize_session=False)
    db.query(PublicDpakOrderArticleFact).filter(PublicDpakOrderArticleFact.business_code == business).delete(
        synchronize_session=False
    )
    db.query(PublicDpakOrderSupplierBoxFact).filter(
        PublicDpakOrderSupplierBoxFact.business_code == business
    ).delete(synchronize_session=False)


def _replace_raw_picklog_for_chunk(
    db: Session,
    *,
    business_code: str,
    source_view: str,
    chunk_start: date,
    chunk_end: date,
    rows: list[dict[str, Any]],
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> int:
    business = public_dpak_business_code(business_code)
    start_dt = _dt(chunk_start)
    end_dt = _range_end_dt(chunk_end)
    db.query(PublicDpakRawPicklog).filter(
        PublicDpakRawPicklog.business_code == business,
        PublicDpakRawPicklog.source_view == source_view,
        PublicDpakRawPicklog.chunk_start == start_dt,
        PublicDpakRawPicklog.chunk_end == end_dt,
    ).delete(synchronize_session=False)
    db.flush()
    raw_rows = raw_picklog_rows(
        rows,
        business_code=business,
        source_view=source_view,
        chunk_start=chunk_start,
        chunk_end=chunk_end,
    )
    raw_rows = [
        row
        for row in raw_rows
        if (pick_day := _day(row.get("pick_date"))) is not None and chunk_start <= pick_day <= chunk_end
    ]
    _bulk_insert(
        db,
        PublicDpakRawPicklog,
        raw_rows,
        chunk_size=_raw_picklog_batch_size(),
        label="raw picklog",
        progress=progress,
    )
    return len(raw_rows)


def _replace_raw_picklog_for_chunk_with_retries(
    db: Session,
    *,
    business_code: str,
    source_view: str,
    chunk_start: date,
    chunk_end: date,
    rows: list[dict[str, Any]],
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> int:
    attempts = max(1, int(settings.PUBLIC_DPAK_DB_WRITE_RETRIES or 1))
    for attempt in range(1, attempts + 1):
        try:
            inserted = _replace_raw_picklog_for_chunk(
                db,
                business_code=business_code,
                source_view=source_view,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
                rows=rows,
                progress=progress,
            )
            db.commit()
            return inserted
        except DB_WRITE_ERRORS as exc:
            try:
                db.rollback()
            except Exception:
                db.invalidate()
            if attempt >= attempts:
                raise
            if progress:
                progress(
                    {
                        "type": "db_retry",
                        "attempt": attempt + 1,
                        "attempts": attempts,
                        "view": source_view,
                        "start": chunk_start.isoformat(),
                        "end": chunk_end.isoformat(),
                        "error": str(exc).splitlines()[0][:200],
                    }
                )
            time_module.sleep(min(30, 3 * attempt))
    return 0


def _raw_picklog_chunk_count(
    db: Session,
    business_code: str,
    source_view: str,
    chunk_start: date,
    chunk_end: date,
    company_codes: list[str] | None = None,
) -> int:
    query = db.query(func.count(PublicDpakRawPicklog.id)).filter(
        PublicDpakRawPicklog.business_code == public_dpak_business_code(business_code),
        PublicDpakRawPicklog.source_view == source_view,
        PublicDpakRawPicklog.chunk_start == _dt(chunk_start),
        PublicDpakRawPicklog.chunk_end == _range_end_dt(chunk_end),
    )
    if company_codes:
        query = query.filter(func.upper(PublicDpakRawPicklog.company).in_([code.upper() for code in company_codes]))
    return int(query.scalar() or 0)


def _replace_all_raw_picklog(
    db: Session,
    *,
    business_code: str,
    pick_sources: list[tuple[str, str | None, list[dict[str, Any]]]],
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> int:
    business = public_dpak_business_code(business_code)
    db.query(PublicDpakRawPicklog).filter(PublicDpakRawPicklog.business_code == business).delete(
        synchronize_session=False
    )
    db.flush()
    total = 0
    for source_view, source_file, rows in pick_sources:
        raw_rows = raw_picklog_rows(
            rows,
            business_code=business,
            source_view=source_view,
            source_file=source_file,
        )
        _bulk_insert(
            db,
            PublicDpakRawPicklog,
            raw_rows,
            chunk_size=_raw_picklog_batch_size(),
            label="raw picklog",
            progress=progress,
        )
        total += len(raw_rows)
    return total


def _raw_dataset_result(
    db: Session,
    *,
    business_code: str,
    source_summary: dict[str, Any] | None = None,
    status: str | None = None,
) -> DpakBuildResult:
    business = public_dpak_business_code(business_code)
    pick_rows = int(
        db.query(func.count(PublicDpakRawPicklog.id))
        .filter(PublicDpakRawPicklog.business_code == business)
        .scalar()
        or 0
    )
    alias_rows = int(
        db.query(func.count(PublicDpakRawItemAlias.id))
        .filter(PublicDpakRawItemAlias.business_code == business)
        .scalar()
        or 0
    )
    attribute_rows = int(
        db.query(func.count(PublicDpakRawItemAttribute.id))
        .filter(PublicDpakRawItemAttribute.business_code == business)
        .scalar()
        or 0
    )
    coverage_start_dt, coverage_end_dt = (
        db.query(func.min(PublicDpakRawPicklog.pick_date), func.max(PublicDpakRawPicklog.pick_date))
        .filter(PublicDpakRawPicklog.business_code == business)
        .one()
    )
    coverage_start = _day(coverage_start_dt)
    coverage_end = _day(coverage_end_dt)
    dataset = db.query(PublicDpakDataset).filter(PublicDpakDataset.business_code == business).one_or_none()
    if dataset is None:
        dataset = PublicDpakDataset(business_code=business)
        db.add(dataset)
    dataset.coverage_start = _dt(coverage_start)
    dataset.coverage_end = _dt(coverage_end)
    dataset.pick_rows = pick_rows
    dataset.order_article_rows = 0
    dataset.order_supplier_rows = 0
    dataset.alias_rows = alias_rows
    dataset.attribute_rows = attribute_rows
    dataset.source_summary = source_summary or dataset.source_summary or {}
    dataset.status = status or ("ready" if pick_rows and alias_rows and attribute_rows else "empty")
    dataset.error_text = None
    dataset.built_at = datetime.now(timezone.utc)
    db.flush()
    return DpakBuildResult(
        business_code=business,
        pick_rows=pick_rows,
        order_article_rows=0,
        order_supplier_rows=0,
        alias_rows=alias_rows,
        attribute_rows=attribute_rows,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
    )


def replace_public_dpak_dataset(
    db: Session,
    *,
    business_code: str,
    pick_sources: list[tuple[str, list[dict[str, Any]]]],
    alias_rows: list[dict[str, Any]],
    attribute_rows: list[dict[str, Any]],
    source_summary: dict[str, Any] | None = None,
) -> DpakBuildResult:
    business = public_dpak_business_code(business_code)
    factor_map = _factor_by_item(alias_rows)
    supplier_map = _supplier_by_item(attribute_rows)

    normalized_rows: list[dict[str, Any]] = []
    for source_view, rows in pick_sources:
        normalized_rows.extend(
            normalize_pick_rows(source_view, rows, business_code=business, supplier_by_item=supplier_map)
        )
    normalized_rows = _dedupe_pick_rows(normalized_rows)
    article_facts = build_order_article_facts(normalized_rows, factor_map, business_code=business)
    supplier_facts = build_order_supplier_box_facts(normalized_rows, business_code=business)

    coverage_days = [_day(row.get("pick_date")) for row in normalized_rows if row.get("pick_date") is not None]
    coverage_start = min(coverage_days) if coverage_days else None
    coverage_end = max(coverage_days) if coverage_days else None

    db.query(PublicDpakPickRow).filter(PublicDpakPickRow.business_code == business).delete(synchronize_session=False)
    db.query(PublicDpakOrderArticleFact).filter(PublicDpakOrderArticleFact.business_code == business).delete(
        synchronize_session=False
    )
    db.query(PublicDpakOrderSupplierBoxFact).filter(
        PublicDpakOrderSupplierBoxFact.business_code == business
    ).delete(synchronize_session=False)
    db.query(PublicDpakRawPicklog).filter(PublicDpakRawPicklog.business_code == business).delete(synchronize_session=False)
    db.query(PublicDpakRawItemAlias).filter(PublicDpakRawItemAlias.business_code == business).delete(
        synchronize_session=False
    )
    db.query(PublicDpakRawItemAttribute).filter(PublicDpakRawItemAttribute.business_code == business).delete(
        synchronize_session=False
    )
    db.query(PublicDpakDataset).filter(PublicDpakDataset.business_code == business).delete(synchronize_session=False)
    db.flush()

    _bulk_insert(
        db,
        PublicDpakRawItemAlias,
        raw_alias_rows(alias_rows, business_code=business, source_file="item_alias"),
    )
    _bulk_insert(
        db,
        PublicDpakRawItemAttribute,
        raw_attribute_rows(attribute_rows, business_code=business, source_file="item_attribute"),
    )
    _replace_all_raw_picklog(
        db,
        business_code=business,
        pick_sources=[(source_view, None, rows) for source_view, rows in pick_sources],
    )
    _bulk_insert(db, PublicDpakPickRow, normalized_rows)
    _bulk_insert(db, PublicDpakOrderArticleFact, article_facts)
    _bulk_insert(db, PublicDpakOrderSupplierBoxFact, supplier_facts)

    dataset = PublicDpakDataset(
        business_code=business,
        coverage_start=_dt(coverage_start),
        coverage_end=_dt(coverage_end),
        pick_rows=len(normalized_rows),
        order_article_rows=len(article_facts),
        order_supplier_rows=len(supplier_facts),
        alias_rows=len(alias_rows),
        attribute_rows=len(attribute_rows),
        source_summary=source_summary or {},
        status="ready" if article_facts else "empty",
        error_text=None,
        built_at=datetime.now(timezone.utc),
    )
    db.add(dataset)
    db.flush()
    return DpakBuildResult(
        business_code=business,
        pick_rows=len(normalized_rows),
        order_article_rows=len(article_facts),
        order_supplier_rows=len(supplier_facts),
        alias_rows=len(alias_rows),
        attribute_rows=len(attribute_rows),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
    )


def _stored_pick_row_to_mapping(row: PublicDpakPickRow) -> dict[str, Any]:
    return {
        "business_code": row.business_code,
        "source_view": row.source_view,
        "source_rowid": row.source_rowid,
        "pick_date": row.pick_date,
        "date_int": row.date_int,
        "order_num": row.order_num,
        "customer_num": row.customer_num,
        "customer_desc": row.customer_desc,
        "line_num": row.line_num,
        "pick_zone": row.pick_zone,
        "location": row.location,
        "item_num": row.item_num,
        "item_desc": row.item_desc,
        "qty_pre": row.qty_pre or 0.0,
        "qty_suf": row.qty_suf or 0.0,
        "pick_pall_num": row.pick_pall_num,
        "responsible": row.responsible,
        "company": row.company,
        "supplier": row.supplier,
    }


def _stored_pick_rows(db: Session, business_code: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    query = (
        db.query(PublicDpakPickRow)
        .filter(PublicDpakPickRow.business_code == business_code)
        .order_by(PublicDpakPickRow.pick_date, PublicDpakPickRow.id)
    )
    for row in query.yield_per(5000):
        rows.append(_stored_pick_row_to_mapping(row))
    return rows


PUBLIC_DPAK_FACT_INDEX_SQL: tuple[tuple[str, str], ...] = (
    (
        "ix_public_dpak_fact_business_date",
        "CREATE INDEX IF NOT EXISTS ix_public_dpak_fact_business_date "
        "ON public_dpak_order_article_facts (business_code, pick_date)",
    ),
    (
        "ix_public_dpak_fact_business_zone",
        "CREATE INDEX IF NOT EXISTS ix_public_dpak_fact_business_zone "
        "ON public_dpak_order_article_facts (business_code, pick_zone)",
    ),
    (
        "ix_public_dpak_fact_business_supplier",
        "CREATE INDEX IF NOT EXISTS ix_public_dpak_fact_business_supplier "
        "ON public_dpak_order_article_facts (business_code, supplier)",
    ),
    (
        "ix_public_dpak_fact_business_item",
        "CREATE INDEX IF NOT EXISTS ix_public_dpak_fact_business_item "
        "ON public_dpak_order_article_facts (business_code, item_num)",
    ),
    (
        "ix_public_dpak_fact_business_order",
        "CREATE INDEX IF NOT EXISTS ix_public_dpak_fact_business_order "
        "ON public_dpak_order_article_facts (business_code, order_num)",
    ),
    (
        "ix_public_dpak_box_business_date",
        "CREATE INDEX IF NOT EXISTS ix_public_dpak_box_business_date "
        "ON public_dpak_order_supplier_box_facts (business_code, pick_date)",
    ),
    (
        "ix_public_dpak_box_business_supplier",
        "CREATE INDEX IF NOT EXISTS ix_public_dpak_box_business_supplier "
        "ON public_dpak_order_supplier_box_facts (business_code, supplier)",
    ),
    (
        "ix_public_dpak_box_business_order",
        "CREATE INDEX IF NOT EXISTS ix_public_dpak_box_business_order "
        "ON public_dpak_order_supplier_box_facts (business_code, order_num)",
    ),
    (
        "ix_public_dpak_box_business_zone",
        "CREATE INDEX IF NOT EXISTS ix_public_dpak_box_business_zone "
        "ON public_dpak_order_supplier_box_facts (business_code, pick_zone)",
    ),
)


def _drop_public_dpak_fact_indexes(
    db: Session,
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> None:
    if progress:
        progress("Droppar temporara fact-index for snabbare bulk-load...")
    for index_name, _create_sql in PUBLIC_DPAK_FACT_INDEX_SQL:
        db.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
    db.commit()


def _create_public_dpak_fact_indexes(
    db: Session,
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> None:
    if progress:
        progress("Aterskapar fact-index...")
    for _index_name, create_sql in PUBLIC_DPAK_FACT_INDEX_SQL:
        db.execute(text(create_sql))
    db.commit()


def rebuild_public_dpak_facts(
    db: Session,
    *,
    business_code: str,
    alias_rows: list[dict[str, Any]],
    attribute_rows: list[dict[str, Any]],
    source_summary: dict[str, Any] | None = None,
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> DpakBuildResult:
    business = public_dpak_business_code(business_code)
    if progress:
        progress("Läser lagrade pickrader från Postgres...")
    raw_rows = _stored_pick_rows(db, business)
    if progress:
        progress(f"Bygger D-pak-fakta från {len(raw_rows):,} pickrader...".replace(",", " "))
    supplier_map = _supplier_by_item(attribute_rows)
    for row in raw_rows:
        item_num = row.get("item_num")
        if item_num in supplier_map:
            row["supplier"] = supplier_map[item_num]
    normalized_rows = _dedupe_pick_rows(raw_rows)
    factor_map = _factor_by_item(alias_rows)
    article_facts = build_order_article_facts(normalized_rows, factor_map, business_code=business)
    supplier_facts = build_order_supplier_box_facts(normalized_rows, business_code=business)
    if progress:
        progress(
            "Fakta klara i minnet: "
            f"{len(article_facts):,} order/artikel, {len(supplier_facts):,} order/leverantor.".replace(",", " ")
        )

    coverage_days = [_day(row.get("pick_date")) for row in normalized_rows if row.get("pick_date") is not None]
    coverage_start = min(coverage_days) if coverage_days else None
    coverage_end = max(coverage_days) if coverage_days else None

    db.query(PublicDpakOrderArticleFact).filter(PublicDpakOrderArticleFact.business_code == business).delete(
        synchronize_session=False
    )
    db.query(PublicDpakOrderSupplierBoxFact).filter(
        PublicDpakOrderSupplierBoxFact.business_code == business
    ).delete(synchronize_session=False)
    db.query(PublicDpakDataset).filter(PublicDpakDataset.business_code == business).delete(synchronize_session=False)
    db.commit()

    fact_chunk_size = max(1, int(settings.PUBLIC_DPAK_FACT_INSERT_BATCH_SIZE or settings.PUBLIC_DPAK_INSERT_BATCH_SIZE))
    _drop_public_dpak_fact_indexes(db, progress=progress)
    try:
        _bulk_insert(
            db,
            PublicDpakOrderArticleFact,
            article_facts,
            chunk_size=fact_chunk_size,
            commit_each_batch=True,
            label="order/artikel",
            progress=progress,
        )
        _bulk_insert(
            db,
            PublicDpakOrderSupplierBoxFact,
            supplier_facts,
            chunk_size=fact_chunk_size,
            commit_each_batch=True,
            label="order/leverantor",
            progress=progress,
        )
    except BaseException:
        db.rollback()
        raise
    finally:
        _create_public_dpak_fact_indexes(db, progress=progress)

    summary = dict(source_summary or {})
    summary.setdefault("raw_pick_rows", len(raw_rows))
    summary.setdefault("deduped_pick_rows", len(normalized_rows))

    db.add(
        PublicDpakDataset(
            business_code=business,
            coverage_start=_dt(coverage_start),
            coverage_end=_dt(coverage_end),
            pick_rows=len(normalized_rows),
            order_article_rows=len(article_facts),
            order_supplier_rows=len(supplier_facts),
            alias_rows=len(alias_rows),
            attribute_rows=len(attribute_rows),
            source_summary=summary,
            status="ready" if article_facts else "empty",
            error_text=None,
            built_at=datetime.now(timezone.utc),
        )
    )
    db.flush()
    return DpakBuildResult(
        business_code=business,
        pick_rows=len(normalized_rows),
        order_article_rows=len(article_facts),
        order_supplier_rows=len(supplier_facts),
        alias_rows=len(alias_rows),
        attribute_rows=len(attribute_rows),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
    )


def _required_api_settings() -> list[str]:
    names = (
        "DATA_SOURCE_API_BASE_URL",
        "DATA_SOURCE_API_KEY",
        "DATA_SOURCE_API_CLIENT",
        "DATA_SOURCE_API_KEY_HEADER",
        "DATA_SOURCE_API_CLIENT_HEADER",
        "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE",
    )
    return [name for name in names if not str(getattr(settings, name, "")).strip()]


def _api_client() -> ExternalDataClient:
    missing = _required_api_settings()
    if missing:
        raise ExternalDataClientError(f"Saknar {', '.join(missing)} i servermiljön.")
    return ExternalDataClient(
        base_url=settings.DATA_SOURCE_API_BASE_URL.strip(),
        api_key=settings.DATA_SOURCE_API_KEY.strip() or None,
        api_client=settings.DATA_SOURCE_API_CLIENT.strip() or None,
        api_key_header=settings.DATA_SOURCE_API_KEY_HEADER.strip() or None,
        api_client_header=settings.DATA_SOURCE_API_CLIENT_HEADER.strip() or None,
        view_data_path_template=settings.DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE.strip(),
        timeout=settings.DATA_SOURCE_TIMEOUT_SECONDS,
        verify_ssl=settings.DATA_SOURCE_VERIFY_SSL,
        ca_bundle=settings.DATA_SOURCE_CA_BUNDLE.strip() or None,
    )


def _fetch_api_rows_with_retries(
    client: ExternalDataClient,
    view_id: str,
    *,
    filters: list[dict[str, Any]],
    chunk_start: date,
    chunk_end: date,
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> list[dict[str, Any]]:
    attempts = max(1, int(settings.PUBLIC_DPAK_API_RETRIES or 1))
    delay = max(0.0, float(settings.PUBLIC_DPAK_API_RETRY_DELAY_SECONDS or 0))
    for attempt in range(1, attempts + 1):
        try:
            return client.fetch_data(view_id, filters=filters)
        except ExternalDataClientError as exc:
            if attempt >= attempts:
                raise
            if progress:
                progress(
                    {
                        "type": "api_retry",
                        "attempt": attempt + 1,
                        "attempts": attempts,
                        "view": view_id,
                        "start": chunk_start.isoformat(),
                        "end": chunk_end.isoformat(),
                        "error": str(exc).splitlines()[0][:200],
                    }
                )
            time_module.sleep(min(90, delay * attempt))
    return []


def _date_filter_for_view(view_id: str, start: date, end: date) -> list[dict[str, Any]]:
    view = load_catalog().view(view_id)
    column = _preferred_date_column(view)
    if column is None:
        raise ExternalDataClientError(f"Vyn {view_id} saknar datumkolumn i katalogen.")
    period = _date_period_payload("public_dpak_sync", start, end)
    return [{"id": column.id, "operator": "Between", "value": _period_values_for_column(period, column)}]


def _public_dpak_company_codes() -> list[str]:
    return [
        code
        for code in (normalize_business_code(part) for part in settings.PUBLIC_DPAK_COMPANY_CODES.split(","))
        if code
    ]


def _pick_filters_for_view(view_id: str, start: date, end: date, company_codes: list[str]) -> list[dict[str, Any]]:
    filters = _date_filter_for_view(view_id, start, end)
    if not company_codes:
        return filters
    view = load_catalog().view(view_id)
    if "company" not in view.column_by_id:
        return filters
    if len(company_codes) == 1:
        filters.append({"id": "company", "operator": "EQ", "value": company_codes[0]})
    else:
        filters.append({"id": "company", "operator": "Terms", "value": company_codes})
    return filters


def _quote_duckdb_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _archive_duckdb_path() -> Path | None:
    configured = settings.PUBLIC_DPAK_ARCHIVE_DUCKDB.strip()
    if not configured:
        return None
    path = Path(configured)
    if not path.is_file():
        raise ExternalDataClientError(f"PUBLIC_DPAK_ARCHIVE_DUCKDB finns inte: {path}")
    return path


def _fetch_archive_duckdb_rows(
    view_id: str,
    start: date,
    end: date,
    company_codes: list[str],
) -> list[dict[str, Any]] | None:
    path = _archive_duckdb_path()
    if path is None or view_id != settings.PUBLIC_DPAK_ARCHIVE_PICK_VIEW:
        return None
    try:
        import duckdb
    except ImportError as exc:
        raise ExternalDataClientError("PUBLIC_DPAK_ARCHIVE_DUCKDB kräver Python-paketet duckdb.") from exc

    con = duckdb.connect(str(path), read_only=True)
    try:
        exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
            [view_id],
        ).fetchone()
        if exists is None:
            raise ExternalDataClientError(f"DuckDB-arkivet saknar tabellen {view_id}.")
        columns = [
            str(row[0])
            for row in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ? ORDER BY ordinal_position",
                [view_id],
            ).fetchall()
            if str(row[0]) != "_row_date"
        ]
        if "_row_date" not in {
            str(row[0])
            for row in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                [view_id],
            ).fetchall()
        }:
            raise ExternalDataClientError(f"DuckDB-arkivet saknar _row_date för {view_id}.")
        select_sql = ", ".join(_quote_duckdb_identifier(column) for column in columns)
        where_parts = ["_row_date BETWEEN ? AND ?"]
        params: list[Any] = [start, end]
        if company_codes and "company" in columns:
            placeholders = ", ".join("?" for _code in company_codes)
            where_parts.append(f"upper({_quote_duckdb_identifier('company')}) IN ({placeholders})")
            params.extend(company_codes)
        query = (
            f"SELECT {select_sql} FROM {_quote_duckdb_identifier(view_id)} "
            f"WHERE {' AND '.join(where_parts)} ORDER BY _row_date"
        )
        cursor = con.execute(query, params)
        names = [str(item[0]) for item in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        con.close()


def _chunks(start: date, end: date, chunk_days: int) -> Iterable[tuple[date, date]]:
    current = start
    span = max(1, int(chunk_days or 1))
    while current <= end:
        chunk_end = min(end, date.fromordinal(current.toordinal() + span - 1))
        yield current, chunk_end
        current = date.fromordinal(chunk_end.toordinal() + 1)


def _pick_source_ranges(start: date, end: date, *, today: date | None = None) -> list[tuple[str, date, date]]:
    live_view = settings.PUBLIC_DPAK_LIVE_PICK_VIEW
    archive_view = settings.PUBLIC_DPAK_ARCHIVE_PICK_VIEW
    if not archive_view or live_view == archive_view:
        return [(live_view, start, end)]
    if settings.PUBLIC_DPAK_PREFER_ARCHIVE_DUCKDB and _archive_duckdb_path() is not None:
        return [(archive_view, start, end)]

    today = today or datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=PUBLIC_DPAK_LIVE_RETENTION_DAYS)
    if end < cutoff:
        return [(archive_view, start, end)]
    if start >= cutoff:
        return [(live_view, start, end)]
    archive_end = cutoff - timedelta(days=1)
    return [(archive_view, start, archive_end), (live_view, cutoff, end)]


def _source_chunks(start: date, end: date, chunk_days: int) -> list[tuple[str, date, date]]:
    return [
        (view_id, chunk_start, chunk_end)
        for view_id, range_start, range_end in _pick_source_ranges(start, end)
        for chunk_start, chunk_end in _chunks(range_start, range_end, chunk_days)
    ]


def _cleanup_public_dpak_sync_scope(
    db: Session,
    *,
    business_code: str,
    source_ranges: list[tuple[str, date, date]],
    planned_chunks: list[tuple[str, date, date]],
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> None:
    if progress:
        progress("Städar bort gamla D-pak-rader och chunkstatusar utanför aktiv källa...")

    planned_keys = {(view_id, _dt(chunk_start), _dt(chunk_end)) for view_id, chunk_start, chunk_end in planned_chunks}
    for chunk in db.query(PublicDpakSyncChunk).filter(PublicDpakSyncChunk.business_code == business_code).all():
        key = (chunk.source_view, chunk.chunk_start, chunk.chunk_end)
        if key not in planned_keys:
            db.delete(chunk)

    keep_filters = [
        and_(
            PublicDpakPickRow.source_view == view_id,
            PublicDpakPickRow.pick_date >= _dt(range_start),
            PublicDpakPickRow.pick_date <= _range_end_dt(range_end),
        )
        for view_id, range_start, range_end in source_ranges
    ]
    if keep_filters:
        db.query(PublicDpakPickRow).filter(
            PublicDpakPickRow.business_code == business_code,
            ~or_(*keep_filters),
        ).delete(synchronize_session=False)
    raw_keep_filters = [
        and_(
            PublicDpakRawPicklog.source_view == view_id,
            PublicDpakRawPicklog.pick_date >= _dt(range_start),
            PublicDpakRawPicklog.pick_date <= _range_end_dt(range_end),
        )
        for view_id, range_start, range_end in source_ranges
    ]
    if raw_keep_filters:
        db.query(PublicDpakRawPicklog).filter(
            PublicDpakRawPicklog.business_code == business_code,
            ~or_(*raw_keep_filters),
        ).delete(synchronize_session=False)
    db.commit()


def _range_end_dt(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=timezone.utc)


def _sync_chunk(
    db: Session,
    *,
    business_code: str,
    source_view: str,
    chunk_start: date,
    chunk_end: date,
) -> PublicDpakSyncChunk:
    start_dt = _dt(chunk_start)
    end_dt = _dt(chunk_end)
    chunk = (
        db.query(PublicDpakSyncChunk)
        .filter(
            PublicDpakSyncChunk.business_code == business_code,
            PublicDpakSyncChunk.source_view == source_view,
            PublicDpakSyncChunk.chunk_start == start_dt,
            PublicDpakSyncChunk.chunk_end == end_dt,
        )
        .one_or_none()
    )
    if chunk is None:
        chunk = PublicDpakSyncChunk(
            business_code=business_code,
            source_view=source_view,
            chunk_start=start_dt,
            chunk_end=end_dt,
            status="pending",
            row_count=0,
        )
        db.add(chunk)
        db.flush()
    return chunk


def _mark_public_dpak_dataset_status(
    db: Session,
    *,
    business_code: str,
    status: str,
    error_text: str | None = None,
) -> None:
    dataset = db.query(PublicDpakDataset).filter(PublicDpakDataset.business_code == business_code).one_or_none()
    if dataset is None:
        dataset = PublicDpakDataset(
            business_code=business_code,
            coverage_start=None,
            coverage_end=None,
            pick_rows=0,
            order_article_rows=0,
            order_supplier_rows=0,
            alias_rows=0,
            attribute_rows=0,
            source_summary={},
            status=status,
            error_text=error_text,
            built_at=datetime.now(timezone.utc),
        )
        db.add(dataset)
    else:
        dataset.status = status
        dataset.error_text = error_text
        dataset.built_at = datetime.now(timezone.utc)
    db.flush()


def _replace_pick_rows_for_chunk(
    db: Session,
    *,
    business_code: str,
    source_view: str,
    chunk_start: date,
    chunk_end: date,
    rows: list[dict[str, Any]],
    commit_batches: bool = False,
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> None:
    db.query(PublicDpakPickRow).filter(
        PublicDpakPickRow.business_code == business_code,
        PublicDpakPickRow.source_view == source_view,
        PublicDpakPickRow.pick_date >= _dt(chunk_start),
        PublicDpakPickRow.pick_date <= _range_end_dt(chunk_end),
    ).delete(synchronize_session=False)
    if commit_batches:
        db.commit()
    else:
        db.flush()
    _bulk_insert(db, PublicDpakPickRow, rows, commit_each_batch=commit_batches, progress=progress)


def _replace_pick_rows_for_chunk_with_retries(
    db: Session,
    *,
    business_code: str,
    source_view: str,
    chunk_start: date,
    chunk_end: date,
    rows: list[dict[str, Any]],
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> None:
    attempts = max(1, int(settings.PUBLIC_DPAK_DB_WRITE_RETRIES or 1))
    for attempt in range(1, attempts + 1):
        try:
            _replace_pick_rows_for_chunk(
                db,
                business_code=business_code,
                source_view=source_view,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
                rows=rows,
                commit_batches=True,
                progress=progress,
            )
            return
        except DB_WRITE_ERRORS as exc:
            try:
                db.rollback()
            except Exception:
                db.invalidate()
            if attempt >= attempts:
                raise
            if progress:
                progress(
                    {
                        "type": "db_retry",
                        "attempt": attempt + 1,
                        "attempts": attempts,
                        "view": source_view,
                        "start": chunk_start.isoformat(),
                        "end": chunk_end.isoformat(),
                        "error": str(exc).splitlines()[0][:200],
                    }
                )
            time_module.sleep(min(30, 3 * attempt))


def sync_public_dpak_pick_chunks(
    db: Session,
    support_directory: Path,
    *,
    business_code: str | None = None,
    start: date | None = None,
    end: date | None = None,
    chunk_days: int | None = None,
    force: bool = False,
    progress: Callable[[dict[str, Any] | str], None] | None = None,
) -> DpakSyncResult:
    business = public_dpak_business_code(business_code)
    start_day = start or parse_settings_date(settings.PUBLIC_DPAK_START_DATE, date(2025, 7, 1))
    end_day = end or parse_settings_date(settings.PUBLIC_DPAK_END_DATE, date(2026, 7, 1))
    if end_day < start_day:
        raise ValueError("Slutdatum maste vara samma som eller efter startdatum.")

    alias_file, attribute_file = load_support_csv_files(support_directory)
    client: ExternalDataClient | None = None
    span = chunk_days or settings.PUBLIC_DPAK_CHUNK_DAYS
    company_codes = _public_dpak_company_codes()
    source_ranges = _pick_source_ranges(start_day, end_day)
    planned_chunks = _source_chunks(start_day, end_day, span)
    views = list(dict.fromkeys(view_id for view_id, _range_start, _range_end in source_ranges))
    total_chunks = len(planned_chunks)
    chunks_fetched = 0
    chunks_skipped = 0
    rows_imported = 0

    _mark_public_dpak_dataset_status(db, business_code=business, status="syncing")
    _clear_derived_public_dpak_rows(db, business)
    replace_raw_support_rows(
        db,
        business_code=business,
        alias_file=alias_file,
        attribute_file=attribute_file,
        progress=progress,
    )
    db.commit()

    if progress:
        progress(
            {
                "type": "start",
                "business_code": business,
                "start": start_day.isoformat(),
                "end": end_day.isoformat(),
                "chunk_days": span,
                "views": views,
                "company_codes": company_codes,
                "archive_duckdb": str(_archive_duckdb_path() or ""),
                "source_ranges": [
                    {
                        "view": view_id,
                        "start": range_start.isoformat(),
                        "end": range_end.isoformat(),
                    }
                    for view_id, range_start, range_end in source_ranges
                ],
                "total_chunks": total_chunks,
            }
        )

    for chunk_index, (view_id, chunk_start, chunk_end) in enumerate(planned_chunks, start=1):
        chunk = _sync_chunk(
            db,
            business_code=business,
            source_view=view_id,
            chunk_start=chunk_start,
            chunk_end=chunk_end,
        )
        raw_chunk_rows = _raw_picklog_chunk_count(db, business, view_id, chunk_start, chunk_end, company_codes)
        if chunk.status == "complete" and raw_chunk_rows > 0 and not force:
            chunks_skipped += 1
            if progress:
                progress(
                    {
                        "type": "skip",
                        "index": chunk_index,
                        "total_chunks": total_chunks,
                        "view": view_id,
                        "start": chunk_start.isoformat(),
                        "end": chunk_end.isoformat(),
                        "rows": int(raw_chunk_rows or chunk.row_count or 0),
                        "rows_imported": rows_imported,
                        "chunks_fetched": chunks_fetched,
                        "chunks_skipped": chunks_skipped,
                    }
                )
            continue

        chunk.status = "running"
        chunk.started_at = datetime.now(timezone.utc)
        chunk.completed_at = None
        chunk.error_text = None
        db.commit()

        try:
            if progress:
                progress(
                    {
                        "type": "chunk_start",
                        "index": chunk_index,
                        "total_chunks": total_chunks,
                        "view": view_id,
                        "start": chunk_start.isoformat(),
                        "end": chunk_end.isoformat(),
                        "rows_imported": rows_imported,
                        "chunks_fetched": chunks_fetched,
                        "chunks_skipped": chunks_skipped,
                    }
                )
            row_source = "api"
            api_rows = _fetch_archive_duckdb_rows(view_id, chunk_start, chunk_end, company_codes)
            if api_rows is None:
                if client is None:
                    client = _api_client()
                api_rows = _fetch_api_rows_with_retries(
                    client,
                    view_id,
                    filters=_pick_filters_for_view(view_id, chunk_start, chunk_end, company_codes),
                    chunk_start=chunk_start,
                    chunk_end=chunk_end,
                    progress=progress,
                )
            else:
                row_source = "local_archive"
            inserted_rows = _replace_raw_picklog_for_chunk_with_retries(
                db,
                business_code=business,
                source_view=view_id,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
                rows=api_rows,
                progress=progress,
            )
            chunk = _sync_chunk(
                db,
                business_code=business,
                source_view=view_id,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
            )
            chunk.status = "complete"
            chunk.row_count = inserted_rows
            chunk.completed_at = datetime.now(timezone.utc)
            chunk.error_text = None
            db.commit()
            chunks_fetched += 1
            rows_imported += inserted_rows
            if progress:
                progress(
                    {
                        "type": "chunk_done",
                        "index": chunk_index,
                        "total_chunks": total_chunks,
                        "view": view_id,
                        "start": chunk_start.isoformat(),
                        "end": chunk_end.isoformat(),
                        "rows": inserted_rows,
                        "source": row_source,
                        "rows_imported": rows_imported,
                        "chunks_fetched": chunks_fetched,
                        "chunks_skipped": chunks_skipped,
                    }
                )
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                db.invalidate()
            try:
                failed_chunk = _sync_chunk(
                    db,
                    business_code=business,
                    source_view=view_id,
                    chunk_start=chunk_start,
                    chunk_end=chunk_end,
                )
                failed_chunk.status = "failed"
                failed_chunk.error_text = str(exc)[:4000]
                failed_chunk.completed_at = datetime.now(timezone.utc)
                _mark_public_dpak_dataset_status(
                    db,
                    business_code=business,
                    status="error",
                    error_text=f"{view_id} {chunk_start.isoformat()}..{chunk_end.isoformat()}: {exc}",
                )
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    db.invalidate()
            raise

    _cleanup_public_dpak_sync_scope(
        db,
        business_code=business,
        source_ranges=source_ranges,
        planned_chunks=planned_chunks,
        progress=progress,
    )

    build = _raw_dataset_result(
        db,
        business_code=business,
        source_summary={
            "mode": "raw_api_picklog_csv_support",
            "support_directory": str(support_directory),
            "item_alias": alias_file.source_file,
            "item_attribute": attribute_file.source_file,
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "chunk_days": span,
            "views": views,
            "company_codes": company_codes,
            "archive_duckdb": str(_archive_duckdb_path() or ""),
            "source_ranges": [
                {
                    "view": view_id,
                    "start": range_start.isoformat(),
                    "end": range_end.isoformat(),
                }
                for view_id, range_start, range_end in source_ranges
            ],
            "chunks_fetched": chunks_fetched,
            "chunks_skipped": chunks_skipped,
            "rows_imported": rows_imported,
        },
    )
    db.commit()
    if progress:
        progress(
            {
                "type": "rebuild_done",
                "total_chunks": total_chunks,
                "rows_imported": rows_imported,
                "chunks_fetched": chunks_fetched,
                "chunks_skipped": chunks_skipped,
                "pick_rows": build.pick_rows,
                "order_article_rows": build.order_article_rows,
                "order_supplier_rows": build.order_supplier_rows,
                "alias_rows": build.alias_rows,
                "attribute_rows": build.attribute_rows,
            }
        )
    return DpakSyncResult(
        build=build,
        chunks_fetched=chunks_fetched,
        chunks_skipped=chunks_skipped,
        rows_imported=rows_imported,
    )


def _dataset(db: Session, business_code: str) -> PublicDpakDataset | None:
    business = public_dpak_business_code(business_code)
    return db.query(PublicDpakDataset).filter(PublicDpakDataset.business_code == business).one_or_none()


def dataset_status(db: Session, business_code: str | None = None) -> dict[str, Any]:
    business = public_dpak_business_code(business_code)
    dataset = _dataset(db, business)
    raw_pick_rows = int(
        db.query(func.count(PublicDpakRawPicklog.id)).filter(PublicDpakRawPicklog.business_code == business).scalar() or 0
    )
    raw_alias_rows = int(
        db.query(func.count(PublicDpakRawItemAlias.id))
        .filter(PublicDpakRawItemAlias.business_code == business)
        .scalar()
        or 0
    )
    raw_attribute_rows = int(
        db.query(func.count(PublicDpakRawItemAttribute.id))
        .filter(PublicDpakRawItemAttribute.business_code == business)
        .scalar()
        or 0
    )
    chunk_counts = {
        str(status): int(count or 0)
        for status, count in (
            db.query(PublicDpakSyncChunk.status, func.count(PublicDpakSyncChunk.id))
            .filter(PublicDpakSyncChunk.business_code == business)
            .group_by(PublicDpakSyncChunk.status)
            .all()
        )
    }
    if dataset is None:
        return {"ready": False, "business_code": business, "status": "missing", "chunks": chunk_counts}
    raw_ready = raw_pick_rows > 0 and raw_alias_rows > 0 and raw_attribute_rows > 0
    status_value = dataset.status if raw_ready else "missing_raw"
    return {
        "ready": dataset.status == "ready" and raw_ready,
        "business_code": business,
        "status": status_value,
        "coverage_start": _day(dataset.coverage_start).isoformat() if dataset.coverage_start else None,
        "coverage_end": _day(dataset.coverage_end).isoformat() if dataset.coverage_end else None,
        "target_start": (dataset.source_summary or {}).get("start") if isinstance(dataset.source_summary, dict) else None,
        "target_end": (dataset.source_summary or {}).get("end") if isinstance(dataset.source_summary, dict) else None,
        "pick_rows": raw_pick_rows,
        "order_article_rows": int(dataset.order_article_rows or 0),
        "order_supplier_rows": int(dataset.order_supplier_rows or 0),
        "alias_rows": raw_alias_rows,
        "attribute_rows": raw_attribute_rows,
        "built_at": dataset.built_at.isoformat(timespec="seconds") if dataset.built_at else None,
        "chunks": chunk_counts,
    }


def _normalize_question(text: str) -> str:
    return str(text or "").strip().lower().replace("å", "a").replace("ä", "a").replace("ö", "o")


def _normalize_question(text: str) -> str:
    normalized = str(text or "").strip().lower()
    replacements = {
        "\u00e5": "a",
        "\u00e4": "a",
        "\u00f6": "o",
        "\u00c3\u00a5": "a",
        "\u00c3\u00a4": "a",
        "\u00c3\u00b6": "o",
        "\ufffd": "a",
    }
    for before, after in replacements.items():
        normalized = normalized.replace(before, after)
    return normalized


def _format_int(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _format_pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _latest_user_messages(messages: list[dict[str, str]]) -> list[str]:
    return [str(item.get("content") or "") for item in messages if item.get("role") == "user"]


def _dataset_period_year(month: int, dataset: PublicDpakDataset | None) -> int | None:
    start = _day(dataset.coverage_start) if dataset else None
    end = _day(dataset.coverage_end) if dataset else None
    if start is None or end is None:
        return None
    for year in range(end.year, start.year - 1, -1):
        last_day = calendar.monthrange(year, month)[1]
        candidate_start = date(year, month, 1)
        candidate_end = date(year, month, last_day)
        if candidate_end >= start and candidate_start <= end:
            return year
    return None


def infer_period(texts: list[str], dataset: PublicDpakDataset | None) -> Period | None:
    for text in reversed(texts):
        match = MONTH_PATTERN.search(_normalize_question(text))
        if not match:
            continue
        month = MONTH_ALIASES.get(match.group(1))
        if not month:
            continue
        year = int(match.group(2)) if match.group(2) else _dataset_period_year(month, dataset)
        if not year:
            continue
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        if dataset and dataset.coverage_start:
            start = max(start, _day(dataset.coverage_start) or start)
        if dataset and dataset.coverage_end:
            end = min(end, _day(dataset.coverage_end) or end)
        month_name = next(key for key, value in MONTH_ALIASES.items() if value == month and len(key) > 3)
        return Period(start=start, end=end, label=f"{month_name} {year}")
    return None


def infer_zone(texts: list[str]) -> str | None:
    for text in reversed(texts):
        normalized = _normalize_question(text)
        match = re.search(r"\bzon\s+([a-z0-9]+)\b", normalized)
        if match:
            return match.group(1).upper()
    return None


def infer_supplier(text: str) -> str | None:
    patterns = (
        r"leverant[oö]ren\s+(.+?)(?:\s+bryts|\s+brut|$)",
        r"leverant[oö]r\s+(.+?)(?:\s+bryts|\s+brut|$)",
        r"fr[aå]n\s+(.+?)(?:\s+bryts|\s+brut|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            supplier = re.sub(r"[^A-Za-z0-9ÅÄÖåäö .&-].*$", "", match.group(1)).strip()
            return supplier or None
    return None


def infer_supplier(text: str) -> str | None:
    patterns = (
        r"leverant[o\u00f6]ren\s+(.+?)(?:\s+bryts|\s+brut|$)",
        r"leverant[o\u00f6]r\s+(.+?)(?:\s+bryts|\s+brut|$)",
        r"fr[a\u00e5]n\s+(.+?)(?:\s+bryts|\s+brut|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            supplier = re.sub(r"[^A-Za-z0-9\u00c5\u00c4\u00d6\u00e5\u00e4\u00f6 .&-].*$", "", match.group(1)).strip()
            return supplier or None
    return None


def _date_bounds(period: Period | None) -> tuple[datetime | None, datetime | None]:
    if period is None:
        return None, None
    return _dt(period.start), datetime.combine(period.end, time.max, tzinfo=timezone.utc)


def _fact_query(db: Session, business_code: str, period: Period | None = None, zone: str | None = None):
    query = db.query(PublicDpakOrderArticleFact).filter(PublicDpakOrderArticleFact.business_code == business_code)
    start_dt, end_dt = _date_bounds(period)
    if start_dt is not None:
        query = query.filter(PublicDpakOrderArticleFact.pick_date >= start_dt)
    if end_dt is not None:
        query = query.filter(PublicDpakOrderArticleFact.pick_date <= end_dt)
    if zone:
        query = query.filter(func.upper(PublicDpakOrderArticleFact.pick_zone) == zone.upper())
    return query


def _box_query(db: Session, business_code: str, period: Period | None = None):
    query = db.query(PublicDpakOrderSupplierBoxFact).filter(
        PublicDpakOrderSupplierBoxFact.business_code == business_code
    )
    start_dt, end_dt = _date_bounds(period)
    if start_dt is not None:
        query = query.filter(PublicDpakOrderSupplierBoxFact.pick_date >= start_dt)
    if end_dt is not None:
        query = query.filter(PublicDpakOrderSupplierBoxFact.pick_date <= end_dt)
    return query


def _period_suffix(period: Period | None) -> str:
    return f" under {period.label}" if period else ""


def _zone_suffix(zone: str | None) -> str:
    return f" i zon {zone.upper()}" if zone else ""


def _result(answer: str, *, table: list[dict[str, Any]] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"answer": answer, "table": table or [], "context": context or {}, "model": "deterministic-dpak"}


def _sum_dpack_sold(db: Session, business_code: str, period: Period | None, zone: str | None) -> dict[str, Any]:
    total = _fact_query(db, business_code, period, zone).with_entities(func.coalesce(func.sum(PublicDpakOrderArticleFact.dpack_sold), 0)).scalar()
    return _result(
        f"{_format_int(total)} D-pak sålda{_zone_suffix(zone)}{_period_suffix(period)}.",
        context={"intent": "dpack_sold", "period": period.label if period else None, "zone": zone},
    )


def _sum_unnecessary_breaks(db: Session, business_code: str, period: Period | None, zone: str | None) -> dict[str, Any]:
    query = _fact_query(db, business_code, period, zone)
    broken = query.with_entities(func.coalesce(func.sum(PublicDpakOrderArticleFact.dpack_broken), 0)).scalar()
    occasions = query.filter(PublicDpakOrderArticleFact.unnecessary_break.is_(True)).count()
    return _result(
        f"{_format_int(broken)} D-pak var onödigt brutna{_zone_suffix(zone)}{_period_suffix(period)} vid {_format_int(occasions)} order/artikel-tillfällen.",
        context={"intent": "unnecessary_breaks", "period": period.label if period else None, "zone": zone},
    )


def _supplier_count(db: Session, business_code: str, period: Period | None, zone: str | None) -> dict[str, Any]:
    query = _fact_query(db, business_code, period, zone).filter(PublicDpakOrderArticleFact.supplier.is_not(None))
    total = query.with_entities(func.count(func.distinct(PublicDpakOrderArticleFact.supplier))).scalar() or 0
    return _result(
        f"{_format_int(total)} leverantörer har plockats{_zone_suffix(zone)}{_period_suffix(period)}.",
        context={"intent": "supplier_count", "period": period.label if period else None, "zone": zone},
    )


def _autostore_orders(db: Session, business_code: str, period: Period | None, zone: str | None) -> dict[str, Any]:
    query = _fact_query(db, business_code, period, zone).filter(PublicDpakOrderArticleFact.has_autostore.is_(True))
    total = query.with_entities(func.count(func.distinct(PublicDpakOrderArticleFact.order_num))).scalar() or 0
    return _result(
        f"{_format_int(total)} ordrar finns i AUTOSTORE-siffrorna{_zone_suffix(zone)}{_period_suffix(period)}.",
        context={"intent": "autostore_orders", "period": period.label if period else None, "zone": zone},
    )


def _top_broken_articles(db: Session, business_code: str, supplier: str | None, period: Period | None, zone: str | None) -> dict[str, Any]:
    query = _fact_query(db, business_code, period, zone)
    if supplier:
        query = query.filter(PublicDpakOrderArticleFact.supplier.ilike(f"%{supplier}%"))
    rows = (
        query.with_entities(
            PublicDpakOrderArticleFact.item_num,
            func.max(PublicDpakOrderArticleFact.item_desc).label("item_desc"),
            PublicDpakOrderArticleFact.supplier,
            func.coalesce(func.sum(PublicDpakOrderArticleFact.dpack_broken), 0).label("broken"),
            func.count(PublicDpakOrderArticleFact.id).label("occasions"),
        )
        .filter(PublicDpakOrderArticleFact.dpack_broken > 0)
        .group_by(
            PublicDpakOrderArticleFact.item_num,
            PublicDpakOrderArticleFact.supplier,
        )
        .order_by(func.coalesce(func.sum(PublicDpakOrderArticleFact.dpack_broken), 0).desc(), func.count(PublicDpakOrderArticleFact.id).desc())
        .limit(10)
        .all()
    )
    table = [
        {
            "Artikelnr": item_num,
            "Artikel": item_desc,
            "Leverantör": row_supplier,
            "Onödigt brutna": int(broken or 0),
            "Tillfällen": int(occasions or 0),
        }
        for item_num, item_desc, row_supplier, broken, occasions in rows
    ]
    if not table:
        name = f" för {supplier}" if supplier else ""
        return _result(f"Jag hittade inga onödigt brutna D-pak{name}{_zone_suffix(zone)}{_period_suffix(period)}.", table=[])
    name = f" från {supplier}" if supplier else ""
    return _result(
        f"De artiklar{name} som bryts oftast är sorterade på antal onödigt brutna D-pak.",
        table=table,
        context={"intent": "top_broken_articles", "supplier": supplier, "period": period.label if period else None, "zone": zone},
    )


def _supplier_box_spread(db: Session, business_code: str, period: Period | None) -> dict[str, Any]:
    query = _box_query(db, business_code, period)
    total = query.filter(PublicDpakOrderSupplierBoxFact.can_spread.is_(True)).count()
    spread = query.filter(PublicDpakOrderSupplierBoxFact.spread.is_(True)).count()
    pct = (spread / total * 100) if total else 0
    answer = (
        f"{_format_int(spread)} av {_format_int(total)} order/leverantör-kombinationer i zon R "
        f"är spridda över flera lådor ({_format_pct(pct)}%){_period_suffix(period)}."
    )
    return _result(
        answer,
        context={"intent": "supplier_box_spread", "period": period.label if period else None, "zone": "R"},
    )


def _dates_answer(dataset: PublicDpakDataset | None, business_code: str) -> dict[str, Any]:
    if dataset is None:
        return _result(f"Det finns inget färdigladdat D-pak-underlag för {business_code} ännu.")
    start = _day(dataset.coverage_start)
    end = _day(dataset.coverage_end)
    summary = dataset.source_summary or {}
    target_start = summary.get("start") if isinstance(summary, dict) else None
    target_end = summary.get("end") if isinstance(summary, dict) else None
    if start is None or end is None:
        if target_start and target_end:
            return _result(f"Underlaget är hämtat för {target_start} till {target_end}, men raderna saknar datumtäckning.")
        return _result("Underlaget är laddat men saknar datumtäckning.")
    if target_start and target_end:
        return _result(
            f"Underlaget är hämtat för {target_start} till {target_end}. Raderna i databasen sträcker sig från {start.isoformat()} till {end.isoformat()} och byggdes {dataset.built_at.isoformat(timespec='seconds') if dataset.built_at else 'okänd tid'}.",
            context={"intent": "dates"},
        )
    return _result(
        f"Underlaget täcker {start.isoformat()} till {end.isoformat()} och byggdes {dataset.built_at.isoformat(timespec='seconds') if dataset.built_at else 'okänd tid'}.",
        context={"intent": "dates"},
    )


def answer_public_dpak_question(
    db: Session,
    *,
    messages: list[dict[str, str]],
    business_code: str | None = None,
) -> dict[str, Any]:
    business = public_dpak_business_code(business_code)
    dataset = _dataset(db, business)
    if dataset is None or dataset.status != "ready":
        return _dates_answer(dataset, business)

    user_messages = _latest_user_messages(messages)
    latest = user_messages[-1] if user_messages else ""
    normalized = _normalize_question(latest)
    period = infer_period(user_messages, dataset)
    zone = infer_zone([latest]) or (infer_zone(user_messages[:-1]) if len(normalized) <= 12 else None)
    previous_text = user_messages[-2] if len(user_messages) >= 2 else ""
    previous = _normalize_question(user_messages[-2]) if len(user_messages) >= 2 else ""

    if "vilka datum" in normalized or ("datum" in normalized and "kollar" in normalized):
        return _dates_answer(dataset, business)

    if ("zon r" in normalized or normalized in {"i zon r?", "i zon r", "zon r?"}) and previous:
        if "leverantor" in previous and "hur manga" in previous:
            return _supplier_count(db, business, period, "R")
        if ("d-pak" in previous or "dpak" in previous or "dfp" in previous) and ("salde" in previous or "sålde" in previous):
            return _sum_dpack_sold(db, business, period, "R")
        if "autostore" in previous and "ord" in previous:
            return _autostore_orders(db, business, period, "R")

    if "autostore" in normalized and "ord" in normalized:
        return _autostore_orders(db, business, period, zone)

    if "leverantor" in normalized and "hur manga" in normalized:
        return _supplier_count(db, business, period, zone)

    if ("olika lador" in normalized or "olika lådor" in latest.lower() or "spridd" in normalized) and "leverantor" in normalized:
        return _supplier_box_spread(db, business, period)

    if ("d-pak" in latest.lower() or "dpak" in normalized or "dfp" in normalized) and ("salde" in normalized or "sålde" in latest.lower() or "sålda" in latest.lower()):
        return _sum_dpack_sold(db, business, period, zone)

    if previous and ("tabell" in normalized or "onodigt" in normalized) and (
        "artiklar" in previous or "bryt" in previous or "brut" in previous
    ):
        supplier = infer_supplier(latest) or infer_supplier(previous_text)
        if supplier:
            return _top_broken_articles(db, business, supplier, period, zone)

    if "onodigt" in normalized and ("brut" in normalized or "bryt" in normalized):
        supplier = infer_supplier(latest)
        if "vilka artiklar" in latest.lower() or "artiklar" in normalized:
            return _top_broken_articles(db, business, supplier, period, zone)
        return _sum_unnecessary_breaks(db, business, period, zone)

    if ("vilka artiklar" in latest.lower() or "artiklar" in normalized) and ("bryts" in normalized or "brut" in normalized or "bryt" in normalized):
        return _top_broken_articles(db, business, infer_supplier(latest), period, zone)

    return _result(
        "Jag kan räkna D-pak sålda, onödigt brutna D-pak, zon R, leverantörer, AUTOSTORE-ordrar, datumtäckning och artiklar per leverantör. Skriv gärna frågan med månad, zon eller leverantörsnamn.",
        context={"intent": "fallback"},
    )


def parse_settings_date(value: str, fallback: date) -> date:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return fallback


def import_from_csv_directory(db: Session, directory: Path, *, business_code: str | None = None) -> DpakBuildResult:
    business = public_dpak_business_code(business_code)
    alias_file, attribute_file = load_support_csv_files(directory)
    pick_sources = load_pick_csv_files(directory)
    _clear_derived_public_dpak_rows(db, business)
    replace_raw_support_rows(
        db,
        business_code=business,
        alias_file=alias_file,
        attribute_file=attribute_file,
    )
    _replace_all_raw_picklog(db, business_code=business, pick_sources=pick_sources)
    return _raw_dataset_result(
        db,
        business_code=business,
        source_summary={
            "mode": "raw_csv_directory",
            "directory": str(directory),
            "item_alias": alias_file.source_file,
            "item_attribute": attribute_file.source_file,
            "picklog_sources": [
                {"view": view_id, "file": source_file, "rows": len(rows)}
                for view_id, source_file, rows in pick_sources
            ],
        },
    )


def import_from_api_and_csv_support(
    db: Session,
    directory: Path,
    *,
    business_code: str | None = None,
    start: date | None = None,
    end: date | None = None,
    chunk_days: int | None = None,
) -> DpakBuildResult:
    return sync_public_dpak_pick_chunks(
        db,
        directory,
        business_code=public_dpak_business_code(business_code),
        start=start,
        end=end,
        chunk_days=chunk_days,
    ).build
