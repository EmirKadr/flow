from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import pytest

from app.backend.bootstrap_local import _sync_lightweight_sqlite_columns, _sync_sqlite_business_constraints
from app.backend.database import Base
from app.backend.models import Activity, Area, Business, Person, PersonScheduleTemplate, ScheduleCell
from app.backend.seed import ACTIVITIES, AREAS, PERSONS, remove_duplicate_persons, seed_persons


def test_seed_contains_ehandel_area_and_default_activities():
    areas_by_code = {area["code"]: area for area in AREAS}
    activity_codes = {activity["code"] for activity in ACTIVITIES}

    assert areas_by_code["EH"]["name"] == "E-Handel"
    assert {"EH_PLOCK", "EH_PACK", "EH_STOD", "EH_VAS"} <= activity_codes


def test_seed_removes_existing_duplicate_person_names():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        business = Business(code="STIGAMO", name="Stigamo", sort_order=1)
        session.add(business)
        session.flush()
        area = Area(code="GG", name="Granngården", sort_order=1, business_id=business.id)
        session.add(area)
        session.flush()
        activity = Activity(
            code="GG_VM",
            label="GG VM",
            business_id=business.id,
            area_id=area.id,
            color="#ffffff",
            category="work",
            sort_order=1,
            is_active=True,
        )
        duplicate_name = PERSONS[0]
        kept = Person(name=duplicate_name, business_id=business.id, home_area_id=area.id, competencies=[])
        duplicate = Person(name=duplicate_name, business_id=business.id, home_area_id=area.id, competencies=[])
        session.add_all(
            [
                activity,
                kept,
                duplicate,
            ]
        )
        session.flush()
        session.add_all(
            [
                ScheduleCell(
                    year=2026,
                    week=21,
                    weekday=1,
                    hour=7,
                    person_id=duplicate.id,
                    activity_id=activity.id,
                ),
                PersonScheduleTemplate(person_id=duplicate.id, weekday=1, start_hour=7, end_hour=16),
            ]
        )
        session.flush()

        remove_duplicate_persons(session)
        seed_persons(session, business, {"GG": area})
        session.flush()

        duplicates = session.query(Person).filter_by(name=duplicate_name).all()
        assert len(duplicates) == 1
        assert duplicates[0].id == kept.id
        assert duplicates[0].home_activity_id == activity.id
        assert session.query(ScheduleCell).filter_by(person_id=duplicate.id).count() == 0
        assert session.query(PersonScheduleTemplate).filter_by(person_id=duplicate.id).count() == 0
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_local_bootstrap_migrates_legacy_sqlite_business_constraints(tmp_path):
    db_path = tmp_path / "legacy-local.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255),
                display_name VARCHAR(100),
                role VARCHAR(20) NOT NULL,
                is_active BOOLEAN NOT NULL,
                must_change_password BOOLEAN NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE areas (
                id INTEGER PRIMARY KEY,
                code VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100) NOT NULL,
                sort_order INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                code VARCHAR(40) NOT NULL UNIQUE,
                label VARCHAR(60) NOT NULL,
                area_id INTEGER,
                summary_activity_id INTEGER,
                color VARCHAR(20) NOT NULL,
                category VARCHAR(20) NOT NULL,
                sort_order INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL,
                required_competency VARCHAR(40)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE app_settings (
                "key" VARCHAR(80) NOT NULL PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
                updated_by INTEGER
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO areas (id, code, name, sort_order, is_active) VALUES (1, 'GG', 'Granngården', 1, 1)"
        )
        connection.exec_driver_sql(
            """
            INSERT INTO activities (id, code, label, area_id, color, category, sort_order, is_active)
            VALUES (1, 'LEDIG', 'Ledig', NULL, '#dddddd', 'absence', 91, 1)
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO app_settings (key, value, updated_by) VALUES ('lock_foreign_schedule_cells', 'false', NULL)"
        )

    Base.metadata.create_all(engine)
    _sync_lightweight_sqlite_columns(engine)
    _sync_sqlite_business_constraints(engine)

    with engine.begin() as connection:
        stigamo_id = connection.exec_driver_sql("SELECT id FROM businesses WHERE code = 'STIGAMO'").scalar_one()
        r3_id = connection.exec_driver_sql("SELECT id FROM businesses WHERE code = 'R3'").scalar_one()
        assert connection.exec_driver_sql("SELECT business_id FROM activities WHERE code = 'LEDIG'").scalar_one() == stigamo_id

        connection.exec_driver_sql(
            "INSERT INTO areas (business_id, code, name, sort_order, is_active) VALUES (?, 'GG', 'GG R3', 1, 1)",
            (r3_id,),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO activities (business_id, code, label, area_id, color, category, sort_order, is_active)
            VALUES (?, 'LEDIG', 'Ledig R3', NULL, '#dddddd', 'absence', 91, 1)
            """,
            (r3_id,),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO app_settings (business_id, key, value, updated_by)
            VALUES (?, 'lock_foreign_schedule_cells', 'true', NULL)
            """,
            (r3_id,),
        )

        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "INSERT INTO activities (business_id, code, label, color, category, sort_order, is_active) VALUES (?, 'LEDIG', 'Duplicate', '#fff', 'absence', 1, 1)",
                (stigamo_id,),
            )
