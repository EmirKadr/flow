from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Activity, Area, Business, Person, User
from app.backend.routers.schedule import get_schedule, get_summary


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def close_session(engine, session):
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_schedule_start_date_data(session, *, home_activity: bool = False):
    business = Business(code="MG", name="Mestergruppen", sort_order=1, is_active=True)
    session.add(business)
    session.flush()
    area = Area(business_id=business.id, code="PACK", name="Pack", sort_order=1, is_active=True)
    session.add(area)
    session.flush()
    activity = Activity(
        business_id=business.id,
        code="PACK_VM",
        label="Packning",
        area_id=area.id,
        color="#86efac",
        category="work",
        sort_order=1,
        is_active=True,
    )
    session.add(activity)
    session.flush()
    person = Person(
        business_id=business.id,
        name="Ny Person",
        noman="ny",
        home_area_id=area.id,
        home_activity_id=activity.id if home_activity else None,
        competencies=[],
        has_fixed_schedule=True,
        is_active=True,
        sort_order=1,
        created_at=datetime(2026, 6, 8, 9, 0, tzinfo=ZoneInfo("Europe/Stockholm")),
    )
    user = User(
        id=1,
        username="planner",
        role="admin",
        roles=["admin"],
        business_id=business.id,
        is_active=True,
    )
    session.add_all([person, user])
    session.commit()
    return activity, person, user


def test_implicit_schedule_hours_without_home_activity_stay_empty():
    engine, session = make_session()
    try:
        _activity, person, user = _seed_schedule_start_date_data(session, home_activity=False)

        before = get_schedule(2026, 23, 1, None, None, session, user)
        assert before.persons[0].id == person.id
        assert before.persons[0].home_activity_id is None
        assert before.scheduled_hours == {}
        assert before.scheduled_defaults == {}

        expected_hours = [7, 8, 9, 10, 11, 13, 14, 15]
        after = get_schedule(2026, 24, 1, None, None, session, user)
        assert after.scheduled_hours == {person.id: expected_hours}
        assert after.persons[0].home_activity_id is None
        assert after.scheduled_defaults == {}
        assert get_summary(2026, 24, 1, None, None, session, user) == []
    finally:
        close_session(engine, session)


def test_implicit_schedule_hours_use_explicit_home_activity_as_default():
    engine, session = make_session()
    try:
        activity, person, user = _seed_schedule_start_date_data(session, home_activity=True)

        expected_hours = [7, 8, 9, 10, 11, 13, 14, 15]
        after = get_schedule(2026, 24, 1, None, None, session, user)
        assert after.scheduled_hours == {person.id: expected_hours}
        assert after.persons[0].home_activity_id == activity.id
        assert after.scheduled_defaults == {person.id: {hour: activity.id for hour in expected_hours}}
        summary = get_summary(2026, 24, 1, None, None, session, user)
        assert [(row.activity_id, row.hours) for row in summary] == [(activity.id, 8.0)]
    finally:
        close_session(engine, session)
