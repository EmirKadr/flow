"""Health checks for the central flow backend."""
from __future__ import annotations

from dataclasses import dataclass
import time
from urllib.parse import urljoin

import requests

from core.app_info import SERVER_BASE_URL


@dataclass(frozen=True)
class HealthInfo:
    status: str
    environment: str = ""


class HealthCheckError(RuntimeError):
    """Raised when the central backend cannot be reached or is unhealthy."""


def build_health_url(base_url: str = SERVER_BASE_URL) -> str:
    return urljoin(base_url.rstrip("/") + "/", "api/health")


def check_server_health(
    base_url: str = SERVER_BASE_URL,
    timeout: int = 8,
    session=None,
    attempts: int = 1,
    retry_delay: float = 0.0,
) -> HealthInfo:
    http = session or requests
    url = build_health_url(base_url)
    max_attempts = max(1, int(attempts or 1))
    transient_statuses = {502, 503, 504}
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        should_retry = False
        try:
            response = http.get(
                url,
                headers={"Accept": "application/json"},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = exc
            should_retry = True
        else:
            status_code = getattr(response, "status_code", None)
            try:
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                last_error = exc
                should_retry = status_code in transient_statuses
            else:
                status = str(data.get("status") or "").lower()
                if status == "ok":
                    return HealthInfo(
                        status=str(data.get("status") or "ok"),
                        environment=str(data.get("environment") or ""),
                    )
                last_error = HealthCheckError("Servern svarade, men health endpoint returnerade inte ok.")

        if attempt < max_attempts - 1 and should_retry:
            if retry_delay > 0:
                time.sleep(retry_delay)
            continue
        break

    raise HealthCheckError(str(last_error or "Servern kunde inte nas."))
