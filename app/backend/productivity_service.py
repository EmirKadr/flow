from __future__ import annotations

import csv
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import settings


HOURS = tuple(range(6, 24))


class ProductivitySourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceFileSpec:
    key: str
    label: str
    prefix: str
    required: bool = True
    visible: bool = True


@dataclass(frozen=True)
class SectionSpec:
    id: str
    group_id: str
    title: str
    source: str
    process: str
    target_company: str
    target_metric: str
    total_source: str
    predicate: Callable[[dict[str, Any]], bool]


SOURCE_SPECS = (
    SourceFileSpec("pick", "Plocklogg", "v_ask_pick_log_full"),
    SourceFileSpec("trans", "Translogg", "v_ask_trans_log"),
    SourceFileSpec("pallet", "Palllastningslogg", "v_ask_palletloading_log"),
    SourceFileSpec("kpi", "KPI-Mål", "v_ask_kpi_target", required=True, visible=False),
)

SOURCE_SPEC_BY_KEY = {spec.key: spec for spec in SOURCE_SPECS}
VISIBLE_SOURCE_SPECS = tuple(spec for spec in SOURCE_SPECS if spec.visible)

HEADER_HINTS = {
    "pick": {"Zon", "Plockat", "Användare", "Ändrad", "Bolag"},
    "trans": {"Pallid", "Från", "Till", "Antal", "Timestamp"},
    "pallet": {"Plockpallsnr.", "Palltyp", "Pallplacering", "Transnr.", "Vikt"},
    "kpi": {"Flödesnamn", "Processnamn", "Beskrivning", "Rader", "Kollin"},
}

GROUPS = (
    {"id": "gg", "title": "Granngården"},
    {"id": "autostore", "title": "Autostore och e-handel"},
    {"id": "mg", "title": "Mestergruppen"},
)

GROUP_TITLES = {group["id"]: group["title"] for group in GROUPS}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_reference_dir() -> Path:
    configured_data_dir = (settings.PRODUCTIVITY_DATA_DIR or "").strip()
    if configured_data_dir:
        return Path(configured_data_dir)
    configured = (settings.PRODUCTIVITY_REFERENCE_DIR or "").strip()
    if configured:
        return Path(configured)
    return _repo_root() / "data"


def _latest_file(reference_dir: Path, prefix: str) -> Path:
    matches = [
        path
        for path in reference_dir.glob(f"{prefix}*.csv")
        if path.is_file() and not path.name.startswith("~$")
    ]
    if not matches:
        raise ProductivitySourceError(f"Saknar referensfil med prefix {prefix} i {reference_dir}")
    return max(matches, key=lambda path: (path.stat().st_mtime_ns, path.name))


def find_source_files(reference_dir: Path) -> dict[str, Path]:
    if not reference_dir.exists():
        raise ProductivitySourceError(f"Produktivitetsmappen finns inte: {reference_dir}")
    return {spec.key: _latest_file(reference_dir, spec.prefix) for spec in SOURCE_SPECS}


def _try_find_file(reference_dir: Path, prefix: str) -> Path | None:
    try:
        return _latest_file(reference_dir, prefix)
    except ProductivitySourceError:
        return None


def _detect_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters="\t;,")
    except csv.Error:
        class Fallback(csv.excel):
            delimiter = "\t" if sample.count("\t") >= sample.count(";") else ";"

        return Fallback


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        dialect = _detect_dialect(sample)
        return list(csv.DictReader(handle, dialect=dialect))


def _iter_csv_values(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        dialect = _detect_dialect(sample)
        reader = csv.reader(handle, dialect=dialect)
        try:
            headers = next(reader)
        except StopIteration:
            return
        lookup = {
            str(header).strip().lstrip("\ufeff").lower(): index
            for index, header in enumerate(headers)
        }
        for values in reader:
            yield lookup, values


def _cell(values: list[str], lookup: dict[str, int], *names: str) -> str:
    for name in names:
        index = lookup.get(name.lower())
        if index is not None and index < len(values):
            return str(values[index]).strip()
    return ""


def _decode_sample(sample: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return sample.decode(encoding)
        except UnicodeDecodeError:
            continue
    return sample.decode("utf-8", errors="replace")


def _headers_from_sample(sample: bytes) -> set[str]:
    text = _decode_sample(sample)
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return set()
    dialect = _detect_dialect(first_line)
    return {value.strip().strip('"') for value in next(csv.reader([first_line], dialect=dialect), [])}


def classify_productivity_file(filename: str | None, sample: bytes = b"") -> str | None:
    name = Path(filename or "").name.lower()
    for spec in SOURCE_SPECS:
        if name.startswith(spec.prefix.lower()):
            return spec.key

    headers = _headers_from_sample(sample)
    if not headers:
        return None
    normalized = {header.lower() for header in headers}
    for key, hints in HEADER_HINTS.items():
        if {hint.lower() for hint in hints}.issubset(normalized):
            return key
    return None


def _safe_upload_name(filename: str | None, spec: SourceFileSpec) -> str:
    original = Path(filename or "").name
    suffix = Path(original).suffix.lower()
    if suffix != ".csv":
        suffix = ".csv"
    stem = Path(original).stem or spec.prefix
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-") or spec.prefix
    if not safe.lower().startswith(spec.prefix.lower()):
        safe = f"{spec.prefix}-{safe}"
    return f"{safe[:120]}{suffix}"


def _remove_existing_files(reference_dir: Path, spec: SourceFileSpec) -> None:
    for path in reference_dir.glob(f"{spec.prefix}*.csv"):
        if path.is_file():
            path.unlink()


def save_productivity_file(
    *,
    source_path: Path,
    filename: str | None,
    file_type: str,
    reference_dir: Path | str | None = None,
) -> dict[str, Any]:
    spec = SOURCE_SPEC_BY_KEY[file_type]
    target_dir = Path(reference_dir) if reference_dir is not None else default_reference_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / _safe_upload_name(filename, spec)
    tmp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    shutil.copyfile(source_path, tmp_path)
    _remove_existing_files(target_dir, spec)
    tmp_path.replace(target_path)
    clear_productivity_cache()
    return _file_status_payload(spec, target_path)


def clear_productivity_file(file_type: str, reference_dir: Path | str | None = None) -> None:
    spec = SOURCE_SPEC_BY_KEY.get(file_type)
    if spec is None or not spec.visible:
        raise ProductivitySourceError("Okänd produktivitetsfil")
    target_dir = Path(reference_dir) if reference_dir is not None else default_reference_dir()
    _remove_existing_files(target_dir, spec)
    clear_productivity_cache()


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} kB"
    return f"{size} B"


def _file_status_payload(spec: SourceFileSpec, path: Path | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": spec.key,
        "label": spec.label,
        "required": spec.required,
        "visible": spec.visible,
        "uploaded": path is not None,
        "name": None,
        "modified_at": None,
        "size": None,
        "size_label": None,
    }
    if path is None:
        return payload
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone()
    payload.update(
        {
            "name": path.name,
            "modified_at": modified.isoformat(timespec="seconds"),
            "size": stat.st_size,
            "size_label": _format_size(stat.st_size),
        }
    )
    return payload


def build_productivity_file_status(reference_dir: Path | str | None = None) -> dict[str, Any]:
    target_dir = Path(reference_dir) if reference_dir is not None else default_reference_dir()
    files = {
        spec.key: _file_status_payload(
            spec,
            _try_find_file(target_dir, spec.prefix) if target_dir.exists() else None,
        )
        for spec in SOURCE_SPECS
    }
    visible_files = {key: value for key, value in files.items() if value["visible"]}
    missing = [
        item["key"]
        for item in visible_files.values()
        if item["required"] and not item["uploaded"]
    ]
    kpi_loaded = bool(files["kpi"]["uploaded"])
    return {
        "ready": not missing and kpi_loaded,
        "missing": missing,
        "files": visible_files,
    }


def _get(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None:
            return str(value).strip()
    return ""


def _number(value: Any) -> float:
    text = str(value or "").strip().replace("\xa0", "").replace(" ", "")
    if not text:
        return 0.0
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y%m%d %H:%M:%S", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _company_contains(event: dict[str, Any], company: str) -> bool:
    return company.upper() in str(event.get("company", "")).upper()


def _company_is(event: dict[str, Any], company: str) -> bool:
    return str(event.get("company", "")).strip().upper() == company.upper()


def _clean_user(value: str) -> str:
    return value.strip()


def _parse_pick_row(row: dict[str, str]) -> dict[str, Any] | None:
    user = _clean_user(_get(row, "Användare", "Anvandare"))
    if not user:
        return None
    return {
        "user": user,
        "zone": _get(row, "Zon").upper(),
        "company": _get(row, "Bolag"),
        "timestamp": _timestamp(_get(row, "Ändrad", "Andrad")),
        "kolli": _number(_get(row, "Plockat")),
        "vikt": _number(_get(row, "Vikt")),
    }


def _parse_pick_values(values: list[str], lookup: dict[str, int]) -> dict[str, Any] | None:
    user = _clean_user(_cell(values, lookup, "Användare", "Anvandare"))
    if not user:
        return None
    return {
        "user": user,
        "zone": _cell(values, lookup, "Zon").upper(),
        "company": _cell(values, lookup, "Bolag"),
        "timestamp": _timestamp(_cell(values, lookup, "Ändrad", "Andrad")),
        "kolli": _number(_cell(values, lookup, "Plockat")),
        "vikt": _number(_cell(values, lookup, "Vikt")),
    }


def _parse_pick_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in rows:
        event = _parse_pick_row(row)
        if event is not None:
            events.append(event)
    return events


def _parse_trans_row(row: dict[str, str]) -> dict[str, Any] | None:
    user = _clean_user(_get(row, "Användare", "Anvandare"))
    if not user:
        return None
    return {
        "user": user,
        "company": _get(row, "Bolag"),
        "to": _get(row, "Till"),
        "timestamp": _timestamp(_get(row, "Timestamp")),
        "antal": _number(_get(row, "Antal")),
    }


def _parse_trans_values(values: list[str], lookup: dict[str, int]) -> dict[str, Any] | None:
    user = _clean_user(_cell(values, lookup, "Användare", "Anvandare"))
    if not user:
        return None
    return {
        "user": user,
        "company": _cell(values, lookup, "Bolag"),
        "to": _cell(values, lookup, "Till"),
        "timestamp": _timestamp(_cell(values, lookup, "Timestamp")),
        "antal": _number(_cell(values, lookup, "Antal")),
    }


def _parse_trans_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in rows:
        event = _parse_trans_row(row)
        if event is not None:
            events.append(event)
    return events


def _parse_pallet_row(row: dict[str, str]) -> dict[str, Any] | None:
    user = _clean_user(_get(row, "Användare", "Anvandare"))
    if not user:
        return None
    return {
        "user": user,
        "company": _get(row, "Bolag"),
        "type": _get(row, "Typ"),
        "timestamp": _timestamp(_get(row, "Ändrad", "Andrad")),
    }


def _parse_pallet_values(values: list[str], lookup: dict[str, int]) -> dict[str, Any] | None:
    user = _clean_user(_cell(values, lookup, "Användare", "Anvandare"))
    if not user:
        return None
    return {
        "user": user,
        "company": _cell(values, lookup, "Bolag"),
        "type": _cell(values, lookup, "Typ"),
        "timestamp": _timestamp(_cell(values, lookup, "Ändrad", "Andrad")),
    }


def _parse_pallet_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in rows:
        event = _parse_pallet_row(row)
        if event is not None:
            events.append(event)
    return events


def _parse_kpi_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    targets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        company = _get(row, "Bolag").upper()
        process = _get(row, "Processnamn").upper()
        if not company or not process:
            continue
        targets[(company, process)] = {
            "description": _get(row, "Beskrivning"),
            "rader": _number(_get(row, "Rader")),
            "kollin": _number(_get(row, "Kollin", "Kolli")),
            "pallar": _number(_get(row, "Pallar")),
        }
    return targets


def _target_value(
    targets: dict[tuple[str, str], dict[str, Any]],
    company: str,
    process: str,
    metric: str,
) -> float | None:
    target = targets.get((company.upper(), process.upper()))
    if not target:
        return None
    value = target.get(metric.lower())
    return float(value) if value else None


def _parse_report_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _event_date(event: dict[str, Any]) -> date | None:
    timestamp = event.get("timestamp")
    return timestamp.date() if isinstance(timestamp, datetime) else None


def _available_dates(*event_sets: list[dict[str, Any]]) -> list[date]:
    dates = {
        event_date
        for events in event_sets
        for event in events
        if (event_date := _event_date(event)) is not None
    }
    return sorted(dates)


def _totals_for_date(
    *,
    pick_events: list[dict[str, Any]],
    trans_events: list[dict[str, Any]],
    report_date: date,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    pick_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"kolli": 0.0, "vikt": 0.0})
    trans_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"antal": 0.0})

    for event in pick_events:
        if _event_date(event) != report_date:
            continue
        user = str(event["user"])
        pick_totals[user]["kolli"] += float(event.get("kolli") or 0)
        pick_totals[user]["vikt"] += float(event.get("vikt") or 0)

    for event in trans_events:
        if _event_date(event) != report_date:
            continue
        user = str(event["user"])
        trans_totals[user]["antal"] += float(event.get("antal") or 0)

    return pick_totals, trans_totals


def _section_specs() -> tuple[SectionSpec, ...]:
    excluded_gg = {"FILI10", "SEBA80"}
    excluded_mg = {"ANTO87", "HUGO49"}

    return (
        SectionSpec(
            "gg_pick_ab",
            "gg",
            "Plockzon A/B",
            "pick",
            "Manual_Pick",
            "GG",
            "rader",
            "pick",
            lambda event: (
                _company_contains(event, "GG")
                and event.get("zone") in {"A", "B"}
                and event.get("user") not in excluded_gg
            ),
        ),
        SectionSpec(
            "gg_pick_s",
            "gg",
            "Plockzon S",
            "pick",
            "Bulky_Pick",
            "GG",
            "rader",
            "pick",
            lambda event: (
                _company_contains(event, "GG")
                and event.get("zone") == "S"
                and event.get("user") not in excluded_gg
            ),
        ),
        SectionSpec(
            "as_store_pick",
            "autostore",
            "Butik Plock AS - GG + MG",
            "pick",
            "Autostore",
            "GG",
            "rader",
            "pick",
            lambda event: event.get("zone") == "R",
        ),
        SectionSpec(
            "gg_decanting",
            "autostore",
            "Granngården Dekantering",
            "trans",
            "Decanting",
            "GG",
            "rader",
            "trans",
            lambda event: _company_is(event, "GG") and str(event.get("to", "")).upper().startswith("AS"),
        ),
        SectionSpec(
            "gg_ecom_pick",
            "autostore",
            "Granngården E-Handel Plock",
            "pick",
            "E_Commerce",
            "GG",
            "rader",
            "pick",
            lambda event: _company_contains(event, "GG") and event.get("zone") == "E",
        ),
        SectionSpec(
            "gg_ecom_pack",
            "autostore",
            "Granngården E-Handel Pack",
            "pallet",
            "Ecom_pack",
            "GG",
            "pallar",
            "none",
            lambda event: (
                _company_is(event, "GG")
                and str(event.get("type", "")).strip() == "220"
                and event.get("user") != "swisslogautostoreintegration"
            ),
        ),
        SectionSpec(
            "mg_decanting",
            "autostore",
            "Mestergruppen Dekantering",
            "trans",
            "Decanting",
            "MG",
            "rader",
            "trans",
            lambda event: _company_is(event, "MG") and str(event.get("to", "")).upper().startswith("AS"),
        ),
        SectionSpec(
            "mg_ecom_pick",
            "autostore",
            "Mestergruppen E-Handel Plock",
            "pick",
            "E_Commerce",
            "MG",
            "rader",
            "pick",
            lambda event: _company_contains(event, "MG") and event.get("zone") == "Q",
        ),
        SectionSpec(
            "mg_ecom_pack",
            "autostore",
            "Mestergruppen E-Handel Pack",
            "pallet",
            "Ecom_pack",
            "MG",
            "pallar",
            "none",
            lambda event: (
                _company_is(event, "MG")
                and str(event.get("type", "")).strip() == "220"
                and event.get("user") != "swisslogautostoreintegration"
            ),
        ),
        SectionSpec(
            "mg_pick_abn",
            "mg",
            "Plockzon A/B/N",
            "pick",
            "Manual_Pick",
            "MG",
            "rader",
            "pick",
            lambda event: (
                _company_contains(event, "MG")
                and event.get("zone") in {"A", "B", "N"}
                and event.get("user") not in excluded_mg
            ),
        ),
        SectionSpec(
            "mg_pick_o",
            "mg",
            "Plockzon O",
            "pick",
            "Bulky_Pick",
            "MG",
            "rader",
            "pick",
            lambda event: (
                _company_contains(event, "MG")
                and event.get("zone") == "O"
                and event.get("user") not in excluded_mg
            ),
        ),
    )


def _add_section_event(
    *,
    event: dict[str, Any],
    sections: list[SectionSpec],
    section_buckets: Any,
) -> None:
    timestamp = event.get("timestamp")
    if not isinstance(timestamp, datetime):
        return
    hour = timestamp.hour
    if hour not in HOURS:
        return
    user = str(event["user"])
    for spec in sections:
        if spec.predicate(event):
            section_buckets[spec.id][user][hour] += 1


def _rows_from_buckets(
    *,
    spec: SectionSpec,
    buckets: dict[str, dict[int, int]],
    targets: dict[tuple[str, str], dict[str, Any]],
    pick_totals: dict[str, dict[str, float]],
    trans_totals: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    target = _target_value(targets, spec.target_company, spec.process, spec.target_metric)
    rows: list[dict[str, Any]] = []
    for user in sorted(buckets, key=lambda value: value.upper()):
        hourly = buckets[user]
        total_rows = sum(hourly.values())
        if total_rows <= 0:
            continue
        correction = 0
        worked_hours = max(0, sum(1 for value in hourly.values() if value > 0) - correction)
        rows_per_hour = total_rows / worked_hours if worked_hours else None
        productivity_pct = rows_per_hour / target if rows_per_hour is not None and target else None

        total_kolli: float | None = None
        total_weight: float | None = None
        if spec.total_source == "pick":
            total_kolli = pick_totals.get(user, {}).get("kolli", 0.0)
            total_weight = pick_totals.get(user, {}).get("vikt", 0.0)
        elif spec.total_source == "trans":
            total_kolli = trans_totals.get(user, {}).get("antal", 0.0)

        rows.append(
            {
                "user": user,
                "hourly": {str(hour): count for hour, count in hourly.items() if count},
                "total_rows": total_rows,
                "total_kolli": total_kolli,
                "total_weight": total_weight,
                "worked_hours": worked_hours,
                "rows_per_hour": rows_per_hour,
                "correction": correction,
                "target_per_hour": target,
                "target_metric": spec.target_metric,
                "productivity_pct": productivity_pct,
            }
        )
    return rows


def _bucketed_rows(
    *,
    spec: SectionSpec,
    events: list[dict[str, Any]],
    targets: dict[tuple[str, str], dict[str, Any]],
    pick_totals: dict[str, dict[str, float]],
    trans_totals: dict[str, dict[str, float]],
    report_date: date,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[int, int]] = defaultdict(lambda: {hour: 0 for hour in HOURS})

    for event in events:
        if not spec.predicate(event):
            continue
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, datetime):
            continue
        if timestamp.date() != report_date:
            continue
        hour = timestamp.hour
        if hour not in HOURS:
            continue
        buckets[str(event["user"])][hour] += 1

    return _rows_from_buckets(
        spec=spec,
        buckets=buckets,
        targets=targets,
        pick_totals=pick_totals,
        trans_totals=trans_totals,
    )


def _source_payload(spec: SourceFileSpec, path: Path, rows: int) -> dict[str, Any]:
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone()
    return {
        "key": spec.key,
        "label": spec.label,
        "visible": spec.visible,
        "name": path.name,
        "path": str(path),
        "rows": rows,
        "modified_at": modified.isoformat(timespec="seconds"),
    }


def _cache_key(files: dict[str, Path], report_date: date | None) -> tuple[tuple[str, str, int, int] | tuple[str, str], ...]:
    key = []
    for name, path in sorted(files.items()):
        stat = path.stat()
        key.append((name, str(path.resolve()), stat.st_mtime_ns, stat.st_size))
    key.append(("date", report_date.isoformat() if report_date else "latest"))
    return tuple(key)


_REPORT_CACHE: dict[tuple[tuple[str, str, int, int] | tuple[str, str], ...], dict[str, Any]] = {}


def clear_productivity_cache() -> None:
    _REPORT_CACHE.clear()


def build_productivity_report(
    reference_dir: Path | str | None = None,
    report_date: date | str | None = None,
) -> dict[str, Any]:
    base_dir = Path(reference_dir) if reference_dir is not None else default_reference_dir()
    files = find_source_files(base_dir)
    requested_date = _parse_report_date(report_date)
    key = _cache_key(files, requested_date)
    if key in _REPORT_CACHE:
        return _REPORT_CACHE[key]

    kpi_raw = _read_csv(files["kpi"])
    targets = _parse_kpi_rows(kpi_raw)

    section_specs = _section_specs()
    sections_by_source: dict[str, list[SectionSpec]] = defaultdict(list)
    for spec in section_specs:
        sections_by_source[spec.source].append(spec)

    dates_seen: set[date] = set()
    raw_counts = {
        "pick": 0,
        "trans": 0,
        "pallet": 0,
        "kpi": len(kpi_raw),
    }

    for lookup, values in _iter_csv_values(files["pick"]):
        raw_counts["pick"] += 1
        timestamp = _timestamp(_cell(values, lookup, "Ändrad", "Andrad"))
        if timestamp is not None:
            dates_seen.add(timestamp.date())

    for lookup, values in _iter_csv_values(files["trans"]):
        raw_counts["trans"] += 1
        timestamp = _timestamp(_cell(values, lookup, "Timestamp"))
        if timestamp is not None:
            dates_seen.add(timestamp.date())

    for lookup, values in _iter_csv_values(files["pallet"]):
        raw_counts["pallet"] += 1
        timestamp = _timestamp(_cell(values, lookup, "Ändrad", "Andrad"))
        if timestamp is not None:
            dates_seen.add(timestamp.date())

    dates = sorted(dates_seen)
    if not dates:
        raise ProductivitySourceError("Produktivitetsunderlagen saknar datum")
    selected_date = requested_date or dates[-1]
    if selected_date not in dates:
        raise ProductivitySourceError(f"Saknar produktivitetsdata för {selected_date.isoformat()}")
    key = _cache_key(files, selected_date)
    if key in _REPORT_CACHE:
        return _REPORT_CACHE[key]

    section_buckets = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    pick_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"kolli": 0.0, "vikt": 0.0})
    trans_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"antal": 0.0})

    for lookup, values in _iter_csv_values(files["pick"]):
        event = _parse_pick_values(values, lookup)
        if event is None or _event_date(event) != selected_date:
            continue
        user = str(event["user"])
        pick_totals[user]["kolli"] += float(event.get("kolli") or 0)
        pick_totals[user]["vikt"] += float(event.get("vikt") or 0)
        _add_section_event(
            event=event,
            sections=sections_by_source["pick"],
            section_buckets=section_buckets,
        )

    for lookup, values in _iter_csv_values(files["trans"]):
        event = _parse_trans_values(values, lookup)
        if event is None or _event_date(event) != selected_date:
            continue
        user = str(event["user"])
        trans_totals[user]["antal"] += float(event.get("antal") or 0)
        _add_section_event(
            event=event,
            sections=sections_by_source["trans"],
            section_buckets=section_buckets,
        )

    for lookup, values in _iter_csv_values(files["pallet"]):
        event = _parse_pallet_values(values, lookup)
        if event is None or _event_date(event) != selected_date:
            continue
        _add_section_event(
            event=event,
            sections=sections_by_source["pallet"],
            section_buckets=section_buckets,
        )

    sections_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    section_count = 0
    total_rows = 0
    total_worked_hours = 0
    productivity_values: list[float] = []

    for spec in section_specs:
        rows = _rows_from_buckets(
            spec=spec,
            buckets=section_buckets.get(spec.id, {}),
            targets=targets,
            pick_totals=pick_totals,
            trans_totals=trans_totals,
        )
        section_total_rows = sum(row["total_rows"] for row in rows)
        section_worked_hours = sum(row["worked_hours"] for row in rows)
        section_target = _target_value(targets, spec.target_company, spec.process, spec.target_metric)
        section_rows_per_hour = (
            section_total_rows / section_worked_hours if section_worked_hours else None
        )
        section_productivity = (
            section_rows_per_hour / section_target
            if section_rows_per_hour is not None and section_target
            else None
        )
        if section_productivity is not None:
            productivity_values.append(section_productivity)
        total_rows += section_total_rows
        total_worked_hours += section_worked_hours
        section_count += 1

        sections_by_group[spec.group_id].append(
            {
                "id": spec.id,
                "title": spec.title,
                "source": spec.source,
                "process": spec.process,
                "target_company": spec.target_company,
                "target_metric": spec.target_metric,
                "target_per_hour": section_target,
                "total_rows": section_total_rows,
                "worked_hours": section_worked_hours,
                "rows_per_hour": section_rows_per_hour,
                "productivity_pct": section_productivity,
                "rows": rows,
            }
        )

    groups = [
        {
            "id": group["id"],
            "title": GROUP_TITLES[group["id"]],
            "sections": sections_by_group.get(group["id"], []),
        }
        for group in GROUPS
    ]
    users = {
        row["user"]
        for group in groups
        for section in group["sections"]
        for row in section["rows"]
    }

    report = {
        "generated_at": datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds"),
        "date": selected_date.isoformat(),
        "available_dates": [item.isoformat() for item in dates],
        "hours": list(HOURS),
        "sources": {
            spec.key: _source_payload(spec, files[spec.key], raw_counts[spec.key])
            for spec in SOURCE_SPECS
        },
        "summary": {
            "sections": section_count,
            "users": len(users),
            "total_rows": total_rows,
            "worked_hours": total_worked_hours,
            "rows_per_hour": total_rows / total_worked_hours if total_worked_hours else None,
            "average_productivity_pct": (
                sum(productivity_values) / len(productivity_values)
                if productivity_values
                else None
            ),
        },
        "groups": groups,
    }
    _REPORT_CACHE.clear()
    _REPORT_CACHE[key] = report
    if requested_date is None:
        _REPORT_CACHE[_cache_key(files, None)] = report
    return report
