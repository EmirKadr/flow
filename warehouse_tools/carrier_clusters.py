from __future__ import annotations

import io
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


CARRIER_CLUSTER_DEFAULTS: dict[str, dict[str, Any]] = {}


def _register_carrier_cluster_defaults(carrier_nums: tuple[int, ...], **defaults: Any) -> None:
    for carrier_num in carrier_nums:
        CARRIER_CLUSTER_DEFAULTS[str(carrier_num)] = dict(defaults)


_register_carrier_cluster_defaults((78, 79), clusterGroup="Schenker", assignmentOrder=0, startSeq=205, endSeq=356, color="#94a3b8")
_register_carrier_cluster_defaults((76, 77), clusterGroup="Schenker", assignmentOrder=1, startSeq=205, endSeq=356, color="#60a5fa")
_register_carrier_cluster_defaults((93, 94), clusterGroup="Schenker", assignmentOrder=2, startSeq=205, endSeq=356, color="#94a3b8")
_register_carrier_cluster_defaults((74, 75), clusterGroup="Schenker", assignmentOrder=3, startSeq=205, endSeq=356, color="#fb923c")
_register_carrier_cluster_defaults((82, 83), clusterGroup="Schenker", assignmentOrder=4, startSeq=205, endSeq=356, color="#34d399")
_register_carrier_cluster_defaults((80, 81), clusterGroup="Schenker", assignmentOrder=5, startSeq=205, endSeq=356, color="#2dd4bf")
_register_carrier_cluster_defaults((41,), assignmentOrder=6, startSeq=356, endSeq=205, color="#fcd34d")
_register_carrier_cluster_defaults((61, 63, 69), assignmentOrder=7, startSeq=356, endSeq=205, color="#86efac")
_register_carrier_cluster_defaults((85,), assignmentOrder=8, startSeq=356, endSeq=205, color="#f9a8d4")
_register_carrier_cluster_defaults((42, 43), clusterGroup="Freja", assignmentOrder=9, startSeq=600, endSeq=652, color="#c4b5fd")
_register_carrier_cluster_defaults((39, 40), clusterGroup="Freja", assignmentOrder=10, startSeq=600, endSeq=652, color="#c4b5fd")
_register_carrier_cluster_defaults((44, 45), clusterGroup="Freja", assignmentOrder=11, startSeq=600, endSeq=652, color="#c4b5fd")
_register_carrier_cluster_defaults((48, 49), clusterGroup="Freja", assignmentOrder=12, startSeq=600, endSeq=652, color="#c4b5fd")
_register_carrier_cluster_defaults((46, 47), clusterGroup="Freja", assignmentOrder=13, startSeq=600, endSeq=652, color="#c4b5fd")
_register_carrier_cluster_defaults((51,), assignmentOrder=14, startSeq=652, endSeq=600, color="#fdba74")
_register_carrier_cluster_defaults((53,), clusterGroup="Sandahls Sundsvall", assignmentOrder=15, startSeq=205, endSeq=652, color="#f472b6")
_register_carrier_cluster_defaults((55,), clusterGroup="Sandahls Sundsvall", assignmentOrder=16, startSeq=205, endSeq=652, color="#f472b6")
_register_carrier_cluster_defaults((57,), clusterGroup="Sandahls Norrland", assignmentOrder=17, startSeq=600, endSeq=652, color="#fb7185")
_register_carrier_cluster_defaults((59,), clusterGroup="Sandahls Norrland", assignmentOrder=18, startSeq=600, endSeq=652, color="#fda4af")
_register_carrier_cluster_defaults((97,), assignmentOrder=19, startSeq=205, endSeq=652, color="#e879f9")
_register_carrier_cluster_defaults((65, 67), assignmentOrder=20, startSeq=205, endSeq=652, color="#4ade80")
_register_carrier_cluster_defaults((71, 73), assignmentOrder=21, startSeq=205, endSeq=652, color="#fbbf24")


def text_value(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "nat", "none", "null"} else text


def identifier_value(value: object) -> str:
    text = text_value(value)
    match = re.fullmatch(r"(\d+)\.0+", text)
    return match.group(1) if match else text


def carrier_match_key(value: object) -> str:
    text = text_value(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _column_key(value: object) -> str:
    text = text_value(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _find_column(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    lookup = {_column_key(column): column for column in df.columns}
    for alias in aliases:
        column = lookup.get(_column_key(alias))
        if column is not None:
            return column
    return None


def _to_int(value: object) -> int | None:
    text = text_value(value).replace(",", ".")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        digits = re.findall(r"\d+", text)
        return int(digits[0]) if digits else None


def _first_value(row: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if key in row:
            return row.get(key)
    return None


def _carrier_cluster_defaults(carrier_num: str, alias: str, description: str) -> dict[str, Any]:
    for value in (carrier_num, alias, description):
        key = text_value(value)
        if key in CARRIER_CLUSTER_DEFAULTS:
            return CARRIER_CLUSTER_DEFAULTS[key]
    return {}


def _read_csv(path: Path) -> pd.DataFrame:
    data = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    return pd.read_csv(io.StringIO(text), sep=None, engine="python")


def normalize_carrier_cluster_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        carrier_num = identifier_value(
            _first_value(row, "carrierNum", "carrier_num", "agencyNum", "agency_num", "AGENCY_NUM")
        )
        description = text_value(
            _first_value(row, "description", "agencyDesc", "agency_desc", "AGENCY_DESC", "carrier", "transportor")
        )
        alias = text_value(
            _first_value(row, "alias", "agencyAlias", "agency_alias", "AGENCY_ALIAS")
        )
        label = alias or description or carrier_num
        if not label:
            continue
        cluster_group = text_value(
            _first_value(row, "clusterGroup", "cluster_group", "CLUSTER_GROUP", "cluster")
        )
        assignment_order = _to_int(
            _first_value(row, "assignmentOrder", "assignment_order", "ASSIGNMENT_ORDER", "order")
        )
        start_seq = _to_int(
            _first_value(row, "startSeq", "start_seq", "START_SEQ", "from", "utlFrom")
        )
        end_seq = _to_int(
            _first_value(row, "endSeq", "end_seq", "END_SEQ", "to", "utlTo")
        )
        defaults = _carrier_cluster_defaults(carrier_num, alias, description)
        normalized.append(
            {
                "id": text_value(row.get("id")) or carrier_num or f"row-{index + 1}",
                "carrierNum": carrier_num,
                "description": description,
                "alias": alias,
                "clusterGroup": cluster_group or defaults.get("clusterGroup", ""),
                "assignmentOrder": assignment_order if assignment_order is not None else defaults.get("assignmentOrder"),
                "startSeq": start_seq if start_seq is not None else defaults.get("startSeq"),
                "endSeq": end_seq if end_seq is not None else defaults.get("endSeq"),
                "color": text_value(_first_value(row, "color", "colour")) or text_value(defaults.get("color")),
            }
        )
    normalized.sort(
        key=lambda row: (
            row["assignmentOrder"] if row["assignmentOrder"] is not None else 10_000,
            carrier_match_key(row["alias"] or row["description"] or row["carrierNum"]),
            row["carrierNum"],
        )
    )
    return normalized


def read_carrier_clusters(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    df = _read_csv(source)
    if df.empty:
        rows: list[dict[str, Any]] = []
    else:
        columns = {
            "carrierNum": _find_column(df, ("agency_num", "carrier_num", "transportor_num", "trans_nr", "trans nr")),
            "description": _find_column(df, ("agency_desc", "carrier", "transportor", "transportor namn", "description")),
            "alias": _find_column(df, ("agency_alias", "carrier_alias", "transportor_alias", "alias")),
            "clusterGroup": _find_column(df, ("cluster_group", "cluster", "cluster group", "kluster", "klustergrupp")),
            "assignmentOrder": _find_column(df, ("assignment_order", "assignment order", "sortering", "ordning", "order")),
            "startSeq": _find_column(df, ("start_seq", "start seq", "start", "fran", "utl fran", "utl from")),
            "endSeq": _find_column(df, ("end_seq", "end seq", "end", "till", "utl till", "utl to")),
            "color": _find_column(df, ("color", "colour", "farg")),
        }
        raw_rows = []
        for _, df_row in df.iterrows():
            raw_rows.append(
                {
                    key: df_row[column]
                    for key, column in columns.items()
                    if column is not None
                }
            )
        rows = normalize_carrier_cluster_rows(raw_rows)
    return {
        "version": 1,
        "source": {"name": source.name, "rowCount": len(rows)},
        "rows": rows,
    }


def normalize_carrier_cluster_payload(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    payload = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        payload = json.loads(text)
    if isinstance(payload, list):
        rows = normalize_carrier_cluster_rows(payload)
        return {"version": 1, "source": {"name": "Manuellt", "rowCount": len(rows)}, "rows": rows}
    if not isinstance(payload, dict):
        return None
    rows_value = payload.get("rows")
    rows = normalize_carrier_cluster_rows(rows_value if isinstance(rows_value, list) else [])
    return {
        "version": 1,
        "source": payload.get("source") if isinstance(payload.get("source"), dict) else {"name": "Transportorer", "rowCount": len(rows)},
        "rows": rows,
    }
