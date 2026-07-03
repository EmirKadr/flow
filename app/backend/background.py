"""Centralt register och runner för backend-bakgrundsjobb.

Alla bakgrundsjobb som ska köras vid appstart registreras i main.BACKGROUND_JOBS
och startas av appens lifespan via start_background_jobs(). Runnern äger trådar,
felhantering och statusrapportering; jobbfunktionerna innehåller bara sitt arbete.
Ett nytt bakgrundsjobb ska registreras här i stället för att skapa egna trådar
eller startup-hooks i main.py.

Status per jobb exponeras via background_job_status() och visas i healthcheck-
rapporten, så drift kan se senaste start/slut/fel utan att läsa loggar.

Viktig driftbegränsning: registret antar exakt en uvicorn-worker. Flera workers
skulle köra varje jobb en gång per worker. Kontraktstest på Dockerfile skyddar
mot att --workers läggs till utan ledarlås.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackgroundJob:
    """Ett bakgrundsjobb som startas när appen startar.

    in_thread=True kör jobbet i en daemon-tråd och är rätt för allt som väntar,
    sover eller gör IO. in_thread=False kör jobbet synkront under uppstarten och
    får bara användas för snabba anrop (t.ex. att starta en egen scheduler).
    """

    name: str
    run: Callable[[], None]
    description: str = ""
    in_thread: bool = True


_STATUS_LOCK = threading.Lock()
_STATUS: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _set_status(name: str, **fields: Any) -> None:
    with _STATUS_LOCK:
        _STATUS.setdefault(name, {}).update(fields)


def background_job_status() -> dict[str, dict[str, Any]]:
    """Statusöversikt per jobb: state, senaste start/slut och eventuellt fel."""
    with _STATUS_LOCK:
        return {name: dict(entry) for name, entry in _STATUS.items()}


def _run_job(job: BackgroundJob) -> None:
    _set_status(job.name, state="running", started_at=_now_iso(), error=None)
    try:
        job.run()
    except Exception as exc:  # noqa: BLE001 - ett jobbfel får aldrig fälla appen eller andra jobb
        logger.warning("Bakgrundsjobbet %s misslyckades.", job.name, exc_info=True)
        _set_status(
            job.name,
            state="error",
            finished_at=_now_iso(),
            error=f"{type(exc).__name__}: {exc}",
        )
        return
    _set_status(job.name, state="finished", finished_at=_now_iso())


def start_background_jobs(jobs: list[BackgroundJob]) -> None:
    """Starta alla registrerade jobb; trådade jobb startas som daemon-trådar."""
    for job in jobs:
        _set_status(
            job.name,
            state="scheduled",
            description=job.description,
            in_thread=job.in_thread,
        )
        if job.in_thread:
            threading.Thread(target=_run_job, args=(job,), name=f"bg:{job.name}", daemon=True).start()
        else:
            _run_job(job)
