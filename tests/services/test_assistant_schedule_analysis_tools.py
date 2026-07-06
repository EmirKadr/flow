"""Tester för apphjälpens nya schema-analystools (nattpass 2026-07-06).

Täcker: schedule_coverage_gaps, person_utilization, schedule_period_compare.
Seed: V27 (2026-06-29) och V28 (2026-07-06) med arbete + frånvaro.
"""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend import assistant_tools
from app.backend.database import Base
from app.backend.models import Activity, Area, Business, Person, ScheduleCell, User

V28_MONDAY = date(2026, 7, 6)
V27_MONDAY = date(2026, 6, 29)


def make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def cell(day, hour, person_id, activity_id):
    iso = day.isocalendar()
    return ScheduleCell(year=iso[0], week=iso[1], weekday=iso[2], hour=hour, person_id=person_id, activity_id=activity_id)


def seed(session):
    stigamo = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    session.add(stigamo)
    session.flush()
    gg = Area(business_id=stigamo.id, code="GG", name="Granngården", sort_order=1)
    frys = Area(business_id=stigamo.id, code="FRYS", name="Frys", sort_order=2)
    session.add_all([gg, frys])
    session.flush()
    plock = Activity(business_id=stigamo.id, code="PLOCK", label="Plock", category="work", sort_order=1)
    ledig = Activity(business_id=stigamo.id, code="LEDIG", label="Ledig", category="absence", sort_order=2)
    session.add_all([plock, ledig])
    session.flush()
    anna = Person(business_id=stigamo.id, name="Anna Andersson", home_area_id=gg.id)
    bert = Person(business_id=stigamo.id, name="Bert Berg", home_area_id=frys.id)
    session.add_all([anna, bert])
    session.flush()
    leader = User(username="ledare", role="leader", roles=["leader"], business_id=stigamo.id, is_active=True)
    session.add(leader)
    session.flush()

    # V28 måndag: Anna plock 8-10 (GG), Bert ledig kl 8 och plock kl 10 (FRYS).
    session.add_all(
        [
            cell(V28_MONDAY, 8, anna.id, plock.id),
            cell(V28_MONDAY, 9, anna.id, plock.id),
            cell(V28_MONDAY, 10, anna.id, plock.id),
            cell(V28_MONDAY, 8, bert.id, ledig.id),
            cell(V28_MONDAY, 10, bert.id, plock.id),
        ]
    )
    # V27 måndag: Anna plock 8-9 + ledig kl 10.
    session.add_all(
        [
            cell(V27_MONDAY, 8, anna.id, plock.id),
            cell(V27_MONDAY, 9, anna.id, plock.id),
            cell(V27_MONDAY, 10, anna.id, ledig.id),
        ]
    )
    session.commit()
    return {"leader": leader, "anna": anna}


def run(session, user, name, args):
    payload = assistant_tools.run_tool(session, user, name, args)
    assert "error" not in payload, payload
    return payload["result"]


def test_schedule_coverage_gaps_per_area():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(
            session, data["leader"], "schedule_coverage_gaps", {"date": "2026-07-06"}
        )
        assert result["hour_span"] == "08-10"
        areas = {row["area"]: row for row in result["areas"]}
        # GG (Anna) är bemannad hela spannet; FRYS (Bert) saknar 8 och 9 —
        # hans ledighet kl 8 räknas inte som bemanning.
        assert areas["GG"]["gap_hours"] == []
        assert areas["FRYS"]["gap_hours"] == [8, 9]

        empty = run(
            session, data["leader"], "schedule_coverage_gaps", {"date": "2026-01-05"}
        )
        assert "Ingen bemanning" in empty["note"]
    finally:
        session.close()
        engine.dispose()


def test_person_utilization_buckets_weeks():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(
            session, data["leader"], "person_utilization",
            {"person": "Anna Andersson", "date_from": "2026-06-29", "date_to": "2026-07-12"},
        )
        assert [week["week"] for week in result["weeks"]] == ["2026-V27", "2026-V28"]
        v27, v28 = result["weeks"]
        assert v27 == {"week": "2026-V27", "work_hours": 2.0, "absence_hours": 1.0, "days_scheduled": 1}
        assert v28 == {"week": "2026-V28", "work_hours": 3.0, "absence_hours": 0.0, "days_scheduled": 1}
        assert result["total_work_hours"] == 5.0
        assert result["total_absence_hours"] == 1.0

        too_long = assistant_tools.run_tool(
            session, data["leader"], "person_utilization",
            {"person": "Anna Andersson", "date_from": "2026-01-01", "date_to": "2026-06-30"},
        )
        assert "högst 92" in too_long["error"]
    finally:
        session.close()
        engine.dispose()


def test_schedule_period_compare_weeks():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(
            session, data["leader"], "schedule_period_compare",
            {"date_a": "2026-06-29", "date_b": "2026-07-06"},
        )
        assert result["week_a"] == "2026-V27"
        assert result["week_b"] == "2026-V28"
        plock_row = next(row for row in result["activities"] if row["activity"] == "Plock")
        assert plock_row == {"activity": "Plock", "hours_a": 2.0, "hours_b": 4.0, "diff_hours": 2.0}
        assert result["totals"]["persons_a"] == 1
        assert result["totals"]["persons_b"] == 2
        assert result["totals"]["absence_hours_a"] == 1.0
        assert result["totals"]["absence_hours_b"] == 1.0

        same_week = assistant_tools.run_tool(
            session, data["leader"], "schedule_period_compare",
            {"date_a": "2026-07-06", "date_b": "2026-07-07"},
        )
        assert "samma ISO-vecka" in same_week["error"]
    finally:
        session.close()
        engine.dispose()
