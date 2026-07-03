"""KPI-poangsattning: mal, handelser och score_kpi_events."""
from __future__ import annotations

import gzip
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..home_activity import build_home_activity_resolver
from ..models import Activity, Area, Person, ScheduleCell
from ..productivity_service import (
    HOURS,
    SOURCE_SPECS,
    SOURCE_SPEC_BY_KEY,
    ProductivitySourceError,
    _detect_dialect,
    _format_size,
    _get,
    _number,
    _source_payload,
    _timestamp,
)
from ..template_service import get_template_hours_map_for_dates
from .rules import (  # noqa: F401
    METRIC_TARGET_COLUMNS,
    METRIC_POINT_COLUMNS,
    EVENT_DATE_SOURCE_KEYS,
    KPI_LOGIC_SOURCE_KEY,
    KPI_LOGIC_SOURCE_LABEL,
    KpiTarget,
    KpiLogEvent,
    KpiPointEvent,
    KpiRule,
    normalize_process,
    normalize_name,
    split_process_names,
    _canonical_header,
    _row_text,
    _row_number,
    _row_upper,
    _row_int_text,
    _company,
    _warehouse,
    _one,
    _pall_num,
    _sort_company,
    _sort_warehouse,
    RULE_METRIC_ALIASES,
    RULE_SOURCE_ALIASES,
    _split_rule_values,
    _upper_values,
    _rule_bool,
    _normalize_rule_metric,
    _normalize_rule_source,
    _row_config_value,
    _starts_any,
    _column_value_getter,
    _distinct_key_getter,
    _rule_value_getter,
    _rule_criteria,
    _rule_predicate,
    parse_kpi_rule_rows,
    rules_by_process,
    kpi_rule_contract,
    _sql_reference_kpi_rule_source,
    load_kpi_rules,
)


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        dialect = _detect_dialect(sample)
        import csv

        reader = csv.DictReader(handle, dialect=dialect)
        headers = [str(header or "").strip().lstrip("\ufeff") for header in (reader.fieldnames or [])]
        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned = {
                str(header or "").strip().lstrip("\ufeff"): "" if value is None else str(value)
                for header, value in row.items()
                if header is not None
            }
            if any(value.strip() for value in cleaned.values()):
                rows.append(cleaned)
        return headers, rows


def _status_payload_for_path(key: str, path: Path, rows: int) -> dict[str, Any]:
    spec = SOURCE_SPEC_BY_KEY.get(key)
    if spec is not None:
        payload = _source_payload(spec, path, rows)
    else:
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone()
        payload = {
            "key": key,
            "label": key,
            "visible": True,
            "name": path.name,
            "path": str(path),
            "rows": rows,
            "modified_at": modified.isoformat(timespec="seconds"),
        }
    payload["size"] = path.stat().st_size
    payload["size_label"] = _format_size(path.stat().st_size)
    return payload


def parse_kpi_targets(rows: list[dict[str, str]]) -> dict[tuple[str, str], KpiTarget]:
    targets: dict[tuple[str, str], KpiTarget] = {}
    for row in rows:
        company = _row_text(row, "Bolag", "company").strip().upper()
        process = _row_text(row, "Processnamn", "action_id").strip()
        process_key = normalize_process(process)
        if not company or not process_key:
            continue
        metric_targets: dict[str, float] = {}
        metric_points: dict[str, float] = {}
        for metric, aliases in METRIC_TARGET_COLUMNS.items():
            metric_targets[metric] = _row_number(row, *aliases)
        for metric, aliases in METRIC_POINT_COLUMNS.items():
            metric_points[metric] = _row_number(row, *aliases)
            if metric_points[metric] <= 0 and metric_targets.get(metric, 0) > 0:
                metric_points[metric] = 100.0 / metric_targets[metric]
        targets[(company, process_key)] = KpiTarget(
            company=company,
            warehouse=_row_text(row, "Lager", "wareh_num"),
            process=process.strip(),
            description=_row_text(row, "Beskrivning", "description"),
            targets=metric_targets,
            points=metric_points,
        )
    return targets


def _event_user(row: dict[str, str], source: str) -> str:
    if source == "sort":
        return _row_text(row, "AnvÃ¤ndare", "Anvandare", "username", "user_id")
    return _row_text(row, "AnvÃ¤ndare", "Anvandare", "user_id")


def _event_timestamp(row: dict[str, str], source: str) -> datetime | None:
    if source in {"pick", "pallet"}:
        return _timestamp(_row_text(row, "Ã„ndrad", "Andrad", "timestamp"))
    return _timestamp(_row_text(row, "Timestamp", "timestamp", "Ã„ndrad", "Andrad"))


def _event_company(row: dict[str, str], source: str) -> str:
    if source == "sort":
        event = KpiLogEvent(source, "", "", "", datetime.now(), row, 0)
        return _sort_company(event)
    return _row_text(row, "Bolag", "company").strip().upper()


def _event_warehouse(row: dict[str, str], source: str) -> str:
    if source == "sort":
        event = KpiLogEvent(source, "", "", "", datetime.now(), row, 0)
        return _sort_warehouse(event)
    return _row_text(row, "Lager", "wareh_num").strip().upper()


def _events_from_rows(source: str, rows: list[dict[str, str]], report_date: date) -> list[KpiLogEvent]:
    events: list[KpiLogEvent] = []
    for index, row in enumerate(rows):
        user = _event_user(row, source)
        timestamp = _event_timestamp(row, source)
        if not user or timestamp is None or timestamp.date() != report_date:
            continue
        event = KpiLogEvent(
            source=source,
            user=user.strip(),
            company=_event_company(row, source),
            warehouse=_event_warehouse(row, source),
            timestamp=timestamp,
            row=row,
            row_index=index,
        )
        if event.company:
            events.append(event)
    return events


def _rule_applies_for_target(rule: KpiRule, event: KpiLogEvent, targets: dict[tuple[str, str], KpiTarget]) -> KpiTarget | None:
    process_key = rule.process_key
    return targets.get((_company(event), process_key))


def _rule_context(events_by_source: dict[str, list[KpiLogEvent]]) -> dict[str, Any]:
    trans_events = events_by_source.get("trans", [])
    type_66_pall_nums = {
        _pall_num(event, {})
        for event in trans_events
        if _row_int_text(event.row, "Typ", "type") == "66" and _pall_num(event, {})
    }
    return {"trans_type_66_pall_nums": type_66_pall_nums}


def score_kpi_events(
    *,
    rows_by_source: dict[str, list[dict[str, str]]],
    targets: dict[tuple[str, str], KpiTarget],
    rules: Iterable[KpiRule],
    report_date: date,
) -> tuple[list[KpiPointEvent], dict[str, Any]]:
    rules = tuple(rules)
    rule_map = rules_by_process(rules)
    events_by_source = {
        source: _events_from_rows(source, rows, report_date)
        for source, rows in rows_by_source.items()
        if source in EVENT_DATE_SOURCE_KEYS
    }
    context = _rule_context(events_by_source)
    scored: list[KpiPointEvent] = []
    seen_distinct: set[tuple[str, str, str, str, str]] = set()
    missing_rule_processes = sorted(
        {
            target.process
            for (_company_key, process_key), target in targets.items()
            if process_key not in rule_map
        },
        key=str.upper,
    )

    for rule in rules:
        for event in events_by_source.get(rule.source, []):
            if rule.company_override and _company(event) != rule.company_override.upper():
                continue
            target = _rule_applies_for_target(rule, event, targets)
            if target is None:
                continue
            if not rule.predicate(event, context):
                continue
            if rule.distinct_key is not None:
                distinct_value = rule.distinct_key(event, context)
                if not distinct_value:
                    continue
                distinct_key = (_company(event), _warehouse(event), rule.process_key, rule.metric, distinct_value)
                if distinct_key in seen_distinct:
                    continue
                seen_distinct.add(distinct_key)
            value = float(rule.value(event, context) or 0)
            point_per_unit = float(target.points.get(rule.metric) or 0)
            points = value * point_per_unit
            if value <= 0 or points <= 0:
                continue
            scored.append(
                KpiPointEvent(
                    user=event.user,
                    user_key=normalize_name(event.user),
                    company=_company(event),
                    warehouse=_warehouse(event),
                    process=target.process or rule.process,
                    process_key=rule.process_key,
                    metric=rule.metric,
                    value=value,
                    points=points,
                    timestamp=event.timestamp,
                    source=event.source,
                    rule_key=rule.sql_key,
                )
            )

    return scored, {
        "missing_rule_processes": missing_rule_processes,
        "rules": len(rules),
    }
