from __future__ import annotations

import os
import re
import shutil
import hashlib
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code
from .config import settings
from .models import CoreDataFile


class CoreDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class CoreDataFileSpec:
    key: str
    label: str
    prefix: str
    aliases: tuple[str, ...] = ()


def _normalize_coredata_prefix(value: str | None) -> str:
    text = (value or "").replace("\ufeff", "").strip().lower()
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


CORE_DATA_SPECS = (
    CoreDataFileSpec("custom", "Custom", "custom"),
    CoreDataFileSpec("dimension", "Dimension", "dimension"),
    CoreDataFileSpec("dispatch_template", "Dispatch template", "dispatch_template"),
    CoreDataFileSpec("item", "Item", "item"),
    CoreDataFileSpec("item_alias", "Item alias", "item_alias"),
    CoreDataFileSpec("item_attribute", "Item attribute", "item_attribute"),
    CoreDataFileSpec("item_option", "Item option", "item_option"),
    CoreDataFileSpec("item_security_info", "Artikel säkerhetsinformation", "item_security_info"),
    CoreDataFileSpec("kpi_target_rule", "KPI target rule", "kpi_target_rule"),
    CoreDataFileSpec("location", "Location", "location", ("lagerplats", "lagerplatser")),
    CoreDataFileSpec("location_cost", "Location cost", "location_cost"),
    CoreDataFileSpec("pallet_type", "Pallet type", "pallet_type"),
    CoreDataFileSpec("trans_agency", "Transport agency", "trans_agency", ("transportorer", "transportor", "agency", "agencies")),
    CoreDataFileSpec("kpi", "KPI-Mal", "v_ask_kpi_target"),
)

CORE_DATA_SPEC_BY_KEY = {spec.key: spec for spec in CORE_DATA_SPECS}
CORE_DATA_PREFIXES = tuple(
    sorted(
        (
            (spec, _normalize_coredata_prefix(prefix))
            for spec in CORE_DATA_SPECS
            for prefix in (spec.prefix, *spec.aliases)
        ),
        key=lambda item: len(item[1]),
        reverse=True,
    )
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _real_default_data_dir() -> Path:
    configured = (settings.PRODUCTIVITY_DATA_DIR or "").strip()
    if configured:
        return Path(configured)
    configured = (settings.PRODUCTIVITY_REFERENCE_DIR or "").strip()
    if configured:
        return Path(configured)
    return _repo_root() / "data"


def _demo_data_root_override() -> Path | None:
    """Returnera demo-sessionens datakatalog om den aktiva requesten är demo."""
    try:
        from .demo_session import demo_data_root_var
    except Exception:
        return None
    return demo_data_root_var.get()


def default_data_dir() -> Path:
    override = _demo_data_root_override()
    if override is not None:
        return override
    return _real_default_data_dir()


def coredata_root(reference_dir: Path | str | None = None) -> Path:
    base_dir = Path(reference_dir) if reference_dir is not None else default_data_dir()
    return base_dir if base_dir.name.lower() == "coredata" else base_dir / "coredata"


def coredata_legacy_base_dir(reference_dir: Path | str | None = None) -> Path:
    base_dir = Path(reference_dir) if reference_dir is not None else default_data_dir()
    return base_dir.parent if base_dir.name.lower() == "coredata" else base_dir


def coredata_business_segment(value: str | None) -> str:
    code = normalize_business_code(value)
    if not code:
        return ""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", code).strip("._-").lower()
    return safe or "business"


def _normalized_business_code(value: str | None) -> str:
    return normalize_business_code(value) or DEFAULT_BUSINESS_CODE


def _coredata_db_row(
    db: Session | None,
    file_type: str,
    business_code: str | None,
) -> CoreDataFile | None:
    if db is None:
        return None
    return (
        db.query(CoreDataFile)
        .filter(CoreDataFile.business_code == _normalized_business_code(business_code))
        .filter(CoreDataFile.file_type == file_type)
        .one_or_none()
    )


def _coredata_db_rows_by_type(
    db: Session | None,
    business_code: str | None,
) -> dict[str, CoreDataFile]:
    if db is None:
        return {}
    rows = (
        db.query(CoreDataFile)
        .filter(CoreDataFile.business_code == _normalized_business_code(business_code))
        .all()
    )
    return {row.file_type: row for row in rows}


def _db_materialized_dir(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
) -> Path:
    if reference_dir is not None:
        return business_coredata_dir(reference_dir, business_code)
    return Path(tempfile.gettempdir()) / "flow-coredata" / coredata_business_segment(business_code)


def _materialize_coredata_row(
    row: CoreDataFile,
    reference_dir: Path | str | None = None,
) -> Path:
    target_dir = _db_materialized_dir(reference_dir, row.business_code)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / _safe_upload_name(row.filename, CORE_DATA_SPEC_BY_KEY[row.file_type])
    if target_path.is_file():
        try:
            if hashlib.sha256(target_path.read_bytes()).hexdigest() == row.content_hash:
                return target_path
        except OSError:
            pass
    tmp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    tmp_path.write_bytes(row.data)
    tmp_path.replace(target_path)
    return target_path


def _same_business_segment(path: Path, segment: str) -> bool:
    return coredata_business_segment(path.name) == segment


def _business_dirs(root: Path, business_code: str | None) -> list[Path]:
    segment = coredata_business_segment(business_code)
    if not segment:
        return [root]

    dirs: list[Path] = []
    preferred = root / segment
    dirs.append(preferred)
    if root.exists():
        try:
            for child in root.iterdir():
                if child.is_dir() and _same_business_segment(child, segment) and child not in dirs:
                    dirs.append(child)
        except OSError:
            pass
    return dirs


def business_coredata_dir(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
) -> Path:
    dirs = _business_dirs(coredata_root(reference_dir), business_code)
    for directory in dirs:
        if directory.exists():
            return directory
    return dirs[0]


def coredata_read_dirs(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    *,
    include_legacy_scoped: bool = True,
) -> list[Path]:
    root = coredata_root(reference_dir)
    dirs = _business_dirs(root, business_code)
    if include_legacy_scoped and business_code:
        legacy = coredata_legacy_base_dir(reference_dir) / coredata_business_segment(business_code)
        if legacy not in dirs:
            dirs.append(legacy)
    # Demo-användaren ska kunna LÄSA prod-filer som fallback även om demo-mappen är tom,
    # men WRITES (save_coredata_file) använder coredata_root som pekar mot demo-mappen.
    if reference_dir is None and _demo_data_root_override() is not None:
        real_root = _real_default_data_dir()
        real_coredata_root = real_root if real_root.name.lower() == "coredata" else real_root / "coredata"
        for path in _business_dirs(real_coredata_root, business_code):
            if path not in dirs:
                dirs.append(path)
        if include_legacy_scoped and business_code:
            legacy_real = (real_root.parent if real_root.name.lower() == "coredata" else real_root) / coredata_business_segment(business_code)
            if legacy_real not in dirs:
                dirs.append(legacy_real)
    return dirs


def _stem_matches_prefix(stem: str, prefix: str) -> bool:
    if stem == prefix:
        return True
    return any(stem.startswith(f"{prefix}{separator}") for separator in ("-", "_", ".", " "))


def classify_coredata_file(filename: str | None) -> str | None:
    stem = _normalize_coredata_prefix(Path(filename or "").stem)
    if not stem:
        return None
    for spec, prefix in CORE_DATA_PREFIXES:
        if _stem_matches_prefix(stem, prefix):
            return spec.key
    return None


def _matches_spec(path: Path, spec: CoreDataFileSpec) -> bool:
    return path.is_file() and path.suffix.lower() == ".csv" and classify_coredata_file(path.name) == spec.key


def _latest_file(reference_dir: Path, spec: CoreDataFileSpec) -> Path:
    matches = [path for path in reference_dir.glob("*.csv") if _matches_spec(path, spec)]
    if not matches:
        raise CoreDataError(f"Saknar karnfil med prefix {spec.prefix} i {reference_dir}")
    return max(matches, key=lambda path: (path.stat().st_mtime_ns, path.name))


def find_coredata_file(
    file_type: str,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    *,
    allow_legacy_stigamo_root: bool = True,
    db: Session | None = None,
) -> Path:
    spec = CORE_DATA_SPEC_BY_KEY.get(file_type)
    if spec is None:
        raise CoreDataError("Okänd kärnfil")

    db_row = _coredata_db_row(db, file_type, business_code)
    if db_row is not None:
        return _materialize_coredata_row(db_row, reference_dir)

    for directory in coredata_read_dirs(reference_dir, business_code):
        if not directory.exists():
            continue
        try:
            return _latest_file(directory, spec)
        except CoreDataError:
            pass

    business_code_normalized = normalize_business_code(business_code)
    if allow_legacy_stigamo_root and file_type == "kpi" and business_code_normalized == DEFAULT_BUSINESS_CODE:
        legacy_root = coredata_legacy_base_dir(reference_dir)
        if legacy_root.exists():
            try:
                return _latest_file(legacy_root, spec)
            except CoreDataError:
                pass

    first_dir = coredata_read_dirs(reference_dir, business_code)[0]
    raise CoreDataError(f"Saknar kärnfil med prefix {spec.prefix} i {first_dir}")


def _safe_upload_name(filename: str | None, spec: CoreDataFileSpec) -> str:
    original = Path(filename or "").name
    suffix = Path(original).suffix.lower()
    if suffix != ".csv":
        suffix = ".csv"
    stem = Path(original).stem or spec.prefix
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-") or spec.prefix
    if classify_coredata_file(f"{safe}.csv") != spec.key:
        safe = f"{spec.prefix}-{safe}"
    return f"{safe[:120]}{suffix}"


def remove_existing_coredata_files(reference_dir: Path, file_type: str) -> None:
    spec = CORE_DATA_SPEC_BY_KEY.get(file_type)
    if spec is None:
        raise CoreDataError("Okänd kärnfil")
    if not reference_dir.exists():
        return
    for path in reference_dir.glob("*.csv"):
        if _matches_spec(path, spec):
            path.unlink()


def save_coredata_file(
    *,
    source_path: Path,
    filename: str | None,
    file_type: str,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    db: Session | None = None,
    uploaded_by: int | None = None,
) -> dict[str, Any]:
    spec = CORE_DATA_SPEC_BY_KEY.get(file_type)
    if spec is None:
        raise CoreDataError("Okänd kärnfil")
    if db is not None:
        data = source_path.read_bytes()
        normalized_business = _normalized_business_code(business_code)
        safe_name = _safe_upload_name(filename, spec)
        now = datetime.now(timezone.utc)
        row = _coredata_db_row(db, file_type, normalized_business)
        if row is None:
            row = CoreDataFile(
                business_code=normalized_business,
                file_type=file_type,
                filename=safe_name,
                content_type="text/csv",
                size_bytes=len(data),
                content_hash=hashlib.sha256(data).hexdigest(),
                data=data,
                source="upload",
                uploaded_by=uploaded_by,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            row.filename = safe_name
            row.content_type = "text/csv"
            row.size_bytes = len(data)
            row.content_hash = hashlib.sha256(data).hexdigest()
            row.data = data
            row.source = "upload"
            row.uploaded_by = uploaded_by
            row.updated_at = now
        db.flush()
        fallback_dir = business_coredata_dir(reference_dir, normalized_business)
        remove_existing_coredata_files(fallback_dir, file_type)
        _materialize_coredata_row(row, reference_dir)
        return coredata_db_status_payload(spec, row)

    target_dir = business_coredata_dir(reference_dir, business_code)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / _safe_upload_name(filename, spec)
    tmp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    shutil.copyfile(source_path, tmp_path)
    remove_existing_coredata_files(target_dir, file_type)
    tmp_path.replace(target_path)
    return coredata_file_status_payload(spec, target_path)


def clear_coredata_file(
    file_type: str,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    db: Session | None = None,
) -> None:
    db_row = _coredata_db_row(db, file_type, business_code)
    if db_row is not None and db is not None:
        db.delete(db_row)
        db.flush()
    target_dir = business_coredata_dir(reference_dir, business_code)
    remove_existing_coredata_files(target_dir, file_type)


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} kB"
    return f"{size} B"


def coredata_file_status_payload(spec: CoreDataFileSpec, path: Path | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": spec.key,
        "label": spec.label,
        "prefix": spec.prefix,
        "kind": "coredata",
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


def coredata_db_status_payload(spec: CoreDataFileSpec, row: CoreDataFile | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": spec.key,
        "label": spec.label,
        "prefix": spec.prefix,
        "kind": "coredata",
        "uploaded": row is not None,
        "name": None,
        "modified_at": None,
        "size": None,
        "size_label": None,
        "hash": None,
        "storage": "postgres" if row is not None else None,
    }
    if row is None:
        return payload
    modified = row.updated_at or row.created_at
    payload.update(
        {
            "name": row.filename,
            "modified_at": modified.astimezone().isoformat(timespec="seconds") if modified else None,
            "size": row.size_bytes,
            "size_label": _format_size(int(row.size_bytes or 0)),
            "hash": row.content_hash,
        }
    )
    return payload


def try_find_coredata_file(
    file_type: str,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    *,
    db: Session | None = None,
) -> Path | None:
    try:
        return find_coredata_file(file_type, reference_dir, business_code, db=db)
    except CoreDataError:
        return None


def build_coredata_status(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    *,
    db: Session | None = None,
) -> dict[str, Any]:
    db_rows = _coredata_db_rows_by_type(db, business_code)
    files = {
        spec.key: (
            coredata_db_status_payload(spec, db_rows[spec.key])
            if spec.key in db_rows
            else coredata_file_status_payload(
                spec,
                try_find_coredata_file(spec.key, reference_dir, business_code),
            )
        )
        for spec in CORE_DATA_SPECS
    }
    return {
        "business_code": _normalized_business_code(business_code),
        "root": str(coredata_root(reference_dir)),
        "files": files,
    }
