import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Activity, Area, Business, Person, ScheduleCell, User
from app.backend.routers.schedule import split_cell
from app.backend.schemas import SegmentVersionRef, SplitCellRequest, SplitSegmentRange


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def close_session(engine, session):
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def seed_schedule_split_data(session):
    business = Business(code="FLOW", name="Flow", sort_order=1, is_active=True)
    session.add(business)
    session.flush()
    area = Area(business_id=business.id, code="GG", name="GG", sort_order=1, is_active=True)
    session.add(area)
    session.flush()
    activity = Activity(
        business_id=business.id,
        code="GG_PLOCK",
        label="GG Plock",
        area_id=area.id,
        color="#86efac",
        category="work",
        sort_order=1,
        is_active=True,
    )
    person = Person(
        business_id=business.id,
        name="Split Person",
        home_area_id=area.id,
        competencies=[],
        has_fixed_schedule=False,
        is_active=True,
        sort_order=1,
    )
    user = User(
        username="planner",
        role="admin",
        roles=["admin"],
        business_id=business.id,
        area_id=area.id,
        is_active=True,
    )
    session.add_all([activity, person, user])
    session.commit()
    return activity, person, user


def test_split_cell_uses_requested_first_minutes_and_can_merge_back():
    engine, session = make_session()
    try:
        activity, person, user = seed_schedule_split_data(session)
        source = ScheduleCell(
            year=2026,
            week=24,
            weekday=2,
            hour=8,
            minute_start=0,
            minute_end=60,
            person_id=person.id,
            activity_id=activity.id,
            empty_override=False,
            version=1,
            updated_by=user.id,
        )
        session.add(source)
        session.commit()

        split_response = split_cell(
            SplitCellRequest(
                year=2026,
                week=24,
                weekday=2,
                hour=8,
                person_id=person.id,
                split_minute=17,
                segments=[SegmentVersionRef(minute_start=0, minute_end=60, expected_version=1)],
            ),
            db=session,
            user=user,
        )

        split_segments = split_response["segments"]
        assert [(item["minute_start"], item["minute_end"]) for item in split_segments] == [(0, 17), (17, 60)]
        assert {item["activity_id"] for item in split_segments} == {activity.id}

        merge_response = split_cell(
            SplitCellRequest(
                year=2026,
                week=24,
                weekday=2,
                hour=8,
                person_id=person.id,
                merge_minute_start=17,
                segments=[
                    SegmentVersionRef(
                        minute_start=item["minute_start"],
                        minute_end=item["minute_end"],
                        expected_version=item["version"],
                    )
                    for item in split_segments
                ],
            ),
            db=session,
            user=user,
        )

        assert [(item["minute_start"], item["minute_end"]) for item in merge_response["segments"]] == [(0, 60)]
        assert merge_response["segments"][0]["activity_id"] == activity.id
    finally:
        close_session(engine, session)


def test_split_cell_can_create_three_custom_parts_and_merge_back():
    engine, session = make_session()
    try:
        activity, person, user = seed_schedule_split_data(session)
        source = ScheduleCell(
            year=2026,
            week=24,
            weekday=2,
            hour=10,
            minute_start=0,
            minute_end=60,
            person_id=person.id,
            activity_id=activity.id,
            empty_override=False,
            version=1,
            updated_by=user.id,
        )
        session.add(source)
        session.commit()

        split_response = split_cell(
            SplitCellRequest(
                year=2026,
                week=24,
                weekday=2,
                hour=10,
                person_id=person.id,
                split_segments=[
                    SplitSegmentRange(minute_start=0, minute_end=20),
                    SplitSegmentRange(minute_start=20, minute_end=40),
                    SplitSegmentRange(minute_start=40, minute_end=60),
                ],
                segments=[SegmentVersionRef(minute_start=0, minute_end=60, expected_version=1)],
            ),
            db=session,
            user=user,
        )

        split_segments = split_response["segments"]
        assert [(item["minute_start"], item["minute_end"]) for item in split_segments] == [
            (0, 20),
            (20, 40),
            (40, 60),
        ]
        assert {item["activity_id"] for item in split_segments} == {activity.id}

        merge_response = split_cell(
            SplitCellRequest(
                year=2026,
                week=24,
                weekday=2,
                hour=10,
                person_id=person.id,
                merge_minute_start=20,
                segments=[
                    SegmentVersionRef(
                        minute_start=item["minute_start"],
                        minute_end=item["minute_end"],
                        expected_version=item["version"],
                    )
                    for item in split_segments
                ],
            ),
            db=session,
            user=user,
        )

        assert [(item["minute_start"], item["minute_end"]) for item in merge_response["segments"]] == [(0, 60)]
        assert merge_response["segments"][0]["activity_id"] == activity.id
        remaining = session.query(ScheduleCell).filter_by(person_id=person.id, hour=10).all()
        assert len(remaining) == 1
    finally:
        close_session(engine, session)


def test_split_empty_cell_uses_requested_first_minutes():
    engine, session = make_session()
    try:
        _activity, person, user = seed_schedule_split_data(session)

        response = split_cell(
            SplitCellRequest(
                year=2026,
                week=24,
                weekday=2,
                hour=9,
                person_id=person.id,
                split_minute=17,
                segments=[],
            ),
            db=session,
            user=user,
        )

        assert [(item["minute_start"], item["minute_end"]) for item in response["segments"]] == [(0, 17), (17, 60)]
        assert [item["activity_id"] for item in response["segments"]] == [None, None]
    finally:
        close_session(engine, session)


def test_split_empty_cell_can_create_three_custom_parts():
    engine, session = make_session()
    try:
        _activity, person, user = seed_schedule_split_data(session)

        response = split_cell(
            SplitCellRequest(
                year=2026,
                week=24,
                weekday=2,
                hour=11,
                person_id=person.id,
                split_segments=[
                    SplitSegmentRange(minute_start=0, minute_end=20),
                    SplitSegmentRange(minute_start=20, minute_end=40),
                    SplitSegmentRange(minute_start=40, minute_end=60),
                ],
                segments=[],
            ),
            db=session,
            user=user,
        )

        assert [(item["minute_start"], item["minute_end"]) for item in response["segments"]] == [
            (0, 20),
            (20, 40),
            (40, 60),
        ]
        assert [item["activity_id"] for item in response["segments"]] == [None, None, None]
    finally:
        close_session(engine, session)


def test_split_cell_rejects_non_contiguous_custom_parts():
    engine, session = make_session()
    try:
        _activity, person, user = seed_schedule_split_data(session)

        with pytest.raises(HTTPException) as exc_info:
            split_cell(
                SplitCellRequest(
                    year=2026,
                    week=24,
                    weekday=2,
                    hour=12,
                    person_id=person.id,
                    split_segments=[
                        SplitSegmentRange(minute_start=0, minute_end=20),
                        SplitSegmentRange(minute_start=30, minute_end=60),
                    ],
                    segments=[],
                ),
                db=session,
                user=user,
            )

        assert getattr(exc_info.value, "status_code", None) == 400
        assert "2-4 sammanhangande delar" in str(getattr(exc_info.value, "detail", ""))
    finally:
        close_session(engine, session)
