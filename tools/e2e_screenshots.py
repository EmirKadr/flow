"""Bakåtkompatibel genväg till e2e-verktyget (smoke-scenariot).

Verktyget bor numera i paketet tools/e2e/ (fler scenarier, konsol-/nätverks-
fångst, rapport). Kör hellre `python -m tools.e2e --list`. Denna modul finns
kvar så gamla kommandon inte bryts.
"""
from __future__ import annotations

import sys

from tools.e2e.__main__ import main

if __name__ == "__main__":
    # Vidarebefordra ev. flaggor, men kör alltid smoke-scenariot.
    raise SystemExit(main(["smoke", *sys.argv[1:]]))
