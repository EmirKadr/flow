from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models import (
    Activity,
    Area,
    AuditLog,
    Person,
    PersonScheduleTemplate,
    ScheduleCell,
    ScheduleFreezeState,
    User,
)
from app.backend.routers import person_schedules
from app.backend.schemas import TemplateUpdate
from app.backend.template_service import get_template_hours

# put_schedule fryser gardagen innan mallen andras (se schedule_freeze), sa
# riggen behover aven frys-, cell- och audittabellerna.
_TABLES = (
    Area.__table__,
    Activity.__table__,
    Person.__table__,
    PersonScheduleTemplate.__table__,
    ScheduleCell.__table__,
    ScheduleFreezeState.__table__,
    AuditLog.__table__,
)


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in _TABLES:
        table.create(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def close_session(engine, session):
    session.close()
    for table in reversed(_TABLES):
        table.drop(engine)
    engine.dispose()


def test_hourly_worker_flag_is_not_saved_as_off_days(monkeypatch):
    monkeypatch.setattr(person_schedules, "audit_log", lambda *args, **kwargs: None)
    engine, session = make_session()
    try:
        person = Person(
            name="Timmis Test",
            competencies=[],
            has_fixed_schedule=True,
            is_active=True,
            sort_order=1,
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        response = person_schedules.put_schedule(
            person.id,
            TemplateUpdate(has_fixed_schedule=False, days=[]),
            session,
            User(id=1, username="admin", role="admin", is_active=True),
        )

        assert response.has_fixed_schedule is False
        assert session.query(PersonScheduleTemplate).count() == 0
        assert get_template_hours(session, person.id, 1) is None

        person_schedules.put_schedule(
            person.id,
            TemplateUpdate(has_fixed_schedule=True, days=[]),
            session,
            User(id=1, username="admin", role="admin", is_active=True),
        )
        assert get_template_hours(session, person.id, 1) == {7, 8, 9, 10, 11, 13, 14, 15}
    finally:
        close_session(engine, session)
