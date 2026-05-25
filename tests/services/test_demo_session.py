"""Tester för demo-sessionens livscykel: snapshot, isolering, städning."""
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend import demo_session as demo
from app.backend.database import Base
from app.backend.models import Activity, Area, Business, Person, User


def _seed_live_db(source_url: str) -> None:
    engine = create_engine(source_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        business = Business(code="STIGAMO", name="Stigamo", sort_order=1, is_active=True)
        session.add(business)
        session.flush()
        area = Area(business_id=business.id, code="GG", name="Granngården", sort_order=1, is_active=True)
        session.add(area)
        session.flush()
        activity = Activity(business_id=business.id, code="GG_VM", label="GG VM", area_id=area.id, color="#fff", category="work", sort_order=1, is_active=True)
        session.add(activity)
        session.flush()
        person = Person(business_id=business.id, name="Demo Persson", home_area_id=area.id, home_activity_id=activity.id, competencies=[], sort_order=1, is_active=True)
        user = User(username="demo", role="admin", roles=["admin"], business_id=business.id, is_active=True, password_hash="$2b$12$abcdef")
        session.add_all([person, user])
        session.commit()
    engine.dispose()


class _FakeRequest:
    def __init__(self):
        self.session: dict[str, str] = {}


@pytest.fixture
def live_db_url(tmp_path):
    path = tmp_path / "live.sqlite"
    url = f"sqlite:///{path.as_posix()}"
    _seed_live_db(url)
    return url


@pytest.fixture
def isolated_sessions_root(tmp_path, monkeypatch):
    sessions_root = tmp_path / "flow_demo_sessions_test"
    monkeypatch.setattr(demo, "DEMO_SESSIONS_ROOT", sessions_root)
    yield sessions_root
    # Cleanup engines that may still hold references
    for sid in list(demo._ENGINES.keys()):
        demo._dispose_engine(sid)


def test_is_demo_user_matches_username():
    assert demo.is_demo_user(User(username="demo")) is True
    assert demo.is_demo_user(User(username="DEMO")) is True
    assert demo.is_demo_user(User(username=" demo ")) is True
    assert demo.is_demo_user(User(username="admin")) is False
    assert demo.is_demo_user(None) is False


def test_start_demo_session_creates_snapshot_and_data_dir(monkeypatch, live_db_url, isolated_sessions_root):
    monkeypatch.setattr(demo.settings, "DATABASE_URL", live_db_url)
    request = _FakeRequest()
    user = User(username="demo", role="admin", is_active=True)

    sid = demo.start_demo_session(request, user)

    assert request.session["demo_session_id"] == sid
    db_path = isolated_sessions_root / f"{sid}.sqlite"
    data_path = isolated_sessions_root / sid / "data"
    assert db_path.is_file()
    assert data_path.is_dir()
    # Snapshot innehåller raderna från live
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        assert session.query(Person).count() == 1
    engine.dispose()


def test_demo_session_writes_dont_touch_live(monkeypatch, live_db_url, isolated_sessions_root):
    monkeypatch.setattr(demo.settings, "DATABASE_URL", live_db_url)
    request = _FakeRequest()
    user = User(username="demo", role="admin", is_active=True)
    sid = demo.start_demo_session(request, user)

    demo_session_factory = demo.get_demo_session_local(sid)
    with demo_session_factory() as session:
        new_person = Person(
            business_id=session.query(Business).one().id,
            name="Ny demo-person",
            home_area_id=session.query(Area).one().id,
            competencies=[],
            sort_order=99,
            is_active=True,
        )
        session.add(new_person)
        session.commit()

    # Verifiera mot live (separat anslutning) — ingen ny person ska finnas där
    live_engine = create_engine(live_db_url)
    LiveSession = sessionmaker(bind=live_engine)
    with LiveSession() as session:
        assert session.query(Person).count() == 1
    live_engine.dispose()


def test_end_demo_session_removes_files_and_disposes_engine(monkeypatch, live_db_url, isolated_sessions_root):
    monkeypatch.setattr(demo.settings, "DATABASE_URL", live_db_url)
    request = _FakeRequest()
    user = User(username="demo", role="admin", is_active=True)
    sid = demo.start_demo_session(request, user)
    # Få upp engine-cachen
    demo.get_demo_engine(sid)

    db_path = isolated_sessions_root / f"{sid}.sqlite"
    data_path = isolated_sessions_root / sid
    assert db_path.exists()

    demo.end_demo_session(request)

    assert "demo_session_id" not in request.session
    assert not db_path.exists()
    assert not data_path.exists()
    assert sid not in demo._ENGINES


def test_session_exists_returns_false_when_file_missing(isolated_sessions_root):
    assert demo.session_exists(None) is False
    assert demo.session_exists("") is False
    assert demo.session_exists("nonexistent-uuid") is False


def test_cleanup_stale_demo_sessions_removes_old_files(monkeypatch, live_db_url, isolated_sessions_root):
    monkeypatch.setattr(demo.settings, "DATABASE_URL", live_db_url)
    request = _FakeRequest()
    user = User(username="demo", role="admin", is_active=True)
    sid_old = demo.start_demo_session(request, user)
    db_path = isolated_sessions_root / f"{sid_old}.sqlite"
    data_path = isolated_sessions_root / sid_old
    # Backdate mtime > 1 hour
    very_old = time.time() - 7200
    os.utime(db_path, (very_old, very_old))
    os.utime(data_path, (very_old, very_old))

    request2 = _FakeRequest()
    sid_fresh = demo.start_demo_session(request2, user)

    removed = demo.cleanup_stale_demo_sessions(max_age_hours=1.0)

    assert not db_path.exists()
    assert not data_path.exists()
    fresh_db_path = isolated_sessions_root / f"{sid_fresh}.sqlite"
    assert fresh_db_path.exists()
    assert removed >= 2  # filen + mappen
