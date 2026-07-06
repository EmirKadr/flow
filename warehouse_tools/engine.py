"""Facade over the in-house warehouse engine.

Historik: motorlogiken var tidigare vendorerad i ``vendor/allokering12.1.py``
och laddades dynamiskt via importlib. Sedan 2026-07 ligger den i riktiga
moduler under ``warehouse_tools/engine_core/``. Denna fasad behåller det gamla
API:t — modulobjektet ``engine`` plus namngivna re-exports — så flows,
allocation-bryggan och tester fungerar oförändrat. Ny kod ska importera från
``warehouse_tools.engine_core`` direkt; tester ska monkeypatcha
implementationsmodulen (t.ex. ``engine_core.runtime_paths``), inte fasaden.

Resursdata (``lowfreqdata/buffertpall``) ligger kvar under
``warehouse_tools/vendor/`` tillsammans med legacy-modulerna ``app_info`` och
``update_service``.
"""
from __future__ import annotations

from . import engine_core as engine

# Domain functions used by the API/flow layer.
read_table = engine._read_cli_table
normalize_saldo = engine.normalize_saldo
normalize_items = engine.normalize_items
normalize_not_putaway = engine.normalize_not_putaway
allocate = engine.allocate
calculate_refill = engine.calculate_refill
compute_pallet_spaces = engine.compute_pallet_spaces
reclassify_skrymmande = engine.reclassify_skrymmande
merge_item_flags = engine._merge_item_flags
build_observations_update_result = engine.build_observations_update_result
fetch_observations_from_github = engine.fetch_observations_from_github
business_observations_path = engine.business_observations_path
business_artikel_max_path = engine.business_artikel_max_path
ensure_business_allocation_data_files = engine.ensure_business_allocation_data_files

APP_VERSION = engine.APP_VERSION
APP_TITLE = engine.APP_TITLE


def detect_file_type(path: str):
    """Reuse the engine's file detector without instantiating any UI."""
    return engine.detect_file_type(path)
