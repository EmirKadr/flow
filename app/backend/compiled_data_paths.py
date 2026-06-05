from __future__ import annotations

import csv
import gzip
import re
import shutil
from pathlib import Path

from .business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code
from .config import settings


def compiled_data_root() -> Path:
    configured = (settings.PRODUCTIVITY_DATA_DIR or "").strip()
    if configured:
        return Path(configured)
    media_root = (settings.MEDIA_STORE_ROOT or "").strip()
    if media_root:
        return Path(media_root) / "flow-data"
    return Path(__file__).resolve().parents[2] / "local_media" / "flow-data"


def business_segment(business_code: str | None) -> str:
    code = normalize_business_code(business_code) or DEFAULT_BUSINESS_CODE
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", code).strip("._-").lower()
    return safe or "business"


def article_max_dir(business_code: str | None) -> Path:
    return compiled_data_root() / "buffertpall" / business_segment(business_code)


def article_max_path(business_code: str | None) -> Path:
    return article_max_dir(business_code) / "artikel_max.csv"


def bufferpall_observations_path(business_code: str | None) -> Path:
    return article_max_dir(business_code) / "observations.csv.gz"


def legacy_bufferpall_path(business_code: str | None, filename: str) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "warehouse_tools"
        / "vendor"
        / "lowfreqdata"
        / "buffertpall"
        / business_segment(business_code)
        / filename
    )


def legacy_article_max_path(business_code: str | None) -> Path:
    return legacy_bufferpall_path(business_code, "artikel_max.csv")


def legacy_bufferpall_observations_path(business_code: str | None) -> Path:
    return legacy_bufferpall_path(business_code, "observations.csv.gz")


def _legacy_bufferpall_candidates(business_code: str | None, filename: str) -> list[Path]:
    candidates = [legacy_bufferpall_path(business_code, filename)]
    if normalize_business_code(business_code) == DEFAULT_BUSINESS_CODE:
        root_file = candidates[0].parent.parent / filename
        if root_file not in candidates:
            candidates.append(root_file)
    return candidates


def _copy_first_existing(target_path: Path, candidates: list[Path]) -> bool:
    for source_path in candidates:
        if source_path.is_file() and source_path.resolve() != target_path.resolve():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            return True
    return False


def _has_data_rows(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    try:
        with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header_seen = False
            for row in reader:
                if not any(str(cell).strip() for cell in row):
                    continue
                if not header_seen:
                    header_seen = True
                    continue
                return True
    except (OSError, UnicodeError, EOFError):
        return False
    return False


def article_max_has_data(path: Path) -> bool:
    return _has_data_rows(path)


def bufferpall_observations_has_history(path: Path) -> bool:
    return _has_data_rows(path)


def seed_article_max_file(business_code: str | None) -> Path | None:
    path = article_max_path(business_code)
    if path.is_file():
        return path
    if _copy_first_existing(path, _legacy_bufferpall_candidates(business_code, "artikel_max.csv")):
        return path
    return None


def ensure_article_max_file(business_code: str | None) -> Path:
    path = seed_article_max_file(business_code) or article_max_path(business_code)
    if article_max_has_data(path):
        return path

    observations_path = ensure_bufferpall_observations_file(business_code)
    if not bufferpall_observations_has_history(observations_path):
        raise FileNotFoundError(
            "Ingen buffertpallhistorik finns for verksamheten. "
            "Ladda upp buffertpall forst sa artikel_max.csv kan byggas."
        )

    raise FileNotFoundError(
        "artikel_max.csv saknas eller saknar datarader for verksamheten. "
        "Ladda upp buffertpall igen sa artikel_max.csv kan raknas om."
    )


def ensure_bufferpall_observations_file(business_code: str | None) -> Path:
    path = bufferpall_observations_path(business_code)
    if path.is_file():
        return path
    if _copy_first_existing(path, _legacy_bufferpall_candidates(business_code, "observations.csv.gz")):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["artikelnummer", "pallid", "antal"])
        writer.writeheader()
    return path
