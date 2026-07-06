"""Sökvägar för bufferpall-/lowfreqdata-resurser. Datafiler ligger kvar under warehouse_tools/vendor/."""
from __future__ import annotations

import base64
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .constants import (
    BUFFERPALL_PATH_PARTS,
    DEFAULT_OBSERVATIONS_BUSINESS_CODE,
)

def _app_config_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "flow" / "warehouse_tools_config.json"

def _vendor_data_root() -> Path:
    """Resursdata (lowfreqdata/) ligger kvar under warehouse_tools/vendor."""
    return Path(__file__).resolve().parents[1] / "vendor"


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return _vendor_data_root()

def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _vendor_data_root()

def _resource_path(*parts: str) -> Path:
    return _bundle_root().joinpath(*parts)

def _bufferpall_resource_path(*parts: str) -> Path:
    return _resource_path(*BUFFERPALL_PATH_PARTS, *parts)

def _bufferpall_runtime_dir() -> Path:
    return _runtime_root().joinpath(*BUFFERPALL_PATH_PARTS)

def _normalise_observations_business_code(business_code: Optional[str] = None) -> str:
    value = str(business_code or DEFAULT_OBSERVATIONS_BUSINESS_CODE).strip().upper()
    return value or DEFAULT_OBSERVATIONS_BUSINESS_CODE

def _business_path_segment(business_code: Optional[str] = None) -> str:
    code = _normalise_observations_business_code(business_code)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", code).strip("._-").lower()
    return safe or "business"

def _business_bufferpall_runtime_dir(business_code: Optional[str] = None) -> Path:
    segment = _business_path_segment(business_code)
    root = _bufferpall_runtime_dir()
    return root / segment if segment else root

def _business_bufferpall_resource_path(business_code: Optional[str], filename: str) -> Path:
    segment = _business_path_segment(business_code)
    return _bufferpall_resource_path(segment, filename)

def _legacy_default_bufferpall_resource_path(business_code: Optional[str], filename: str) -> Optional[Path]:
    if _normalise_observations_business_code(business_code) != DEFAULT_OBSERVATIONS_BUSINESS_CODE:
        return None
    return _bufferpall_resource_path(filename)

def _seed_bufferpall_runtime_file(filename: str, business_code: Optional[str] = None) -> Path:
    runtime_path = _business_bufferpall_runtime_dir(business_code) / filename
    runtime_path.parent.mkdir(parents=True, exist_ok=True)

    resource_paths = [_business_bufferpall_resource_path(business_code, filename)]
    legacy_default_path = _legacy_default_bufferpall_resource_path(business_code, filename)
    if legacy_default_path is not None:
        resource_paths.append(legacy_default_path)
    for resource_path in resource_paths:
        if not runtime_path.exists() and resource_path.exists() and resource_path.resolve() != runtime_path.resolve():
            shutil.copy2(resource_path, runtime_path)
            break
    return runtime_path
