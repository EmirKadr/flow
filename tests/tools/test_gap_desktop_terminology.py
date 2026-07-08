"""W28 — Desktop terminology parity gap test.

The web frontend/backend are already guarded against legacy product words
(Ställen, Avdelningar, Affärsenheter) by ``test_activity_terminology.py``.
The PyQt desktop shell (``desktop/``) renders its own native strings —
window titles, menus, QAction labels, setText calls — that are NOT covered
by the frontend scan. This module closes that gap: no forbidden legacy term
may appear in any desktop Python source, and specifically not inside PyQt
user-facing string calls.

Reuses the shared contract helper ``forbidden_terms_in_text`` so desktop and
web stay locked to the same canonical vocabulary.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest

# Reuse the exact same forbidden-term contract the web scan uses.
from tools.terminology_contracts import (
    forbidden_terms,
    forbidden_terms_in_text,
)


ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "desktop"


def _desktop_py_files() -> list[Path]:
    return [
        p
        for p in DESKTOP.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def test_desktop_directory_is_present():
    # Guard: if the desktop shell is ever removed/renamed this test must be
    # revisited rather than silently passing on an empty scan.
    assert DESKTOP.is_dir(), f"expected desktop package at {DESKTOP}"
    assert _desktop_py_files(), "no desktop *.py sources found to scan"


def test_shared_forbidden_terms_include_legacy_desktop_vocabulary():
    # Sanity check that the contract we import actually protects the three
    # legacy words this gap test cares about.
    terms = set(forbidden_terms())
    assert "Ställen" in terms
    assert "Avdelningar" in terms
    assert "Affärsenheter" in terms


@pytest.mark.parametrize(
    "path",
    _desktop_py_files(),
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_desktop_source_has_no_forbidden_terminology(path: Path):
    text = path.read_text(encoding="utf-8")
    matches = forbidden_terms_in_text(text)
    relative = path.relative_to(ROOT).as_posix()
    assert matches == [], (
        f"{relative} contains forbidden legacy terminology: "
        f"{', '.join(matches)}"
    )


# --- Focused PyQt user-facing string extraction ---------------------------

# Matches the string literal argument of common PyQt text-setting calls, e.g.
#   setWindowTitle("...")  QAction("...")  addMenu("...")  setText("...")
_PYQT_STRING_CALL = re.compile(
    r"""
    (?:setWindowTitle|QAction|addMenu|addAction|setText|setToolTip
       |setPlaceholderText|setStatusTip|setLabelText|setTitle|setWhatsThis)
    \s*\(\s*
    f?["']((?:[^"'\\]|\\.)*)["']
    """,
    re.VERBOSE,
)


def _iter_pyqt_strings(text: str):
    for match in _PYQT_STRING_CALL.finditer(text):
        yield match.group(1)


def test_pyqt_user_facing_strings_have_no_forbidden_terminology():
    """The tightest form of the gap: even if a legacy word snuck into a code
    comment (which the file-level scan would also catch), it must never appear
    in a rendered PyQt widget string."""
    offenders: list[str] = []
    for path in _desktop_py_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        for label in _iter_pyqt_strings(text):
            matches = forbidden_terms_in_text(label)
            if matches:
                offenders.append(
                    f"{relative}: {label!r} -> {', '.join(matches)}"
                )
    assert offenders == [], (
        "forbidden legacy terminology in PyQt strings:\n"
        + "\n".join(offenders)
    )
