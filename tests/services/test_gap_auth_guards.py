"""Auth-guards (routers/auth.py): två gränsfall som ska ge 409 utan sidoeffekter.

1. login med tvetydigt Noman: två aktiva personer delar noman "100". Auto-skapandet
   av person-user ska vägra (409) och INTE skapa någon User.
2. set-password när lösenord redan är satt (hash finns, must_change_password=False):
   ska ge 409 "Lösenord är redan skapat" och lämna hashen orörd.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.login_rate_limit import login_rate_limiter
from app.backend.main import app
from app.backend.models import Business, Person, User
from app.backend.security import hash_password


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    session.add(Business(id=1, code="STIGAMO", name="Stigamo", sort_order=1, is_active=True))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    # Rensa den processlokala rate-limitern så testerna inte påverkar varandra.
    login_rate_limiter._failures.clear()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        login_rate_limiter._failures.clear()


def test_login_duplicate_noman_conflicts_and_creates_no_user(client, db_session):
    # Två aktiva personer delar samma Noman-namn "100".
    db_session.add_all(
        [
            Person(id=1, business_id=1, name="Arne Ek", noman="100", is_active=True),
            Person(id=2, business_id=1, name="Bea Alm", noman="100", is_active=True),
        ]
    )
    db_session.commit()

    # Ingen User heter "100" ännu -> login går via auto-create av person-user.
    assert db_session.query(User).filter_by(username="100").count() == 0

    response = client.post("/api/auth/login", json={"username": "100", "password": ""})

    assert response.status_code == 409, response.text
    assert "Flera personer har samma Noman-namn" in response.json()["detail"]

    # Ingen User ska ha auto-skapats av det tvetydiga försöket.
    db_session.expire_all()
    assert db_session.query(User).filter_by(username="100").count() == 0
    assert db_session.query(User).count() == 0


def test_set_password_conflicts_when_already_set_and_hash_unchanged(client, db_session):
    original_hash = hash_password("secret123")
    user = User(
        id=1,
        username="arne",
        password_hash=original_hash,
        display_name="Arne Ek",
        role="leader",
        roles=["leader"],
        business_id=1,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    db_session.commit()

    # Logga in med rätt lösenord -> 200, sessionen sätts.
    login = client.post("/api/auth/login", json={"username": "arne", "password": "secret123"})
    assert login.status_code == 200, login.text

    # Lösenordet är redan satt (hash finns, must_change_password=False) -> 409.
    response = client.post("/api/auth/set-password", json={"password": "newpassword1"})
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Lösenord är redan skapat"

    # Hashen ska vara oförändrad.
    db_session.expire_all()
    refreshed = db_session.get(User, 1)
    assert refreshed.password_hash == original_hash
    assert refreshed.must_change_password is False
