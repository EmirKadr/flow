"""Load and expose the vendored warehouse runtime.

The legacy runtime still lives in one large file for output parity with the
existing Allokering app.  flow now vendors that runtime here instead of
importing a sibling application at runtime.  New code should be added as clean
modules under `warehouse_tools`, and the vendored file can be reduced flow by
flow once golden parity tests exist.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
VENDOR_ROOT = PACKAGE_ROOT / "vendor"
ENGINE_FILE = VENDOR_ROOT / "allokering12.1.py"


def _load_engine():
    if not ENGINE_FILE.exists():
        raise FileNotFoundError(f"Hittar inte lagerverktygsmotorn: {ENGINE_FILE}")

    vendor_path = str(VENDOR_ROOT)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)

    spec = importlib.util.spec_from_file_location("warehouse_tools_legacy_engine", ENGINE_FILE)
    if spec is None or spec.loader is None:
        raise ImportError(f"Kunde inte ladda lagerverktygsmotorn: {ENGINE_FILE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["warehouse_tools_legacy_engine"] = module
    spec.loader.exec_module(module)
    return module


engine = _load_engine()

# Domain functions used by the API/flow layer.
read_table = engine._read_cli_table
normalize_saldo = engine.normalize_saldo
normalize_items = engine.normalize_items
normalize_not_putaway = engine.normalize_not_putaway
allocate = engine.allocate
calculate_refill = engine.calculate_refill
compute_pallet_spaces = engine.compute_pallet_spaces
reclassify_skrymmande = engine.App._reclassify_skrymmande
merge_item_flags = engine._merge_item_flags
open_df_in_excel = engine._open_df_in_excel
build_observations_update_result = engine.build_observations_update_result
fetch_observations_from_github = engine.fetch_observations_from_github
business_observations_path = engine.business_observations_path
business_artikel_max_path = engine.business_artikel_max_path

APP_VERSION = engine.APP_VERSION
APP_TITLE = engine.APP_TITLE


def detect_file_type(path: str):
    """Reuse the legacy file detector without instantiating the GUI."""
    return engine.App._detect_file_type(None, path)
