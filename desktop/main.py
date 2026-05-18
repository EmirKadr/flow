"""Entry point for the Bemanning desktop client."""
from __future__ import annotations

import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _smoke_test() -> int:
    from core.app_info import APP_NAME
    from services.health_service import build_health_url
    from services.update_service import is_newer_version
    from desktop.local_app_server import localize_set_cookie

    assert APP_NAME == "Bemanning"
    assert build_health_url().endswith("/api/health")
    assert is_newer_version("0.1.1", "0.1.0") is True
    assert "Secure" not in localize_set_cookie("bemanning_session=x; Path=/; Secure")
    return 0


if "--smoke-test" in sys.argv:
    raise SystemExit(_smoke_test())

from desktop.app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
