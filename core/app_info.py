"""Desktop client identity and release metadata."""
from __future__ import annotations

import os
from urllib.parse import urljoin


APP_NAME = "flow"
APP_VERSION = "0.1.5"
APP_TITLE = f"{APP_NAME} {APP_VERSION}"
GITHUB_REPO = "EmirKadr/flow"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
UPDATE_DISABLED_ENV = "FLOW_DISABLE_UPDATE_CHECK"

DEFAULT_SERVER_BASE_URL = "https://stigamo.nu"
SERVER_BASE_URL = os.environ.get(
    "FLOW_SERVER_BASE_URL",
    DEFAULT_SERVER_BASE_URL,
).rstrip("/")
SERVER_HEALTH_URL = urljoin(SERVER_BASE_URL + "/", "api/health")

DESKTOP_LOCAL_HOST = os.environ.get("FLOW_DESKTOP_HOST", "127.0.0.1")
DESKTOP_LOCAL_PORT = int(os.environ.get("FLOW_DESKTOP_PORT", "8766"))
