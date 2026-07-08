"""Query budgets for core endpoints and N+1-sensitive schedule flows.

The flow-development baseline from 2026-07-07 showed that endpoint latency is
mostly database round trips times Azure SQL latency, not row-volume explosion.
These tests lock that property: a future change that adds a query per person,
cell, or row should fail locally before it becomes production slowness.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import (
    Activity,
    Area,
    Business,
    Person,
    PersonScheduleTemplate,
    ScheduleCell,
    User,
)
from app.backend.security import hash_password

_TARGET = date.today() + timedelta(days=7)
_ISO = _TARGET.isocalendar()

# Measured 2026-07-07: areas 2, activities 2, persons 4, schedule 10,
# summary 9, overview 10, revision 5. Margin +2 for harmless drift. With
# 30 seeded persons, a real N+1 adds about +30 and breaks the budget.
QUERY_BUDGETS = {
    "/api/areas": 4,
    "/api/activities": 4,
    "/api/persons": 6,
    f"/api/schedule?year={_ISO[0]}&week={_ISO[1]}&weekday=3": 12,
    f"/api/schedule/summary?year={_ISO[0]}&week={_ISO[1]}&weekday=3": 11,
    f"/api/overview?year={_ISO[0]}&week={_ISO[1]}": 12,
    f"/api/overview/revision?year={_ISO[0]}&week={_ISO[1]}": 7,
}

PERSONS = 30


@pytest.fixture(scope="module")
def counted_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()

    business = Business(id=1, code="STIGAMO", name="Stigamo", sort_order=1, is_active=True)
    session.add(business)
    session.flush()
    for area_id in (1, 2):
        session.add(
            Area(
                id=area_id,
                business_id=1,
                code=f"A{area_id}",
                name=f"Omrade {area_id}",
                sort_order=area_id,
                is_active=True,
            )
        )
    for activity_id in range(1, 5):
        session.add(
            Activity(
                id=activity_id,
                business_id=1,
                code=f"AKT{activity_id}",
                label=f"Aktivitet {activity_id}",
                category="work",
                area_id=1 + (activity_id % 2),
                sort_order=activity_id,
                is_active=True,
            )
        )
    session.flush()
    for person_id in range(1, PERSONS + 1):
        session.add(
            Person(
                id=person_id,
                business_id=1,
                name=f"Person {person_id:02d}",
                home_area_id=1 + (person_id % 2),
                is_active=True,
                has_fixed_schedule=True,
            )
        )
    session.flush()
    for person_id in range(1, PERSONS + 1):
        for weekday in range(1, 6):
            session.add(PersonScheduleTemplate(person_id=person_id, weekday=weekday, start_hour=7, end_hour=16))
            for hour in range(7, 16):
                session.add(
                    ScheduleCell(
                        year=_ISO[0],
                        week=_ISO[1],
                        weekday=weekday,
                        hour=hour,
                        person_id=person_id,
                        activity_id=1 + (hour % 4),
                    )
                )
    session.add(
        User(
            username="ledare",
            password_hash=hash_password("pass"),
            role="leader",
            roles=["leader"],
            business_id=1,
            is_active=True,
            must_change_password=False,
        )
    )
    session.commit()

    counter = {"count": 0, "selects": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        counter["count"] += 1
        if str(statement).lstrip().upper().startswith("SELECT"):
            counter["selects"] += 1

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "ledare", "password": "pass"})
            assert login.status_code == 200, login.text
            yield client, counter
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        engine.dispose()


@pytest.mark.parametrize("endpoint", sorted(QUERY_BUDGETS))
def test_endpoint_stays_within_query_budget(counted_client, endpoint):
    client, counter = counted_client
    counter["count"] = 0
    response = client.get(endpoint)
    assert response.status_code == 200, response.text
    used = counter["count"]
    budget = QUERY_BUDGETS[endpoint]
    assert used <= budget, (
        f"{endpoint} ran {used} SQL queries (budget {budget}). "
        f"With {PERSONS} seeded persons, a broken budget usually means a new N+1."
    )


def test_schedule_bulk_cells_batches_current_hour_lookup(counted_client):
    client, counter = counted_client
    payload = {
        "action": "drag_fill",
        "atomic": True,
        "cells": [
            {
                "year": _ISO[0],
                "week": _ISO[1],
                "weekday": 3,
                "hour": 8,
                "minute_start": 0,
                "minute_end": 60,
                "person_id": person_id,
                "activity_id": 1,
                "expected_version": 1,
            }
            for person_id in range(1, PERSONS + 1)
        ],
    }

    counter["count"] = 0
    response = client.post("/api/schedule/cells", json=payload)

    assert response.status_code == 200, response.text
    used = counter["count"]
    assert used <= 16, (
        f"/api/schedule/cells ran {used} SQL queries for {PERSONS} cells. "
        "Drag-fill must batch current-hour reads instead of SELECTing once per cell."
    )


def test_overview_bulk_days_batches_current_day_lookup(counted_client):
    client, counter = counted_client
    payload = {
        "atomic": True,
        "days": [
            {
                "year": _ISO[0],
                "week": _ISO[1],
                "weekday": 4,
                "person_id": person_id,
                "activity_id": 1,
            }
            for person_id in range(1, PERSONS + 1)
        ],
    }

    counter["count"] = 0
    counter["selects"] = 0
    response = client.post("/api/overview/days/bulk", json=payload)

    assert response.status_code == 200, response.text
    used = counter["selects"]
    assert used <= 12, (
        f"/api/overview/days/bulk ran {used} SELECTs for {PERSONS} days. "
        "Overview bulk edits must batch current-day reads instead of SELECTing once per day."
    )
