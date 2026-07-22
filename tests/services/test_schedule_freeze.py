"""Schemafrysning: historik är en logg som aldrig skrivs om.

Täcker materialiseringen (implicita malltimmar -> is_template_fill-celler),
frysgränsen i template_service, backfill via materialize_pending_days samt
de nya raderingskontrakten: ta bort person/aktivitet rensar framtiden men
bevarar historiken, och frysta dagar visar personer som senare tagits bort.

Källa: app/backend/schedule_freeze.py, app/backend/template_service.py,
app/backend/routers/persons.py::delete_person,
app/backend/routers/activities.py::delete_activity.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.backend.models import (
    Activity,
    AuditLog,
    Person,
    PersonScheduleTemplate,
    ScheduleCell,
    ScheduleFreezeState,
)
from app.backend.schedule_freeze import (
    materialize_pending_days,
    materialize_schedule_day,
)
from app.backend.template_service import (
    get_schedule_freeze_horizon,
    get_template_hours_map_for_dates,
)

# Återanvänd in-memory-SQLite-riggen och login-hjälparen.
from tests.services.test_bug_reports import (  # noqa: F401  (fixtures via namespace)
    client,
    db_session,
    login,
)


def _past_weekday_date(days_back_at_least: int = 5) -> date:
    """Ett vardagsdatum (mån-fre) minst N dagar bakåt, för stabila malltimmar."""
    candidate = date.today() - timedelta(days=days_back_at_least)
    while candidate.isoweekday() > 5:
        candidate -= timedelta(days=1)
    return candidate


def _make_activity(db_session, *, code: str, label: str, business_id: int = 1) -> Activity:
    activity = Activity(business_id=business_id, code=code, label=label, color="#ff0000")
    db_session.add(activity)
    db_session.commit()
    db_session.refresh(activity)
    return activity


def _make_person(
    db_session,
    *,
    name: str,
    business_id: int = 1,
    home_activity_id: int | None = None,
    has_fixed_schedule: bool = True,
    created_days_ago: int = 60,
) -> Person:
    person = Person(
        business_id=business_id,
        name=name,
        home_activity_id=home_activity_id,
        has_fixed_schedule=has_fixed_schedule,
        created_at=datetime.now() - timedelta(days=created_days_ago),
    )
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)
    return person


def _add_template(db_session, person_id: int, weekday: int, start: int, end: int) -> None:
    db_session.add(
        PersonScheduleTemplate(person_id=person_id, weekday=weekday, start_hour=start, end_hour=end)
    )
    db_session.commit()


def _add_cell(db_session, person_id: int, target: date, hour: int, **kwargs) -> ScheduleCell:
    iso = target.isocalendar()
    cell = ScheduleCell(
        year=iso.year,
        week=iso.week,
        weekday=iso.weekday,
        hour=hour,
        minute_start=kwargs.pop("minute_start", 0),
        minute_end=kwargs.pop("minute_end", 60),
        person_id=person_id,
        **kwargs,
    )
    db_session.add(cell)
    db_session.commit()
    db_session.refresh(cell)
    return cell


def _cells_for_date(db_session, person_id: int, target: date) -> list[ScheduleCell]:
    iso = target.isocalendar()
    return (
        db_session.query(ScheduleCell)
        .filter_by(person_id=person_id, year=iso.year, week=iso.week, weekday=iso.weekday)
        .order_by(ScheduleCell.hour, ScheduleCell.minute_start)
        .all()
    )


def test_materialize_writes_fill_cells_with_home_activity(db_session):
    """Malltimmar utan explicita celler blir is_template_fill-celler med huvudaktivitet."""
    target = _past_weekday_date()
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    other = _make_activity(db_session, code="PACK", label="Pack")
    person = _make_person(db_session, name="Frys Person", home_activity_id=activity.id)
    # Mall 8-11 (timmar 8,9,10; lunch = start+5 = 13 ligger utanför fönstret).
    _add_template(db_session, person.id, target.isoweekday(), 8, 11)
    # Timme 9 redan explicit med annan aktivitet: ska inte röras.
    _add_cell(db_session, person.id, target, 9, activity_id=other.id)
    # Timme 10 har en ren lånemarkeringsrad (aktivitet None, ej override):
    # blockerar insättning så unik-nyckeln inte krockar.
    _add_cell(db_session, person.id, target, 10, loan_area_id=None, empty_override=False)

    result = materialize_schedule_day(db_session, target)
    db_session.commit()

    assert result["status"] == "materialized"
    cells = _cells_for_date(db_session, person.id, target)
    fills = [cell for cell in cells if cell.is_template_fill]
    assert [cell.hour for cell in fills] == [8]
    assert fills[0].activity_id == activity.id
    assert fills[0].empty_override is False
    assert fills[0].updated_by is None
    # Explicit cell orörd, blockeringsraden orörd.
    hour9 = [cell for cell in cells if cell.hour == 9]
    assert len(hour9) == 1 and hour9[0].activity_id == other.id
    hour10 = [cell for cell in cells if cell.hour == 10]
    assert len(hour10) == 1 and not hour10[0].is_template_fill
    # Frysgränsen flyttad och auditrad skriven.
    assert get_schedule_freeze_horizon(db_session) == target
    audit = (
        db_session.query(AuditLog)
        .filter_by(entity_type="schedule_freeze", action="materialize")
        .one()
    )
    assert audit.new_value["date"] == target.isoformat()
    assert audit.user_id is None


def test_materialize_without_home_activity_freezes_empty_override(db_session):
    """Schemalagd timme utan huvudaktivitet fryses som uttryckligen tom."""
    target = _past_weekday_date()
    person = _make_person(db_session, name="Utan Hemaktivitet", home_activity_id=None)
    _add_template(db_session, person.id, target.isoweekday(), 8, 10)

    materialize_schedule_day(db_session, target)
    db_session.commit()

    fills = [cell for cell in _cells_for_date(db_session, person.id, target) if cell.is_template_fill]
    assert [cell.hour for cell in fills] == [8, 9]
    assert all(cell.activity_id is None and cell.empty_override for cell in fills)


def test_materialize_respects_created_at_and_hourly_workers(db_session):
    """Inga fills före personens skapandedatum eller för timanställda."""
    target = _past_weekday_date()
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    created_after = _make_person(
        db_session, name="Ny Person", home_activity_id=activity.id, created_days_ago=0
    )
    hourly = _make_person(
        db_session,
        name="Timmis",
        home_activity_id=activity.id,
        has_fixed_schedule=False,
    )
    _add_template(db_session, created_after.id, target.isoweekday(), 8, 10)
    _add_template(db_session, hourly.id, target.isoweekday(), 8, 10)

    materialize_schedule_day(db_session, target)
    db_session.commit()

    assert _cells_for_date(db_session, created_after.id, target) == []
    assert _cells_for_date(db_session, hourly.id, target) == []


def test_materialize_is_idempotent_and_never_touches_today(db_session):
    """Andra körningen är no-op; dagens datum materialiseras aldrig."""
    target = _past_weekday_date()
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    person = _make_person(db_session, name="Idempotent", home_activity_id=activity.id)
    _add_template(db_session, person.id, target.isoweekday(), 8, 10)

    first = materialize_schedule_day(db_session, target)
    db_session.commit()
    second = materialize_schedule_day(db_session, target)
    db_session.commit()

    assert first["status"] == "materialized" and first["cells_created"] == 2
    assert second["status"] == "already_frozen" and second["cells_created"] == 0
    assert len(_cells_for_date(db_session, person.id, target)) == 2

    today_result = materialize_schedule_day(db_session, date.today())
    assert today_result["status"] == "not_past"


def test_template_edit_does_not_change_frozen_dates(db_session):
    """Kärnbuggen: malländring efter frysning ändrar inte förfluten tid."""
    target = _past_weekday_date()
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    person = _make_person(db_session, name="Mallbyte", home_activity_id=activity.id)
    _add_template(db_session, person.id, target.isoweekday(), 8, 11)

    materialize_schedule_day(db_session, target)
    db_session.commit()

    # Malländring: både utökning och krympning får noll effekt på fryst datum.
    row = (
        db_session.query(PersonScheduleTemplate)
        .filter_by(person_id=person.id, weekday=target.isoweekday())
        .one()
    )
    row.start_hour = 6
    row.end_hour = 20
    db_session.commit()

    template_map = get_template_hours_map_for_dates(db_session, [person.id], [target])
    assert template_map[(person.id, target)] is None
    fills = [cell for cell in _cells_for_date(db_session, person.id, target) if cell.is_template_fill]
    assert [cell.hour for cell in fills] == [8, 9, 10]


def test_materialize_pending_days_backfills_and_advances(db_session):
    """Första körningen backfyller från äldsta data; andra är no-op."""
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    person = _make_person(
        db_session, name="Backfill", home_activity_id=activity.id, created_days_ago=4
    )
    for weekday in range(1, 8):
        _add_template(db_session, person.id, weekday, 8, 10)

    result = materialize_pending_days(db_session)
    yesterday = date.today() - timedelta(days=1)

    assert result["status"] == "materialized"
    assert get_schedule_freeze_horizon(db_session) == yesterday
    # Alla dagar från skapandet t.o.m. igår har fått fills (4 dagar).
    fill_count = (
        db_session.query(ScheduleCell)
        .filter(ScheduleCell.person_id == person.id, ScheduleCell.is_template_fill)
        .count()
    )
    assert fill_count == 4 * 2

    second = materialize_pending_days(db_session)
    assert second == {"status": "current", "days": 0, "cells_created": 0}


def test_delete_person_keeps_history_and_purges_future(client, db_session):
    """DELETE person: historiska celler kvar, framtida borta, personen inaktiv."""
    past = _past_weekday_date()
    future = date.today() + timedelta(days=3)
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    person = _make_person(db_session, name="Radera Mig", home_activity_id=activity.id)
    person_id = person.id
    _add_cell(db_session, person_id, past, 8, activity_id=activity.id)
    _add_cell(db_session, person_id, future, 8, activity_id=activity.id)

    login(client, "anna")
    response = client.delete(f"/api/persons/{person_id}")

    assert response.status_code == 204, response.text
    db_session.expire_all()
    kept = db_session.get(Person, person_id)
    assert kept is not None
    assert kept.is_active is False
    assert kept.has_fixed_schedule is False
    assert len(_cells_for_date(db_session, person_id, past)) >= 1
    assert _cells_for_date(db_session, person_id, future) == []
    audit = (
        db_session.query(AuditLog)
        .filter_by(entity_type="person", entity_id=person_id, action="delete")
        .one()
    )
    assert audit.new_value["mode"] == "history_preserved"

    # Den frysta dagen visar fortfarande personen och timmen i dagvyn.
    iso = past.isocalendar()
    day = client.get(
        f"/api/schedule?year={iso.year}&week={iso.week}&weekday={iso.weekday}"
    )
    assert day.status_code == 200, day.text
    payload = day.json()
    assert any(row["id"] == person_id for row in payload["persons"])
    assert any(cell["person_id"] == person_id and cell["hour"] == 8 for cell in payload["cells"])


def test_delete_person_preserves_todays_worked_hours(client, db_session):
    """En borttagning mitt pa dagen far inte radera dagens redan arbetade timmar."""
    today = date.today()
    if today.isoweekday() > 5:
        pytest.skip("Standardmallen ar tom pa helger.")
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    person = _make_person(db_session, name="Borttagen idag", home_activity_id=activity.id)
    _add_template(db_session, person.id, today.isoweekday(), 8, 11)
    person_id = person.id

    login(client, "anna")
    assert client.delete(f"/api/persons/{person_id}").status_code == 204
    db_session.expire_all()

    # Dagens timmar finns kvar som celler trots att personen ar inaktiverad.
    kept = db_session.get(Person, person_id)
    assert kept.is_active is False and kept.has_fixed_schedule is False
    today_cells = _cells_for_date(db_session, person_id, today)
    assert sorted(cell.hour for cell in today_cells) == [8, 9, 10]
    assert all(cell.activity_id == activity.id for cell in today_cells)

    iso = today.isocalendar()
    day = client.get(f"/api/schedule?year={iso.year}&week={iso.week}&weekday={iso.weekday}")
    payload = day.json()
    assert any(row["id"] == person_id for row in payload["persons"])
    assert sum(1 for cell in payload["cells"] if cell["person_id"] == person_id) == 3


def test_delete_person_without_history_hard_deletes(client, db_session):
    """Person helt utan schemaceller tas bort på riktigt som förut.

    Skapad idag: backfillen i delete-flödet materialiserar inga historikdagar
    (created_at-vakten), så personen saknar celler och hårdraderas.
    """
    person = _make_person(db_session, name="Felskapad", created_days_ago=0)
    person_id = person.id

    login(client, "anna")
    response = client.delete(f"/api/persons/{person_id}")

    assert response.status_code == 204, response.text
    db_session.expire_all()
    assert db_session.get(Person, person_id) is None


def test_delete_activity_keeps_history_and_clears_future(client, db_session):
    """DELETE aktivitet: historiska celler behåller aktiviteten, framtida töms."""
    past = _past_weekday_date()
    future = date.today() + timedelta(days=3)
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    activity_id = activity.id
    person = _make_person(db_session, name="Aktivitetshistorik", home_activity_id=activity_id)
    person_id = person.id
    _add_cell(db_session, person_id, past, 8, activity_id=activity_id)
    future_cell = _add_cell(db_session, person_id, future, 8, activity_id=activity_id)
    future_cell_id = future_cell.id

    login(client, "root")
    response = client.delete(f"/api/activities/{activity_id}")

    assert response.status_code == 204, response.text
    db_session.expire_all()
    kept = db_session.get(Activity, activity_id)
    assert kept is not None and kept.is_active is False
    past_cells = _cells_for_date(db_session, person_id, past)
    assert any(cell.activity_id == activity_id for cell in past_cells)
    cleared = db_session.get(ScheduleCell, future_cell_id)
    assert cleared.activity_id is None and cleared.empty_override is True
    assert db_session.get(Person, person_id).home_activity_id is None
    audit = (
        db_session.query(AuditLog)
        .filter_by(entity_type="activity", entity_id=activity_id, action="delete")
        .one()
    )
    assert audit.new_value["mode"] == "history_preserved"


def test_delete_activity_without_history_hard_deletes(client, db_session):
    """Aktivitet utan schemaceller tas bort på riktigt som förut."""
    activity = _make_activity(db_session, code="TOM", label="Tom aktivitet")
    activity_id = activity.id

    login(client, "root")
    response = client.delete(f"/api/activities/{activity_id}")

    assert response.status_code == 204, response.text
    db_session.expire_all()
    assert db_session.get(Activity, activity_id) is None


def test_summary_is_stable_after_freeze_despite_template_and_home_changes(client, db_session):
    """Summeringens timmar för en fryst dag står stilla vid mall-/hemaktivitetsbyte."""
    target = _past_weekday_date()
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    other = _make_activity(db_session, code="PACK", label="Pack")
    person = _make_person(db_session, name="Summering", home_activity_id=activity.id)
    _add_template(db_session, person.id, target.isoweekday(), 8, 11)

    materialize_schedule_day(db_session, target)
    db_session.commit()

    iso = target.isocalendar()
    login(client, "anna")
    url = f"/api/schedule/summary?year={iso.year}&week={iso.week}&weekday={iso.weekday}"
    before = {row["activity_id"]: row["hours"] for row in client.get(url).json()}
    assert before.get(activity.id) == 3.0

    # Byt hemaktivitet och utöka mallen: den frysta dagen ska stå stilla.
    person.home_activity_id = other.id
    row = (
        db_session.query(PersonScheduleTemplate)
        .filter_by(person_id=person.id, weekday=target.isoweekday())
        .one()
    )
    row.start_hour = 6
    row.end_hour = 20
    db_session.commit()

    after = {row["activity_id"]: row["hours"] for row in client.get(url).json()}
    assert after == before


def _effective_activity_by_hour(day_payload: dict) -> dict[tuple[int, int], int | None]:
    """Vad varje timme faktiskt visar, med samma regler som klienten.

    Explicit cell vinner; annars huvudaktiviteten for en schemalagd timme
    (`scheduled_defaults`), utom nar timmen ar uttryckligen tomd.
    """
    result: dict[tuple[int, int], int | None] = {}
    covered: dict[tuple[int, int], bool] = {}
    for cell in day_payload["cells"]:
        key = (cell["person_id"], cell["hour"])
        if cell["activity_id"] is not None:
            result[key] = cell["activity_id"]
            covered[key] = True
        elif cell["empty_override"]:
            result.setdefault(key, None)
            covered[key] = True
    for person_id, hours in day_payload["scheduled_hours"].items():
        defaults = day_payload["scheduled_defaults"].get(str(person_id), {})
        for hour in hours:
            key = (int(person_id), int(hour))
            if covered.get(key):
                continue
            result[key] = defaults.get(str(hour))
    return {key: value for key, value in result.items() if value is not None}


def test_freezing_does_not_change_what_the_day_looks_like(client, db_session):
    """Kardinalregeln: sjalva frysningen far inte andra en enda vy.

    Materialiseringen skriver om hur dagen LAGRAS, inte vad den VISAR. Det har
    testet jamfor Bemanning, summeringen och Oversikt precis fore och efter
    frysningen - det ar guardrailen som fangar en yta jag glomt anpassa.
    """
    target = _past_weekday_date()
    plock = _make_activity(db_session, code="PLOCK", label="Plock")
    pack = _make_activity(db_session, code="PACK", label="Pack")
    # Fyra profiler: full mall, mall + explicit avvikelse, mall utan
    # huvudaktivitet, och timmis helt utan malltimmar.
    full = _make_person(db_session, name="Full mall", home_activity_id=plock.id)
    partial = _make_person(db_session, name="Avvikelse", home_activity_id=plock.id)
    no_home = _make_person(db_session, name="Utan hemaktivitet", home_activity_id=None)
    hourly = _make_person(db_session, name="Timmis", home_activity_id=plock.id, has_fixed_schedule=False)
    weekday = target.isoweekday()
    for person in (full, partial, no_home, hourly):
        _add_template(db_session, person.id, weekday, 8, 12)
    _add_cell(db_session, partial.id, target, 9, activity_id=pack.id)
    _add_cell(db_session, partial.id, target, 10, activity_id=None, empty_override=True)

    iso = target.isocalendar()
    login(client, "anna")
    day_url = f"/api/schedule?year={iso.year}&week={iso.week}&weekday={iso.weekday}"
    summary_url = f"/api/schedule/summary?year={iso.year}&week={iso.week}&weekday={iso.weekday}"
    overview_url = f"/api/overview?year={iso.year}&week={iso.week}"

    before_day = _effective_activity_by_hour(client.get(day_url).json())
    before_summary = sorted(
        (row["activity_id"], row["hours"]) for row in client.get(summary_url).json()
    )
    before_overview = sorted(
        (item["person_id"], item["activity_id"], item["mixed"], item["hours_total"], item["template_hours"])
        for item in client.get(overview_url).json()["matrix"]
        if item["weekday"] == iso.weekday
    )

    materialize_schedule_day(db_session, target)
    db_session.commit()

    after_day = _effective_activity_by_hour(client.get(day_url).json())
    after_summary = sorted(
        (row["activity_id"], row["hours"]) for row in client.get(summary_url).json()
    )
    after_overview = sorted(
        (item["person_id"], item["activity_id"], item["mixed"], item["hours_total"], item["template_hours"])
        for item in client.get(overview_url).json()["matrix"]
        if item["weekday"] == iso.weekday
    )

    assert after_day == before_day
    assert after_summary == before_summary
    assert after_overview == before_overview
    # Och dagen ska faktiskt ha varit icke-trivial.
    assert before_summary and any(hours > 0 for _activity_id, hours in before_summary)


def test_overview_reports_scheduled_hours_on_frozen_day(client, db_session):
    """Regression: fryst dag far inte rapportera template_hours=0.

    Oversiktens klient ritar `template_hours === 0` som "Ledig" for personer
    med fast schema. Nar mallen slutar galla for frysta datum maste antalet
    harledas ur cellerna, annars ser hela historiken tom ut.
    """
    target = _past_weekday_date()
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    person = _make_person(db_session, name="Oversikt", home_activity_id=activity.id)
    _add_template(db_session, person.id, target.isoweekday(), 8, 11)

    materialize_schedule_day(db_session, target)
    db_session.commit()

    iso = target.isocalendar()
    login(client, "anna")
    week = client.get(f"/api/overview?year={iso.year}&week={iso.week}")
    assert week.status_code == 200, week.text
    cell = next(
        item
        for item in week.json()["matrix"]
        if item["person_id"] == person.id and item["weekday"] == iso.weekday
    )
    assert cell["template_hours"] == 3
    assert cell["hours_total"] == 3.0
    assert cell["activity_id"] == activity.id

    month = client.get(f"/api/overview/month?year={target.year}&month={target.month}")
    assert month.status_code == 200, month.text
    month_cell = next(
        item
        for item in month.json()["matrix"]
        if item["person_id"] == person.id and item["date"] == target.isoformat()
    )
    assert month_cell["template_hours"] == 3
    assert month_cell["hours_total"] == 3.0


def test_day_view_keeps_scheduled_marker_on_frozen_day(client, db_session):
    """Fryst dag ska fortsatt markera schemalagda timmar i Bemanning."""
    target = _past_weekday_date()
    person = _make_person(db_session, name="Utan aktivitet", home_activity_id=None)
    _add_template(db_session, person.id, target.isoweekday(), 8, 10)

    materialize_schedule_day(db_session, target)
    db_session.commit()

    iso = target.isocalendar()
    login(client, "anna")
    day = client.get(f"/api/schedule?year={iso.year}&week={iso.week}&weekday={iso.weekday}")
    assert day.status_code == 200, day.text
    payload = day.json()
    assert payload["scheduled_hours"][str(person.id)] == [8, 9]
    # Mallen galler inte langre, sa ingen nuvarande huvudaktivitet far lacka in.
    assert payload["scheduled_defaults"].get(str(person.id)) is None


def test_copy_day_skips_materialized_template_fills(client, db_session):
    """Kopiera dag ska bete sig som fore frysningen: bara riktiga celler."""
    target = _past_weekday_date()
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    other = _make_activity(db_session, code="PACK", label="Pack")
    person = _make_person(db_session, name="Kopiera", home_activity_id=activity.id)
    _add_template(db_session, person.id, target.isoweekday(), 8, 11)
    _add_cell(db_session, person.id, target, 9, activity_id=other.id)

    materialize_schedule_day(db_session, target)
    db_session.commit()

    iso = target.isocalendar()
    future = date.today() + timedelta(days=7)
    future_iso = future.isocalendar()
    login(client, "anna")
    response = client.post(
        "/api/schedule/copy",
        json={
            "from_year": iso.year,
            "from_week": iso.week,
            "from_weekday": iso.weekday,
            "to_year": future_iso.year,
            "to_week": future_iso.week,
            "to_weekday": future_iso.weekday,
            "overwrite": True,
        },
    )

    assert response.status_code == 200, response.text
    copied = _cells_for_date(db_session, person.id, future)
    # Bara den explicita cellen kopieras - inte de tva materialiserade fills.
    assert [(cell.hour, cell.activity_id) for cell in copied] == [(9, other.id)]
    assert all(not cell.is_template_fill for cell in copied)


def test_template_edit_freezes_pending_days_first(client, db_session):
    """Malländring stanger midnattsfonstret: gardagen fryses fore skrivningen."""
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    person = _make_person(db_session, name="Midnatt", home_activity_id=activity.id, created_days_ago=2)
    yesterday = date.today() - timedelta(days=1)
    for weekday in range(1, 8):
        _add_template(db_session, person.id, weekday, 8, 11)

    # Ingen frysning har korts an - gardagen ar fortfarande live.
    assert get_schedule_freeze_horizon(db_session) is None

    login(client, "anna")
    response = client.put(
        f"/api/persons/{person.id}/schedule",
        json={
            "has_fixed_schedule": True,
            "days": [
                {"weekday": weekday, "is_off": False, "start_hour": 6, "end_hour": 20}
                for weekday in range(1, 8)
            ],
        },
    )

    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert get_schedule_freeze_horizon(db_session) == yesterday
    # Gardagen behaller sina tre timmar trots att mallen nu ar 6-20.
    fills = [cell for cell in _cells_for_date(db_session, person.id, yesterday) if cell.is_template_fill]
    assert sorted(cell.hour for cell in fills) == [8, 9, 10]


def test_concurrent_materialization_does_not_duplicate(db_session):
    """Tva materialiseringar av samma dag far aldrig skapa dubbla fill-celler."""
    target = _past_weekday_date()
    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    person = _make_person(db_session, name="Samtidig", home_activity_id=activity.id)
    _add_template(db_session, person.id, target.isoweekday(), 8, 10)

    materialize_schedule_day(db_session, target)
    db_session.commit()
    # Simulera en andra korning som laste frysgransen innan den forsta hann
    # committa: cachen rensas, men den lasta omlasningen ser dagen som fryst.
    db_session.info.pop("schedule_freeze_horizon", None)
    second = materialize_schedule_day(db_session, target)
    db_session.commit()

    assert second["status"] == "already_frozen"
    assert len(_cells_for_date(db_session, person.id, target)) == 2


def test_freeze_lock_emits_real_lock_on_mssql():
    """Guardrail mot teater: MSSQL tystar bort with_for_update() helt.

    Utan tabellhinten kompilerar laset till ingenting i drift, och tva
    processer kan da materialisera samma dag samtidigt.
    """
    from sqlalchemy import select as sa_select
    from sqlalchemy.dialects import mssql, postgresql

    query = (
        sa_select(ScheduleFreezeState)
        .where(ScheduleFreezeState.id == 1)
        .with_hint(ScheduleFreezeState, "WITH (UPDLOCK, HOLDLOCK)", "mssql")
        .with_for_update()
    )
    assert "UPDLOCK" in str(query.compile(dialect=mssql.dialect()))
    assert "FOR UPDATE" in str(query.compile(dialect=postgresql.dialect()))


def test_freeze_state_id_is_not_identity_on_mssql():
    """Singelraden satts av migrationen med explicit id=1.

    Blir kolumnen IDENTITY pa MSSQL avvisas den INSERT:en och hela
    migrationen faller vid deploy.
    """
    from sqlalchemy.dialects import mssql
    from sqlalchemy.schema import CreateTable

    ddl = str(CreateTable(ScheduleFreezeState.__table__).compile(dialect=mssql.dialect()))
    assert "IDENTITY" not in ddl.upper()


def test_request_path_defers_large_backfill(db_session):
    """Request-vagen far inte dra igang en flerdagars backfill."""
    from app.backend.schedule_freeze import freeze_pending_for_request

    activity = _make_activity(db_session, code="PLOCK", label="Plock")
    person = _make_person(db_session, name="Backfilltak", home_activity_id=activity.id, created_days_ago=60)
    for weekday in range(1, 8):
        _add_template(db_session, person.id, weekday, 8, 10)

    result = freeze_pending_for_request(db_session)

    assert result["status"] == "deferred"
    assert result["pending_days"] > 3
    assert get_schedule_freeze_horizon(db_session) is None


def test_healthcheck_warns_when_freeze_lags(db_session):
    """Guardrail: en tyst havererad frysning ska synas i Halsa, inte gomma sig.

    Bakgrundsjobbet fangar sina egna fel och forblir "running", sa utan den har
    kontrollen skulle en trasig frysning inte ge nagot utslag alls.
    """
    from app.backend.healthcheck_service import collect_schedule_freeze
    from app.backend.schedule_freeze import advance_freeze_horizon

    # Tom databas: ingen historik att skydda an -> information, inte varning.
    checks: list[dict] = []
    result = collect_schedule_freeze(db_session, checks)
    assert checks[0]["status"] == "info"
    assert result["frozen_until"] is None

    # Med schemadata men utan frysgrans: ska varna.
    person = _make_person(db_session, name="Halsa")
    _add_cell(db_session, person.id, _past_weekday_date(), 8)
    checks = []
    result = collect_schedule_freeze(db_session, checks)
    assert checks[0]["status"] == "warn"
    assert result["frozen_until"] is None

    # Efterslapande grans: ska varna med antal dagar.
    advance_freeze_horizon(db_session, date.today() - timedelta(days=4))
    db_session.commit()
    checks = []
    result = collect_schedule_freeze(db_session, checks)
    assert checks[0]["status"] == "warn"
    assert result["lag_days"] == 3

    # Ikapp: ska vara ok.
    advance_freeze_horizon(db_session, date.today() - timedelta(days=1))
    db_session.commit()
    checks = []
    result = collect_schedule_freeze(db_session, checks)
    assert checks[0]["status"] == "ok"
    assert result["lag_days"] == 0


def test_freeze_state_singleton_row(db_session):
    """Frysgränsen flyttas bara framåt."""
    from app.backend.schedule_freeze import advance_freeze_horizon

    d1 = date.today() - timedelta(days=10)
    d2 = date.today() - timedelta(days=5)
    advance_freeze_horizon(db_session, d1)
    db_session.commit()
    advance_freeze_horizon(db_session, d2)
    db_session.commit()
    advance_freeze_horizon(db_session, d1)
    db_session.commit()

    row = db_session.get(ScheduleFreezeState, 1)
    assert row.frozen_until == d2
