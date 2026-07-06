"""DB-baserat ledarlås för bakgrundsjobb och schedulers.

Ersätter det rena single-worker-antagandet: endast processen som håller
lease-raden i `leader_leases` startar `BACKGROUND_JOBS`. Med en uvicorn-worker
(dagens deploy) blir processen ledare direkt och beteendet är oförändrat. Med
flera workers — fortfarande ett medvetet beslut, se arkitekturkontraktet —
startar bara ledaren jobben, och en annan process tar över om ledarens
heartbeat är äldre än lease-tiden (processdöd, hängning).

Avstängning: FLOW_DISABLE_LEADER_LOCK=1 startar jobben direkt utan lås
(används inte i drift; finns som felsökningsventil).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError

from .database import SessionLocal
from .models import LeaderLease

logger = logging.getLogger(__name__)

LOCK_NAME = "background-jobs"
LEASE_SECONDS = 90
RENEW_SECONDS = 30


def _utcnow() -> datetime:
    # Naiv UTC genomgaende: samma semantik i SQLite, Postgres och MSSQL,
    # och inga naiv/aware-krockar vid jamforelser.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LeaderLock:
    """Ett namngivet lease i databasen. try_acquire är idempotent för hållaren:
    ledaren förnyar sitt heartbeat med samma anrop som utmanare försöker ta över med."""

    def __init__(
        self,
        name: str = LOCK_NAME,
        holder_id: str | None = None,
        lease_seconds: int = LEASE_SECONDS,
    ) -> None:
        self.name = name
        self.holder_id = holder_id or uuid.uuid4().hex
        self.lease_seconds = lease_seconds

    def try_acquire(self, db) -> bool:
        now = _utcnow()
        stale_before = now - timedelta(seconds=self.lease_seconds)

        if db.get(LeaderLease, self.name) is None:
            db.add(LeaderLease(name=self.name, holder_id=self.holder_id, heartbeat_at=now))
            try:
                db.commit()
                return True
            except IntegrityError:
                db.rollback()  # en annan process hann skapa raden

        result = db.execute(
            update(LeaderLease)
            .where(
                LeaderLease.name == self.name,
                or_(
                    LeaderLease.holder_id == self.holder_id,
                    LeaderLease.holder_id.is_(None),
                    LeaderLease.heartbeat_at.is_(None),
                    LeaderLease.heartbeat_at < stale_before,
                ),
            )
            .values(holder_id=self.holder_id, heartbeat_at=now)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return bool(result.rowcount)


def start_leader_gated(
    run_as_leader: Callable[[], None],
    *,
    session_factory: Callable = SessionLocal,
    poll_seconds: float = RENEW_SECONDS,
    lock: LeaderLock | None = None,
) -> threading.Thread:
    """Starta en daemon-tråd som tar/förnyar ledarlåset och kör run_as_leader
    exakt en gång i den process som blir ledare."""

    active_lock = lock or LeaderLock()
    started = threading.Event()

    def loop() -> None:
        while True:
            try:
                db = session_factory()
                try:
                    is_leader = active_lock.try_acquire(db)
                finally:
                    db.close()
                if is_leader and not started.is_set():
                    started.set()
                    logger.info(
                        "Ledarlås %s taget av %s - startar bakgrundsjobben.",
                        active_lock.name,
                        active_lock.holder_id,
                    )
                    run_as_leader()
                elif not is_leader and started.is_set():
                    # Ska inte kunna hända med en worker. Jobb som redan körs kan
                    # inte stoppas härifrån - kräver processomstart, därför error.
                    logger.error(
                        "Ledarlås %s förlorat efter start av jobben - risk för dubbelkörning, starta om processen.",
                        active_lock.name,
                    )
            except Exception:
                logger.warning("Ledarlås-loopen fick ett fel.", exc_info=True)
            time.sleep(poll_seconds)

    thread = threading.Thread(target=loop, name="flowLeaderLock", daemon=True)
    thread.start()
    return thread
