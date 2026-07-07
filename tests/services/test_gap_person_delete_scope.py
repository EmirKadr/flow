"""Verksamhetsscope + cascade för DELETE /api/persons/{id}.

En icke-super arbetsledare i verksamhet A får inte radera en person i
verksamhet B (scoped_get -> 404, B-personen ligger kvar). Positivt: när
ledaren raderar en egen-verksamhets-person ska ScheduleCell och
PersonScheduleTemplate cascada bort och en delete-auditrad skrivas.

Källa: app/backend/routers/persons.py::delete_person (~837) och
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


def test_leader_deleting_own_business_person_cascades_and_audits(client, db_session):
    """Radering av egen-verksamhets-person: 204, cascade + delete-audit."""
    person = _make_person(db_session, business_id=1, name="Stigamo Person")
    person_id = person.id

    # Schemaceller kopplade till personen.
    db_session.add_all(
        [
            ScheduleCell(
                year=2026, week=28, weekday=0, hour=8,
                minute_start=0, minute_end=60, person_id=person_id,
            ),
            ScheduleCell(
                year=2026, week=28, weekday=0, hour=9,
                minute_start=0, minute_end=60, person_id=person_id,
            ),
        ]
    )
    # Schemamall-rader kopplade till personen.
    db_session.add_all(
        [
            PersonScheduleTemplate(person_id=person_id, weekday=0, start_hour=6, end_hour=14),
            PersonScheduleTemplate(person_id=person_id, weekday=1, is_off=True),
        ]
    )
    db_session.commit()

    assert db_session.query(ScheduleCell).filter_by(person_id=person_id).count() == 2
    assert db_session.query(PersonScheduleTemplate).filter_by(person_id=person_id).count() == 2

    login(client, "anna")  # leader i samma verksamhet (business_id=1)
    response = client.delete(f"/api/persons/{person_id}")

    assert response.status_code == 204, response.text
    # Personen borta.
    assert db_session.get(Person, person_id) is None
    # Cascade: schemaceller och mallrader borta.
    assert db_session.query(ScheduleCell).filter_by(person_id=person_id).count() == 0
    assert db_session.query(PersonScheduleTemplate).filter_by(person_id=person_id).count() == 0
    # Delete-audit skriven med korrekt entitet/verksamhet.
    audit = (
        db_session.query(AuditLog)
        .filter_by(entity_type="person", entity_id=person_id, action="delete")
        .one()
    )
    assert audit.new_value is None
    assert audit.old_value is not None
    assert audit.business_id == 1
