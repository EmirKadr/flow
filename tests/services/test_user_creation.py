from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import AppSetting, Area, AuditLog, Business, Person, PersonScheduleTemplate, ScheduleCell, User
from app.backend.routers import auth as auth_router
from app.backend.routers import users as users_router
from app.backend.schemas import LoginRequest, PasswordSetRequest, UserCreate, UserUpdate
from app.backend.security import verify_password


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def admin_user():
    return User(id=999, username="regular-admin", role="admin", is_active=True)


@pytest.fixture
def super_user():
    return User(id=1000, username="root", role="super_user", roles=["super_user"], is_active=True)


def test_create_user_without_password_marks_password_setup_required(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    result = users_router.create_user(
        UserCreate(username="anna", display_name="Anna Andersson", role="leader"),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="anna").one()
    assert result.must_change_password is True
    assert saved.password_hash is None
    assert saved.must_change_password is True


def test_create_user_with_password_hashes_password(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    result = users_router.create_user(
        UserCreate(username="bo", password="hemligt123", role="leader"),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="bo").one()
    assert result.must_change_password is False
    assert saved.password_hash is not None
    assert verify_password("hemligt123", saved.password_hash) is True
    assert saved.must_change_password is False


def test_create_user_always_saves_active_user(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    result = users_router.create_user(
        UserCreate(username="always-active", role="leader", is_active=False),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="always-active").one()
    assert result.is_active is True
    assert saved.is_active is True


def test_create_viewer_user(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    result = users_router.create_user(
        UserCreate(username="viola", display_name="Viola Visning", role="viewer"),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="viola").one()
    assert result.role == "viewer"
    assert result.roles == ["viewer"]
    assert saved.role == "viewer"
    assert saved.roles == ["viewer"]


def test_create_user_with_multiple_roles(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    result = users_router.create_user(
        UserCreate(username="mira", display_name="Mira Multi", roles=["viewer", "leader"]),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="mira").one()
    assert result.role == "leader"
    assert result.roles == ["viewer", "leader"]
    assert saved.role == "leader"
    assert saved.roles == ["viewer", "leader"]


def test_create_lagerkontorist_user(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    result = users_router.create_user(
        UserCreate(username="lina", display_name="Lina Lager", roles=["warehouse_clerk"]),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="lina").one()
    assert result.role == "warehouse_clerk"
    assert result.roles == ["warehouse_clerk"]
    assert saved.role == "warehouse_clerk"
    assert saved.roles == ["warehouse_clerk"]


def test_create_bemanningsansvarig_user(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    result = users_router.create_user(
        UserCreate(username="petra", display_name="Petra flow", roles=["staffing_manager"]),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="petra").one()
    assert result.role == "staffing_manager"
    assert result.roles == ["staffing_manager"]
    assert saved.role == "staffing_manager"
    assert saved.roles == ["staffing_manager"]


def test_only_super_user_can_create_super_user(monkeypatch, db_session, admin_user, super_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        users_router.create_user(
            UserCreate(username="not-root", roles=["super_user"]),
            db_session,
            admin_user,
        )

    assert exc_info.value.status_code == 403

    result = users_router.create_user(
        UserCreate(username="new-root", roles=["super_user"]),
        db_session,
        super_user,
    )

    saved = db_session.query(User).filter_by(username="new-root").one()
    assert result.role == "super_user"
    assert result.roles == ["super_user"]
    assert result.is_super_user is True
    assert saved.role == "super_user"
    assert saved.roles == ["super_user"]


def test_create_artikelplacerare_user(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    result = users_router.create_user(
        UserCreate(username="arvid", display_name="Arvid Artikel", roles=["article_placer"]),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="arvid").one()
    assert result.role == "article_placer"
    assert result.roles == ["article_placer"]
    assert saved.role == "article_placer"
    assert saved.roles == ["article_placer"]


def test_create_user_with_default_area(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)
    area = Area(code="MG", name="Mestergruppen", sort_order=1, is_active=True)
    db_session.add(area)
    db_session.commit()
    db_session.refresh(area)

    result = users_router.create_user(
        UserCreate(username="maria", display_name="Maria MG", role="leader", area_id=area.id),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="maria").one()
    assert result.area_id == area.id
    assert saved.area_id == area.id


def test_update_user_can_change_multiple_roles(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)
    user = User(
        username="nina",
        password_hash=None,
        display_name="Nina",
        role="viewer",
        roles=["viewer"],
        is_active=True,
        must_change_password=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    result = users_router.update_user(
        user.id,
        UserUpdate(roles=["viewer", "leader"]),
        db_session,
        admin_user,
    )

    saved = db_session.query(User).filter_by(username="nina").one()
    assert result.role == "leader"
    assert result.roles == ["viewer", "leader"]
    assert saved.role == "leader"
    assert saved.roles == ["viewer", "leader"]


def test_update_user_rejects_inactivation(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)
    user = User(username="sara", role="leader", roles=["leader"], is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    with pytest.raises(HTTPException) as exc_info:
        users_router.update_user(
            user.id,
            UserUpdate(is_active=False),
            db_session,
            admin_user,
        )

    assert exc_info.value.status_code == 400
    assert "Ta bort användaren" in exc_info.value.detail
    assert db_session.get(User, user.id).is_active is True


def test_update_user_reactivates_legacy_inactive_user(monkeypatch, db_session, admin_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)
    user = User(username="legacy", display_name="Legacy", role="leader", roles=["leader"], is_active=False)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    result = users_router.update_user(
        user.id,
        UserUpdate(display_name="Legacy Aktiv"),
        db_session,
        admin_user,
    )

    saved = db_session.get(User, user.id)
    assert result.is_active is True
    assert saved.is_active is True
    assert saved.display_name == "Legacy Aktiv"


def test_delete_user_removes_account_and_clears_user_references(db_session):
    business = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    db_session.add(business)
    db_session.flush()
    admin = User(username="admin-delete", role="admin", roles=["admin"], business_id=business.id, is_active=True)
    target = User(username="old-user", role="leader", roles=["leader"], business_id=business.id, is_active=True)
    person = Person(business_id=business.id, name="Planerbar", competencies=[], sort_order=1)
    db_session.add_all([admin, target, person])
    db_session.flush()
    cell = ScheduleCell(
        id=1,
        year=2026,
        week=21,
        weekday=1,
        hour=7,
        minute_start=0,
        minute_end=60,
        person_id=person.id,
        updated_by=target.id,
    )
    template = PersonScheduleTemplate(person_id=person.id, weekday=1, updated_by=target.id)
    setting = AppSetting(business_id=business.id, key="lock_foreign_schedule_cells", value="true", updated_by=target.id)
    old_audit = AuditLog(
        business_id=business.id,
        entity_type="person",
        entity_id=person.id,
        action="update",
        user_id=target.id,
    )
    db_session.add_all([cell, template, setting, old_audit])
    db_session.commit()

    users_router.delete_user(target.id, db_session, admin)

    assert db_session.get(User, target.id) is None
    assert db_session.get(ScheduleCell, cell.id).updated_by is None
    assert db_session.get(PersonScheduleTemplate, template.id).updated_by is None
    assert db_session.query(AppSetting).filter_by(business_id=business.id, key=setting.key).one().updated_by is None
    assert db_session.get(AuditLog, old_audit.id).user_id is None
    delete_entry = db_session.query(AuditLog).filter_by(entity_type="user", entity_id=target.id, action="delete").one()
    assert delete_entry.user_id == admin.id
    assert delete_entry.old_value["username"] == "old-user"
    assert delete_entry.new_value is None


def test_delete_user_rejects_self_delete(db_session):
    admin = User(username="admin-self", role="admin", roles=["admin"], is_active=True)
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    with pytest.raises(HTTPException) as exc_info:
        users_router.delete_user(admin.id, db_session, admin)

    assert exc_info.value.status_code == 409
    assert db_session.get(User, admin.id) is not None


def test_only_super_user_can_add_or_remove_super_user_role(monkeypatch, db_session, admin_user, super_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)
    user = User(
        username="nina",
        password_hash=None,
        display_name="Nina",
        role="leader",
        roles=["leader"],
        is_active=True,
        must_change_password=True,
    )
    db_session.add(user)
    db_session.add(User(username="backup-admin", role="admin", roles=["admin"], is_active=True))
    db_session.commit()
    db_session.refresh(user)

    with pytest.raises(HTTPException) as exc_info:
        users_router.update_user(
            user.id,
            UserUpdate(roles=["leader", "super_user"]),
            db_session,
            admin_user,
        )

    assert exc_info.value.status_code == 403

    result = users_router.update_user(
        user.id,
        UserUpdate(roles=["leader", "super_user"]),
        db_session,
        super_user,
    )
    assert result.roles == ["leader", "super_user"]
    assert result.is_super_user is True

    with pytest.raises(HTTPException) as exc_info:
        users_router.update_user(
            user.id,
            UserUpdate(roles=["leader"]),
            db_session,
            admin_user,
        )

    assert exc_info.value.status_code == 403

    result = users_router.update_user(
        user.id,
        UserUpdate(roles=["leader"]),
        db_session,
        super_user,
    )
    assert result.roles == ["leader"]
    assert result.is_super_user is False


def test_passwordless_user_can_log_in_with_empty_password(db_session):
    user = User(
        username="cecilia",
        password_hash=None,
        display_name="Cecilia",
        role="leader",
        is_active=True,
        must_change_password=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    request = SimpleNamespace(session={})
    result = auth_router.login(LoginRequest(username="cecilia", password=""), request, db_session)

    assert request.session["user_id"] == user.id
    assert result.must_change_password is True


def test_passwordless_user_rejects_non_empty_password(db_session):
    user = User(
        username="david",
        password_hash=None,
        display_name="David",
        role="leader",
        is_active=True,
        must_change_password=True,
    )
    db_session.add(user)
    db_session.commit()

    request = SimpleNamespace(session={})
    with pytest.raises(HTTPException) as exc_info:
        auth_router.login(LoginRequest(username="david", password="secret"), request, db_session)

    assert exc_info.value.status_code == 401
    assert "tomt" in exc_info.value.detail


def test_set_password_writes_audit_without_password_value(db_session):
    user = User(
        username="cecilia",
        password_hash=None,
        display_name="Cecilia",
        role="leader",
        is_active=True,
        must_change_password=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    result = auth_router.set_password(
        PasswordSetRequest(password="nyttlosen123"),
        user,
        db_session,
    )

    assert result.must_change_password is False
    entry = db_session.query(AuditLog).filter_by(entity_type="user", action="set_password").one()
    assert entry.entity_id == user.id
    assert entry.user_id == user.id
    assert entry.old_value["password_hash_set"] is False
    assert entry.new_value["password_hash_set"] is True
    assert "nyttlosen123" not in str(entry.old_value)
    assert "nyttlosen123" not in str(entry.new_value)
