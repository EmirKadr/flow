from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models import Area, User
from app.backend.routers import auth as auth_router
from app.backend.routers import users as users_router
from app.backend.schemas import LoginRequest, UserCreate, UserUpdate
from app.backend.security import verify_password


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Area.__table__.create(engine)
    User.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        User.__table__.drop(engine)
        Area.__table__.drop(engine)
        engine.dispose()


@pytest.fixture
def admin_user():
    return User(id=999, username="admin", role="admin", is_active=True)


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
