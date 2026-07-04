from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Activity, Area, Person, PersonProductivityDaily, ScheduleCell
from .productivity_kpi_rules import (
    KpiRule,
    build_person_productivity_report_from_files,
    build_schedule_segments,
    load_kpi_rules,
    normalize_name,
    normalize_process,
    parse_kpi_targets,
    rules_by_process,
    score_kpi_events,
)
from .productivity_service import _read_csv_rows_with_headers


PRODUCTIVITY_CACHE_ROW_PERSON = "person"
PRODUCTIVITY_CACHE_ROW_CELL = "cell"
PRODUCTIVITY_CACHE_ROW_CELL_PROCESS = "cell_process"
PRODUCTIVITY_CACHE_ROW_ACTIVITY = "activity"
PRODUCTIVITY_CACHE_ROW_PROCESS = "process"
PRODUCTIVITY_CACHE_METRIC_PRIORITY = ("rows", "packages", "pallets", "orders")
PRODUCTIVITY_CACHE_METRIC_LABELS = {
    "rows": "rader",
    "packages": "paket",
    "pallets": "pallar",
    "orders": "order",
    "points": "poang",
}


def productivity_metric_label(metric: str | None) -> str:
    value = str(metric or "").strip().lower()
    return PRODUCTIVITY_CACHE_METRIC_LABELS.get(value, value or "enheter")


def productivity_cache_schedule_signature(db: Session, snapshot_date: date, *, business_id: int | None) -> str:
    iso = snapshot_date.isocalendar()
    query = (
        select(
            func.count(ScheduleCell.id),
            func.max(ScheduleCell.updated_at),
            func.coalesce(func.sum(ScheduleCell.version), 0),
        )
        .select_from(ScheduleCell)
        .join(Person, Person.id == ScheduleCell.person_id)
        .where(
            ScheduleCell.year == iso.year,
            ScheduleCell.week == iso.week,
            ScheduleCell.weekday == iso.weekday,
        )
    )
    if business_id is not None:
        query = query.where(Person.business_id == business_id)
    count, updated_at, version_sum = db.execute(query).one()
    updated = updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at or "")
    return f"{int(count or 0)}:{updated}:{int(version_sum or 0)}"


def productivity_snapshot_signature(sync: dict[str, Any] | None) -> str:
    if not sync:
        return ""
    return str(sync.get("last_sync_at") or sync.get("date") or "")


def _cache_query(db: Session, snapshot_date: date, business_id: int | None):
    query = db.query(PersonProductivityDaily).filter(PersonProductivityDaily.snapshot_date == snapshot_date)
    if business_id is None:
        return query
    return query.filter(PersonProductivityDaily.business_id == business_id)


def person_productivity_cache_is_current(
    db: Session,
    snapshot_date: date,
    *,
    business_id: int | None,
    sync: dict[str, Any] | None,
) -> bool:
    row = (
        _cache_query(db, snapshot_date, business_id)
        .filter(PersonProductivityDaily.row_type == PRODUCTIVITY_CACHE_ROW_PERSON)
        .order_by(PersonProductivityDaily.calculated_at.desc())
        .first()
    )
    if row is None:
        return False
    return (
        (row.source_snapshot_at or "") == productivity_snapshot_signature(sync)
        and (row.schedule_signature or "") == productivity_cache_schedule_signature(db, snapshot_date, business_id=business_id)
    )


def person_productivity_daily_report_if_current(
    db: Session,
    snapshot_date: date,
    *,
    business_id: int | None,
    person_id: int,
    sync: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not person_productivity_cache_is_current(db, snapshot_date, business_id=business_id, sync=sync):
        return None

    rows = (
        _cache_query(db, snapshot_date, business_id)
        .filter(PersonProductivityDaily.person_id == person_id)
        .order_by(
            PersonProductivityDaily.row_type.asc(),
            PersonProductivityDaily.start_minute.asc(),
            PersonProductivityDaily.item_key.asc(),
        )
        .all()
    )
    person_rows = [row for row in rows if row.row_type == PRODUCTIVITY_CACHE_ROW_PERSON]
    cell_rows = [row for row in rows if row.row_type == PRODUCTIVITY_CACHE_ROW_CELL]
    if not rows:
        return {"date": snapshot_date.isoformat(), "people": []}

    person_row = person_rows[0] if person_rows else None
    time_cells: list[dict[str, Any]] = []
    for row in cell_rows:
        kind = str(row.kind or "")
        minutes = row.kpi_minutes
        if kind == "support":
            minutes = row.support_minutes
        elif kind == "absence":
            minutes = row.absence_minutes
        time_cells.append(
            {
                "kind": kind,
                "activity_id": row.activity_id,
                "activity_label": row.activity_label,
                "display": row.activity_label or row.process_label or "",
                "start_minute": row.start_minute,
                "end_minute": row.end_minute,
                "points": row.kpi_points,
                "expected_points": row.planned_kpi_points,
                "minutes": minutes,
                "event_count": row.event_count,
                "diff_count": row.diff_count,
            }
        )

    return {
        "date": snapshot_date.isoformat(),
        "people": [
            {
                "person_id": person_id,
                "kpi_points": person_row.kpi_points if person_row else sum(row.kpi_points for row in cell_rows),
                "planned_kpi_points": person_row.planned_kpi_points
                if person_row
                else sum(row.planned_kpi_points for row in cell_rows),
                "kpi_minutes": person_row.kpi_minutes if person_row else sum(row.kpi_minutes for row in cell_rows),
                "support_minutes": person_row.support_minutes if person_row else sum(row.support_minutes for row in cell_rows),
                "absence_minutes": person_row.absence_minutes if person_row else sum(row.absence_minutes for row in cell_rows),
                "time_cells": time_cells,
            }
        ],
    }


def _time_label_from_minute(minute: int | None) -> str:
    value = max(0, min(24 * 60, int(minute or 0)))
    return f"{value // 60:02d}:{value % 60:02d}"


def _cell_minutes_from_cache_row(row: PersonProductivityDaily) -> int:
    kind = str(row.kind or "")
    if kind == "support":
        return int(row.support_minutes or 0)
    if kind == "absence":
        return int(row.absence_minutes or 0)
    return int(row.kpi_minutes or 0)


def _cell_score_pct(points: float, planned_points: float) -> float | None:
    if planned_points <= 0:
        return None
    return round((points / planned_points) * 100.0, 1)


def _cell_score_status(points: float, planned_points: float) -> str | None:
    pct = _cell_score_pct(points, planned_points)
    if pct is None:
        return None
    if pct < 80:
        return "low"
    if pct < 100:
        return "warn"
    return "good"


def _person_cache_metadata(db: Session, person_ids: set[int]) -> dict[int, dict[str, Any]]:
    if not person_ids:
        return {}
    rows = (
        db.execute(
            select(Person.id, Person.name, Person.collar_type, Area.name)
            .select_from(Person)
            .outerjoin(Area, Person.home_area_id == Area.id)
            .where(Person.id.in_(person_ids))
        )
        .all()
    )
    return {
        int(person_id): {
            "name": name,
            "collar_type": collar_type,
            "home_area": home_area,
        }
        for person_id, name, collar_type, home_area in rows
    }


def _activity_cache_metadata(db: Session, activity_ids: set[int]) -> dict[int, dict[str, Any]]:
    if not activity_ids:
        return {}
    rows = (
        db.execute(
            select(Activity.id, Activity.area_id, Activity.label, Area.code, Area.name)
            .select_from(Activity)
            .outerjoin(Area, Activity.area_id == Area.id)
            .where(Activity.id.in_(activity_ids))
        )
        .all()
    )
    return {
        int(activity_id): {
            "activity_area_id": area_id,
            "activity_label": label,
            "activity_area_code": area_code,
            "activity_area_name": area_name,
        }
        for activity_id, area_id, label, area_code, area_name in rows
    }


def person_productivity_daily_full_report_if_current(
    db: Session,
    snapshot_date: date,
    *,
    business_id: int | None,
    sync: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not person_productivity_cache_is_current(db, snapshot_date, business_id=business_id, sync=sync):
        return None

    rows = (
        _cache_query(db, snapshot_date, business_id)
        .filter(
            PersonProductivityDaily.row_type.in_(
                (
                    PRODUCTIVITY_CACHE_ROW_PERSON,
                    PRODUCTIVITY_CACHE_ROW_CELL,
                    PRODUCTIVITY_CACHE_ROW_CELL_PROCESS,
                )
            )
        )
        .order_by(
            PersonProductivityDaily.person_id.asc(),
            PersonProductivityDaily.row_type.asc(),
            PersonProductivityDaily.start_minute.asc(),
            PersonProductivityDaily.item_key.asc(),
        )
        .all()
    )
    if not rows:
        return {
            "date": snapshot_date.isoformat(),
            "available_dates": [snapshot_date.isoformat()],
            "people": [],
            "summary": {
                "people": 0,
                "kpi_points": 0.0,
                "planned_kpi_points": 0.0,
                "kpi_minutes": 0,
                "support_minutes": 0,
                "absence_minutes": 0,
                "average_productivity_pct": None,
                "person_average_productivity_pct": None,
                "diff_count": 0,
                "unmatched_event_count": 0,
                "missing_target_processes": [],
                "missing_rule_processes": [],
                "scored_event_count": 0,
            },
            "cache": {"source": "person_productivity_daily"},
        }

    person_ids = {int(row.person_id) for row in rows if row.person_id is not None}
    activity_ids = {int(row.activity_id) for row in rows if row.activity_id is not None}
    person_meta = _person_cache_metadata(db, person_ids)
    activity_meta = _activity_cache_metadata(db, activity_ids)
    person_rows: dict[int, PersonProductivityDaily] = {}
    cell_rows_by_person: dict[int, list[PersonProductivityDaily]] = defaultdict(list)
    process_rows_by_cell: dict[tuple[int, str], list[PersonProductivityDaily]] = defaultdict(list)

    for row in rows:
        person_id = int(row.person_id)
        if row.row_type == PRODUCTIVITY_CACHE_ROW_PERSON:
            person_rows[person_id] = row
        elif row.row_type == PRODUCTIVITY_CACHE_ROW_CELL:
            cell_rows_by_person[person_id].append(row)
        elif row.row_type == PRODUCTIVITY_CACHE_ROW_CELL_PROCESS:
            cell_key = str(row.item_key or "").split(":process:", 1)[0]
            process_rows_by_cell[(person_id, cell_key)].append(row)

    people: list[dict[str, Any]] = []
    total_points = 0.0
    total_planned = 0.0
    total_kpi_minutes = 0
    total_support_minutes = 0
    total_absence_minutes = 0
    total_diff_count = 0
    total_scored_events = 0
    productivity_values: list[float] = []

    for person_id in sorted(person_ids):
        person_row = person_rows.get(person_id)
        meta = person_meta.get(person_id, {})
        time_cells: list[dict[str, Any]] = []
        for row in sorted(cell_rows_by_person.get(person_id, []), key=lambda item: (item.start_minute or 0, item.item_key or "")):
            activity = activity_meta.get(int(row.activity_id)) if row.activity_id is not None else {}
            points = float(row.kpi_points or 0.0)
            planned = float(row.planned_kpi_points or 0.0)
            start_minute = int(row.start_minute or 0)
            end_minute = int(row.end_minute or start_minute)
            process_points = [
                {
                    "process": process_row.process_label or process_row.process_key or "Poang",
                    "process_key": process_row.process_key or normalize_process(process_row.process_label),
                    "points": round(float(process_row.kpi_points or 0.0), 2),
                    "event_count": int(process_row.event_count or 0),
                }
                for process_row in process_rows_by_cell.get((person_id, str(row.item_key or "")), [])
                if float(process_row.kpi_points or 0.0) != 0
            ]
            time_cells.append(
                {
                    "hour": start_minute // 60,
                    "minute_start": start_minute % 60,
                    "minute_end": end_minute % 60 if end_minute % 60 else 60,
                    "start": _time_label_from_minute(start_minute),
                    "end": _time_label_from_minute(end_minute),
                    "start_minute": start_minute,
                    "end_minute": end_minute,
                    "kind": str(row.kind or ""),
                    "display": row.activity_label or activity.get("activity_label") or row.process_label or "",
                    "activity_id": row.activity_id,
                    "activity_label": row.activity_label or activity.get("activity_label") or "",
                    "activity_area_id": activity.get("activity_area_id"),
                    "activity_area_code": activity.get("activity_area_code"),
                    "activity_area_name": activity.get("activity_area_name"),
                    "points": round(points, 2),
                    "expected_points": round(planned, 2),
                    "minutes": _cell_minutes_from_cache_row(row),
                    "event_count": int(row.event_count or 0),
                    "diff_count": int(row.diff_count or 0),
                    "diffs": [],
                    "score_pct": _cell_score_pct(points, planned),
                    "score_status": _cell_score_status(points, planned),
                    "process_points": process_points,
                }
            )

        person_points = float(person_row.kpi_points or 0.0) if person_row else sum(float(row.kpi_points or 0.0) for row in cell_rows_by_person.get(person_id, []))
        person_planned = float(person_row.planned_kpi_points or 0.0) if person_row else sum(float(row.planned_kpi_points or 0.0) for row in cell_rows_by_person.get(person_id, []))
        person_kpi_minutes = int(person_row.kpi_minutes or 0) if person_row else sum(int(row.kpi_minutes or 0) for row in cell_rows_by_person.get(person_id, []))
        person_support_minutes = int(person_row.support_minutes or 0) if person_row else sum(int(row.support_minutes or 0) for row in cell_rows_by_person.get(person_id, []))
        person_absence_minutes = int(person_row.absence_minutes or 0) if person_row else sum(int(row.absence_minutes or 0) for row in cell_rows_by_person.get(person_id, []))
        person_diff_count = int(person_row.diff_count or 0) if person_row else sum(int(row.diff_count or 0) for row in cell_rows_by_person.get(person_id, []))
        productivity_pct = person_points / person_planned if person_planned > 0 else None
        if productivity_pct is not None:
            productivity_values.append(productivity_pct)
        total_points += person_points
        total_planned += person_planned
        total_kpi_minutes += person_kpi_minutes
        total_support_minutes += person_support_minutes
        total_absence_minutes += person_absence_minutes
        total_diff_count += person_diff_count
        total_scored_events += sum(int(row.event_count or 0) for row in cell_rows_by_person.get(person_id, []))
        people.append(
            {
                "person_id": person_id,
                "name": meta.get("name") or str(person_id),
                "home_area": meta.get("home_area"),
                "collar_type": meta.get("collar_type"),
                "productivity_pct": productivity_pct,
                "kpi_points": round(person_points, 2),
                "planned_kpi_points": round(person_planned, 2),
                "kpi_minutes": person_kpi_minutes,
                "support_minutes": person_support_minutes,
                "absence_minutes": person_absence_minutes,
                "segments": [],
                "time_cells": time_cells,
                "diffs": [],
                "missing_target_processes": [],
                "missing_rule_processes": [],
            }
        )

    return {
        "generated_at": datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds"),
        "date": snapshot_date.isoformat(),
        "available_dates": [snapshot_date.isoformat()],
        "sources": {},
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
            "diff_count": total_diff_count,
            "unmatched_event_count": 0,
            "missing_target_processes": [],
            "missing_rule_processes": [],
            "scored_event_count": total_scored_events,
        },
        "cache": {"source": "person_productivity_daily"},
    }


def person_productivity_period_stats_if_current(
    db: Session,
    snapshot_dates: list[date],
    *,
    business_id: int | None,
    person_id: int,
    sync_by_date: dict[date, dict[str, Any]],
) -> dict[str, Any] | None:
    dates = sorted(set(snapshot_dates))
    if not dates:
        return {
            "dates": [],
            "activities": [],
            "summary": {
                "days_with_data": 0,
                "days_with_activity": 0,
                "kpi_points": 0,
                "planned_kpi_points": 0,
                "productivity_pct": None,
                "points_per_hour": None,
                "kpi_minutes": 0,
                "kpi_hours": 0,
                "support_minutes": 0,
                "absence_minutes": 0,
                "event_count": 0,
                "diff_count": 0,
            },
        }

    for snapshot_date in dates:
        if not person_productivity_cache_is_current(
            db,
            snapshot_date,
            business_id=business_id,
            sync=sync_by_date.get(snapshot_date),
        ):
            return None

    base_filters = [
        PersonProductivityDaily.snapshot_date.in_(dates),
        PersonProductivityDaily.person_id == person_id,
    ]
    if business_id is not None:
        base_filters.append(PersonProductivityDaily.business_id == business_id)

    person_summary = db.execute(
        select(
            func.count(func.distinct(PersonProductivityDaily.snapshot_date)),
            func.coalesce(func.sum(PersonProductivityDaily.support_minutes), 0),
            func.coalesce(func.sum(PersonProductivityDaily.absence_minutes), 0),
        ).where(
            *base_filters,
            PersonProductivityDaily.row_type == PRODUCTIVITY_CACHE_ROW_PERSON,
        )
    ).one()
    days_with_data = int(person_summary[0] or 0)
    support_minutes = int(person_summary[1] or 0)
    absence_minutes = int(person_summary[2] or 0)

    # Ingen strangliteral i uttrycket: SQL Server tillater inte bindparametrar
    # i GROUP BY (pyodbc parametriserar; pymssql interpolerar klientside, darfor
    # bet felet bara i deployade miljon). NULL-fallbacken gors i Python nedan.
    activity_label = func.coalesce(
        PersonProductivityDaily.activity_label,
        PersonProductivityDaily.process_label,
    )
    activity_rows = db.execute(
        select(
            activity_label.label("activity"),
            func.coalesce(func.sum(PersonProductivityDaily.kpi_points), 0),
            func.coalesce(func.sum(PersonProductivityDaily.planned_kpi_points), 0),
            func.coalesce(func.sum(PersonProductivityDaily.kpi_minutes), 0),
            func.count(PersonProductivityDaily.id),
            func.coalesce(func.sum(PersonProductivityDaily.event_count), 0),
            func.coalesce(func.sum(PersonProductivityDaily.diff_count), 0),
        )
        .where(
            *base_filters,
            PersonProductivityDaily.row_type == PRODUCTIVITY_CACHE_ROW_CELL,
            PersonProductivityDaily.kind == "kpi",
            PersonProductivityDaily.planned_kpi_points > 0,
        )
        .group_by(activity_label)
    ).all()

    activities: list[dict[str, float | int | str | None]] = []
    total_points = 0.0
    total_planned = 0.0
    total_minutes = 0
    event_count = 0
    diff_count = 0
    for row in activity_rows:
        points = float(row[1] or 0)
        planned = float(row[2] or 0)
        minutes = int(row[3] or 0)
        periods = int(row[4] or 0)
        events = int(row[5] or 0)
        diffs = int(row[6] or 0)
        hours = minutes / 60.0 if minutes else 0.0
        total_points += points
        total_planned += planned
        total_minutes += minutes
        event_count += events
        diff_count += diffs
        activities.append(
            {
                "activity": str(row[0] or "Okand aktivitet"),
                "productivity_pct": points / planned if planned > 0 else None,
                "points_per_hour": points / hours if hours > 0 else None,
                "kpi_points": round(points, 2),
                "planned_kpi_points": round(planned, 2),
                "kpi_minutes": minutes,
                "kpi_hours": round(hours, 2),
                "periods": periods,
                "event_count": events,
                "diff_count": diffs,
            }
        )

    activities.sort(key=lambda item: (-float(item["kpi_minutes"] or 0), str(item["activity"]).upper()))
    total_hours = total_minutes / 60.0 if total_minutes else 0.0
    days_with_activity = int(
        db.execute(
            select(func.count(func.distinct(PersonProductivityDaily.snapshot_date))).where(
                *base_filters,
                PersonProductivityDaily.row_type == PRODUCTIVITY_CACHE_ROW_CELL,
                PersonProductivityDaily.kind == "kpi",
                PersonProductivityDaily.planned_kpi_points > 0,
            )
        ).scalar()
        or 0
    )
    used_dates = db.execute(
        select(PersonProductivityDaily.snapshot_date)
        .where(
            *base_filters,
            PersonProductivityDaily.row_type == PRODUCTIVITY_CACHE_ROW_PERSON,
        )
        .distinct()
        .order_by(PersonProductivityDaily.snapshot_date.asc())
    ).scalars().all()
    return {
        "dates": [item.isoformat() for item in used_dates],
        "activities": activities,
        "summary": {
            "days_with_data": days_with_data,
            "days_with_activity": days_with_activity,
            "kpi_points": round(total_points, 2),
            "planned_kpi_points": round(total_planned, 2),
            "productivity_pct": total_points / total_planned if total_planned > 0 else None,
            "points_per_hour": total_points / total_hours if total_hours > 0 else None,
            "kpi_minutes": total_minutes,
            "kpi_hours": round(total_hours, 2),
            "support_minutes": support_minutes,
            "absence_minutes": absence_minutes,
            "event_count": event_count,
            "diff_count": diff_count,
        },
    }


def _read_rows_by_source(files: dict[str, Path]) -> dict[str, list[dict[str, str]]]:
    rows_by_source: dict[str, list[dict[str, str]]] = {}
    for key, path in files.items():
        if key not in {"pick", "trans", "pallet", "receive", "order_log", "sort", "base_pallet", "kpi"}:
            continue
        _headers, rows = _read_csv_rows_with_headers(Path(path), compressed=str(path).endswith(".gz"))
        rows_by_source[key] = rows
    return rows_by_source


def _rule_metrics_by_process(rules: Iterable[KpiRule]) -> dict[str, set[str]]:
    return {
        process_key: {str(rule.metric or "").strip().lower() for rule in process_rules if str(rule.metric or "").strip()}
        for process_key, process_rules in rules_by_process(rules).items()
    }


def _preferred_metric(metrics: set[str]) -> str:
    for metric in PRODUCTIVITY_CACHE_METRIC_PRIORITY:
        if metric in metrics:
            return metric
    return sorted(metrics)[0] if metrics else "rows"


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _person_business_map(db: Session, person_ids: Iterable[int]) -> dict[int, int | None]:
    ids = {int(person_id) for person_id in person_ids}
    if not ids:
        return {}
    rows = db.execute(select(Person.id, Person.business_id).where(Person.id.in_(ids))).all()
    return {int(person_id): business_id for person_id, business_id in rows}


def _build_activity_rows(
    person_id: int,
    business_id: int | None,
    snapshot_date: date,
    person_payload: dict[str, Any],
    *,
    source_snapshot_at: str,
    schedule_signature: str,
) -> list[PersonProductivityDaily]:
    buckets: dict[str, dict[str, Any]] = {}
    for cell in person_payload.get("time_cells") or []:
        if cell.get("kind") != "kpi":
            continue
        expected = _float(cell.get("expected_points"))
        if expected <= 0:
            continue
        activity_id = cell.get("activity_id")
        activity_label = str(cell.get("activity_label") or cell.get("display") or "Okand aktivitet")
        key = f"activity:{activity_id}" if activity_id is not None else f"activity-label:{activity_label}"
        bucket = buckets.setdefault(
            key,
            {
                "activity_id": activity_id,
                "activity_label": activity_label,
                "points": 0.0,
                "planned": 0.0,
                "minutes": 0,
                "events": 0,
                "diffs": 0,
            },
        )
        bucket["points"] += _float(cell.get("points"))
        bucket["planned"] += expected
        bucket["minutes"] += _int(cell.get("minutes"))
        bucket["events"] += _int(cell.get("event_count"))
        bucket["diffs"] += _int(cell.get("diff_count"))

    rows: list[PersonProductivityDaily] = []
    for key, bucket in buckets.items():
        rows.append(
            PersonProductivityDaily(
                business_id=business_id,
                snapshot_date=snapshot_date,
                person_id=person_id,
                row_type=PRODUCTIVITY_CACHE_ROW_ACTIVITY,
                item_key=key,
                metric="points",
                unit=productivity_metric_label("points"),
                activity_id=bucket.get("activity_id"),
                activity_label=str(bucket.get("activity_label") or ""),
                kpi_points=float(bucket["points"]),
                planned_kpi_points=float(bucket["planned"]),
                kpi_minutes=int(bucket["minutes"]),
                units=float(bucket["points"]),
                event_count=int(bucket["events"]),
                diff_count=int(bucket["diffs"]),
                source_snapshot_at=source_snapshot_at,
                schedule_signature=schedule_signature,
            )
        )
    return rows


def _build_report_rows(
    db: Session,
    report: dict[str, Any],
    snapshot_date: date,
    *,
    business_id: int | None,
    source_snapshot_at: str,
    schedule_signature: str,
) -> list[PersonProductivityDaily]:
    person_ids = [int(person.get("person_id") or 0) for person in report.get("people") or [] if person.get("person_id")]
    person_business = _person_business_map(db, person_ids)
    rows: list[PersonProductivityDaily] = []
    for person_payload in report.get("people") or []:
        person_id = int(person_payload.get("person_id") or 0)
        if person_id <= 0:
            continue
        row_business_id = person_business.get(person_id, business_id)
        rows.append(
            PersonProductivityDaily(
                business_id=row_business_id,
                snapshot_date=snapshot_date,
                person_id=person_id,
                row_type=PRODUCTIVITY_CACHE_ROW_PERSON,
                item_key="person",
                metric="points",
                unit=productivity_metric_label("points"),
                kpi_points=_float(person_payload.get("kpi_points")),
                planned_kpi_points=_float(person_payload.get("planned_kpi_points")),
                kpi_minutes=_int(person_payload.get("kpi_minutes")),
                support_minutes=_int(person_payload.get("support_minutes")),
                absence_minutes=_int(person_payload.get("absence_minutes")),
                units=_float(person_payload.get("kpi_points")),
                event_count=sum(_int(cell.get("event_count")) for cell in person_payload.get("time_cells") or []),
                diff_count=len(person_payload.get("diffs") or []),
                source_snapshot_at=source_snapshot_at,
                schedule_signature=schedule_signature,
            )
        )
        for cell in person_payload.get("time_cells") or []:
            start_minute = _int(cell.get("start_minute"))
            end_minute = _int(cell.get("end_minute"))
            activity_id = cell.get("activity_id")
            activity_label = str(cell.get("activity_label") or cell.get("display") or "")
            cell_key = f"cell:{start_minute}:{end_minute}:{activity_id if activity_id is not None else activity_label}"
            rows.append(
                PersonProductivityDaily(
                    business_id=row_business_id,
                    snapshot_date=snapshot_date,
                    person_id=person_id,
                    row_type=PRODUCTIVITY_CACHE_ROW_CELL,
                    item_key=cell_key,
                    metric="points",
                    unit=productivity_metric_label("points"),
                    activity_id=activity_id,
                    activity_label=activity_label,
                    kind=str(cell.get("kind") or ""),
                    start_minute=start_minute,
                    end_minute=end_minute,
                    kpi_points=_float(cell.get("points")),
                    planned_kpi_points=_float(cell.get("expected_points")),
                    kpi_minutes=_int(cell.get("minutes")) if cell.get("kind") == "kpi" else 0,
                    support_minutes=_int(cell.get("minutes")) if cell.get("kind") == "support" else 0,
                    absence_minutes=_int(cell.get("minutes")) if cell.get("kind") == "absence" else 0,
                    units=_float(cell.get("points")),
                    event_count=_int(cell.get("event_count")),
                    diff_count=_int(cell.get("diff_count")),
                    source_snapshot_at=source_snapshot_at,
                    schedule_signature=schedule_signature,
                )
            )
            for process_point in cell.get("process_points") or []:
                process_label = str(process_point.get("process") or "Poang")
                process_key = normalize_process(process_point.get("process_key") or process_label)
                if not process_key:
                    continue
                rows.append(
                    PersonProductivityDaily(
                        business_id=row_business_id,
                        snapshot_date=snapshot_date,
                        person_id=person_id,
                        row_type=PRODUCTIVITY_CACHE_ROW_CELL_PROCESS,
                        item_key=f"{cell_key}:process:{process_key}",
                        metric="points",
                        unit=productivity_metric_label("points"),
                        activity_id=activity_id,
                        activity_label=activity_label,
                        process_key=process_key,
                        process_label=process_label,
                        kind=str(cell.get("kind") or ""),
                        start_minute=start_minute,
                        end_minute=end_minute,
                        kpi_points=_float(process_point.get("points")),
                        units=_float(process_point.get("points")),
                        event_count=_int(process_point.get("event_count")),
                        source_snapshot_at=source_snapshot_at,
                        schedule_signature=schedule_signature,
                    )
                )
        rows.extend(
            _build_activity_rows(
                person_id,
                row_business_id,
                snapshot_date,
                person_payload,
                source_snapshot_at=source_snapshot_at,
                schedule_signature=schedule_signature,
            )
        )
    return rows


def _build_process_rows(
    db: Session,
    files: dict[str, Path],
    snapshot_date: date,
    *,
    business_id: int | None,
    source_snapshot_at: str,
    schedule_signature: str,
) -> list[PersonProductivityDaily]:
    rows_by_source = _read_rows_by_source(files)
    if "kpi" not in rows_by_source:
        return []
    targets = parse_kpi_targets(rows_by_source["kpi"])
    rules, _rule_source = load_kpi_rules(db, business_id=business_id, files=files, allow_empty=True)
    rule_metrics = _rule_metrics_by_process(rules)
    point_events, _status = score_kpi_events(
        rows_by_source=rows_by_source,
        targets=targets,
        rules=rules,
        report_date=snapshot_date,
    )
    schedule_by_person = build_schedule_segments(db, snapshot_date, business_id=business_id)
    person_by_noman = {
        normalize_name(data["person"].noman): int(person_id)
        for person_id, data in schedule_by_person.items()
        if normalize_name(data["person"].noman)
    }
    process_labels: dict[str, str] = {}
    process_minutes: dict[tuple[int, str], int] = defaultdict(int)
    person_business = {
        int(person_id): getattr(data["person"], "business_id", business_id)
        for person_id, data in schedule_by_person.items()
    }
    for person_id, data in schedule_by_person.items():
        for segment in data.get("segments") or []:
            if segment.get("kind") != "kpi":
                continue
            process_names = list(segment.get("processes") or [])
            process_keys = [normalize_process(process) for process in process_names if normalize_process(process)]
            for index, process_key in enumerate(process_keys):
                process_minutes[(int(person_id), process_key)] += _int(segment.get("minutes"))
                process_labels.setdefault(process_key, process_names[index] if index < len(process_names) else process_key)

    process_units: dict[tuple[int, str, str], dict[str, float | int]] = defaultdict(lambda: {"units": 0.0, "points": 0.0, "events": 0})
    for event in point_events:
        person_id = person_by_noman.get(event.user_key)
        process_key = normalize_process(event.process_key)
        metric = str(event.metric or "").strip().lower()
        if person_id is None or not process_key or not metric:
            continue
        process_labels.setdefault(process_key, event.process or process_key)
        bucket = process_units[(int(person_id), process_key, metric)]
        bucket["units"] = float(bucket["units"]) + float(event.value or 0)
        bucket["points"] = float(bucket["points"]) + float(event.points or 0)
        bucket["events"] = int(bucket["events"]) + 1

    rows: list[PersonProductivityDaily] = []
    for (person_id, process_key), minutes in process_minutes.items():
        metrics = set(rule_metrics.get(process_key) or ())
        metrics.update(metric for (event_person_id, event_process_key, metric) in process_units if event_person_id == person_id and event_process_key == process_key)
        if not metrics:
            metrics = {_preferred_metric(set())}
        for metric in metrics:
            payload = process_units.get((person_id, process_key, metric), {"units": 0.0, "points": 0.0, "events": 0})
            rows.append(
                PersonProductivityDaily(
                    business_id=person_business.get(person_id, business_id),
                    snapshot_date=snapshot_date,
                    person_id=person_id,
                    row_type=PRODUCTIVITY_CACHE_ROW_PROCESS,
                    item_key=f"process:{process_key}",
                    metric=metric,
                    unit=productivity_metric_label(metric),
                    process_key=process_key,
                    process_label=process_labels.get(process_key, process_key),
                    kpi_points=float(payload.get("points") or 0),
                    planned_kpi_points=(minutes / 60.0) * 100.0,
                    kpi_minutes=int(minutes),
                    units=float(payload.get("units") or 0),
                    event_count=int(payload.get("events") or 0),
                    source_snapshot_at=source_snapshot_at,
                    schedule_signature=schedule_signature,
                )
            )
    return rows


def materialize_person_productivity_daily(
    db: Session,
    files: dict[str, Path],
    *,
    report_date: date,
    business_id: int | None,
    sync: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_snapshot_at = productivity_snapshot_signature(sync)
    schedule_signature = productivity_cache_schedule_signature(db, report_date, business_id=business_id)
    report_payload = report or build_person_productivity_report_from_files(
        db,
        files,
        report_date=report_date,
        business_id=business_id,
        sync=sync,
    )
    rows = _build_report_rows(
        db,
        report_payload,
        report_date,
        business_id=business_id,
        source_snapshot_at=source_snapshot_at,
        schedule_signature=schedule_signature,
    )
    rows.extend(
        _build_process_rows(
            db,
            files,
            report_date,
            business_id=business_id,
            source_snapshot_at=source_snapshot_at,
            schedule_signature=schedule_signature,
        )
    )
    _cache_query(db, report_date, business_id).delete(synchronize_session=False)
    if rows:
        db.add_all(rows)
    db.commit()
    return {
        "date": report_date.isoformat(),
        "status": "materialized",
        "rows": len(rows),
        "calculated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def ensure_person_productivity_daily_cache(
    db: Session,
    files: dict[str, Path],
    *,
    report_date: date,
    business_id: int | None,
    sync: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not force and person_productivity_cache_is_current(db, report_date, business_id=business_id, sync=sync):
        return {"date": report_date.isoformat(), "status": "current", "rows": 0}
    return materialize_person_productivity_daily(
        db,
        files,
        report_date=report_date,
        business_id=business_id,
        sync=sync,
        report=report,
    )
