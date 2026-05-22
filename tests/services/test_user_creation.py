from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models import Area, AuditLog, User
from app.backend.routers import auth as auth_router
from app.backend.routers import users as users_router
from app.backend.schemas import LoginRequest, PasswordSetRequest, UserCreate, UserUpdate
from app.backend.security import verify_password


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Area.__table__.create(engine)
    User.__table__.create(engine)
    AuditLog.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        AuditLog.__table__.drop(engine)
        User.__table__.drop(engine)
        Area.__table__.drop(engine)
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
