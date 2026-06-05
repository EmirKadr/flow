"""Move legacy repo data into the configured truth stores.

Run from ``app/``:

    python -m backend.scripts.migrate_legacy_data_to_truth

Coredata/KPI files are upserted into ``coredata_files``. Compiled data is copied
to ``PRODUCTIVITY_DATA_DIR`` or ``MEDIA_STORE_ROOT/flow-data``. The script does
not delete legacy repo files; remove them only after verification.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code
from ..compiled_data_paths import (
    article_max_path,
    bufferpall_observations_path,
    compiled_data_root,
)
from ..coredata_service import classify_coredata_file, save_coredata_file
from ..database import SessionLocal
from ..productivity_service import COMPILED_PRODUCTIVITY_LOG_SPECS, productivity_compiled_log_path


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
BUFFERPALL_DIR = ROOT / "warehouse_tools" / "vendor" / "lowfreqdata" / "buffertpall"


@dataclass(frozen=True)
class CoredataCandidate:
    business_code: str
    file_type: str
    path: Path


@dataclass(frozen=True)
class CopyCandidate:
    label: str
    business_code: str
    source_path: Path
    target_path: Path


def _business_code(value: str | None) -> str:
    return normalize_business_code(value) or DEFAULT_BUSINESS_CODE


def _latest(paths: list[Path]) -> Path:
    return max(paths, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _collect_coredata_candidates() -> list[CoredataCandidate]:
    grouped: dict[tuple[str, str], list[Path]] = {}

    coredata_root = DATA_DIR / "coredata"
    if coredata_root.is_dir():
        for path in coredata_root.glob("*/*.csv"):
            file_type = classify_coredata_file(path.name)
            if file_type:
                key = (_business_code(path.parent.name), file_type)
                grouped.setdefault(key, []).append(path)

    for path in DATA_DIR.glob("*/v_ask_kpi_target*.csv"):
        if path.parent.name.lower() == "coredata":
            continue
        key = (_business_code(path.parent.name), "kpi")
        grouped.setdefault(key, []).append(path)

    for path in DATA_DIR.glob("v_ask_kpi_target*.csv"):
        key = (DEFAULT_BUSINESS_CODE, "kpi")
        grouped.setdefault(key, []).append(path)

    return [
        CoredataCandidate(business_code=business_code, file_type=file_type, path=_latest(paths))
        for (business_code, file_type), paths in sorted(grouped.items())
    ]


def _collect_productivity_compiled_candidates() -> list[CopyCandidate]:
    specs_by_name = {spec.filename: spec for spec in COMPILED_PRODUCTIVITY_LOG_SPECS}
    candidates: list[CopyCandidate] = []
    coredata_root = DATA_DIR / "coredata"
    if not coredata_root.is_dir():
        return candidates
    for path in coredata_root.glob("*/*.csv.gz"):
        spec = specs_by_name.get(path.name)
        if spec is None:
            continue
        business_code = _business_code(path.parent.name)
        candidates.append(
            CopyCandidate(
                label=spec.key,
                business_code=business_code,
                source_path=path,
                target_path=productivity_compiled_log_path(spec.source_key, business_code=business_code),
            )
        )
    return candidates


def _collect_bufferpall_candidates() -> list[CopyCandidate]:
    grouped: dict[tuple[str, str], list[Path]] = {}
    if not BUFFERPALL_DIR.is_dir():
        return []

    for filename in ("artikel_max.csv", "observations.csv.gz"):
        root_path = BUFFERPALL_DIR / filename
        if root_path.is_file():
            grouped.setdefault((DEFAULT_BUSINESS_CODE, filename), []).append(root_path)

    for path in BUFFERPALL_DIR.glob("*/*"):
        if not path.is_file() or path.name not in {"artikel_max.csv", "observations.csv.gz"}:
            continue
        grouped.setdefault((_business_code(path.parent.name), path.name), []).append(path)

    candidates: list[CopyCandidate] = []
    for (business_code, filename), paths in sorted(grouped.items()):
        source_path = _latest(paths)
        if filename == "artikel_max.csv":
            target_path = article_max_path(business_code)
            label = "article_max"
        else:
            target_path = bufferpall_observations_path(business_code)
            label = "bufferpall_observations"
        candidates.append(
            CopyCandidate(
                label=label,
                business_code=business_code,
                source_path=source_path,
                target_path=target_path,
            )
        )
    return candidates


def _copy_candidate(candidate: CopyCandidate, *, dry_run: bool, overwrite: bool) -> str:
    target = candidate.target_path
    if target.is_file() and not overwrite:
        return "exists"
    if dry_run:
        return "would_copy"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate.source_path, target)
    return "copied"


def migrate_coredata(*, dry_run: bool) -> list[str]:
    candidates = _collect_coredata_candidates()
    lines: list[str] = []
    if dry_run:
        for item in candidates:
            lines.append(f"would_upsert coredata {item.business_code}/{item.file_type}: {item.path}")
        return lines

    with tempfile.TemporaryDirectory(prefix="flow-coredata-migrate-") as tmp_dir:
        reference_dir = Path(tmp_dir)
        with SessionLocal() as db:
            for item in candidates:
                save_coredata_file(
                    source_path=item.path,
                    filename=item.path.name,
                    file_type=item.file_type,
                    reference_dir=reference_dir,
                    business_code=item.business_code,
                    db=db,
                )
                lines.append(f"upserted coredata {item.business_code}/{item.file_type}: {item.path.name}")
            db.commit()
    return lines


def migrate_compiled(*, dry_run: bool, overwrite: bool) -> list[str]:
    lines: list[str] = [f"compiled_data_root: {compiled_data_root()}"]
    candidates = [
        *_collect_productivity_compiled_candidates(),
        *_collect_bufferpall_candidates(),
    ]
    for item in candidates:
        status = _copy_candidate(item, dry_run=dry_run, overwrite=overwrite)
        lines.append(
            f"{status} {item.label} {item.business_code}: "
            f"{item.source_path} -> {item.target_path}"
        )
    return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Only print planned writes.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing compiled data files.")
    parser.add_argument("--skip-coredata", action="store_true", help="Do not write coredata_files.")
    parser.add_argument("--skip-compiled", action="store_true", help="Do not copy compiled data to disk.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output: list[str] = []
    if not args.skip_coredata:
        output.extend(migrate_coredata(dry_run=args.dry_run))
    if not args.skip_compiled:
        output.extend(migrate_compiled(dry_run=args.dry_run, overwrite=args.overwrite))
    for line in output:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
