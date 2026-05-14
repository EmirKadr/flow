from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models import User
from app.backend.routers import auth as auth_router
from app.backend.routers import users as users_router
from app.backend.schemas import LoginRequest, UserCreate
from app.backend.security import verify_password


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    User.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        User.__table__.drop(engine)
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
