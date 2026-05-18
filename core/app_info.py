"""Desktop client identity and release metadata."""
from __future__ import annotations

import os
from urllib.parse import urljoin


APP_NAME = "Bemanning"
APP_VERSION = "0.1.2"
APP_TITLE = f"{APP_NAME} {APP_VERSION}"
GITHUB_REPO = "EmirKadr/Bemanning"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
UPDATE_DISABLED_ENV = "BEMANNING_DISABLE_UPDATE_CHECK"

DEFAULT_SERVER_BASE_URL = "https://stigamo.nu"
SERVER_BASE_URL = os.environ.get(
    "BEMANNING_SERVER_BASE_URL",
    DEFAULT_SERVER_BASE_URL,
).rstrip("/")
SERVER_HEALTH_URL = urljoin(SERVER_BASE_URL + "/", "api/health")

DESKTOP_LOCAL_HOST = os.environ.get("BEMANNING_DESKTOP_HOST", "127.0.0.1")
DESKTOP_LOCAL_PORT = int(os.environ.get("BEMANNING_DESKTOP_PORT", "8766"))
