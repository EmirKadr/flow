"""Authz-kontrakt för POST /api/workflow-data/source (_assert_workflow_source_allowed).

Vi monkeypatchar INTE själva behörighetshjälparen — vi driver den riktiga
kedjan get_role_view_access -> can_use_allocation_process / can_access_view och
verifierar statuskoder + felmeddelanden. Alla fyra fall avvisas innan någon
källhämtning sker, så ingen nätverks-/datakälla rörs.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import Business, User
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
    session.add_all(
        [
            # Vanlig inloggad arbetsledare utan allocationProcess/productivity i
            # role-view-access (standard leader-default saknar båda).
            User(
                username="leader1", password_hash=hash_password("pass"),
                role="leader", roles=["leader"],
                business_id=1, is_active=True, must_change_password=False,
            ),
            # Super user passerar alla behörighetskontroller -> kan nå källkontrollen.
            User(
                username="root", password_hash=hash_password("pass"),
                role="super_user", roles=["super_user"],
                business_id=1, is_active=True, must_change_password=False,
            ),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def login(client, username):
    response = client.post("/api/auth/login", json={"username": username, "password": "pass"})
    assert response.status_code == 200, response.text
    return client


def post_source(client, feature, source_key, flow_id=""):
    return client.post(
        "/api/workflow-data/source",
        json={"feature": feature, "flow_id": flow_id, "source_key": source_key},
    )


def test_allocation_without_process_edit_is_forbidden(client):
    """feature=allocation utan can_use_allocation_process (edit) -> 403."""
    login(client, "leader1")
    # source_key är i sig giltig för flödet, men behörigheten avvisas först.
    response = post_source(client, "allocation", "orders", flow_id="ordersaldo")
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Bearbeta kräver behörighet"


def test_productivity_without_view_is_forbidden(client):
    """feature=productivity utan productivity-view -> 403."""
    login(client, "leader1")
    response = post_source(client, "productivity", "pick")
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Sidan kräver behörighet"


def test_allocation_source_outside_flow_map_is_bad_request(client):
    """Behörig användare, giltig feature, men source_key utanför flödets karta -> 400."""
    login(client, "root")
    response = post_source(client, "allocation", "inte_en_riktig_kalla_zz", flow_id="ordersaldo")
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "API-källan hör inte till flödet."


def test_productivity_source_outside_map_is_bad_request(client):
    """Behörig användare, feature=productivity, source_key utanför kartan -> 400."""
    login(client, "root")
    response = post_source(client, "productivity", "inte_en_riktig_kalla_zz")
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "API-källan hör inte till flödet."


def test_unknown_feature_is_bad_request(client):
    """Okänd feature -> 400, oavsett behörighet (permissiongrenar hoppas över)."""
    login(client, "leader1")
    response = post_source(client, "nonsense", "pick")
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Okänd workflow-källa."
