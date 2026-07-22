"""Schemasegment och personproduktivitetsrapport."""
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

from sqlalchemy import func, or_, select
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
from ..template_service import LOCAL_TIMEZONE, get_template_hours_map_for_dates
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
from .scoring import (  # noqa: F401
    _read_csv_rows,
    _status_payload_for_path,
    parse_kpi_targets,
    _event_user,
    _event_timestamp,
    _event_company,
    _event_warehouse,
    _events_from_rows,
    _rule_applies_for_target,
    _rule_context,
    score_kpi_events,
)


def _minute_of_day(hour: int, minute: int) -> int:
    return int(hour) * 60 + int(minute)


def _time_label(minute_of_day: int) -> str:
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def _covered_intervals(cells: list[ScheduleCell]) -> list[tuple[int, int]]:
    intervals = sorted(
        (
            max(0, int(cell.minute_start)),
            min(60, int(cell.minute_end)),
        )
        for cell in cells
        if cell.activity_id is not None or cell.empty_override
    )
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _uncovered_intervals(covered: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = 0
    for start, end in covered:
        if start > cursor:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < 60:
        result.append((cursor, 60))
    return result


def _segment_kind(activity: Activity | None, processes: list[str], source: str) -> str:
    process_keys = {normalize_process(process) for process in processes}
    if activity is not None and activity.category == "absence":
        return "absence"
    if "ABSENCE" in process_keys:
        return "absence"
    if source == "off":
        return "off"
    if not process_keys or process_keys & {"STOD", "STÃ–D", "SUPPORT"}:
        return "support"
    return "kpi"


def _segment_display(activity: Activity | None, processes: list[str], kind: str) -> str:
    if kind == "absence":
        return "absence"
    if kind == "support":
        return "STÃ–D"
    if kind == "off":
        return "Ledig"
    return ", ".join(processes) or (activity.label if activity is not None else "KPI")


def _activity_segment(
    *,
    hour: int,
    start: int,
    end: int,
    activity: Activity | None,
    source: str,
) -> dict[str, Any]:
    processes = split_process_names(getattr(activity, "kpi_process_name", None))
    kind = _segment_kind(activity, processes, source)
    start_minute = _minute_of_day(hour, start)
    end_minute = _minute_of_day(hour, end)
    area = getattr(activity, "area", None) if activity is not None else None
    return {
        "activity_id": getattr(activity, "id", None),
        "activity_label": getattr(activity, "label", None) or "OkÃ¤nd aktivitet",
        "activity_area_id": getattr(activity, "area_id", None),
        "activity_area_code": getattr(area, "code", None),
        "activity_area_name": getattr(area, "name", None),
        "category": getattr(activity, "category", None),
        "kind": kind,
        "display": _segment_display(activity, processes, kind),
        "processes": processes,
        "process_keys": [normalize_process(process) for process in processes],
        "start": _time_label(start_minute),
        "end": _time_label(end_minute),
        "start_minute": start_minute,
        "end_minute": end_minute,
        "minutes": max(0, end_minute - start_minute),
        "source": source,
        "color": getattr(activity, "color", None),
    }


def _off_segment(hour: int, start: int, end: int) -> dict[str, Any]:
    start_minute = _minute_of_day(hour, start)
    end_minute = _minute_of_day(hour, end)
    return {
        "activity_id": None,
        "activity_label": "Ledig",
        "category": None,
        "kind": "off",
        "display": "Ledig",
        "processes": [],
        "process_keys": [],
        "start": _time_label(start_minute),
        "end": _time_label(end_minute),
        "start_minute": start_minute,
        "end_minute": end_minute,
        "minutes": max(0, end_minute - start_minute),
        "source": "off",
        "color": None,
    }


def _merge_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for segment in sorted(segments, key=lambda item: (item["start_minute"], item["end_minute"], item["display"])):
        if segment["minutes"] <= 0 or segment["kind"] == "off":
            continue
        if (
            merged
            and merged[-1]["end_minute"] == segment["start_minute"]
            and merged[-1]["activity_id"] == segment["activity_id"]
            and merged[-1]["kind"] == segment["kind"]
            and merged[-1]["process_keys"] == segment["process_keys"]
        ):
            merged[-1]["end_minute"] = segment["end_minute"]
            merged[-1]["end"] = segment["end"]
            merged[-1]["minutes"] += segment["minutes"]
        else:
            merged.append(dict(segment))
    return merged


def _find_segment(segments: list[dict[str, Any]], timestamp: datetime) -> dict[str, Any] | None:
    minute = timestamp.hour * 60 + timestamp.minute
    return next((segment for segment in segments if segment["start_minute"] <= minute < segment["end_minute"]), None)


def _event_matches_segment(event: KpiPointEvent, segment: dict[str, Any] | None) -> bool:
    if not segment or segment.get("kind") != "kpi":
        return False
    expected_keys = {normalize_process(process) for process in (segment.get("processes") or [])}
    return event.process_key in expected_keys


def _event_should_warn_as_diff(event: KpiPointEvent, segment: dict[str, Any] | None) -> bool:
    if segment is not None and segment.get("kind") != "kpi":
        return False
    return not _event_matches_segment(event, segment)


def _segment_time_cells(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for segment in segments:
        start = int(segment.get("start_minute") or 0)
        end = int(segment.get("end_minute") or 0)
        current = start
        while current < end:
            next_hour = ((current // 60) + 1) * 60
            cell_end = min(end, next_hour if next_hour > current else current + 60)
            cells.append(
                {
                    "hour": current // 60,
                    "minute_start": current % 60,
                    "minute_end": cell_end % 60 if cell_end % 60 else 60,
                    "start": _time_label(current),
                    "end": _time_label(cell_end),
                    "start_minute": current,
                    "end_minute": cell_end,
                    "minutes": max(0, cell_end - current),
                    "kind": segment.get("kind"),
                    "display": segment.get("display"),
                    "activity_id": segment.get("activity_id"),
                    "activity_label": segment.get("activity_label"),
                    "activity_area_id": segment.get("activity_area_id"),
                    "activity_area_code": segment.get("activity_area_code"),
                    "activity_area_name": segment.get("activity_area_name"),
                    "points": 0.0,
                    "expected_points": round(((cell_end - current) / 60.0) * 100.0, 2)
                    if segment.get("kind") == "kpi"
                    else 0.0,
                    "event_count": 0,
                    "diff_count": 0,
                    "diffs": [],
                    "_process_points": {},
                }
            )
            current = cell_end
    return cells


def _build_time_cells(segments: list[dict[str, Any]], events: list[KpiPointEvent]) -> list[dict[str, Any]]:
    cells = _segment_time_cells(segments)
    for event in events:
        minute = event.timestamp.hour * 60 + event.timestamp.minute
        cell = next((item for item in cells if item["start_minute"] <= minute < item["end_minute"]), None)
        if cell is None:
            continue
        segment = _find_segment(segments, event.timestamp)
        cell["points"] += event.points
        cell["event_count"] += 1
        process_label = event.process or "OkÃ¤nd process"
        process_key = event.process_key or normalize_process(process_label)
        process_points = cell["_process_points"].setdefault(
            process_key,
            {"process": process_label, "process_key": process_key, "points": 0.0, "event_count": 0},
        )
        process_points["points"] += event.points
        process_points["event_count"] += 1
        if _event_should_warn_as_diff(event, segment):
            cell["diff_count"] += 1
            cell["diffs"].append(
                {
                    "time": event.timestamp.isoformat(timespec="minutes"),
                    "scheduled_display": segment.get("display") if segment else "Ej schemalagd",
                    "actual_process": event.process,
                    "company": event.company,
                    "points": round(event.points, 2),
                }
            )
    return [
        {
            **{key: value for key, value in cell.items() if key != "_process_points"},
            "points": round(float(cell["points"]), 2),
            "score_pct": (
                round((float(cell["points"]) / float(cell["expected_points"])) * 100.0, 1)
                if float(cell.get("expected_points") or 0) > 0
                else None
            ),
            "score_status": (
                "low"
                if float(cell.get("expected_points") or 0) > 0
                and (float(cell["points"]) / float(cell["expected_points"])) * 100.0 < 80
                else "warn"
                if float(cell.get("expected_points") or 0) > 0
                and (float(cell["points"]) / float(cell["expected_points"])) * 100.0 < 100
                else "good"
                if float(cell.get("expected_points") or 0) > 0
                else None
            ),
            "process_points": [
                {
                    "process": payload["process"],
                    "process_key": payload["process_key"],
                    "points": round(float(payload["points"]), 2),
                    "event_count": int(payload["event_count"]),
                }
                for payload in sorted(
                    cell["_process_points"].values(),
                    key=lambda item: str(item["process"]).upper(),
                )
            ],
        }
        for cell in cells
    ]


def _planned_process_status(
    segments: list[dict[str, Any]],
    targets: dict[tuple[str, str], KpiTarget],
    rule_map: dict[str, list[KpiRule]],
) -> tuple[list[str], list[str]]:
    missing_targets: set[str] = set()
    missing_rules: set[str] = set()
    target_process_keys = {process_key for _company, process_key in targets}
    for segment in segments:
        if segment["kind"] != "kpi":
            continue
        for process in segment["processes"]:
            process_key = normalize_process(process)
            if process_key not in target_process_keys:
                missing_targets.add(process)
            if process_key not in rule_map:
                missing_rules.add(process)
    return sorted(missing_targets, key=str.upper), sorted(missing_rules, key=str.upper)


def build_schedule_segments(
    db: Session,
    report_date: date,
    *,
    business_id: int | None,
) -> dict[int, dict[str, Any]]:
    # Historik: personer som tagits bort/inaktiverats efter dagen ska ändå
    # ingå i ombyggda historikdagar (t.o.m. idag) om de har celler den dagen,
    # och inaktiverade aktiviteter/områden måste kunna slås upp för etiketter.
    iso_report = report_date.isocalendar()
    person_filter = Person.is_active
    if report_date <= datetime.now(LOCAL_TIMEZONE).date():
        historical_ids = (
            select(ScheduleCell.person_id)
            .where(
                ScheduleCell.year == iso_report.year,
                ScheduleCell.week == iso_report.week,
                ScheduleCell.weekday == iso_report.weekday,
            )
            .distinct()
        )
        person_filter = or_(Person.is_active, Person.id.in_(historical_ids))
    persons_query = (
        select(Person)
        .where(
            person_filter,
            func.trim(func.coalesce(Person.noman, "")) != "",
        )
        .order_by(Person.sort_order, Person.name)
    )
    activities_query = select(Activity).order_by(Activity.sort_order, Activity.label)
    areas_query = select(Area).order_by(Area.sort_order, Area.name)
    if business_id is not None:
        persons_query = persons_query.where(Person.business_id == business_id)
        activities_query = activities_query.where(Activity.business_id == business_id)
        areas_query = areas_query.where(Area.business_id == business_id)

    persons = db.execute(persons_query).scalars().all()
    activities = db.execute(activities_query).scalars().all()
    areas = db.execute(areas_query).scalars().all()
    activities_by_id = {activity.id: activity for activity in activities}
    home_activity_for = build_home_activity_resolver(activities, areas)
    person_ids = [person.id for person in persons]
    iso = report_date.isocalendar()
    template_hours_map = get_template_hours_map_for_dates(db, person_ids, [report_date])

    cells_by_person_hour: dict[tuple[int, int], list[ScheduleCell]] = defaultdict(list)
    if person_ids:
        cells = db.execute(
            select(ScheduleCell).where(
                ScheduleCell.year == iso.year,
                ScheduleCell.week == iso.week,
                ScheduleCell.weekday == iso.weekday,
                ScheduleCell.person_id.in_(person_ids),
            )
        ).scalars().all()
        for cell in cells:
            cells_by_person_hour[(cell.person_id, cell.hour)].append(cell)

    result: dict[int, dict[str, Any]] = {}
    for person in persons:
        segments: list[dict[str, Any]] = []
        home_activity_id = home_activity_for(person)
        template_hours = template_hours_map.get((person.id, report_date))
        for hour in HOURS:
            hour_cells = sorted(cells_by_person_hour.get((person.id, hour), []), key=lambda cell: (cell.minute_start, cell.minute_end))
            for cell in hour_cells:
                if cell.activity_id is not None:
                    segments.append(
                        _activity_segment(
                            hour=hour,
                            start=cell.minute_start,
                            end=cell.minute_end,
                            activity=activities_by_id.get(cell.activity_id),
                            source="registered",
                        )
                    )
                elif cell.empty_override:
                    segments.append(_off_segment(hour, cell.minute_start, cell.minute_end))
            if template_hours is not None and hour in template_hours and home_activity_id is not None:
                covered = _covered_intervals(hour_cells)
                for start, end in _uncovered_intervals(covered):
                    segments.append(
                        _activity_segment(
                            hour=hour,
                            start=start,
                            end=end,
                            activity=activities_by_id.get(home_activity_id),
                            source="default",
                        )
                    )
        result[person.id] = {
            "person": person,
            "segments": _merge_segments(segments),
        }
    return result


def _empty_sync() -> dict[str, Any]:
    return {"source": "fallback", "last_sync_at": None, "next_sync_at": None, "status": "not_configured"}


def _available_dates_from_sources(rows_by_source: dict[str, list[dict[str, str]]]) -> list[date]:
    dates: set[date] = set()
    for source, rows in rows_by_source.items():
        if source not in EVENT_DATE_SOURCE_KEYS:
            continue
        for row in rows:
            timestamp = _event_timestamp(row, source)
            if timestamp is not None:
                dates.add(timestamp.date())
    return sorted(dates)


def build_person_productivity_report_from_files(
    db: Session,
    files: dict[str, Path],
    *,
    report_date: date | str | None = None,
    business_id: int | None = None,
    sync: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requested_date = date.fromisoformat(str(report_date)) if report_date is not None and not isinstance(report_date, date) else report_date

    headers_by_source: dict[str, list[str]] = {}
    rows_by_source: dict[str, list[dict[str, str]]] = {}
    for key, path in files.items():
        if key not in {"pick", "trans", "pallet", "receive", "order_log", "sort", "base_pallet", "kpi"}:
            continue
        headers, rows = _read_csv_rows(Path(path))
        headers_by_source[key] = headers
        rows_by_source[key] = rows

    if "kpi" not in rows_by_source:
        raise ProductivitySourceError("Saknar KPI-mÃ¥l")

    available_dates = _available_dates_from_sources(rows_by_source)
    selected_date = requested_date or (available_dates[-1] if available_dates else date.today())
    if requested_date is not None and available_dates and selected_date not in available_dates:
        raise ProductivitySourceError(f"Saknar produktivitetsdata fÃ¶r {selected_date.isoformat()}")

    targets = parse_kpi_targets(rows_by_source["kpi"])
    kpi_rules, _kpi_logic_source = load_kpi_rules(db, business_id=business_id, files=files, allow_empty=True)
    kpi_rules_by_process = rules_by_process(kpi_rules)
    point_events, event_status = score_kpi_events(
        rows_by_source=rows_by_source,
        targets=targets,
        rules=kpi_rules,
        report_date=selected_date,
    )
    schedule_by_person = build_schedule_segments(db, selected_date, business_id=business_id)
    person_by_noman = {
        normalize_name(data["person"].noman): data["person"]
        for data in schedule_by_person.values()
        if normalize_name(data["person"].noman)
    }
    events_by_person_id: dict[int, list[KpiPointEvent]] = defaultdict(list)
    unmatched_event_count = 0
    for event in point_events:
        person = person_by_noman.get(event.user_key)
        if person is None:
            unmatched_event_count += 1
            continue
        events_by_person_id[person.id].append(event)

    people: list[dict[str, Any]] = []
    total_points = 0.0
    total_planned = 0.0
    total_kpi_minutes = 0
    total_support_minutes = 0
    total_absence_minutes = 0
    diff_count = 0
    missing_target_processes: set[str] = set()
    missing_rule_processes: set[str] = set(event_status.get("missing_rule_processes") or [])

    for person_id, data in schedule_by_person.items():
        person: Person = data["person"]
        segments = data["segments"]
        kpi_minutes = sum(segment["minutes"] for segment in segments if segment["kind"] == "kpi")
        support_minutes = sum(segment["minutes"] for segment in segments if segment["kind"] == "support")
        absence_minutes = sum(segment["minutes"] for segment in segments if segment["kind"] == "absence")
        if kpi_minutes <= 0 and support_minutes <= 0:
            continue
        planned_points = (kpi_minutes / 60.0) * 100.0
        person_points = 0.0
        diffs: list[dict[str, Any]] = []

        person_missing_targets, person_missing_rules = _planned_process_status(segments, targets, kpi_rules_by_process)
        missing_target_processes.update(person_missing_targets)
        missing_rule_processes.update(person_missing_rules)

        person_events = sorted(events_by_person_id.get(person_id, []), key=lambda item: item.timestamp)
        for event in person_events:
            person_points += event.points
            segment = _find_segment(segments, event.timestamp)
            expected = list(segment.get("processes") or []) if segment else []
            if not _event_should_warn_as_diff(event, segment):
                continue
            diffs.append(
                {
                    "time": event.timestamp.isoformat(timespec="minutes"),
                    "scheduled_activity": segment.get("activity_label") if segment else "Ej schemalagd",
                    "scheduled_display": segment.get("display") if segment else "Ej schemalagd",
                    "scheduled_processes": expected,
                    "actual_process": event.process,
                    "company": event.company,
                    "warehouse": event.warehouse,
                    "points": round(event.points, 2),
                    "source": event.source,
                }
            )

        productivity_pct = person_points / planned_points if planned_points > 0 else None
        total_points += person_points
        total_planned += planned_points
        total_kpi_minutes += kpi_minutes
        total_support_minutes += support_minutes
        total_absence_minutes += absence_minutes
        diff_count += len(diffs)
        people.append(
            {
                "person_id": person.id,
                "name": person.name,
                "home_area": getattr(person.home_area, "name", None),
                "productivity_pct": productivity_pct,
                "kpi_points": round(person_points, 2),
                "planned_kpi_points": round(planned_points, 2),
                "kpi_minutes": kpi_minutes,
                "support_minutes": support_minutes,
                "absence_minutes": absence_minutes,
                "segments": [
                    {key: value for key, value in segment.items() if key != "process_keys"}
                    for segment in segments
                ],
                "time_cells": _build_time_cells(segments, person_events),
                "diffs": diffs,
                "missing_target_processes": person_missing_targets,
                "missing_rule_processes": person_missing_rules,
            }
        )

    productivity_values = [
        person["productivity_pct"]
        for person in people
        if person["productivity_pct"] is not None
    ]
    sources = {
        key: _status_payload_for_path(key, Path(files[key]), len(rows_by_source.get(key, [])))
        for key in sorted(rows_by_source)
        if key in files
    }
    return {
        "generated_at": datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds"),
        "date": selected_date.isoformat(),
        "available_dates": [item.isoformat() for item in available_dates] or [selected_date.isoformat()],
        "hours": list(HOURS),
        "sources": sources,
        "people": people,
        "summary": {
            "people": len(people),
            "kpi_points": round(total_points, 2),
            "planned_kpi_points": round(total_planned, 2),
            "kpi_minutes": total_kpi_minutes,
            "support_minutes": total_support_minutes,
            "absence_minutes": total_absence_minutes,
            "average_productivity_pct": total_points / total_planned if total_planned > 0 else None,
            "person_average_productivity_pct": (
                sum(productivity_values) / len(productivity_values)
                if productivity_values
                else None
            ),
            "diff_count": diff_count,
            "unmatched_event_count": unmatched_event_count,
            "missing_target_processes": sorted(missing_target_processes, key=str.upper),
            "missing_rule_processes": sorted(missing_rule_processes, key=str.upper),
            "scored_event_count": len(point_events),
        },
        "sync": sync or _empty_sync(),
    }
