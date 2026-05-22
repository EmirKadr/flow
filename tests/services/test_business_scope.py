import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Activity, AppSetting, Area, Business, Person, ScheduleCell, User
from app.backend.routers import public
from app.backend.routers.activities import create_activity, list_activities, update_activity
from app.backend.routers.areas import create_area, delete_area, list_areas
from app.backend.routers.overview import get_overview_revision
from app.backend.routers.persons import create_person, get_person, list_persons, update_person
from app.backend.routers.schedule import get_schedule_revision, update_cell
from app.backend.routers.settings import get_app_settings, update_app_settings
from app.backend.routers.users import create_user, list_users, update_user
from app.backend.schemas import ActivityCreate, ActivityUpdate, AreaCreate, CellUpdate, PersonCreate, PersonUpdate, UserCreate, UserUpdate
from app.backend.schemas import AppSettingsUpdate


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    return engine, session


def seed_two_businesses(session):
    stigamo = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    r3 = Business(code="R3", name="R3", sort_order=2)
    session.add_all([stigamo, r3])
    session.flush()
    gg = Area(business_id=stigamo.id, code="GG", name="GG", sort_order=1)
    r3_area = Area(business_id=r3.id, code="R3", name="R3", sort_order=1)
    session.add_all([gg, r3_area])
    session.flush()
    stigamo_person = Person(business_id=stigamo.id, name="Stigamo Person", home_area_id=gg.id, competencies=[])
    r3_person = Person(business_id=r3.id, name="R3 Person", home_area_id=r3_area.id, competencies=[])
    stigamo_activity = Activity(
        business_id=stigamo.id,
        code="GG_PLOCK",
        label="GG Plock",
        area_id=gg.id,
        color="#ffffff",
        category="work",
        sort_order=1,
    )
    r3_activity = Activity(
        business_id=r3.id,
        code="R3_LEDIG",
        label="R3 Ledig",
        area_id=None,
        color="#ffffff",
        category="absence",
        sort_order=1,
    )
    user = User(username="stigamo-admin", role="admin", roles=["admin"], business_id=stigamo.id, is_active=True)
    r3_user = User(username="r3-admin", role="admin", roles=["admin"], business_id=r3.id, area_id=r3_area.id, is_active=True)
    super_user = User(username="root", role="super_user", roles=["super_user"], business_id=stigamo.id, is_active=True)
    extra_users = [
        User(username=f"stigamo-user-{index}", role="leader", roles=["leader"], business_id=stigamo.id, area_id=gg.id, is_active=True)
        for index in range(5)
    ] + [
        User(username=f"r3-user-{index}", role="leader", roles=["leader"], business_id=r3.id, area_id=r3_area.id, is_active=True)
        for index in range(5)
    ]
    session.add_all([stigamo_person, r3_person, stigamo_activity, r3_activity, user, r3_user, super_user, *extra_users])
    session.commit()
    return {
        "stigamo": stigamo,
        "r3": r3,
        "stigamo_person": stigamo_person,
        "r3_person": r3_person,
        "stigamo_activity": stigamo_activity,
        "r3_activity": r3_activity,
        "user": user,
        "r3_user": r3_user,
        "super_user": super_user,
    }


@pytest.fixture()
def business_session():
    engine, session = make_session()
    try:
        yield session, seed_two_businesses(session)
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def assert_http_status(status_code, fn, *args, **kwargs):
    with pytest.raises(HTTPException) as exc_info:
        fn(*args, **kwargs)
    assert exc_info.value.status_code == status_code


def test_non_super_user_lists_only_own_business_persons():
    engine, session = make_session()
    try:
        data = seed_two_businesses(session)

        persons = list_persons(db=session, user=data["user"])

        assert [person.name for person in persons] == ["Stigamo Person"]
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_schedule_update_rejects_cross_business_activity():
    engine, session = make_session()
    try:
        data = seed_two_businesses(session)

        try:
            update_cell(
                CellUpdate(
                    year=2026,
                    week=21,
                    weekday=1,
                    hour=7,
                    minute_start=0,
                    minute_end=60,
                    person_id=data["stigamo_person"].id,
                    activity_id=data["r3_activity"].id,
                    expected_version=0,
                ),
                session,
                data["super_user"],
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Cross-business schedule update should fail")
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_many_users_are_hidden_between_businesses(business_session):
    session, data = business_session

    stigamo_users = list_users(db=session, admin=data["user"])
    r3_users = list_users(db=session, admin=data["r3_user"])
    global_users = list_users(db=session, admin=data["super_user"])

    assert {user.username for user in stigamo_users} >= {"stigamo-admin", "stigamo-user-0", "stigamo-user-4"}
    assert not any(user.username.startswith("r3-") for user in stigamo_users)
    assert {user.username for user in r3_users} >= {"r3-admin", "r3-user-0", "r3-user-4"}
    assert not any(user.username.startswith("stigamo-") for user in r3_users)
    assert {user.username for user in global_users} >= {"stigamo-admin", "r3-admin", "root"}


def test_lists_filter_areas_activities_and_persons_by_business(business_session):
    session, data = business_session

    assert [area.code for area in list_areas(db=session, user=data["user"])] == ["GG"]
    assert [area.code for area in list_areas(db=session, user=data["r3_user"])] == ["R3"]
    assert {area.code for area in list_areas(db=session, user=data["super_user"])} == {"GG", "R3"}

    assert [activity.label for activity in list_activities(db=session, user=data["user"])] == ["GG Plock"]
    assert [activity.label for activity in list_activities(db=session, user=data["r3_user"])] == ["R3 Ledig"]
    assert {person.name for person in list_persons(db=session, user=data["super_user"])} == {"Stigamo Person", "R3 Person"}
    assert [person.name for person in list_persons(db=session, user=data["super_user"], area_id=data["r3_person"].home_area_id)] == ["R3 Person"]


def test_super_user_r3_area_filter_does_not_leak_stigamo_persons(business_session):
    session, data = business_session

    people = list_persons(db=session, user=data["super_user"], area_id=data["r3_user"].area_id)

    assert [person.name for person in people] == ["R3 Person"]
    assert {person.business_id for person in people} == {data["r3"].id}
    assert all(person.home_area_id == data["r3_user"].area_id for person in people)


def test_non_super_cannot_filter_or_fetch_foreign_business_ids(business_session):
    session, data = business_session

    assert_http_status(404, list_users, business_id=data["r3"].id, db=session, admin=data["user"])
    assert_http_status(404, list_persons, db=session, user=data["user"], business_id=data["r3"].id)
    assert_http_status(404, get_person, data["r3_person"].id, session, data["user"])
    assert_http_status(
        404,
        update_person,
        data["r3_person"].id,
        PersonUpdate(name="Leak"),
        session,
        data["user"],
    )


def test_create_defaults_to_actor_business_and_rejects_foreign_ids(business_session):
    session, data = business_session

    created_person = create_person(
        PersonCreate(name="Ny Stigamo", home_area_id=data["stigamo_person"].home_area_id),
        session,
        data["user"],
    )
    created_activity = create_activity(
        ActivityCreate(label="Stigamo Pack", area_id=data["stigamo_person"].home_area_id),
        session,
        data["user"],
    )
    created_user = create_user(
        UserCreate(username="stigamo-new", roles=["leader"], area_id=data["stigamo_person"].home_area_id),
        session,
        data["user"],
    )

    assert created_person.business_id == data["stigamo"].id
    assert created_activity.business_id == data["stigamo"].id
    assert created_user.business_id == data["stigamo"].id
    assert_http_status(
        404,
        create_user,
        UserCreate(username="bad-r3", roles=["leader"], business_id=data["r3"].id),
        session,
        data["user"],
    )


def test_super_user_must_choose_business_when_create_cannot_infer(business_session):
    session, data = business_session

    assert_http_status(400, create_person, PersonCreate(name="Saknar verksamhet"), session, data["super_user"])
    assert_http_status(400, create_activity, ActivityCreate(label="Saknar verksamhet"), session, data["super_user"])
    assert_http_status(400, create_area, AreaCreate(code="X", name="Saknar verksamhet"), session, data["super_user"])
    assert_http_status(400, create_user, UserCreate(username="missing-business", roles=["leader"]), session, data["super_user"])

    r3_created = create_user(
        UserCreate(username="r3-created-by-super", roles=["leader"], business_id=data["r3"].id),
        session,
        data["super_user"],
    )
    assert r3_created.business_id == data["r3"].id


def test_duplicate_names_and_codes_are_scoped_per_business(business_session):
    session, data = business_session

    r3_person = create_person(
        PersonCreate(name="Stigamo Person", business_id=data["r3"].id, home_area_id=data["r3_person"].home_area_id),
        session,
        data["super_user"],
    )
    r3_activity = create_activity(
        ActivityCreate(label="GG Plock", business_id=data["r3"].id, area_id=data["r3_person"].home_area_id),
        session,
        data["super_user"],
    )
    r3_area = create_area(
        AreaCreate(business_id=data["r3"].id, code="GG", name="GG i R3"),
        session,
        data["super_user"],
    )

    assert r3_person.business_id == data["r3"].id
    assert r3_activity.business_id == data["r3"].id
    assert r3_area.business_id == data["r3"].id
    assert_http_status(
        409,
        create_person,
        PersonCreate(name="Stigamo Person", home_area_id=data["stigamo_person"].home_area_id),
        session,
        data["user"],
    )


def test_super_user_can_add_r3_area_without_changing_stigamo(business_session):
    session, data = business_session

    created = create_area(
        AreaCreate(business_id=data["r3"].id, code="MG", name="Mestergruppen R3", sort_order=2),
        session,
        data["super_user"],
    )

    assert created.business_id == data["r3"].id
    assert {area.code for area in list_areas(db=session, user=data["r3_user"])} == {"R3", "MG"}
    assert [area.code for area in list_areas(db=session, user=data["user"])] == ["GG"]


def test_delete_area_hard_deletes_empty_and_deactivates_linked_data(business_session):
    session, data = business_session

    empty_area = create_area(
        AreaCreate(business_id=data["r3"].id, code="TMP", name="Tomt område", sort_order=9),
        session,
        data["super_user"],
    )

    assert_http_status(404, delete_area, data["r3_user"].area_id, session, data["user"])
    delete_area(empty_area.id, session, data["super_user"])
    assert session.get(Area, empty_area.id) is None

    linked_area_id = data["r3_user"].area_id
    delete_area(linked_area_id, session, data["super_user"])

    linked_area = session.get(Area, linked_area_id)
    assert linked_area is not None
    assert linked_area.is_active is False
    assert [area.code for area in list_areas(db=session, user=data["r3_user"])] == []
    assert [area.code for area in list_areas(include_inactive=True, db=session, user=data["r3_user"])] == ["R3"]


def test_cross_business_area_activity_and_user_updates_are_blocked(business_session):
    session, data = business_session

    assert_http_status(
        409,
        update_activity,
        data["stigamo_activity"].id,
        ActivityUpdate(area_id=data["r3_person"].home_area_id),
        session,
        data["super_user"],
    )
    assert_http_status(
        409,
        update_person,
        data["stigamo_person"].id,
        PersonUpdate(home_activity_id=data["r3_activity"].id),
        session,
        data["super_user"],
    )
    assert_http_status(
        409,
        update_user,
        data["user"].id,
        UserUpdate(area_id=data["r3_user"].area_id),
        session,
        data["super_user"],
    )


def test_settings_are_separate_per_business_and_foreign_settings_are_hidden(business_session):
    session, data = business_session

    update_app_settings(AppSettingsUpdate(lock_foreign_schedule_cells=True), session, data["user"])
    update_app_settings(
        AppSettingsUpdate(lock_foreign_schedule_cells=False),
        session,
        data["super_user"],
        business_id=data["r3"].id,
    )

    assert get_app_settings(db=session, user=data["user"]).lock_foreign_schedule_cells is True
    assert get_app_settings(db=session, user=data["r3_user"]).lock_foreign_schedule_cells is False
    assert get_app_settings(db=session, user=data["super_user"], business_id=data["r3"].id).lock_foreign_schedule_cells is False
    assert_http_status(404, get_app_settings, business_id=data["r3"].id, db=session, user=data["user"])

    keys_by_business = {(row.business_id, row.key) for row in session.query(AppSetting).all()}
    assert (data["stigamo"].id, "lock_foreign_schedule_cells") in keys_by_business
    assert (data["r3"].id, "lock_foreign_schedule_cells") in keys_by_business


def test_public_api_defaults_to_stigamo_and_never_sums_globally(business_session, monkeypatch):
    session, data = business_session
    monkeypatch.setattr(public.settings, "EXCEL_API_TOKEN", "token")
    session.add_all(
        [
            ScheduleCell(
                id=1,
                year=2026,
                week=21,
                weekday=1,
                hour=7,
                minute_start=0,
                minute_end=60,
                person_id=data["stigamo_person"].id,
                activity_id=data["stigamo_activity"].id,
                updated_by=data["user"].id,
            ),
            ScheduleCell(
                id=2,
                year=2026,
                week=21,
                weekday=1,
                hour=7,
                minute_start=0,
                minute_end=60,
                person_id=data["r3_person"].id,
                activity_id=data["r3_activity"].id,
                updated_by=data["r3_user"].id,
            ),
        ]
    )
    session.commit()

    assert public.get_hours_day(day=None, year=2026, week=21, weekday=1, activity="GG_PLOCK", business=None, token="token", db=session) == "1"
    assert public.get_hours_day(day=None, year=2026, week=21, weekday=1, activity="R3_LEDIG", business=None, token="token", db=session) == "0"
    assert public.get_hours_day(day=None, year=2026, week=21, weekday=1, activity="R3_LEDIG", business="R3", token="token", db=session) == "1"
    default_summary = public.get_summary_day(day=None, year=2026, week=21, weekday=1, business=None, token="token", db=session)
    r3_summary = public.get_summary_day(day=None, year=2026, week=21, weekday=1, business="R3", token="token", db=session)
    assert "GG_PLOCK" in default_summary
    assert "R3_LEDIG" not in default_summary
    assert "R3_LEDIG" in r3_summary


def test_planning_revision_keys_are_business_scoped_and_change_on_visible_cells(business_session):
    session, data = business_session

    before = get_schedule_revision(year=2026, week=21, weekday=1, area_id=None, business_id=None, db=session, user=data["user"])["revision_key"]
    overview_before = get_overview_revision(year=2026, week=21, area_id=None, business_id=None, db=session, user=data["user"])["revision_key"]

    session.add(
        ScheduleCell(
            id=10,
            year=2026,
            week=21,
            weekday=1,
            hour=7,
            minute_start=0,
            minute_end=60,
            person_id=data["r3_person"].id,
            activity_id=data["r3_activity"].id,
            updated_by=data["r3_user"].id,
        )
    )
    session.commit()

    assert get_schedule_revision(year=2026, week=21, weekday=1, area_id=None, business_id=None, db=session, user=data["user"])["revision_key"] == before
    assert get_overview_revision(year=2026, week=21, area_id=None, business_id=None, db=session, user=data["user"])["revision_key"] == overview_before

    session.add(
        ScheduleCell(
            id=11,
            year=2026,
            week=21,
            weekday=1,
            hour=7,
            minute_start=0,
            minute_end=60,
            person_id=data["stigamo_person"].id,
            activity_id=data["stigamo_activity"].id,
            updated_by=data["user"].id,
        )
    )
    session.commit()

    assert get_schedule_revision(year=2026, week=21, weekday=1, area_id=None, business_id=None, db=session, user=data["user"])["revision_key"] != before
    assert get_overview_revision(year=2026, week=21, area_id=None, business_id=None, db=session, user=data["user"])["revision_key"] != overview_before
