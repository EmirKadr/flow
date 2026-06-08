from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Activity, Area, Business, Person, User
from app.backend.routers.schedule import get_schedule


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def close_session(engine, session):
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_implicit_schedule_hours_start_on_person_created_date():
    engine, session = make_session()
    try:
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
        person = Person(
            business_id=business.id,
            name="Ny Person",
            noman="ny",
            home_area_id=area.id,
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
        session.add_all([activity, person, user])
        session.commit()

        before = get_schedule(2026, 23, 1, None, None, session, user)
        assert before.persons[0].id == person.id
        assert before.scheduled_hours == {}
        assert before.scheduled_defaults == {}

        expected_hours = [7, 8, 9, 10, 11, 13, 14, 15]
        after = get_schedule(2026, 24, 1, None, None, session, user)
        assert after.scheduled_hours == {person.id: expected_hours}
        assert after.scheduled_defaults == {person.id: {hour: activity.id for hour in expected_hours}}
    finally:
        close_session(engine, session)
