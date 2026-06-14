from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code, user_business_id, visible_business_id
from .models import Activity, Business, Person, PersonProductivityDaily, User
from .person_productivity_cache import (
    PRODUCTIVITY_CACHE_ROW_CELL,
    PRODUCTIVITY_CACHE_ROW_PROCESS,
    ensure_person_productivity_daily_cache,
)
from .productivity_kpi_rules import (
    KpiRule,
    build_schedule_segments,
    load_kpi_rules,
    normalize_name,
    normalize_process,
    parse_kpi_targets,
    rules_by_process,
    score_kpi_events,
    split_process_names,
)
from .productivity_service import _read_csv_rows_with_headers
from .productivity_sync import (
    LOCAL_TZ,
    ProductivitySyncError,
    ensure_productivity_snapshot,
    productivity_snapshot_files,
    productivity_snapshot_root,
    productivity_snapshot_status,
)
from .settings_service import get_staffing_activity_capacity_activity_ids, get_staffing_history_hours
from .workflow_data import WorkflowDataError, fetch_source_to_temp


STAFFING_CALCULATOR_PROFILE_VERSION = 1
STAFFING_CALCULATOR_HISTORY_DAYS = 90
STAFFING_OUTPUT_METRIC_PRIORITY = ("rows", "packages", "pallets", "orders")
STAFFING_OUTPUT_METRIC_LABELS = {
    "rows": "rader",
    "packages": "paket",
    "pallets": "pallar",
    "orders": "order",
}


def empty_staffing_calculator_profile() -> dict[str, Any]:
    return {"version": STAFFING_CALCULATOR_PROFILE_VERSION, "calculators": []}


def _clean_text(value: Any, max_length: int = 120) -> str:
    return str(value or "").strip()[:max_length]


def _clean_calculator_id(value: Any) -> str:
    cleaned = "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in {"-", "_"})
    return cleaned[:80] or f"calc-{uuid4().hex[:12]}"


def normalize_staffing_calculator_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return empty_staffing_calculator_profile()
    result = empty_staffing_calculator_profile()
    seen_ids: set[str] = set()
    for item in profile.get("calculators") or []:
        if not isinstance(item, dict):
            continue
        calc_id = _clean_calculator_id(item.get("id"))
        while calc_id in seen_ids:
            calc_id = f"{calc_id}-{uuid4().hex[:4]}"
        seen_ids.add(calc_id)
        name = _clean_text(item.get("name"), 80)
        process = _clean_text(item.get("process"), 120)
        company = _clean_text(item.get("company"), 40).upper()
        zone = _clean_text(item.get("zone"), 40).upper()
        try:
            pick_days = int(str(item.get("pick_days", 0)).strip() or 0)
        except (TypeError, ValueError):
            pick_days = 0
        pick_days = max(-31, min(31, pick_days))
        if not name or not process or not company or not zone:
            continue
        result["calculators"].append(
            {
                "id": calc_id,
                "name": name,
                "process": process,
                "company": company,
                "zone": zone,
                "pick_days": pick_days,
            }
        )
    return result


def staffing_calculator_profile_count(profile: Any) -> int:
    return len(normalize_staffing_calculator_profile(profile).get("calculators") or [])


def staffing_process_options(db: Session, user: User) -> list[dict[str, str]]:
    business_id = visible_business_id(db, user, None)
    query = select(Activity).where(Activity.is_active.is_(True))
    if business_id is not None:
        query = query.where(Activity.business_id == business_id)
    activities = db.execute(query.order_by(Activity.sort_order, Activity.label)).scalars().all()
    by_key: dict[str, str] = {}
    for activity in activities:
        for process in split_process_names(getattr(activity, "kpi_process_name", None)):
            key = normalize_process(process)
            if key in {"", "STOD", "STÖD", "SUPPORT", "ABSENCE"}:
                continue
            by_key.setdefault(key, process)
    return [{"value": value, "label": value} for _key, value in sorted(by_key.items(), key=lambda item: item[1].upper())]


def staffing_output_metric_label(metric: str | None) -> str:
    return STAFFING_OUTPUT_METRIC_LABELS.get(str(metric or "").strip().lower(), str(metric or "").strip() or "enheter")


def _staffing_rule_business_id(db: Session, user: User, business_id: int | None) -> int | None:
    return business_id if business_id is not None else user_business_id(db, user)


def _productivity_business_code(db: Session, user: User) -> str:
    try:
        business_id = user_business_id(db, user)
        business = db.get(Business, business_id) if business_id is not None else None
        return normalize_business_code(getattr(business, "code", None)) or DEFAULT_BUSINESS_CODE
    except Exception:
        return DEFAULT_BUSINESS_CODE


def primary_metric_for_process(
    process_key: str,
    targets: dict[tuple[str, str], Any] | None = None,
    *,
    rules: Iterable[KpiRule] | None = None,
) -> str | None:
    key = normalize_process(process_key)
    if not key:
        return None
    rule_metrics = {rule.metric for rule in rules_by_process(rules or ()).get(key, [])}
    target_metrics: set[str] = set()
    if targets:
        for (_company, target_process_key), target in targets.items():
            if normalize_process(target_process_key) != key:
                continue
            for metric in STAFFING_OUTPUT_METRIC_PRIORITY:
                target_value = float((getattr(target, "targets", {}) or {}).get(metric) or 0)
                point_value = float((getattr(target, "points", {}) or {}).get(metric) or 0)
                if target_value > 0 or point_value > 0:
                    target_metrics.add(metric)

    candidates = (rule_metrics & target_metrics) or rule_metrics or target_metrics
    for metric in STAFFING_OUTPUT_METRIC_PRIORITY:
        if metric in candidates:
            return metric
    return sorted(candidates)[0] if candidates else None


def _row_value(row: dict[str, Any], *names: str) -> str:
    lowered = {str(key).strip().lower(): key for key in row}
    for name in names:
        actual = lowered.get(str(name).strip().lower())
        if actual is not None:
            return str(row.get(actual) or "").strip()
    return ""


def _parse_number(value: Any) -> float | None:
    text = str(value or "").strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) >= 10:
        for candidate in (text[:10], text.replace("/", "-")[:10]):
            try:
                return date.fromisoformat(candidate)
            except ValueError:
                pass
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 8:
        for fmt in ("%Y%m%d", "%d%m%Y"):
            try:
                return datetime.strptime(digits, fmt).date()
            except ValueError:
                pass
    return None


def _order_row_matches(row: dict[str, Any], *, company: str, zone: str, order_date: date) -> bool:
    status = _parse_number(_row_value(row, "line_status", "Status", "status"))
    if status is None or status >= 34:
        return False
    row_company = _row_value(row, "company", "Bolag", "bolag").upper()
    if row_company != company.upper():
        return False
    row_zone = _row_value(row, "pick_zone", "Zon", "zon").upper()
    if row_zone != zone.upper():
        return False
    row_date = _parse_date(_row_value(row, "order_date", "Orderdatum", "orderdatum"))
    return row_date == order_date


def order_filter_date(pick_days: int, *, today: date | None = None) -> date:
    base = today or datetime.now(LOCAL_TZ).date()
    return base - timedelta(days=int(pick_days))


def fetch_filtered_order_row_count(calculator: dict[str, Any], *, today: date | None = None) -> tuple[int, dict[str, Any]]:
    target_date = order_filter_date(int(calculator.get("pick_days") or 0), today=today)
    filters = [
        {"id": "line_status", "value": 34, "operator": "LT"},
        {"id": "company", "value": calculator["company"], "operator": "EQ"},
        {"id": "pick_zone", "value": calculator["zone"], "operator": "EQ"},
        {"id": "order_date", "value": target_date.isoformat(), "operator": "EQ"},
    ]
    path: Path | None = None
    try:
        path, entry = fetch_source_to_temp("orders", filters=filters)
        _headers, rows = _read_csv_rows_with_headers(path)
        count = sum(
            1
            for row in rows
            if _order_row_matches(
                row,
                company=str(calculator["company"]),
                zone=str(calculator["zone"]),
                order_date=target_date,
            )
        )
        return count, {
            "order_date": target_date.isoformat(),
            "source": entry.status,
            "source_rows": entry.row_count,
            "filters": {"company": calculator["company"], "zone": calculator["zone"], "line_status": "<34"},
        }
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def _selected_date(year: int, week: int, weekday: int) -> date:
    return date.fromisocalendar(int(year), int(week), int(weekday))


def _next_half_hour_cutoff(now: datetime) -> int:
    minute_of_day = now.hour * 60 + now.minute
    if now.second or now.microsecond:
        minute_of_day += 1
    remainder = minute_of_day % 30
    if remainder:
        minute_of_day += 30 - remainder
    return minute_of_day


def remaining_cutoff_minute(selected_date: date, *, now: datetime | None = None) -> int:
    current = now.astimezone(LOCAL_TZ) if now is not None else datetime.now(LOCAL_TZ)
    today = current.date()
    if selected_date < today:
        return 24 * 60
    if selected_date > today:
        return 6 * 60
    return _next_half_hour_cutoff(current)


def _segment_matches_process(segment: dict[str, Any], process_key: str) -> bool:
    return process_key in {str(key).upper() for key in (segment.get("process_keys") or [])}


def remaining_process_minutes_by_person(
    db: Session,
    *,
    selected_date: date,
    process_key: str,
    business_id: int | None,
    now: datetime | None = None,
) -> dict[int, int]:
    cutoff = remaining_cutoff_minute(selected_date, now=now)
    result: dict[int, int] = {}
    schedule_by_person = build_schedule_segments(db, selected_date, business_id=business_id)
    for person_id, data in schedule_by_person.items():
        minutes = 0
        for segment in data.get("segments") or []:
            if not _segment_matches_process(segment, process_key):
                continue
            start = int(segment.get("start_minute") or 0)
            end = int(segment.get("end_minute") or 0)
            minutes += max(0, end - max(start, cutoff))
        if minutes > 0:
            result[int(person_id)] = minutes
    return result


def _snapshot_dates_before(selected_date: date, *, max_days: int = STAFFING_CALCULATOR_HISTORY_DAYS) -> list[date]:
    root = productivity_snapshot_root()
    dates: list[date] = []
    if root.is_dir():
        for path in root.iterdir():
            if not path.is_dir():
                continue
            try:
                day = date.fromisoformat(path.name)
            except ValueError:
                continue
            if day < selected_date:
                dates.append(day)
    if not dates:
        dates = [selected_date - timedelta(days=offset) for offset in range(1, max_days + 1)]
    return sorted([day for day in dates if day < selected_date], reverse=True)[:max_days]


def _rows_by_source_for_snapshot(day: date) -> dict[str, list[dict[str, str]]]:
    status = productivity_snapshot_status(day)
    if not status.get("ready"):
        return {}
    files = productivity_snapshot_files(day)
    rows_by_source: dict[str, list[dict[str, str]]] = {}
    for key, path in files.items():
        compressed = str(path).endswith(".gz")
        _headers, rows = _read_csv_rows_with_headers(path, compressed=compressed)
        rows_by_source[key] = rows
    return rows_by_source


def _rows_for_snapshot_source(day: date, source_key: str) -> list[dict[str, str]]:
    status = productivity_snapshot_status(day)
    if not status.get("ready"):
        return []
    files = productivity_snapshot_files(day)
    path = files.get(source_key)
    if path is None:
        return []
    compressed = str(path).endswith(".gz")
    _headers, rows = _read_csv_rows_with_headers(path, compressed=compressed)
    return rows


def _latest_primary_metrics_for_processes(
    process_keys: set[str],
    selected_date: date,
    *,
    rules: Iterable[KpiRule],
) -> dict[str, str]:
    normalized_keys = {normalize_process(key) for key in process_keys if normalize_process(key)}
    result: dict[str, str] = {}
    if not normalized_keys:
        return result

    for day in _snapshot_dates_before(selected_date):
        missing = normalized_keys - set(result)
        if not missing:
            break
        kpi_rows = _rows_for_snapshot_source(day, "kpi")
        if not kpi_rows:
            continue
        targets = parse_kpi_targets(kpi_rows)
        for process_key in missing:
            metric = primary_metric_for_process(process_key, targets, rules=rules)
            if metric:
                result[process_key] = metric

    for process_key in normalized_keys - set(result):
        result[process_key] = primary_metric_for_process(process_key, rules=rules) or "rows"
    return result


def historical_output_per_hour_by_person_process(
    db: Session,
    *,
    selected_date: date,
    process_keys: set[str],
    person_ids: set[int],
    business_id: int | None,
    primary_metrics_by_process: dict[str, str] | None = None,
) -> dict[int, dict[str, dict[str, float | str]]]:
    normalized_process_keys = {normalize_process(key) for key in process_keys if normalize_process(key)}
    if not person_ids or not normalized_process_keys:
        return {}
    rules, _rule_source = load_kpi_rules(db, business_id=business_id)
    history_hours = get_staffing_history_hours(db, business_id=business_id)
    metric_by_process = {
        normalize_process(key): str(metric or "").strip().lower()
        for key, metric in (primary_metrics_by_process or {}).items()
        if normalize_process(key) and str(metric or "").strip()
    }
    for process_key in normalized_process_keys - set(metric_by_process):
        metric_by_process[process_key] = primary_metric_for_process(process_key, rules=rules) or "rows"

    buckets: dict[int, dict[str, dict[str, float]]] = {
        person_id: {
            process_key: {"units": 0.0, "hours": 0.0}
            for process_key in normalized_process_keys
        }
        for person_id in person_ids
    }

    for day in _snapshot_dates_before(selected_date):
        if all(
            payload["hours"] >= history_hours
            for person_payload in buckets.values()
            for payload in person_payload.values()
        ):
            break
        sync_status = productivity_snapshot_status(day)
        if not sync_status.get("ready"):
            continue
        ensure_person_productivity_daily_cache(
            db,
            productivity_snapshot_files(day),
            report_date=day,
            business_id=business_id,
            sync=sync_status,
        )
        metrics = {metric for metric in metric_by_process.values() if metric}
        rows = db.execute(
            select(PersonProductivityDaily).where(
                PersonProductivityDaily.snapshot_date == day,
                PersonProductivityDaily.row_type == PRODUCTIVITY_CACHE_ROW_PROCESS,
                PersonProductivityDaily.person_id.in_(person_ids),
                PersonProductivityDaily.process_key.in_(normalized_process_keys),
                PersonProductivityDaily.metric.in_(metrics or {"rows"}),
            )
        ).scalars().all()
        for row in rows:
            process_key = normalize_process(row.process_key)
            if process_key not in normalized_process_keys:
                continue
            if str(row.metric or "").strip().lower() != metric_by_process.get(process_key):
                continue
            person_id = int(row.person_id)
            minutes = int(row.kpi_minutes or 0)
            if minutes <= 0:
                continue
            bucket = buckets[person_id][process_key]
            remaining_hours = history_hours - float(bucket["hours"])
            if remaining_hours <= 0:
                continue
            hours = minutes / 60.0
            used_hours = min(hours, remaining_hours)
            ratio = used_hours / hours if hours > 0 else 0
            bucket["hours"] += used_hours
            bucket["units"] += float(row.units or 0.0) * ratio

    return {
        person_id: {
            process_key: {
                **payload,
                "units_per_hour": (payload["units"] / payload["hours"]) if payload["hours"] > 0 else 0.0,
                "metric": metric_by_process.get(process_key, "rows"),
                "unit": staffing_output_metric_label(metric_by_process.get(process_key, "rows")),
            }
            for process_key, payload in process_payload.items()
        }
        for person_id, process_payload in buckets.items()
    }


def historical_rows_per_hour_by_person(
    db: Session,
    *,
    selected_date: date,
    process_key: str,
    person_ids: set[int],
    business_id: int | None,
) -> dict[int, dict[str, float]]:
    normalized_process_key = normalize_process(process_key)
    rates = historical_output_per_hour_by_person_process(
        db,
        selected_date=selected_date,
        process_keys={normalized_process_key},
        person_ids=person_ids,
        business_id=business_id,
        primary_metrics_by_process={normalized_process_key: "rows"},
    )
    return {
        person_id: {
            "rows": float((rates.get(person_id, {}).get(normalized_process_key) or {}).get("units") or 0.0),
            "hours": float((rates.get(person_id, {}).get(normalized_process_key) or {}).get("hours") or 0.0),
            "rows_per_hour": float(
                (rates.get(person_id, {}).get(normalized_process_key) or {}).get("units_per_hour") or 0.0
            ),
        }
        for person_id in person_ids
    }


def schedule_activity_capacity(
    db: Session,
    user: User,
    *,
    year: int,
    week: int,
    weekday: int,
) -> dict[str, Any]:
    selected = _selected_date(year, week, weekday)
    business_id = visible_business_id(db, user, None)
    rule_business_id = _staffing_rule_business_id(db, user, business_id)

    persons_query = select(Person).where(Person.is_active.is_(True))
    activities_query = select(Activity).where(Activity.is_active.is_(True))
    if business_id is not None:
        persons_query = persons_query.where(Person.business_id == business_id)
        activities_query = activities_query.where(Activity.business_id == business_id)
    persons = [
        person
        for person in db.execute(persons_query.order_by(Person.sort_order, Person.name)).scalars().all()
        if normalize_name(person.noman)
    ]
    activities = [
        activity
        for activity in db.execute(activities_query.order_by(Activity.sort_order, Activity.label)).scalars().all()
        if str(activity.category or "") != "absence" and split_process_names(activity.kpi_process_name)
    ]

    activity_processes: dict[int, list[str]] = {}
    process_labels: dict[str, str] = {}
    process_keys: set[str] = set()
    for activity in activities:
        keys: list[str] = []
        for process in split_process_names(activity.kpi_process_name):
            key = normalize_process(process)
            if not key:
                continue
            keys.append(key)
            process_keys.add(key)
            process_labels.setdefault(key, process)
        if keys:
            activity_processes[int(activity.id)] = keys

    rules, _rule_source = load_kpi_rules(db, business_id=rule_business_id)
    primary_metrics = _latest_primary_metrics_for_processes(process_keys, selected, rules=rules)
    history_hours = get_staffing_history_hours(db, business_id=rule_business_id)
    visible_activity_ids = get_staffing_activity_capacity_activity_ids(db, business_id=rule_business_id)
    visible_activity_id_set = set(visible_activity_ids) if visible_activity_ids is not None else None
    if visible_activity_id_set is not None:
        activities = [activity for activity in activities if int(activity.id) in visible_activity_id_set]
        process_keys = {
            process_key
            for activity in activities
            for process_key in activity_processes.get(int(activity.id), [])
        }
        primary_metrics = _latest_primary_metrics_for_processes(process_keys, selected, rules=rules)
    rates = historical_output_per_hour_by_person_process(
        db,
        selected_date=selected,
        process_keys=process_keys,
        person_ids={int(person.id) for person in persons},
        business_id=rule_business_id,
        primary_metrics_by_process=primary_metrics,
    )

    people: dict[str, dict[str, dict[str, Any]]] = {}
    activities_payload: dict[str, dict[str, Any]] = {}
    for activity in activities:
        keys = activity_processes.get(int(activity.id), [])
        if not keys:
            continue
        primary_key = keys[0]
        primary_metric = primary_metrics.get(primary_key, "rows")
        activities_payload[str(activity.id)] = {
            "activity_id": int(activity.id),
            "activity_label": activity.label,
            "process_key": primary_key,
            "process": process_labels.get(primary_key, primary_key),
            "metric": primary_metric,
            "unit": staffing_output_metric_label(primary_metric),
        }

    for person in persons:
        person_payload: dict[str, dict[str, Any]] = {}
        person_rates = rates.get(int(person.id), {})
        for activity in activities:
            chosen_key: str | None = None
            chosen_rate: dict[str, float | str] | None = None
            for process_key in activity_processes.get(int(activity.id), []):
                rate = person_rates.get(process_key)
                if rate and float(rate.get("units_per_hour") or 0) > 0:
                    chosen_key = process_key
                    chosen_rate = rate
                    break
            if chosen_key is None or chosen_rate is None:
                continue
            value_per_hour = float(chosen_rate.get("units_per_hour") or 0.0)
            person_payload[str(activity.id)] = {
                "activity_id": int(activity.id),
                "activity_label": activity.label,
                "process_key": chosen_key,
                "process": process_labels.get(chosen_key, chosen_key),
                "metric": chosen_rate.get("metric") or primary_metrics.get(chosen_key, "rows"),
                "unit": chosen_rate.get("unit")
                or staffing_output_metric_label(str(chosen_rate.get("metric") or primary_metrics.get(chosen_key, "rows"))),
                "value_per_hour": round(value_per_hour, 1),
                "hours": round(float(chosen_rate.get("hours") or 0.0), 2),
                "units": round(float(chosen_rate.get("units") or 0.0), 1),
            }
        if person_payload:
            people[str(person.id)] = person_payload

    return {
        "date": selected.isoformat(),
        "generated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "history_hours": history_hours,
        "visible_activity_ids": visible_activity_ids,
        "metric_labels": STAFFING_OUTPUT_METRIC_LABELS,
        "activities": activities_payload,
        "people": people,
    }


def schedule_activity_capacity_cell(
    db: Session,
    user: User,
    *,
    year: int,
    week: int,
    weekday: int,
    person_id: int,
    activity_id: int,
) -> dict[str, Any]:
    selected = _selected_date(year, week, weekday)
    business_id = visible_business_id(db, user, None)
    rule_business_id = _staffing_rule_business_id(db, user, business_id)

    person_query = select(Person).where(Person.id == person_id, Person.is_active.is_(True))
    activity_query = select(Activity).where(Activity.id == activity_id, Activity.is_active.is_(True))
    if business_id is not None:
        person_query = person_query.where(Person.business_id == business_id)
        activity_query = activity_query.where(Activity.business_id == business_id)
    person = db.execute(person_query).scalar_one_or_none()
    activity = db.execute(activity_query).scalar_one_or_none()

    base_payload: dict[str, Any] = {
        "date": selected.isoformat(),
        "generated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "person_id": person_id,
        "activity_id": activity_id,
        "activity_label": getattr(activity, "label", "") if activity else "",
        "history_hours": get_staffing_history_hours(db, business_id=rule_business_id),
        "capacity": None,
    }
    if person is None or not normalize_name(person.noman):
        return {**base_payload, "reason": "person_missing"}
    if activity is None:
        return {**base_payload, "reason": "activity_missing"}
    if str(activity.category or "") == "absence":
        return {**base_payload, "reason": "activity_without_kpi"}

    visible_activity_ids = get_staffing_activity_capacity_activity_ids(db, business_id=rule_business_id)
    if visible_activity_ids is not None and int(activity.id) not in set(visible_activity_ids):
        return {**base_payload, "reason": "activity_hidden"}

    process_labels: dict[str, str] = {}
    process_keys: list[str] = []
    for process in split_process_names(activity.kpi_process_name):
        key = normalize_process(process)
        if not key:
            continue
        process_keys.append(key)
        process_labels.setdefault(key, process)
    if not process_keys:
        return {**base_payload, "reason": "activity_without_kpi"}

    rules, _rule_source = load_kpi_rules(db, business_id=rule_business_id)
    primary_metrics = _latest_primary_metrics_for_processes(set(process_keys), selected, rules=rules)
    rates = historical_output_per_hour_by_person_process(
        db,
        selected_date=selected,
        process_keys=set(process_keys),
        person_ids={int(person.id)},
        business_id=rule_business_id,
        primary_metrics_by_process=primary_metrics,
    )
    person_rates = rates.get(int(person.id), {})
    for process_key in process_keys:
        rate = person_rates.get(process_key)
        if not rate or float(rate.get("units_per_hour") or 0) <= 0:
            continue
        metric = str(rate.get("metric") or primary_metrics.get(process_key, "rows"))
        return {
            **base_payload,
            "reason": "",
            "capacity": {
                "activity_id": int(activity.id),
                "activity_label": activity.label,
                "process_key": process_key,
                "process": process_labels.get(process_key, process_key),
                "metric": metric,
                "unit": rate.get("unit") or staffing_output_metric_label(metric),
                "value_per_hour": round(float(rate.get("units_per_hour") or 0.0), 1),
                "hours": round(float(rate.get("hours") or 0.0), 2),
                "units": round(float(rate.get("units") or 0.0), 1),
            },
        }

    return {**base_payload, "reason": "no_history"}


def _completed_productivity_cutoff_minute(selected_date: date, now: datetime | None = None) -> int:
    current = now.astimezone(LOCAL_TZ) if now else datetime.now(LOCAL_TZ)
    if selected_date != current.date():
        return 24 * 60
    return current.hour * 60


def schedule_productivity_summary(
    db: Session,
    user: User,
    *,
    year: int,
    week: int,
    weekday: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    selected = _selected_date(year, week, weekday)
    business_id = visible_business_id(db, user, None)
    rule_business_id = _staffing_rule_business_id(db, user, business_id)
    try:
        sync_status = ensure_productivity_snapshot(
            selected,
            business_code=_productivity_business_code(db, user),
            db=db,
            user_id=getattr(user, "id", None),
            wait_seconds=10,
        )
        cache_status = ensure_person_productivity_daily_cache(
            db,
            productivity_snapshot_files(selected),
            report_date=selected,
            business_id=rule_business_id,
            sync=sync_status,
        )
    except ProductivitySyncError as exc:
        sync_status = productivity_snapshot_status(selected)
        cache_status = {
            "status": "source_unavailable",
            "ready": False,
            "message": str(exc),
            "sync": sync_status,
        }
    cutoff = _completed_productivity_cutoff_minute(selected, now=now)
    query = select(PersonProductivityDaily).where(
        PersonProductivityDaily.snapshot_date == selected,
        PersonProductivityDaily.row_type == PRODUCTIVITY_CACHE_ROW_CELL,
        PersonProductivityDaily.kind == "kpi",
        PersonProductivityDaily.end_minute <= cutoff,
    )
    if business_id is not None:
        query = query.where(PersonProductivityDaily.business_id == business_id)
    rows = db.execute(query).scalars().all()

    buckets: dict[int, dict[str, float | int]] = defaultdict(lambda: {"points": 0.0, "planned": 0.0, "minutes": 0})
    for row in rows:
        expected = float(row.planned_kpi_points or 0.0)
        if expected <= 0:
            continue
        bucket = buckets[int(row.person_id)]
        bucket["points"] = float(bucket["points"]) + float(row.kpi_points or 0.0)
        bucket["planned"] = float(bucket["planned"]) + expected
        bucket["minutes"] = int(bucket["minutes"]) + int(row.kpi_minutes or 0)

    people: dict[str, dict[str, Any]] = {}
    for person_id, bucket in buckets.items():
        planned = float(bucket["planned"] or 0.0)
        if planned <= 0:
            continue
        points = float(bucket["points"] or 0.0)
        people[str(person_id)] = {
            "person_id": person_id,
            "percent": int((points / planned) * 100),
            "productivity_pct": points / planned,
            "kpi_points": round(points, 2),
            "planned_kpi_points": round(planned, 2),
            "kpi_minutes": int(bucket["minutes"] or 0),
        }

    return {
        "date": selected.isoformat(),
        "generated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "cutoff_minute": cutoff,
        "cache": cache_status,
        "people": people,
    }


def calculate_staffing_automatic(
    db: Session,
    user: User,
    profile: dict[str, Any],
    *,
    year: int,
    week: int,
    weekday: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized = normalize_staffing_calculator_profile(profile)
    selected = _selected_date(year, week, weekday)
    business_id = visible_business_id(db, user, None)
    rule_business_id = _staffing_rule_business_id(db, user, business_id)
    rows: list[dict[str, Any]] = []

    for calculator in normalized.get("calculators") or []:
        process_key = normalize_process(calculator["process"])
        result: dict[str, Any] = {
            "id": calculator["id"],
            "name": calculator["name"],
            "process": calculator["process"],
            "status": "ok",
            "message": "",
        }
        try:
            order_rows, source = fetch_filtered_order_row_count(
                calculator,
                today=(now.astimezone(LOCAL_TZ).date() if now else None),
            )
            remaining_minutes = remaining_process_minutes_by_person(
                db,
                selected_date=selected,
                process_key=process_key,
                business_id=business_id,
                now=now,
            )
            rates = historical_rows_per_hour_by_person(
                db,
                selected_date=selected,
                process_key=process_key,
                person_ids=set(remaining_minutes),
                business_id=rule_business_id,
            )
            expected_rows = 0.0
            missing_average_count = 0
            people_count = 0
            for person_id, minutes in remaining_minutes.items():
                hours = minutes / 60.0
                rate = float((rates.get(person_id) or {}).get("rows_per_hour") or 0.0)
                if rate <= 0:
                    missing_average_count += 1
                else:
                    people_count += 1
                expected_rows += hours * rate
            scheduled_hours = sum(remaining_minutes.values()) / 60.0
            result.update(
                {
                    "order_rows": int(order_rows),
                    "scheduled_hours": round(scheduled_hours, 2),
                    "expected_rows": round(expected_rows, 1),
                    "rows_remaining_after_schedule": round(order_rows - expected_rows, 1),
                    "people_with_time": len(remaining_minutes),
                    "people_with_average": people_count,
                    "missing_average_count": missing_average_count,
                    "source": source,
                }
            )
        except (WorkflowDataError, RuntimeError, OSError, ValueError) as exc:
            result.update(
                {
                    "status": "error",
                    "message": str(exc),
                    "order_rows": None,
                    "scheduled_hours": None,
                    "expected_rows": None,
                    "rows_remaining_after_schedule": None,
                    "people_with_time": 0,
                    "people_with_average": 0,
                    "missing_average_count": 0,
                    "source": {},
                }
            )
        rows.append(result)

    return {
        "date": selected.isoformat(),
        "generated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "calculators": rows,
    }
