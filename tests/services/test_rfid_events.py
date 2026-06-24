from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Activity, Area, AuditLog, Business, Person, RfidScanEvent, ScheduleCell, User
from app.backend.routers import rfid
from app.backend.routers.rfid import (
    RfidScanIn,
    apply_rfid_event,
    ignore_rfid_event,
    list_rfid_events,
    receive_rfid_scan,
)


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    return engine, session


def seed_rfid_data(session):
    business = Business(code="STIGAMO", name="Stigamo", company_codes=[], sort_order=1, is_active=True)
    session.add(business)
    session.flush()
    area = Area(business_id=business.id, code="MG", name="MG", sort_order=1, is_active=True)
    session.add(area)
    session.flush()
    old_activity = Activity(
        business_id=business.id,
        code="GG_PLOCK",
        label="GG Plock",
        area_id=area.id,
        color="#ffffff",
        category="work",
        sort_order=1,
        is_active=True,
    )
    mg_plock = Activity(
        business_id=business.id,
        code="MG_PLOCK",
        label="MG Plock",
        area_id=area.id,
        color="#ffffff",
        category="work",
        sort_order=2,
        is_active=True,
    )
    mg_vm = Activity(
        business_id=business.id,
        code="MG_VM",
        label="MG VM",
        area_id=area.id,
        color="#ffffff",
        category="work",
        sort_order=3,
        is_active=True,
    )
    person = Person(
        business_id=business.id,
        name="Emir Kadric",
        noman="100",
        rfid_code="00A1B2C3",
        home_area_id=area.id,
        competencies=[],
        is_active=True,
        sort_order=1,
    )
    user = User(username="admin", role="admin", roles=["admin"], business_id=business.id, is_active=True)
    session.add_all([old_activity, mg_plock, mg_vm, person, user])
    session.commit()
    return {
        "business": business,
        "area": area,
        "old_activity": old_activity,
        "mg_plock": mg_plock,
        "mg_vm": mg_vm,
        "person": person,
        "user": user,
    }


def test_rfid_duplicate_scan_is_dropped_without_event_or_audit(monkeypatch):
    engine, session = make_session()
    try:
        data = seed_rfid_data(session)
        scan_time = datetime(2026, 6, 14, 7, 37, tzinfo=timezone.utc)
        monkeypatch.setattr(rfid, "_now_utc", lambda: scan_time)
        request = SimpleNamespace(headers={})
        payload = RfidScanIn(
            device_id="esp32-mg-plock-01",
            module_name="MG Plock",
            tag_hex="00A1B2C3",
            tag_dec="10597059",
            scan_count=1,
        )

        first = receive_rfid_scan(payload, request=request, response=Response(), db=session)["event"]
        audit_count_after_first = session.query(AuditLog).filter(AuditLog.entity_type == "rfid_scan_event").count()
        second_response = Response()
        second = receive_rfid_scan(
            payload.model_copy(update={"scan_count": 2}),
            request=request,
            response=second_response,
            db=session,
        )

        assert first["status"] == "pending"
        assert second_response.status_code == 200
        assert second["event"] is None
        assert second["registered"] is False
        assert second["duplicate"] is True
        assert session.query(RfidScanEvent).count() == 1
        assert session.query(AuditLog).filter(AuditLog.entity_type == "rfid_scan_event").count() == audit_count_after_first

        ignored = ignore_rfid_event(first["id"], db=session, user=data["user"])["event"]
        assert ignored["status"] == "ignored"

        listed = list_rfid_events(2026, 24, 7, area_id=data["area"].id, db=session, user=data["user"])
        assert [event["status"] for event in listed["events"]] == ["ignored"]
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_rfid_scan_requires_device_token_when_configured(monkeypatch):
    engine, session = make_session()
    try:
        seed_rfid_data(session)
        monkeypatch.setattr(rfid.settings, "RFID_DEVICE_TOKEN", "expected-token")
        payload = RfidScanIn(device_id="esp32-mg-plock-01", module_name="MG Plock", tag_hex="00A1B2C3")

        with pytest.raises(HTTPException) as exc:
            receive_rfid_scan(payload, request=SimpleNamespace(headers={}), response=Response(), db=session)

        assert exc.value.status_code == 401

        accepted = receive_rfid_scan(
            payload,
            request=SimpleNamespace(headers={"x-flow-rfid-token": "expected-token"}),
            response=Response(),
            db=session,
        )["event"]
        assert accepted["status"] == "pending"
    finally:
        monkeypatch.setattr(rfid.settings, "RFID_DEVICE_TOKEN", "")
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_rfid_scan_can_register_mg_vm_activity(monkeypatch):
    engine, session = make_session()
    try:
        data = seed_rfid_data(session)
        monkeypatch.setattr(rfid, "_now_utc", lambda: datetime(2026, 6, 14, 8, 5, tzinfo=timezone.utc))

        event = receive_rfid_scan(
            RfidScanIn(
                device_id="esp32-mg-vm-01",
                module_name="MG VM",
                tag_hex="00A1B2C3",
                tag_dec="10597059",
                scan_count=1,
            ),
            request=SimpleNamespace(headers={}),
            response=Response(),
            db=session,
        )["event"]

        assert event["status"] == "pending"
        assert event["device_id"] == "esp32-mg-vm-01"
        assert event["module_name"] == "MG VM"
        assert event["activity_id"] == data["mg_vm"].id
        assert event["activity_code"] == "MG_VM"
        assert event["activity_label"] == "MG VM"
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_apply_rfid_event_splits_schedule_cell_from_scan_minute(monkeypatch):
    engine, session = make_session()
    try:
        data = seed_rfid_data(session)
        session.add(
            ScheduleCell(
                year=2026,
                week=24,
                weekday=7,
                hour=9,
                minute_start=0,
                minute_end=60,
                person_id=data["person"].id,
                activity_id=data["old_activity"].id,
                empty_override=False,
                version=1,
                updated_by=data["user"].id,
            )
        )
        session.commit()

        monkeypatch.setattr(rfid, "_now_utc", lambda: datetime(2026, 6, 14, 7, 37, tzinfo=timezone.utc))
        event = receive_rfid_scan(
            RfidScanIn(device_id="esp32-mg-plock-01", module_name="MG Plock", tag_hex="00A1B2C3"),
            request=SimpleNamespace(headers={}),
            response=Response(),
            db=session,
        )["event"]

        response = apply_rfid_event(event["id"], db=session, user=data["user"])

        assert response["event"]["status"] == "applied"
        assert [(item["minute_start"], item["minute_end"], item["activity_id"]) for item in response["segments"]] == [
            (0, 37, data["old_activity"].id),
            (37, 60, data["mg_plock"].id),
        ]
        db_event = session.get(RfidScanEvent, event["id"])
        assert db_event.status == "applied"
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
