from __future__ import annotations

import calendar
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
from sqlalchemy import func
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


def _bulk_insert(db: Session, model, rows: list[dict[str, Any]], chunk_size: int = 2000) -> None:
    for index in range(0, len(rows), chunk_size):
        db.bulk_insert_mappings(model, rows[index : index + chunk_size])
        db.flush()


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
    db.query(PublicDpakDataset).filter(PublicDpakDataset.business_code == business).delete(synchronize_session=False)
    db.flush()

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


def rebuild_public_dpak_facts(
    db: Session,
    *,
    business_code: str,
    alias_rows: list[dict[str, Any]],
    attribute_rows: list[dict[str, Any]],
    source_summary: dict[str, Any] | None = None,
) -> DpakBuildResult:
    business = public_dpak_business_code(business_code)
    raw_rows = _stored_pick_rows(db, business)
    supplier_map = _supplier_by_item(attribute_rows)
    for row in raw_rows:
        item_num = row.get("item_num")
        if item_num in supplier_map:
            row["supplier"] = supplier_map[item_num]
    normalized_rows = _dedupe_pick_rows(raw_rows)
    factor_map = _factor_by_item(alias_rows)
    article_facts = build_order_article_facts(normalized_rows, factor_map, business_code=business)
    supplier_facts = build_order_supplier_box_facts(normalized_rows, business_code=business)

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
    db.flush()

    _bulk_insert(db, PublicDpakOrderArticleFact, article_facts)
    _bulk_insert(db, PublicDpakOrderSupplierBoxFact, supplier_facts)

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


def _date_filter_for_view(view_id: str, start: date, end: date) -> list[dict[str, Any]]:
    view = load_catalog().view(view_id)
    column = _preferred_date_column(view)
    if column is None:
        raise ExternalDataClientError(f"Vyn {view_id} saknar datumkolumn i katalogen.")
    period = _date_period_payload("public_dpak_sync", start, end)
    return [{"id": column.id, "operator": "Between", "value": _period_values_for_column(period, column)}]


def _chunks(start: date, end: date, chunk_days: int) -> Iterable[tuple[date, date]]:
    current = start
    span = max(1, int(chunk_days or 1))
    while current <= end:
        chunk_end = min(end, date.fromordinal(current.toordinal() + span - 1))
        yield current, chunk_end
        current = date.fromordinal(chunk_end.toordinal() + 1)


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
) -> None:
    db.query(PublicDpakPickRow).filter(
        PublicDpakPickRow.business_code == business_code,
        PublicDpakPickRow.source_view == source_view,
        PublicDpakPickRow.pick_date >= _dt(chunk_start),
        PublicDpakPickRow.pick_date <= _range_end_dt(chunk_end),
    ).delete(synchronize_session=False)
    db.flush()
    _bulk_insert(db, PublicDpakPickRow, rows)


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

    alias_rows, attribute_rows = load_support_csvs(support_directory)
    supplier_map = _supplier_by_item(attribute_rows)
    client = _api_client()
    span = chunk_days or settings.PUBLIC_DPAK_CHUNK_DAYS
    views = [settings.PUBLIC_DPAK_LIVE_PICK_VIEW, settings.PUBLIC_DPAK_ARCHIVE_PICK_VIEW]
    chunk_ranges = list(_chunks(start_day, end_day, span))
    total_chunks = len(views) * len(chunk_ranges)
    chunks_fetched = 0
    chunks_skipped = 0
    rows_imported = 0

    _mark_public_dpak_dataset_status(db, business_code=business, status="syncing")
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
                "total_chunks": total_chunks,
            }
        )

    chunk_index = 0
    for view_id in views:
        for chunk_start, chunk_end in chunk_ranges:
            chunk_index += 1
            chunk = _sync_chunk(
                db,
                business_code=business,
                source_view=view_id,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
            )
            if chunk.status == "complete" and not force:
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
                            "rows": int(chunk.row_count or 0),
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
                api_rows = client.fetch_data(view_id, filters=_date_filter_for_view(view_id, chunk_start, chunk_end))
                normalized_rows = normalize_pick_rows(
                    view_id,
                    api_rows,
                    business_code=business,
                    supplier_by_item=supplier_map,
                )
                normalized_rows = [
                    row
                    for row in normalized_rows
                    if (pick_day := _day(row.get("pick_date"))) is not None and chunk_start <= pick_day <= chunk_end
                ]
                normalized_rows = _dedupe_pick_rows(normalized_rows)
                _replace_pick_rows_for_chunk(
                    db,
                    business_code=business,
                    source_view=view_id,
                    chunk_start=chunk_start,
                    chunk_end=chunk_end,
                    rows=normalized_rows,
                )
                chunk = _sync_chunk(
                    db,
                    business_code=business,
                    source_view=view_id,
                    chunk_start=chunk_start,
                    chunk_end=chunk_end,
                )
                chunk.status = "complete"
                chunk.row_count = len(normalized_rows)
                chunk.completed_at = datetime.now(timezone.utc)
                chunk.error_text = None
                db.commit()
                chunks_fetched += 1
                rows_imported += len(normalized_rows)
                if progress:
                    progress(
                        {
                            "type": "chunk_done",
                            "index": chunk_index,
                            "total_chunks": total_chunks,
                            "view": view_id,
                            "start": chunk_start.isoformat(),
                            "end": chunk_end.isoformat(),
                            "rows": len(normalized_rows),
                            "rows_imported": rows_imported,
                            "chunks_fetched": chunks_fetched,
                            "chunks_skipped": chunks_skipped,
                        }
                    )
            except Exception as exc:
                db.rollback()
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
                raise

    if progress:
        progress(
            {
                "type": "rebuild_start",
                "total_chunks": total_chunks,
                "rows_imported": rows_imported,
                "chunks_fetched": chunks_fetched,
                "chunks_skipped": chunks_skipped,
            }
        )

    build = rebuild_public_dpak_facts(
        db,
        business_code=business,
        alias_rows=alias_rows,
        attribute_rows=attribute_rows,
        source_summary={
            "mode": "api_pick_logs_csv_support",
            "support_directory": str(support_directory),
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "chunk_days": span,
            "views": views,
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
    return {
        "ready": dataset.status == "ready",
        "business_code": business,
        "status": dataset.status,
        "coverage_start": _day(dataset.coverage_start).isoformat() if dataset.coverage_start else None,
        "coverage_end": _day(dataset.coverage_end).isoformat() if dataset.coverage_end else None,
        "target_start": (dataset.source_summary or {}).get("start") if isinstance(dataset.source_summary, dict) else None,
        "target_end": (dataset.source_summary or {}).get("end") if isinstance(dataset.source_summary, dict) else None,
        "pick_rows": int(dataset.pick_rows or 0),
        "order_article_rows": int(dataset.order_article_rows or 0),
        "order_supplier_rows": int(dataset.order_supplier_rows or 0),
        "built_at": dataset.built_at.isoformat(timespec="seconds") if dataset.built_at else None,
        "chunks": chunk_counts,
    }


def _normalize_question(text: str) -> str:
    return str(text or "").strip().lower().replace("å", "a").replace("ä", "a").replace("ö", "o")


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
            PublicDpakOrderArticleFact.item_desc,
            PublicDpakOrderArticleFact.supplier,
            func.coalesce(func.sum(PublicDpakOrderArticleFact.dpack_broken), 0).label("broken"),
            func.count(PublicDpakOrderArticleFact.id).label("occasions"),
        )
        .filter(PublicDpakOrderArticleFact.dpack_broken > 0)
        .group_by(
            PublicDpakOrderArticleFact.item_num,
            PublicDpakOrderArticleFact.item_desc,
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
    alias_rows, attribute_rows = load_support_csvs(directory)
    pick_sources = load_pick_csvs(directory)
    return replace_public_dpak_dataset(
        db,
        business_code=public_dpak_business_code(business_code),
        pick_sources=pick_sources,
        alias_rows=alias_rows,
        attribute_rows=attribute_rows,
        source_summary={"mode": "csv_directory", "directory": str(directory)},
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
