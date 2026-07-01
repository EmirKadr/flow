from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import Activity, Area, Business, Person, PersonProductivityDaily, User
from app.backend.routers import personal as personal_router
from app.backend.security import hash_password


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        seed_base(session)
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def seed_base(session):
    existing_person_created_at = datetime(2026, 1, 1)
    business = Business(id=1, code="MG", name="Mestergruppen", sort_order=1, is_active=True)
    area = Area(id=1, business_id=1, code="PACK", name="Pack", sort_order=1, is_active=True)
    activity = Activity(
        id=1,
        business_id=1,
        code="PACK_VM",
        label="Packning",
        area_id=1,
        color="#86efac",
        category="work",
        sort_order=1,
        is_active=True,
    )
    person = Person(
        id=1,
        business_id=1,
        name="Anna Andersson",
        noman="anna",
        home_area_id=1,
        home_activity_id=1,
        competencies=[],
        has_fixed_schedule=True,
        is_active=True,
        sort_order=1,
        created_at=existing_person_created_at,
    )
    other = Person(
        id=2,
        business_id=1,
        name="Bo Bengtsson",
        noman="bo",
        home_area_id=1,
        home_activity_id=1,
        competencies=[],
        has_fixed_schedule=True,
        is_active=True,
        sort_order=2,
        created_at=existing_person_created_at,
    )
    session.add_all([business, area, activity, person, other])
    session.commit()


def test_person_login_auto_creates_user_and_can_view_own_schedule(client, db_session):
    login = client.post("/api/auth/login", json={"username": "anna", "password": ""})

    assert login.status_code == 200
    login_data = login.json()
    assert login_data["roles"] == ["person"]
    assert login_data["person_id"] == 1
    assert login_data["must_change_password"] is True

    created = db_session.query(User).filter_by(username="anna").one()
    assert created.person_id == 1
    assert created.business_id == 1
    assert created.area_id == 1

    password = client.post("/api/auth/set-password", json={"password": "personpass"})
    assert password.status_code == 200
    assert password.json()["must_change_password"] is False

    schedule = client.get("/api/personal/schedule?year=2026&week=23")
    assert schedule.status_code == 200
    payload = schedule.json()
    assert payload["person"]["id"] == 1
    assert len(payload["days"]) == 7
    monday = payload["days"][0]
    assert monday["weekday_label"] == "Måndag"
    assert monday["total_minutes"] == 480
    assert monday["activities"][0]["label"] == "Packning"

    forbidden = client.get("/api/personal/schedule?year=2026&week=23&person_id=2")
    assert forbidden.status_code == 403


def test_super_user_can_select_person_in_personal_views(client, db_session):
    db_session.add(
        User(
            username="root",
            password_hash=hash_password("adminpass"),
            display_name="Root",
            role="super_user",
            roles=["super_user"],
            is_active=True,
            must_change_password=False,
        )
    )
    db_session.commit()

    login = client.post("/api/auth/login", json={"username": "root", "password": "adminpass"})
    assert login.status_code == 200
    assert login.json()["is_super_user"] is True

    persons = client.get("/api/personal/persons")
    assert persons.status_code == 200
    assert [person["id"] for person in persons.json()] == [1, 2]

    schedule = client.get("/api/personal/schedule?year=2026&week=23&person_id=2")
    assert schedule.status_code == 200
    assert schedule.json()["person"]["id"] == 2

    productivity = client.get("/api/personal/productivity?date=2026-06-01&person_id=2")
    assert productivity.status_code == 200
    assert productivity.json()["day"]["total_minutes"] == 480


def test_personal_productivity_includes_global_person_activity_stats(client, db_session, monkeypatch, tmp_path):
    report_dates = []

    def fake_report(_db, _files, *, report_date, business_id, sync):
        assert business_id == 1
        assert sync["ready"] is True
        report_dates.append(report_date.isoformat())
        return {
            "date": report_date.isoformat(),
            "people": [
                {
                    "person_id": 1,
                    "support_minutes": 0,
                    "absence_minutes": 0,
                    "time_cells": [
                        {
                            "kind": "kpi",
                            "activity_label": "Packning",
                            "points": 10,
                            "expected_points": 20,
                            "minutes": 60,
                            "event_count": 2,
                            "diff_count": 1,
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(personal_router, "sources_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(personal_router, "productivity_api_source_map", lambda: {"pick": "pick"})
    monkeypatch.setattr(
        personal_router,
        "productivity_snapshot_status",
        lambda *_args, **_kwargs: {"ready": True, "source": "api_snapshot"},
    )
    monkeypatch.setattr(personal_router, "productivity_snapshot_files", lambda day: {"pick": tmp_path / f"{day}.csv"})
    monkeypatch.setattr(personal_router, "build_person_productivity_report_from_files", fake_report)
    monkeypatch.setattr(personal_router, "productivity_backfill_status", lambda *_args, **_kwargs: {"status": "idle"})

    login = client.post("/api/auth/login", json={"username": "anna", "password": ""})
    assert login.status_code == 200
    password = client.post("/api/auth/set-password", json={"password": "personpass"})
    assert password.status_code == 200

    response = client.get("/api/personal/productivity?date=2026-06-03")
    assert response.status_code == 200
    payload = response.json()

    assert payload["person"]["id"] == 1
    assert payload["productivity"]["day"]["status"] == "ok"
    assert payload["productivity"]["day"]["activities"][0]["activity"] == "Packning"
    assert payload["productivity"]["day"]["summary"]["productivity_pct"] == 0.5
    assert payload["productivity"]["day"]["summary"]["points_per_hour"] == 10
    assert payload["productivity"]["week"]["period"]["start_date"] == "2026-06-01"
    assert payload["productivity"]["week"]["period"]["end_date"] == "2026-06-07"
    assert payload["productivity"]["week"]["summary"]["kpi_points"] == 70
    assert payload["productivity"]["week"]["summary"]["planned_kpi_points"] == 140
    assert report_dates.count("2026-06-03") == 1
    assert len(report_dates) == 7


def test_personal_productivity_reads_materialized_daily_cache_before_source_files(client, db_session, monkeypatch, tmp_path):
    snapshot_date = date(2026, 6, 3)
    db_session.add_all(
        [
            PersonProductivityDaily(
                business_id=1,
                snapshot_date=snapshot_date,
                person_id=1,
                row_type="person",
                item_key="person",
                metric="points",
                kpi_points=30,
                planned_kpi_points=60,
                kpi_minutes=90,
                support_minutes=15,
                absence_minutes=5,
                units=30,
                event_count=3,
                diff_count=1,
                source_snapshot_at="sync-1",
                schedule_signature="0::0",
            ),
            PersonProductivityDaily(
                business_id=1,
                snapshot_date=snapshot_date,
                person_id=1,
                row_type="cell",
                item_key="cell:480:570:1",
                metric="points",
                activity_id=1,
                activity_label="Packning",
                kind="kpi",
                start_minute=480,
                end_minute=570,
                kpi_points=30,
                planned_kpi_points=60,
                kpi_minutes=90,
                units=30,
                event_count=3,
                diff_count=1,
                source_snapshot_at="sync-1",
                schedule_signature="0::0",
            ),
        ]
    )
    db_session.commit()

    def fake_snapshot_status(day):
        if day == snapshot_date:
            return {"ready": True, "source": "api_snapshot", "last_sync_at": "sync-1"}
        return {"ready": False, "source": "api_snapshot"}

    def fail_report(*_args, **_kwargs):
        raise AssertionError("materialized cache should avoid rebuilding source-file reports")

    monkeypatch.setattr(personal_router, "sources_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(personal_router, "productivity_api_source_map", lambda: {"pick": "pick"})
    monkeypatch.setattr(personal_router, "productivity_snapshot_status", fake_snapshot_status)
    monkeypatch.setattr(personal_router, "productivity_snapshot_files", lambda day: {"pick": tmp_path / f"{day}.csv"})
    monkeypatch.setattr(personal_router, "build_person_productivity_report_from_files", fail_report)
    monkeypatch.setattr(personal_router, "productivity_backfill_status", lambda *_args, **_kwargs: {"status": "idle"})

    login = client.post("/api/auth/login", json={"username": "anna", "password": ""})
    assert login.status_code == 200
    password = client.post("/api/auth/set-password", json={"password": "personpass"})
    assert password.status_code == 200

    response = client.get("/api/personal/productivity?date=2026-06-03")
    assert response.status_code == 200
    payload = response.json()

    assert payload["productivity"]["day"]["status"] == "ok"
    assert payload["productivity"]["day"]["activities"][0]["activity"] == "Packning"
    assert payload["productivity"]["day"]["summary"]["kpi_points"] == 30
    assert payload["productivity"]["day"]["summary"]["planned_kpi_points"] == 60
    assert payload["productivity"]["day"]["summary"]["support_minutes"] == 15
    assert payload["productivity"]["day"]["summary"]["absence_minutes"] == 5
    assert payload["productivity"]["week"]["status"] == "partial"


def test_personal_productivity_week_aggregates_materialized_daily_cache_with_sql(client, db_session, monkeypatch, tmp_path):
    snapshots = [
        (date(2026, 6, 1), 10, 20, 30),
        (date(2026, 6, 3), 30, 60, 90),
    ]
    rows = []
    for snapshot_date, points, planned, minutes in snapshots:
        rows.extend(
            [
                PersonProductivityDaily(
                    business_id=1,
                    snapshot_date=snapshot_date,
                    person_id=1,
                    row_type="person",
                    item_key="person",
                    metric="points",
                    kpi_points=points,
                    planned_kpi_points=planned,
                    kpi_minutes=minutes,
                    support_minutes=5,
                    absence_minutes=2,
                    units=points,
                    event_count=1,
                    diff_count=1,
                    source_snapshot_at="sync-week",
                    schedule_signature="0::0",
                ),
                PersonProductivityDaily(
                    business_id=1,
                    snapshot_date=snapshot_date,
                    person_id=1,
                    row_type="cell",
                    item_key=f"cell:{snapshot_date.isoformat()}",
                    metric="points",
                    activity_id=1,
                    activity_label="Packning",
                    kind="kpi",
                    start_minute=480,
                    end_minute=480 + minutes,
                    kpi_points=points,
                    planned_kpi_points=planned,
                    kpi_minutes=minutes,
                    units=points,
                    event_count=1,
                    diff_count=1,
                    source_snapshot_at="sync-week",
                    schedule_signature="0::0",
                ),
            ]
        )
    db_session.add_all(rows)
    db_session.commit()

    ready_dates = {item[0] for item in snapshots}

    def fake_snapshot_status(day):
        if day in ready_dates:
            return {"ready": True, "source": "api_snapshot", "last_sync_at": "sync-week"}
        return {"ready": False, "source": "api_snapshot"}

    monkeypatch.setattr(personal_router, "sources_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(personal_router, "productivity_api_source_map", lambda: {"pick": "pick"})
    monkeypatch.setattr(personal_router, "productivity_snapshot_status", fake_snapshot_status)
    monkeypatch.setattr(personal_router, "productivity_snapshot_files", lambda day: {"pick": tmp_path / f"{day}.csv"})
    monkeypatch.setattr(
        personal_router,
        "build_person_productivity_report_from_files",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache SQL path should avoid source report build")),
    )
    monkeypatch.setattr(personal_router, "productivity_backfill_status", lambda *_args, **_kwargs: {"status": "idle"})

    login = client.post("/api/auth/login", json={"username": "anna", "password": ""})
    assert login.status_code == 200
    assert client.post("/api/auth/set-password", json={"password": "personpass"}).status_code == 200

    response = client.get("/api/personal/productivity?date=2026-06-03")
    assert response.status_code == 200
    week = response.json()["productivity"]["week"]

    assert week["status"] == "partial"
    assert week["dates"] == ["2026-06-01", "2026-06-03"]
    assert week["summary"]["kpi_points"] == 40
    assert week["summary"]["planned_kpi_points"] == 80
    assert week["summary"]["kpi_minutes"] == 120
    assert week["summary"]["support_minutes"] == 10
    assert week["summary"]["absence_minutes"] == 4
    assert week["summary"]["days_with_activity"] == 2
