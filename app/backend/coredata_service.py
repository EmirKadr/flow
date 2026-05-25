from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code
from .config import settings


class CoreDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class CoreDataFileSpec:
    key: str
    label: str
    prefix: str


CORE_DATA_SPECS = (
    CoreDataFileSpec("custom", "Custom", "custom"),
    CoreDataFileSpec("dimension", "Dimension", "dimension"),
    CoreDataFileSpec("item", "Item", "item"),
    CoreDataFileSpec("item_alias", "Item alias", "item_alias"),
    CoreDataFileSpec("item_attribute", "Item attribute", "item_attribute"),
    CoreDataFileSpec("item_option", "Item option", "item_option"),
    CoreDataFileSpec("kpi_target_rule", "KPI target rule", "kpi_target_rule"),
    CoreDataFileSpec("pallet_type", "Pallet type", "pallet_type"),
    CoreDataFileSpec("kpi", "KPI-Mal", "v_ask_kpi_target"),
)

CORE_DATA_SPEC_BY_KEY = {spec.key: spec for spec in CORE_DATA_SPECS}
CORE_DATA_SPECS_BY_PREFIX = tuple(sorted(CORE_DATA_SPECS, key=lambda spec: len(spec.prefix), reverse=True))


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
    stem = Path(filename or "").stem.lower().replace("\ufeff", "").strip()
    if not stem:
        return None
    for spec in CORE_DATA_SPECS_BY_PREFIX:
        if _stem_matches_prefix(stem, spec.prefix.lower()):
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
) -> Path:
    spec = CORE_DATA_SPEC_BY_KEY.get(file_type)
    if spec is None:
        raise CoreDataError("Okand karnfil")

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
    raise CoreDataError(f"Saknar karnfil med prefix {spec.prefix} i {first_dir}")


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
        raise CoreDataError("Okand karnfil")
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
) -> dict[str, Any]:
    spec = CORE_DATA_SPEC_BY_KEY.get(file_type)
    if spec is None:
        raise CoreDataError("Okand karnfil")
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
) -> None:
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


def try_find_coredata_file(
    file_type: str,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
) -> Path | None:
    try:
        return find_coredata_file(file_type, reference_dir, business_code)
    except CoreDataError:
        return None


def build_coredata_status(
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
) -> dict[str, Any]:
    files = {
        spec.key: coredata_file_status_payload(
            spec,
            try_find_coredata_file(spec.key, reference_dir, business_code),
        )
        for spec in CORE_DATA_SPECS
    }
    return {
        "business_code": normalize_business_code(business_code) or DEFAULT_BUSINESS_CODE,
        "root": str(coredata_root(reference_dir)),
        "files": files,
    }
