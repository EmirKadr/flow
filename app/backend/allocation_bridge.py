from __future__ import annotations

from pathlib import Path as _Path

_ALLOCATION_BRIDGE_PARTS = (
    "registry.py",
    "process_matrix.py",
    "user_filters.py",
    "serialization.py",
    "upload_cache.py",
    "export.py",
    "flow_execution.py",
)

_ALLOCATION_BRIDGE_PARTS_DIR = _Path(__file__).with_name("allocation_bridge_parts")
for _allocation_bridge_part in _ALLOCATION_BRIDGE_PARTS:
    _allocation_bridge_part_path = _ALLOCATION_BRIDGE_PARTS_DIR / _allocation_bridge_part
    exec(
        compile(
            _allocation_bridge_part_path.read_text(encoding="utf-8"),
            str(_allocation_bridge_part_path),
            "exec",
        ),
        globals(),
        globals(),
    )

del _Path, _ALLOCATION_BRIDGE_PARTS, _ALLOCATION_BRIDGE_PARTS_DIR, _allocation_bridge_part, _allocation_bridge_part_path