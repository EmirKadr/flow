"""Tester för IoT-reläet (routers/iot_relay.py).

Reläet är en fristående brevlåda för GPS-trackers/sensorer: enheter POSTar,
IoT-Dashboard-backenden pollar hem via GET /api/iot-relay/events.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.config import settings
from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import IotRelayEvent
from app.backend.routers import iot_relay

TOKEN = "test-relay-token"

GPS_BODY = {"deviceId": "ESP32-GPS-01", "lat": 57.6541, "lon": 14.1875, "sats": 8, "hdop": 1.5}
READING_BODY = {"deviceId": "ESP32-TEMP-01", "value": 4.2, "unit": "°C"}


@pytest.fixture()
def harness(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(settings, "IOT_RELAY_TOKEN", TOKEN)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), TestingSession
    finally:
        app.dependency_overrides.pop(get_db, None)


def _post_gps(client, **kwargs):
    return client.post(
        "/api/iot-relay/gps",
        json=kwargs.pop("body", GPS_BODY),
        headers=kwargs.pop("headers", {"X-IoT-Device-Token": TOKEN}),
        **kwargs,
    )


def test_gps_returns_503_when_token_not_configured(harness, monkeypatch):
    client, _ = harness
    monkeypatch.setattr(settings, "IOT_RELAY_TOKEN", "")
    assert _post_gps(client).status_code == 503


def test_gps_rejects_missing_and_wrong_token(harness):
    client, _ = harness
    assert client.post("/api/iot-relay/gps", json=GPS_BODY).status_code == 401
    assert _post_gps(client, headers={"X-IoT-Device-Token": "fel"}).status_code == 401


def test_gps_accepts_header_token(harness):
    client, _ = harness
    response = _post_gps(client)
    assert response.status_code == 200
    assert response.json() == {"ok": True, "id": 1}


def test_gps_accepts_query_token(harness):
    client, _ = harness
    response = client.post(f"/api/iot-relay/gps?token={TOKEN}", json=GPS_BODY, headers={})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_gps_requires_device_id_and_numeric_coordinates(harness):
    client, _ = harness
    assert _post_gps(client, body={"lat": 1, "lon": 2}).status_code == 400
    assert _post_gps(client, body={"deviceId": "X", "lon": 2}).status_code == 400
    assert _post_gps(client, body={"deviceId": "X", "lat": "abc", "lon": 2}).status_code == 400


def test_gps_rejects_oversized_payload(harness):
    client, _ = harness
    huge = {**GPS_BODY, "junk": "x" * 20_000}
    assert _post_gps(client, body=huge).status_code == 413


def test_reading_roundtrip(harness):
    client, _ = harness
    response = client.post(
        "/api/iot-relay/reading", json=READING_BODY, headers={"X-IoT-Device-Token": TOKEN}
    )
    assert response.status_code == 200

    events = client.get(f"/api/iot-relay/events?token={TOKEN}").json()
    assert events["latest"] == 1
    entry = events["entries"][0]
    assert entry["kind"] == "reading"
    assert entry["deviceId"] == "ESP32-TEMP-01"
    assert entry["payload"] == READING_BODY


def test_events_requires_token(harness):
    client, _ = harness
    assert client.get("/api/iot-relay/events").status_code == 422  # token saknas helt
    assert client.get("/api/iot-relay/events?token=fel").status_code == 401


def test_events_tail_since_and_limit(harness):
    client, _ = harness
    for i in range(3):
        _post_gps(client, body={**GPS_BODY, "sats": i})

    # tail-läge (utan since): allt, id-stigande, payload verbatim
    tail = client.get(f"/api/iot-relay/events?token={TOKEN}").json()
    assert [e["id"] for e in tail["entries"]] == [1, 2, 3]
    assert tail["latest"] == 3
    assert tail["entries"][0]["payload"]["sats"] == 0
    assert tail["entries"][0]["receivedAt"].endswith("Z")

    since = client.get(f"/api/iot-relay/events?token={TOKEN}&since=1").json()
    assert [e["id"] for e in since["entries"]] == [2, 3]

    capped = client.get(f"/api/iot-relay/events?token={TOKEN}&since=0&limit=1").json()
    assert [e["id"] for e in capped["entries"]] == [1]
    assert capped["latest"] == 3

    empty = client.get(f"/api/iot-relay/events?token={TOKEN}&since=3").json()
    assert empty["entries"] == []
    assert empty["latest"] == 3


def test_old_rows_are_cleaned_up_on_insert(harness, monkeypatch):
    client, session_factory = harness

    with session_factory() as db:
        db.add(
            IotRelayEvent(
                device_id="GAMMAL",
                kind="gps",
                payload={"deviceId": "GAMMAL", "lat": 1, "lon": 2},
                received_at=datetime.now(timezone.utc)
                - timedelta(hours=iot_relay.RETENTION_HOURS + 1),
            )
        )
        db.commit()

    # tvinga städningen att köra (annars sannolikhetsstyrd)
    monkeypatch.setattr(iot_relay.random, "random", lambda: 0.0)
    _post_gps(client)

    with session_factory() as db:
        device_ids = set(db.execute(select(IotRelayEvent.device_id)).scalars())
    assert device_ids == {"ESP32-GPS-01"}
