"""Verksamhetsscope + historikbevarande för DELETE /api/persons/{id}.

En icke-super arbetsledare i verksamhet A får inte radera en person i
verksamhet B (scoped_get -> 404, B-personen ligger kvar). Positivt: när
ledaren raderar en egen-verksamhets-person med schemahistorik ska personen
inaktiveras, historiska ScheduleCell-rader bevaras (historiken är en logg)
och en delete-auditrad med mode=history_preserved skrivas.

Källa: app/backend/routers/persons.py::delete_person och
app/backend/business_scope.py::scoped_get / assert_user_can_access_business.
"""
from __future__ import annotations

import pytest

from app.backend.models import AuditLog, Person, PersonScheduleTemplate, ScheduleCell

# Återanvänd in-memory-SQLite-riggen och login-hjälparen från bug-report-sviten.
# db_session seedar Business 1 (STIGAMO) + Business 2 (R3) samt:
#   anna   -> leader, business_id=1   (icke-super editor i verksamhet A)
#   root   -> super_user, business_id=1
#   r3anna -> leader, business_id=2
from tests.services.test_bug_reports import (  # noqa: F401  (fixtures via namespace)
    client,
    db_session,
    login,
)


def _make_person(db_session, *, business_id: int, name: str) -> Person:
    person = Person(business_id=business_id, name=name, collar_type="blue_collar")
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)
    return person


def test_leader_cannot_delete_person_in_other_business(client, db_session):
    """Ledare i verksamhet A DELETE:ar B-person -> 404, personen kvar."""
    person_b = _make_person(db_session, business_id=2, name="R3 Person")
    person_b_id = person_b.id

    login(client, "anna")  # leader i verksamhet A (business_id=1)
    response = client.delete(f"/api/persons/{person_b_id}")

    assert response.status_code == 404, response.text
    # B-personen ska fortfarande finnas kvar.
    assert db_session.get(Person, person_b_id) is not None
    # Ingen delete-audit ska ha skrivits för det misslyckade försöket.
    assert (
        db_session.query(AuditLog)
        .filter_by(entity_type="person", entity_id=person_b_id, action="delete")
        .count()
        == 0
    )


def test_leader_deleting_person_with_history_preserves_it(client, db_session):
    """Radering av person med schemahistorik: 204, historiken bevaras."""
    from datetime import date, timedelta

    person = _make_person(db_session, business_id=1, name="Stigamo Person")
    person_id = person.id

    past = date.today() - timedelta(days=7)
    iso = past.isocalendar()
    # Historiska schemaceller kopplade till personen.
    db_session.add_all(
        [
            ScheduleCell(
                year=iso.year, week=iso.week, weekday=iso.weekday, hour=8,
                minute_start=0, minute_end=60, person_id=person_id,
            ),
            ScheduleCell(
                year=iso.year, week=iso.week, weekday=iso.weekday, hour=9,
                minute_start=0, minute_end=60, person_id=person_id,
            ),
        ]
    )
    # Schemamall-rader kopplade till personen. Ledig-raden får en annan
    # veckodag än den historiska cellens: iso.weekday följer dagens datum
    # (testet kördes "för 7 dagar sedan"), så en hårdkodad 1:a krockar med
    # unikhetskravet (person_id, weekday) varje måndag.
    off_weekday = iso.weekday % 7 + 1
    db_session.add_all(
        [
            PersonScheduleTemplate(person_id=person_id, weekday=iso.weekday, start_hour=6, end_hour=14),
            PersonScheduleTemplate(person_id=person_id, weekday=off_weekday, is_off=True),
        ]
    )
    db_session.commit()

    assert db_session.query(ScheduleCell).filter_by(person_id=person_id).count() == 2

    login(client, "anna")  # leader i samma verksamhet (business_id=1)
    response = client.delete(f"/api/persons/{person_id}")

    assert response.status_code == 204, response.text
    db_session.expire_all()
    # Personen kvar men inaktiverad: historiken är en logg som ska gå att läsa.
    kept = db_session.get(Person, person_id)
    assert kept is not None
    assert kept.is_active is False
    # Den historiska dagens celler är bevarade orörda. (Personen kan också ha
    # fått dagens timmar utskrivna av borttagningen; det räknas inte här.)
    historical = (
        db_session.query(ScheduleCell)
        .filter_by(person_id=person_id, year=iso.year, week=iso.week, weekday=iso.weekday)
        .all()
    )
    assert sorted(cell.hour for cell in historical) == [8, 9]
    # Delete-audit skriven med korrekt entitet/verksamhet och bevarandeläge.
    audit = (
        db_session.query(AuditLog)
        .filter_by(entity_type="person", entity_id=person_id, action="delete")
        .one()
    )
    assert audit.new_value["mode"] == "history_preserved"
    assert audit.old_value is not None
    assert audit.business_id == 1
