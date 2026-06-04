from __future__ import annotations

import re
from pathlib import Path

from .business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code
from .config import settings


def compiled_data_root() -> Path | None:
    configured = (settings.PRODUCTIVITY_DATA_DIR or "").strip()
    if configured:
        return Path(configured)
    media_root = (settings.MEDIA_STORE_ROOT or "").strip()
    if media_root:
        return Path(media_root) / "flow-data"
    return None


def business_segment(business_code: str | None) -> str:
    code = normalize_business_code(business_code) or DEFAULT_BUSINESS_CODE
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", code).strip("._-").lower()
    return safe or "business"


def article_max_dir(business_code: str | None) -> Path:
    root = compiled_data_root()
    if root is not None:
        return root / "buffertpall" / business_segment(business_code)
    return (
        Path(__file__).resolve().parents[2]
        / "warehouse_tools"
        / "vendor"
        / "lowfreqdata"
        / "buffertpall"
        / business_segment(business_code)
    )


def article_max_path(business_code: str | None) -> Path:
    return article_max_dir(business_code) / "artikel_max.csv"


def legacy_article_max_path(business_code: str | None) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "warehouse_tools"
        / "vendor"
        / "lowfreqdata"
        / "buffertpall"
        / business_segment(business_code)
        / "artikel_max.csv"
    )
