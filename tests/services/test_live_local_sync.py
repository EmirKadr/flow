from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import pytest

from app.backend import prepare_local_database
from app.backend.database import Base
from app.backend.models import Activity, Area, Person, User
from app.backend.sync_live_to_local import sync_database, sync_from_env


def sqlite_url(path):
    return f"sqlite:///{path.as_posix()}"


def test_sync_database_copies_live_rows_to_local_sqlite_file(tmp_path):
    source_path = tmp_path / "live.db"
    target_path = tmp_path / "local.db"
    source_engine = create_engine(sqlite_url(source_path))
    Base.metadata.create_all(source_engine)
    SessionLocal = sessionmaker(bind=source_engine)

    with SessionLocal() as session:
        area = Area(code="MG", name="Mestergruppen", sort_order=1, is_active=True)
        activity = Activity(
            code="MG_LKON",
            label="MG Lkon",
            area=area,
            color="#ffffff",
            category="work",
            sort_order=1,
            is_active=True,
        )
        session.add_all([area, activity])
        session.flush()
        person = Person(
            name="Anton Holmqvist",
            home_area=area,
            home_activity_id=activity.id,
            competencies=[],
            is_active=False,
            sort_order=7,
        )
        user = User(username="admin", role="admin", roles=["admin"], is_active=True)
        session.add_all([person, user])
        session.commit()

    stats = sync_database(sqlite_url(source_path), sqlite_url(target_path))

    assert stats["persons"] == 1
    target_engine = create_engine(sqlite_url(target_path))
    TargetSession = sessionmaker(bind=target_engine)
    with TargetSession() as session:
        copied = session.query(Person).one()
        copied.name = "Lokal ändring"
        session.commit()

    with SessionLocal() as session:
        assert session.query(Person).one().name == "Anton Holmqvist"


def test_sync_database_accepts_legacy_source_without_businesses(tmp_path):
    source_path = tmp_path / "legacy-live.db"
    target_path = tmp_path / "local.db"
    source_engine = create_engine(sqlite_url(source_path))
    with source_engine.begin() as connection:
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
            CREATE TABLE persons (
                id INTEGER PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                home_area_id INTEGER,
                home_activity_id INTEGER,
                competencies JSON NOT NULL,
                comment TEXT,
                has_fixed_schedule BOOLEAN NOT NULL,
                is_active BOOLEAN NOT NULL,
                sort_order INTEGER NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE app_settings (
                "key" VARCHAR(80) NOT NULL PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME,
                updated_by INTEGER
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO areas (id, code, name, sort_order, is_active) VALUES (1, 'GG', 'Granngården', 1, 1)"
        )
        connection.exec_driver_sql(
            """
            INSERT INTO persons (id, name, home_area_id, competencies, has_fixed_schedule, is_active, sort_order)
            VALUES (1, 'Lokal Person', 1, '[]', 1, 1, 1)
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO app_settings (key, value, updated_by) VALUES ('lock_foreign_schedule_cells', 'false', NULL)"
        )

    stats = sync_database(sqlite_url(source_path), sqlite_url(target_path))

    assert stats["businesses"] == 0
    assert stats["areas"] == 1
    assert stats["persons"] == 1
    assert stats["app_settings"] == 1

    target_engine = create_engine(sqlite_url(target_path))
    TargetSession = sessionmaker(bind=target_engine)
    with TargetSession() as session:
        default_business = session.execute(text("SELECT id FROM businesses WHERE code = 'STIGAMO'")).scalar_one()
        assert session.query(Area).one().business_id is None
        assert session.query(Person).one().business_id is None
        setting_business_id = session.execute(text("SELECT business_id FROM app_settings")).scalar_one()
        assert setting_business_id == default_business


def test_sync_database_refuses_non_sqlite_target(tmp_path):
    source_path = tmp_path / "live.db"

    with pytest.raises(ValueError, match="SQLite"):
        sync_database(sqlite_url(source_path), "postgresql+psycopg://postgres:postgres@localhost/flow")


def test_sync_from_env_skips_when_live_database_url_is_missing(monkeypatch):
    monkeypatch.delenv("LIVE_DATABASE_URL", raising=False)
    monkeypatch.delenv("FLOW_LIVE_DATABASE_URL", raising=False)

    assert sync_from_env() is False


def test_prepare_local_database_bootstraps_after_live_sync(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(prepare_local_database, "sync_from_env", lambda: True)
    monkeypatch.setattr(prepare_local_database, "bootstrap_local", lambda: calls.append("bootstrap"))

    prepare_local_database.main()

    assert calls == ["bootstrap"]
