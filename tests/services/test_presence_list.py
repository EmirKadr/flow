from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Activity, Area, Business, Person, ScheduleCell, User
from app.backend.routers.schedule import get_schedule_presence


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def add_cell(session, person, activity, *, hour=7, minute_start=0, minute_end=60, empty_override=False):
    session.add(
        ScheduleCell(
            year=2026,
            week=21,
            weekday=1,
            hour=hour,
            minute_start=minute_start,
            minute_end=minute_end,
            person_id=person.id,
            activity_id=activity.id if activity is not None else None,
            empty_override=empty_override,
        )
    )


def seed_presence_data(session):
    stigamo = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    r3 = Business(code="R3", name="R3", sort_order=2)
    session.add_all([stigamo, r3])
    session.flush()

    gg = Area(business_id=stigamo.id, code="GG", name="GG", sort_order=1)
    r3_area = Area(business_id=r3.id, code="R3", name="R3", sort_order=1)
    session.add_all([gg, r3_area])
    session.flush()

    work = Activity(business_id=stigamo.id, code="GG_VM", label="GG arbete", area_id=gg.id, color="#fff", category="work", sort_order=1)
    pack = Activity(business_id=stigamo.id, code="GG_PACK", label="Pack", area_id=gg.id, color="#fff", category="work", sort_order=2)
    absence = Activity(business_id=stigamo.id, code="LEDIG", label="Ledig", color="#fff", category="absence", sort_order=90)
    r3_work = Activity(business_id=r3.id, code="R3_VM", label="R3 arbete", area_id=r3_area.id, color="#fff", category="work", sort_order=1)
    session.add_all([work, pack, absence, r3_work])
    session.flush()

    current_work = Person(business_id=stigamo.id, name="Current Work", home_area_id=gg.id, competencies=[], sort_order=1)
    absence_now = Person(business_id=stigamo.id, name="Absence Now", home_area_id=gg.id, competencies=[], sort_order=2)
    absent_only = Person(business_id=stigamo.id, name="Absent Only", home_area_id=gg.id, competencies=[], has_fixed_schedule=False, sort_order=3)
    later_work = Person(business_id=stigamo.id, name="Later Work", home_area_id=gg.id, competencies=[], has_fixed_schedule=False, sort_order=4)
    empty_current = Person(business_id=stigamo.id, name="Empty Current", home_area_id=gg.id, competencies=[], sort_order=5)
    split_current = Person(business_id=stigamo.id, name="Split Current", home_area_id=gg.id, competencies=[], has_fixed_schedule=False, sort_order=6)
    r3_person = Person(business_id=r3.id, name="R3 Current", home_area_id=r3_area.id, competencies=[], sort_order=1)
    session.add_all([current_work, absence_now, absent_only, later_work, empty_current, split_current, r3_person])
    session.flush()

    add_cell(session, absence_now, absence, hour=7)
    add_cell(session, absent_only, absence, hour=7)
    add_cell(session, absent_only, absence, hour=8)
    add_cell(session, later_work, work, hour=10)
    add_cell(session, empty_current, None, hour=7, empty_override=True)
    add_cell(session, split_current, work, hour=7, minute_start=0, minute_end=30)
    add_cell(session, split_current, pack, hour=7, minute_start=30, minute_end=60)

    user = User(username="planner", role="admin", roles=["admin"], business_id=stigamo.id, area_id=gg.id, is_active=True)
    super_user = User(username="root", role="super_user", roles=["super_user"], business_id=stigamo.id, is_active=True)
    session.add_all([user, super_user])
    session.commit()
    return {
        "gg": gg,
        "r3_area": r3_area,
        "user": user,
        "super_user": super_user,
    }


def test_presence_uses_work_near_now_and_current_activity_only_for_current_hour():
    engine, session = make_session()
    try:
        data = seed_presence_data(session)

        response = get_schedule_presence(year=2026, week=21, weekday=1, hour=7, area_id=None, business_id=None, db=session, user=data["user"])

        assert [group.business_code for group in response.groups] == ["STIGAMO"]
        rows = {row.name: row for row in response.groups[0].rows}
        assert set(rows) == {"Current Work", "Absence Now", "Empty Current", "Split Current"}
        assert rows["Current Work"].current_activity == "GG arbete"
        assert rows["Absence Now"].current_activity == "Ledig"
        assert rows["Absence Now"].current_activity_category == "absence"
        assert rows["Empty Current"].current_activity == "Ingen"
        assert rows["Split Current"].current_activity == "Blandat: GG arbete / Pack"
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_presence_groups_all_areas_by_business_and_respects_area_scope():
    engine, session = make_session()
    try:
        data = seed_presence_data(session)

        all_response = get_schedule_presence(year=2026, week=21, weekday=1, hour=7, area_id=None, business_id=None, db=session, user=data["super_user"])
        groups = {group.business_code: group for group in all_response.groups}
        assert list(groups) == ["STIGAMO", "R3"]
        assert [row.name for row in groups["R3"].rows] == ["R3 Current"]

        area_response = get_schedule_presence(year=2026, week=21, weekday=1, hour=7, area_id=data["r3_area"].id, business_id=None, db=session, user=data["super_user"])
        assert [group.business_code for group in area_response.groups] == ["R3"]
        assert [row.name for row in area_response.groups[0].rows] == ["R3 Current"]
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
