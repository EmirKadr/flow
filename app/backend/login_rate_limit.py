"""Rate limiting för inloggningsförsök.

Deterministisk limiter med fast fönster per (användarnamn, klient-IP).
In-memory räcker: appen kör medvetet 1 uvicorn-worker (arkitekturkontraktet),
men implementationen är injicerbar (klocka) och utbytbar mot DB-backad
lagring om workers någonsin höjs — testerna antar inget processlokalt läge.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from .config import settings


def client_ip_from_request(request) -> str:
    """Klient-IP bakom ingressen: första hoppet i X-Forwarded-For, annars socket.

    Defensiv mot request-liknande objekt utan headers/client (t.ex. tester som
    anropar login() direkt med ett enkelt namespace).
    """
    headers = getattr(request, "headers", None) or {}
    forwarded = str(headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:64]
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "") or "okänd")[:64]


class LoginRateLimiter:
    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._failures: dict[tuple[str, str], deque[float]] = {}

    @staticmethod
    def _key(username: str, ip: str) -> tuple[str, str]:
        return (str(username or "").strip().lower()[:120], str(ip or "")[:64])

    def _prune(self, attempts: deque[float], cutoff: float) -> None:
        while attempts and attempts[0] < cutoff:
            attempts.popleft()

    def retry_after_seconds(self, username: str, ip: str) -> int | None:
        """Sekunder tills nästa försök tillåts, eller None om inte blockerad."""
        if not settings.AUTH_LOGIN_RATE_LIMIT_ENABLED:
            return None
        window = max(1, int(settings.AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS))
        max_attempts = max(1, int(settings.AUTH_LOGIN_RATE_LIMIT_ATTEMPTS))
        now = self._now()
        with self._lock:
            attempts = self._failures.get(self._key(username, ip))
            if not attempts:
                return None
            self._prune(attempts, now - window)
            if len(attempts) < max_attempts:
                return None
            return max(1, int(attempts[0] + window - now) + 1)

    def register_failure(self, username: str, ip: str) -> int:
        """Registrera ett misslyckat försök; returnerar antal i fönstret."""
        window = max(1, int(settings.AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS))
        now = self._now()
        with self._lock:
            attempts = self._failures.setdefault(self._key(username, ip), deque())
            self._prune(attempts, now - window)
            attempts.append(now)
            return len(attempts)

    def reset(self, username: str, ip: str) -> None:
        with self._lock:
            self._failures.pop(self._key(username, ip), None)


login_rate_limiter = LoginRateLimiter()
