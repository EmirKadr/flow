"""IoT-relä: brevlåda för GPS-trackers och sensorer (IoT-Dashboard-projektet).

ESP32-enheter ute på lagret POSTar hit (stabil URL som alltid är uppe) och
den lokalt körda IoT-Dashboard-backenden pollar hem posterna via GET /events.
Medvetet helt fristående från bemanningsdomänen — ingen session, inga roller,
inga FK:er. Kontraktet ägs av IoT-Dashboard-repot (docs/API.md, avsnittet
"Relä via stigamo.nu").

Auth: IOT_RELAY_TOKEN (env) är obligatorisk — 503 om okonfigurerad, 401 vid
fel token (samma mönster som public.py/EXCEL_API_TOKEN). POST-endpoints
accepterar token via headern X-IoT-Device-Token (det firmware redan skickar)
eller ?token=; GET via ?token=.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_db
from ..models import IotRelayEvent

router = APIRouter(prefix="/api/iot-relay", tags=["iot-relay"])

RETENTION_HOURS = 48
CLEANUP_PROBABILITY = 0.005  # ~1 städning per 200 inserts, billigt och trådlöst
DEFAULT_LIMIT = 500
MAX_LIMIT = 1000
TAIL_LIMIT = 200  # utan ?since=: de senaste posterna (cursor-bootstrap)
MAX_PAYLOAD_BYTES = 16_384  # riktiga enhetspayloads är <300 byte — stoppa skräpfyllning


def _verify_token(token: str | None) -> None:
    expected = (settings.IOT_RELAY_TOKEN or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Token not configured"
        )
    if not token or token.strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _verify_post_token(
    token: str | None = Query(None),
    x_iot_device_token: str | None = Header(None, alias="X-IoT-Device-Token"),
) -> None:
    _verify_token(x_iot_device_token or token)


def _iso_utc(value: datetime) -> str:
    # SQLite ger naiva tidsstämplar (UTC), Postgres tz-medvetna — normalisera.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _maybe_cleanup(db: Session) -> None:
    if random.random() >= CLEANUP_PROBABILITY:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
    db.execute(delete(IotRelayEvent).where(IotRelayEvent.received_at < cutoff))


def _require_float(body: dict, field: str) -> None:
    try:
        float(body[field])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field} kravs (tal)"
        )


def _store_event(db: Session, kind: str, body: dict) -> dict:
    device_id = str(body.get("deviceId") or "").strip()
    if not device_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="deviceId kravs")
    if len(json.dumps(body)) > MAX_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload for stor"
        )
    event = IotRelayEvent(device_id=device_id[:80], kind=kind, payload=body)
    db.add(event)
    _maybe_cleanup(db)
    db.commit()
    db.refresh(event)
    return {"ok": True, "id": event.id}


@router.post("/gps", dependencies=[Depends(_verify_post_token)])
def relay_gps(body: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    """Ta emot en GPS-position — samma body som IoT-Dashboards /api/ingest/gps."""
    _require_float(body, "lat")
    _require_float(body, "lon")
    return _store_event(db, "gps", body)


@router.post("/reading", dependencies=[Depends(_verify_post_token)])
def relay_reading(body: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    """Ta emot en sensoravläsning — samma body som IoT-Dashboards /api/ingest/reading."""
    _require_float(body, "value")
    return _store_event(db, "reading", body)


@router.get("/events")
def relay_events(
    token: str = Query(...),
    since: int | None = Query(None, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
) -> dict:
    """Hämta buffrade händelser, id-stigande. Utan ?since=: tail-läge
    (senaste TAIL_LIMIT posterna) för cursor-bootstrap vid pollerstart."""
    _verify_token(token)
    latest = db.execute(select(func.max(IotRelayEvent.id))).scalar() or 0

    if since is None:
        tail_ids = (
            select(IotRelayEvent.id)
            .order_by(IotRelayEvent.id.desc())
            .limit(min(limit, TAIL_LIMIT))
            .subquery()
        )
        query = (
            select(IotRelayEvent)
            .where(IotRelayEvent.id.in_(select(tail_ids.c.id)))
            .order_by(IotRelayEvent.id)
        )
    else:
        query = (
            select(IotRelayEvent)
            .where(IotRelayEvent.id > since)
            .order_by(IotRelayEvent.id)
            .limit(limit)
        )

    entries = [
        {
            "id": event.id,
            "kind": event.kind,
            "deviceId": event.device_id,
            "receivedAt": _iso_utc(event.received_at),
            "payload": event.payload,
        }
        for event in db.execute(query).scalars().all()
    ]
    return {"entries": entries, "latest": latest}
