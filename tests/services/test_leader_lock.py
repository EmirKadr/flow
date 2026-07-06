"""Tester för DB-ledarlåset: exakt en ledare, stale-övertagande och gated start."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.leader_lock import LeaderLock, start_leader_gated
from app.backend.models import LeaderLease


@pytest.fixture()
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'leader.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def test_only_one_process_becomes_leader(session_factory):
    first = LeaderLock(holder_id="proc-a")
    second = LeaderLock(holder_id="proc-b")

    db = session_factory()
    try:
        assert first.try_acquire(db) is True
        assert second.try_acquire(db) is False
        # Ledaren kan förnya sitt eget lease.
        assert first.try_acquire(db) is True
    finally:
        db.close()


def test_challenger_takes_over_when_heartbeat_is_stale(session_factory):
    leader = LeaderLock(holder_id="proc-a", lease_seconds=90)
    challenger = LeaderLock(holder_id="proc-b", lease_seconds=90)

    db = session_factory()
    try:
        assert leader.try_acquire(db) is True
        stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=300)
        row = db.get(LeaderLease, leader.name)
        row.heartbeat_at = stale
        db.commit()

        assert challenger.try_acquire(db) is True
        # Gamla ledaren är utlåst tills utmanarens heartbeat blir stale.
        assert leader.try_acquire(db) is False
    finally:
        db.close()


def test_start_leader_gated_runs_callback_exactly_once(session_factory):
    calls: list[str] = []
    ran = threading.Event()

    def run_as_leader():
        calls.append("start")
        ran.set()

    thread = start_leader_gated(
        run_as_leader,
        session_factory=session_factory,
        poll_seconds=0.05,
        lock=LeaderLock(holder_id="proc-gated"),
    )
    assert ran.wait(timeout=5), "ledartråden startade aldrig jobben"
    time.sleep(0.2)  # några poll-varv till - callbacken får inte köras igen
    assert calls == ["start"]
    assert thread.daemon is True


def test_non_leader_does_not_run_callback(session_factory):
    db = session_factory()
    try:
        assert LeaderLock(holder_id="proc-holder").try_acquire(db) is True
    finally:
        db.close()

    ran = threading.Event()
    start_leader_gated(
        lambda: ran.set(),
        session_factory=session_factory,
        poll_seconds=0.05,
        lock=LeaderLock(holder_id="proc-late"),
    )
    assert not ran.wait(timeout=0.5), "icke-ledare startade jobben"
