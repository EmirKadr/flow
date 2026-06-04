from __future__ import annotations

import csv
import gzip
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from .config import settings
from .compiled_data_paths import compiled_data_root
from .coredata_service import (
    business_coredata_dir,
    clear_coredata_file,
    coredata_business_segment,
    coredata_read_dirs,
    find_coredata_file,
    save_coredata_file,
    try_find_coredata_file,
)


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
    SourceFileSpec("pick", "Plocklogg Full", "v_ask_pick_log_full"),
    SourceFileSpec("trans", "Translogg", "v_ask_trans_log"),
    SourceFileSpec("pallet", "Pallastningslogg", "v_ask_palletloading_log"),
    SourceFileSpec("kpi", "KPI-Mål", "v_ask_kpi_target", required=True, visible=False),
)

SOURCE_SPEC_BY_KEY = {spec.key: spec for spec in SOURCE_SPECS}
VISIBLE_SOURCE_SPECS = tuple(spec for spec in SOURCE_SPECS if spec.visible)


@dataclass(frozen=True)
class CompiledProductivityLogSpec:
    key: str
    source_key: str
    label: str
    filename: str
    merge_strategy: str


COMPILED_PRODUCTIVITY_LOG_SPECS = (
    CompiledProductivityLogSpec(
        "productivity_pick_observations",
        "pick",
        "Plocklogg Full sammanstalld data",
        "v_ask_pick_log_full_observations.csv.gz",
        "rowid",
    ),
    CompiledProductivityLogSpec(
        "productivity_trans_observations",
        "trans",
        "Translogg sammanstalld data",
        "v_ask_trans_log_observations.csv.gz",
        "rowid",
    ),
    CompiledProductivityLogSpec(
        "productivity_pallet_observations",
        "pallet",
        "Pallastningslogg sammanstalld data",
        "v_ask_palletloading_log_observations.csv.gz",
        "timestamp",
    ),
)
COMPILED_PRODUCTIVITY_LOG_BY_SOURCE = {
    spec.source_key: spec for spec in COMPILED_PRODUCTIVITY_LOG_SPECS
}

HEADER_HINTS = {
    "pick": {"Zon", "Plockat", "Användare", "Ändrad", "Bolag"},
    "trans": {"Pallid", "Från", "Till", "Antal", "Timestamp"},
    "pallet": {"Plockpallsnr.", "Palltyp", "Pallplacering", "Transnr.", "Vikt"},
    "kpi": {"Flödesnamn", "Processnamn", "Beskrivning", "Rader", "Kollin"},
}


def _compiled_status_payload(spec: CompiledProductivityLogSpec, path: Path | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": spec.key,
        "label": spec.label,
        "prefix": Path(spec.filename).name.removesuffix(".csv.gz"),
        "kind": "compiled_data",
        "uploaded": path is not None and path.is_file(),
        "name": None,
        "modified_at": None,
        "size": None,
        "size_label": None,
    }
    if path is None or not path.is_file():
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


def productivity_compiled_log_path(
    file_type: str,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
) -> Path:
    spec = COMPILED_PRODUCTIVITY_LOG_BY_SOURCE.get(file_type)
    if spec is None:
        raise ProductivitySourceError("Okänd produktivitetslogg")
    return business_coredata_dir(reference_dir, business_code) / spec.filename


def build_productivity_compiled_data_status(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for spec in COMPILED_PRODUCTIVITY_LOG_SPECS:
        path = business_coredata_dir(reference_dir, business_code) / spec.filename
        files[spec.key] = _compiled_status_payload(spec, path)
    return files

GROUPS = (
    {"id": "gg", "title": "Granngården"},
    {"id": "as", "title": "Autostore"},
    {"id": "eh", "title": "E-Handel"},
    {"id": "mg", "title": "Mestergruppen"},
)

GROUP_TITLES = {group["id"]: group["title"] for group in GROUPS}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_reference_dir() -> Path:
    configured_data_dir = (settings.PRODUCTIVITY_DATA_DIR or "").strip()
    if configured_data_dir:
        return Path(configured_data_dir)
    persistent_root = compiled_data_root()
    if persistent_root is not None:
        return persistent_root
    configured = (settings.PRODUCTIVITY_REFERENCE_DIR or "").strip()
    if configured:
        return Path(configured)
    return _repo_root() / "data"


def normalize_reference_business_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def business_reference_segment(value: str | None) -> str:
    return coredata_business_segment(value)


def business_reference_dir(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
) -> Path:
    base_dir = Path(reference_dir) if reference_dir is not None else default_reference_dir()
    if base_dir.name.lower() == "coredata" or (base_dir / "coredata").exists():
        return business_coredata_dir(base_dir, business_code)
    segment = business_reference_segment(business_code)
    return base_dir / segment if segment else base_dir


def _business_reference_read_dirs(
    reference_dir: Path | str | None,
    business_code: str | None,
) -> list[Path]:
    base_dir = Path(reference_dir) if reference_dir is not None else default_reference_dir()
    if base_dir.name.lower() == "coredata" or (base_dir / "coredata").exists():
        dirs = coredata_read_dirs(base_dir, business_code)
    else:
        dirs = [business_reference_dir(base_dir, business_code)]
    segment = business_reference_segment(business_code)
    if segment:
        legacy_scoped_dir = base_dir / segment
        if legacy_scoped_dir not in dirs:
            dirs.append(legacy_scoped_dir)
    return dirs


def _latest_file(reference_dir: Path, prefix: str) -> Path:
    matches = [
        path
        for path in reference_dir.glob(f"{prefix}*.csv")
        if path.is_file() and not path.name.startswith("~$")
    ]
    if not matches:
        raise ProductivitySourceError(f"Saknar referensfil med prefix {prefix} i {reference_dir}")
    return max(matches, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _latest_business_file(
    reference_dir: Path | str | None,
    prefix: str,
    business_code: str | None = None,
) -> Path:
    if business_code is None:
        target_dir = Path(reference_dir) if reference_dir is not None else default_reference_dir()
        if not target_dir.exists():
            raise ProductivitySourceError(f"Produktivitetsmappen finns inte: {target_dir}")
        return _latest_file(target_dir, prefix)

    business_code_normalized = normalize_reference_business_code(business_code)
    read_dirs = _business_reference_read_dirs(reference_dir, business_code_normalized)
    for target_dir in read_dirs:
        if target_dir.exists():
            try:
                return _latest_file(target_dir, prefix)
            except ProductivitySourceError:
                pass

    raise ProductivitySourceError(f"Saknar referensfil med prefix {prefix} i {read_dirs[0]}")


def find_source_files(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
) -> dict[str, Path]:
    return {
        spec.key: _latest_business_file(reference_dir, spec.prefix, business_code)
        for spec in SOURCE_SPECS
    }


def find_kpi_file(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    *,
    db: Session | None = None,
) -> Path:
    if business_code is not None:
        try:
            return find_coredata_file("kpi", reference_dir, business_code, db=db)
        except Exception as exc:
            raise ProductivitySourceError(str(exc)) from exc
    return _latest_business_file(reference_dir, SOURCE_SPEC_BY_KEY["kpi"].prefix, business_code)


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


def _clean_csv_header(value: Any) -> str:
    return str(value or "").strip().lstrip("\ufeff")


def _normalized_csv_header(value: Any) -> str:
    return _clean_csv_header(value).lower()


def _read_csv_rows_with_headers(path: Path, *, compressed: bool = False) -> tuple[list[str], list[dict[str, str]]]:
    opener = gzip.open if compressed else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        dialect = _detect_dialect(sample)
        reader = csv.DictReader(handle, dialect=dialect)
        headers = [_clean_csv_header(header) for header in (reader.fieldnames or []) if header is not None]
        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned = {
                _clean_csv_header(header): "" if value is None else str(value)
                for header, value in row.items()
                if header is not None
            }
            if any(str(value).strip() for value in cleaned.values()):
                rows.append(cleaned)
        return headers, rows


def _write_compiled_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with gzip.open(tmp_path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized_values = {_normalized_csv_header(header): value for header, value in row.items()}
            writer.writerow(
                {
                    header: row.get(header, normalized_values.get(_normalized_csv_header(header), ""))
                    for header in headers
                }
            )
    tmp_path.replace(path)


def _union_headers(*header_sets: list[str]) -> list[str]:
    headers: list[str] = []
    seen: set[str] = set()
    for header_set in header_sets:
        for header in header_set:
            normalized = _normalized_csv_header(header)
            if not normalized or normalized in seen:
                continue
            headers.append(header)
            seen.add(normalized)
    return headers


def _row_value(row: dict[str, str], *aliases: str) -> str:
    normalized_aliases = {_normalized_csv_header(alias) for alias in aliases}
    for header, value in row.items():
        if _normalized_csv_header(header) in normalized_aliases:
            return str(value or "").strip()
    return ""


def _rowid_value(row: dict[str, str]) -> str:
    for header, value in row.items():
        normalized = re.sub(r"[^a-z0-9]+", "", _normalized_csv_header(header))
        if normalized in {"rowid", "radid"}:
            return str(value or "").strip()
    return ""


def _row_timestamp(row: dict[str, str]) -> datetime | None:
    return _timestamp(_row_value(row, "Timestamp", "Ändrad", "Andrad"))


def _compiled_merge_rowid(
    existing_rows: list[dict[str, str]],
    new_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], str | None]:
    existing_ids = {_rowid_value(row) for row in existing_rows if _rowid_value(row)}
    if not any(_rowid_value(row) for row in new_rows):
        return [], "saknar rowid/radid"

    rows_to_add: list[dict[str, str]] = []
    seen = set(existing_ids)
    for row in new_rows:
        rowid = _rowid_value(row)
        if not rowid or rowid in seen:
            continue
        seen.add(rowid)
        rows_to_add.append(row)
    return rows_to_add, None


def _compiled_merge_timestamp(
    existing_rows: list[dict[str, str]],
    new_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], str | None]:
    existing_timestamps = [
        timestamp for row in existing_rows if (timestamp := _row_timestamp(row)) is not None
    ]
    max_timestamp = max(existing_timestamps) if existing_timestamps else None
    rows_to_add = [
        row for row in new_rows
        if (timestamp := _row_timestamp(row)) is not None
        and (max_timestamp is None or timestamp > max_timestamp)
    ]
    if not rows_to_add and not any(_row_timestamp(row) for row in new_rows):
        return [], "saknar timestamp"
    return rows_to_add, None


def update_productivity_compiled_log(
    source_path: Path,
    file_type: str,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
) -> dict[str, Any] | None:
    spec = COMPILED_PRODUCTIVITY_LOG_BY_SOURCE.get(file_type)
    if spec is None:
        return None

    new_headers, new_rows = _read_csv_rows_with_headers(source_path)
    target_path = productivity_compiled_log_path(file_type, reference_dir, business_code)
    existing_headers: list[str] = []
    existing_rows: list[dict[str, str]] = []
    if target_path.is_file():
        existing_headers, existing_rows = _read_csv_rows_with_headers(target_path, compressed=True)

    if spec.merge_strategy == "rowid":
        rows_to_add, skipped_reason = _compiled_merge_rowid(existing_rows, new_rows)
    else:
        rows_to_add, skipped_reason = _compiled_merge_timestamp(existing_rows, new_rows)

    headers = _union_headers(existing_headers, new_headers)
    combined_rows = existing_rows + rows_to_add
    if rows_to_add:
        _write_compiled_csv(target_path, headers, combined_rows)
    payload = _compiled_status_payload(spec, target_path)
    payload.update(
        {
            "source_key": file_type,
            "new_rows": len(rows_to_add),
            "total_rows": len(combined_rows),
        }
    )
    if skipped_reason:
        payload["skipped_reason"] = skipped_reason
    return payload


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
    business_code: str | None = None,
    db: Session | None = None,
    uploaded_by: int | None = None,
) -> dict[str, Any]:
    spec = SOURCE_SPEC_BY_KEY[file_type]
    if file_type == "kpi" and business_code is not None:
        payload = save_coredata_file(
            source_path=source_path,
            filename=filename,
            file_type="kpi",
            reference_dir=reference_dir,
            business_code=business_code,
            db=db,
            uploaded_by=uploaded_by,
        )
        clear_productivity_cache()
        result = _file_status_payload(spec, None)
        result.update(
            {
                "uploaded": True,
                "name": payload.get("name"),
                "modified_at": payload.get("modified_at"),
                "size": payload.get("size"),
                "size_label": payload.get("size_label"),
            }
        )
        return result
    target_dir = business_reference_dir(reference_dir, business_code)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / _safe_upload_name(filename, spec)
    tmp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    shutil.copyfile(source_path, tmp_path)
    _remove_existing_files(target_dir, spec)
    tmp_path.replace(target_path)
    clear_productivity_cache()
    return _file_status_payload(spec, target_path)


def clear_productivity_file(
    file_type: str,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    db: Session | None = None,
) -> None:
    spec = SOURCE_SPEC_BY_KEY.get(file_type)
    if spec is None or not spec.visible:
        raise ProductivitySourceError("Okänd produktivitetsfil")
    if file_type == "kpi" and business_code is not None:
        clear_coredata_file("kpi", reference_dir, business_code, db=db)
        clear_productivity_cache()
        return
    target_dir = business_reference_dir(reference_dir, business_code)
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


def _try_find_business_file(
    reference_dir: Path | str | None,
    prefix: str,
    business_code: str | None = None,
    *,
    db: Session | None = None,
) -> Path | None:
    if prefix == SOURCE_SPEC_BY_KEY["kpi"].prefix and business_code is not None:
        return try_find_coredata_file("kpi", reference_dir, business_code, db=db)
    try:
        return _latest_business_file(reference_dir, prefix, business_code)
    except ProductivitySourceError:
        return None


def build_productivity_file_status(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    *,
    db: Session | None = None,
) -> dict[str, Any]:
    files = {
        spec.key: _file_status_payload(
            spec,
            _try_find_business_file(reference_dir, spec.prefix, business_code, db=db),
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


def build_productivity_session_file_status(
    log_files: dict[str, Path],
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    *,
    db: Session | None = None,
) -> dict[str, Any]:
    files = {
        spec.key: _file_status_payload(
            spec,
            Path(log_files[spec.key]) if spec.key in log_files and Path(log_files[spec.key]).is_file() else None,
        )
        for spec in VISIBLE_SOURCE_SPECS
    }
    missing = [
        item["key"]
        for item in files.values()
        if item["required"] and not item["uploaded"]
    ]
    kpi_path: Path | None = None
    try:
        kpi_path = find_kpi_file(reference_dir, business_code, db=db)
    except ProductivitySourceError:
        kpi_path = None
    return {
        "ready": not missing and kpi_path is not None,
        "missing": missing,
        "files": files,
        "kpi_loaded": kpi_path is not None,
    }


def source_files_from_session_logs(
    log_files: dict[str, Path],
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    *,
    db: Session | None = None,
) -> dict[str, Path]:
    missing = [
        spec.label
        for spec in VISIBLE_SOURCE_SPECS
        if spec.key not in log_files or not Path(log_files[spec.key]).is_file()
    ]
    if missing:
        raise ProductivitySourceError(f"Saknar produktivitetsunderlag: {', '.join(missing)}")
    files = {key: Path(path) for key, path in log_files.items() if key in SOURCE_SPEC_BY_KEY}
    files["kpi"] = find_kpi_file(reference_dir, business_code, db=db)
    return files


def read_productivity_targets(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    *,
    db: Session | None = None,
) -> dict[str, Any]:
    return read_productivity_targets_from_file(find_kpi_file(reference_dir, business_code, db=db))


def read_productivity_targets_from_file(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    rows = _read_csv(path)
    targets = _parse_kpi_rows(rows)
    return {
        "source": _source_payload(SOURCE_SPEC_BY_KEY["kpi"], path, len(rows)),
        "targets": [
            {
                "company": company,
                "process": process,
                "description": values.get("description", ""),
                "rader": values.get("rader", 0),
                "kollin": values.get("kollin", 0),
                "pallar": values.get("pallar", 0),
            }
            for (company, process), values in sorted(targets.items())
        ],
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
            "as",
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
            "as",
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
            "eh",
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
            "eh",
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
            "as",
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
            "eh",
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
            "eh",
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
) -> bool:
    timestamp = event.get("timestamp")
    if not isinstance(timestamp, datetime):
        return False
    hour = timestamp.hour
    if hour not in HOURS:
        return False
    user = str(event["user"])
    matched = False
    for spec in sections:
        if spec.predicate(event):
            section_buckets[spec.id][user][hour] += 1
            matched = True
    return matched


def _matches_productivity_section(event: dict[str, Any] | None, sections: list[SectionSpec]) -> bool:
    if event is None:
        return False
    timestamp = event.get("timestamp")
    if not isinstance(timestamp, datetime) or timestamp.hour not in HOURS:
        return False
    return any(spec.predicate(event) for spec in sections)


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
    business_code: str | None = None,
) -> dict[str, Any]:
    files = find_source_files(reference_dir, business_code)
    return build_productivity_report_from_files(files, report_date=report_date)


def build_productivity_report_from_files(
    files: dict[str, Path],
    report_date: date | str | None = None,
) -> dict[str, Any]:
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
        event = _parse_pick_values(values, lookup)
        if _matches_productivity_section(event, sections_by_source["pick"]):
            event_date = _event_date(event)
            if event_date is not None:
                dates_seen.add(event_date)

    for lookup, values in _iter_csv_values(files["trans"]):
        raw_counts["trans"] += 1
        event = _parse_trans_values(values, lookup)
        if _matches_productivity_section(event, sections_by_source["trans"]):
            event_date = _event_date(event)
            if event_date is not None:
                dates_seen.add(event_date)

    for lookup, values in _iter_csv_values(files["pallet"]):
        raw_counts["pallet"] += 1
        event = _parse_pallet_values(values, lookup)
        if _matches_productivity_section(event, sections_by_source["pallet"]):
            event_date = _event_date(event)
            if event_date is not None:
                dates_seen.add(event_date)

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
