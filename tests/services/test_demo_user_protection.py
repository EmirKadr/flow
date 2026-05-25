"""Tester för att demo-användaren inte kan tas bort, döpas om eller bli av med admin."""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Business, User
from app.backend.routers import users as users_router
from app.backend.schemas import UserUpdate
from app.backend.security import hash_password


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
def stigamo_business(db_session):
    business = Business(code="STIGAMO", name="Stigamo", sort_order=1, is_active=True)
    db_session.add(business)
    db_session.commit()
    return business


@pytest.fixture
def admin_user(db_session, stigamo_business):
    user = User(
        username="regular-admin",
        password_hash=hash_password("admin1234"),
        role="admin",
        roles=["admin"],
        business_id=stigamo_business.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def super_user(db_session, stigamo_business):
    user = User(
        username="root",
        password_hash=hash_password("root1234"),
        role="super_user",
        roles=["super_user"],
        business_id=stigamo_business.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def demo_user(db_session, stigamo_business):
    user = User(
        username="demo",
        password_hash=hash_password("demo1234"),
        display_name="Demo (presentationsläge)",
        role="admin",
        roles=["admin"],
        business_id=stigamo_business.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_demo_user_cannot_be_deleted(monkeypatch, db_session, admin_user, demo_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        users_router.delete_user(demo_user.id, db_session, admin_user)

    assert exc_info.value.status_code == 409
    assert "Demo" in exc_info.value.detail
    assert db_session.query(User).filter_by(username="demo").one_or_none() is not None


def test_demo_user_cannot_be_renamed(monkeypatch, db_session, super_user, demo_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        users_router.update_user(
            demo_user.id,
            UserUpdate(username="anything-else"),
            db_session,
            super_user,
        )

    assert exc_info.value.status_code == 409


def test_demo_user_cannot_lose_admin_role(monkeypatch, db_session, super_user, demo_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        users_router.update_user(
            demo_user.id,
            UserUpdate(roles=["viewer"]),
            db_session,
            super_user,
        )

    assert exc_info.value.status_code == 409


def test_demo_user_password_can_be_rotated_by_super_user(monkeypatch, db_session, super_user, demo_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    result = users_router.update_user(
        demo_user.id,
        UserUpdate(password="newpass1234"),
        db_session,
        super_user,
    )

    saved = db_session.query(User).filter_by(username="demo").one()
    from app.backend.security import verify_password

    assert verify_password("newpass1234", saved.password_hash) is True
    assert result.is_demo is True
    assert "admin" in result.roles


def test_demo_user_cannot_be_inactivated(monkeypatch, db_session, super_user, demo_user):
    monkeypatch.setattr(users_router.audit, "log", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        users_router.update_user(
            demo_user.id,
            UserUpdate(is_active=False),
            db_session,
            super_user,
        )

    assert exc_info.value.status_code == 409
