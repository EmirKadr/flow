"""Frysning av schemahistorik: materialisera implicita malltimmar per dag.

Historiska schemadagar var tidigare en live-projektion av nuvarande veckomall,
has_fixed_schedule och huvudaktivitet, så register-/malländringar skrev om
förfluten tid (uppgifter och timmar). Den här modulen gör historiken till en
logg: vid dygnsskifte skrivs gårdagens implicita malltimmar som explicita
``schedule_cells`` med ``is_template_fill=True``, och ``schedule_freeze_state``
flyttas fram. ``template_service`` applicerar därefter aldrig mallen på datum
till och med frysgränsen.

Semantik per malltimme utan täckande explicit cell:

- Personen har huvudaktivitet: cellen materialiseras med den aktiviteten,
  precis som vyerna och summeringen visade dagen.
- Personen saknar huvudaktivitet: cellen materialiseras som uttryckligen tom
  (``empty_override=True``) så timmen varken kan återfyllas eller börja räknas
  om en huvudaktivitet sätts senare.

Första körningen (frysgräns saknas) backfyller hela historiken från äldsta
relevanta datum till och med gårdagen, en dag per commit. Schemaläggaren körs
som bakgrundsjobb bakom ledarlåset och är idempotent: redan frysta datum rörs
aldrig igen.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .audit import log as audit_log
from .models import Activity, Person, ScheduleCell, ScheduleFreezeState
from .template_service import (
    get_elapsed_cutoff,
    get_schedule_freeze_horizon,
    get_template_hours_map_for_dates,
    set_cached_elapsed_cutoff,
    set_cached_freeze_horizon,
)

logger = logging.getLogger(__name__)

LOCAL_TIMEZONE = ZoneInfo("Europe/Stockholm")
SCHEDULER_INTERVAL_SECONDS = 30 * 60
# Request-vägarnas tak: normalt ligger 0-1 dag och väntar (midnattsfönstret).
# Ligger fler an sa ar det en backfill som hor hemma i bakgrundsjobbet.
REQUEST_PATH_MAX_DAYS = 3


def _local_today(now: datetime | date | None = None) -> date:
    """Dagens datum i svensk lokaltid. ``now`` finns för testbarhet."""
    if now is None:
        now = datetime.now(LOCAL_TIMEZONE)
    if isinstance(now, datetime):
        return now.astimezone(LOCAL_TIMEZONE).date() if now.tzinfo is not None else now.date()
    return now


def _blocking_intervals(cells: list[ScheduleCell]) -> list[tuple[int, int]]:
    """Minutintervall som redan har en cellrad, oavsett innehåll.

    Alla befintliga rader blockerar materialisering: rader med aktivitet eller
    empty_override är redan täckta timdelar, och rena lånemarkeringar får inte
    krockas på unik-nyckeln (year, week, weekday, hour, person, minute_start).
    """
    intervals = sorted(
        (max(0, int(cell.minute_start)), min(60, int(cell.minute_end)))
        for cell in cells
    )
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _uncovered_intervals(covered: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = 0
    for start, end in covered:
        if start > cursor:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < 60:
        result.append((cursor, 60))
    return result


def _future_ywd_condition(now=None):
    """SQL-villkor för celler med datum efter idag (lokal tid), i ISO-ordning."""
    iso = _local_today(now).isocalendar()
    return or_(
        ScheduleCell.year > iso.year,
        and_(ScheduleCell.year == iso.year, ScheduleCell.week > iso.week),
        and_(
            ScheduleCell.year == iso.year,
            ScheduleCell.week == iso.week,
            ScheduleCell.weekday > iso.weekday,
        ),
    )


def purge_future_schedule_cells(db: Session, *, person_ids: list[int], now=None) -> int:
    """Ta bort personers framtida celler (datum > idag). Historiken rörs inte."""
    if not person_ids:
        return 0
    return int(
        db.query(ScheduleCell)
        .filter(ScheduleCell.person_id.in_(person_ids), _future_ywd_condition(now))
        .delete(synchronize_session=False)
    )


def clear_future_cells_for_activities(db: Session, activity_ids: list[int], *, now=None) -> int:
    """Töm framtida celler som pekar på aktiviteterna. Historiska celler rörs inte."""
    if not activity_ids:
        return 0
    return int(
        db.query(ScheduleCell)
        .filter(ScheduleCell.activity_id.in_(activity_ids), _future_ywd_condition(now))
        .update(
            {ScheduleCell.activity_id: None, ScheduleCell.empty_override: True},
            synchronize_session=False,
        )
    )


def clear_future_loan_markers(db: Session, area_id: int, *, now=None) -> int:
    """Nollställ framtida lånemarkeringar mot området. Historiska rörs inte."""
    return int(
        db.query(ScheduleCell)
        .filter(ScheduleCell.loan_area_id == area_id, _future_ywd_condition(now))
        .update({ScheduleCell.loan_area_id: None}, synchronize_session=False)
    )


def advance_freeze_horizon(db: Session, new_date: date) -> None:
    """Flytta frysgränsen framåt (aldrig bakåt)."""
    row = db.get(ScheduleFreezeState, 1)
    if row is None:
        db.add(ScheduleFreezeState(id=1, frozen_until=new_date))
        set_cached_freeze_horizon(db, new_date)
    elif row.frozen_until is None or new_date > row.frozen_until:
        row.frozen_until = new_date
        set_cached_freeze_horizon(db, new_date)


def _lock_freeze_state(db: Session) -> date | None:
    """Radlås singelraden och returnera den auktoritativa frysgränsen.

    Låset serialiserar samtidiga materialiseringar (bakgrundsjobbet och en
    request-väg kan köra samtidigt vid första deployen). Eftersom kontrollen
    och insättningen sker i samma låsta transaktion kan två processer aldrig
    skriva fill-celler för samma dag och krocka på unik-nyckeln. Läsningen
    friskar också sessionscachen, som annars kunde vara inaktuell.

    MSSQL saknar ``FOR UPDATE``: SQLAlchemy tystar bort ``with_for_update()``
    där helt, så utan tabellhinten vore låset verkningslöst i drift. Hinten
    gäller bara mssql; ``with_for_update()`` täcker Postgres. På SQLite blir
    det en no-op, vilket duger eftersom lokal drift är enprocessig.
    """
    row = db.execute(
        select(ScheduleFreezeState)
        .where(ScheduleFreezeState.id == 1)
        .with_hint(ScheduleFreezeState, "WITH (UPDLOCK, HOLDLOCK)", "mssql")
        .with_for_update()
    ).scalar_one_or_none()
    horizon = row.frozen_until if row is not None else None
    set_cached_freeze_horizon(db, horizon)
    return horizon


def _stamp_activity_areas(db: Session, target_date: date) -> int:
    """Snäpp fast vilket område varje cells aktivitet tillhörde den dagen.

    Historisk bemanning per område ska stå still även om en aktivitet senare
    flyttas till ett annat område. Utan stämpeln läses området live ur
    ``Activity.area_id`` och en omorganisation skriver om hur mycket som
    bemannades var.
    """
    iso = target_date.isocalendar()
    return int(
        db.query(ScheduleCell)
        .filter(
            ScheduleCell.year == iso.year,
            ScheduleCell.week == iso.week,
            ScheduleCell.weekday == iso.weekday,
            ScheduleCell.activity_id.is_not(None),
            ScheduleCell.activity_area_id.is_(None),
        )
        .update(
            {
                ScheduleCell.activity_area_id: select(Activity.area_id)
                .where(Activity.id == ScheduleCell.activity_id)
                .scalar_subquery()
            },
            synchronize_session=False,
        )
    )


def materialize_elapsed_hours(db: Session, *, now=None) -> dict:
    """Skriv ut dagens redan passerade malltimmar som celler.

    Dagens datum är en blandning av journal och plan: timmarna som passerat är
    utfört arbete och måste överleva en malländring mitt på dagen, medan
    timmarna som återstår fortfarande är en plan som ska följa ändringen.
    Gränsen går vid början av innevarande timme, samma skärning som
    Produktivitet använder för "avslutade timmar".

    Idempotent och billig: normalt finns högst en ny timme att skriva ut.
    Committar inte.
    """
    if now is None:
        now = datetime.now(LOCAL_TIMEZONE)
    today = _local_today(now)
    current_hour = now.hour if isinstance(now, datetime) else 0

    cutoff = get_elapsed_cutoff(db)
    if cutoff is not None and cutoff[0] == today and cutoff[1] >= current_hour:
        return {"date": today.isoformat(), "status": "current", "cells_created": 0}

    cells = [
        cell
        for cell in _build_fill_cells(db, today)
        if cell.hour < current_hour
    ]
    if cells:
        db.add_all(cells)
    _stamp_activity_areas(db, today)

    row = db.get(ScheduleFreezeState, 1)
    if row is None:
        row = ScheduleFreezeState(id=1)
        db.add(row)
    row.elapsed_date = today
    row.elapsed_hour = current_hour
    set_cached_elapsed_cutoff(db, (today, current_hour))
    return {
        "date": today.isoformat(),
        "status": "materialized",
        "through_hour": current_hour,
        "cells_created": len(cells),
    }


def materialize_schedule_day(db: Session, target_date: date, *, now=None) -> dict:
    """Materialisera en dags implicita malltimmar och flytta fram frysgränsen.

    Idempotent: redan frysta datum hoppas över. Dagens datum och framtid
    materialiseras aldrig (de ska fortsätta följa mallen live).
    Committar inte; anroparen äger transaktionen.
    """
    today = _local_today(now)
    if target_date >= today:
        return {"date": target_date.isoformat(), "status": "not_past", "cells_created": 0}
    horizon = _lock_freeze_state(db)
    if horizon is not None and target_date <= horizon:
        return {"date": target_date.isoformat(), "status": "already_frozen", "cells_created": 0}

    to_create = _build_fill_cells(db, target_date)
    if to_create:
        db.add_all(to_create)
        db.flush()
    _stamp_activity_areas(db, target_date)
    advance_freeze_horizon(db, target_date)
    audit_log(
        db,
        entity_type="schedule_freeze",
        entity_id=int(target_date.strftime("%Y%m%d")),
        action="materialize",
        old_value=None,
        new_value={"date": target_date.isoformat(), "cells_created": len(to_create)},
        user_id=None,
        business_id=None,
    )
    return {
        "date": target_date.isoformat(),
        "status": "materialized",
        "cells_created": len(to_create),
    }


def _build_fill_cells(
    db: Session, target_date: date, *, person_ids_filter: list[int] | None = None
) -> list[ScheduleCell]:
    """Bygg fill-celler för en dags implicita malltimmar (utan att spara)."""
    iso = target_date.isocalendar()
    persons_query = select(Person).where(Person.is_active, Person.has_fixed_schedule)
    if person_ids_filter is not None:
        if not person_ids_filter:
            return []
        persons_query = persons_query.where(Person.id.in_(person_ids_filter))
    persons = db.execute(persons_query).scalars().all()
    person_ids = [person.id for person in persons]
    template_map = get_template_hours_map_for_dates(db, person_ids, [target_date])

    cells_by_person_hour: dict[tuple[int, int], list[ScheduleCell]] = {}
    if person_ids:
        rows = (
            db.execute(
                select(ScheduleCell).where(
                    ScheduleCell.year == iso.year,
                    ScheduleCell.week == iso.week,
                    ScheduleCell.weekday == iso.weekday,
                    ScheduleCell.person_id.in_(person_ids),
                )
            )
            .scalars()
            .all()
        )
        for cell in rows:
            cells_by_person_hour.setdefault((cell.person_id, cell.hour), []).append(cell)

    to_create: list[ScheduleCell] = []
    for person in persons:
        template_hours = template_map.get((person.id, target_date))
        if not template_hours:
            continue
        for hour in sorted(template_hours):
            existing = cells_by_person_hour.get((person.id, hour), [])
            for minute_start, minute_end in _uncovered_intervals(_blocking_intervals(existing)):
                if person.home_activity_id is not None:
                    activity_id: int | None = person.home_activity_id
                    empty_override = False
                else:
                    activity_id = None
                    empty_override = True
                to_create.append(
                    ScheduleCell(
                        year=iso.year,
                        week=iso.week,
                        weekday=iso.weekday,
                        hour=hour,
                        minute_start=minute_start,
                        minute_end=minute_end,
                        person_id=person.id,
                        activity_id=activity_id,
                        loan_area_id=None,
                        empty_override=empty_override,
                        is_template_fill=True,
                        version=1,
                        updated_by=None,
                    )
                )

    return to_create


def person_predates_today(person: Person, *, now=None) -> bool:
    """Fanns personen redan före idag?

    Skiljer en felskapad person (skapad idag, inget schema) från någon vars
    dag är en del av historiken.
    """
    created = person.created_at
    if created is None:
        return True
    created_date = (
        created.astimezone(LOCAL_TIMEZONE).date()
        if isinstance(created, datetime) and created.tzinfo is not None
        else (created.date() if isinstance(created, datetime) else created)
    )
    return created_date < _local_today(now)




def freeze_pending_for_request(db: Session) -> dict:
    """Säkra journalen fram till nu innan en registerändring skrivs.

    Två luckor stängs: gårdagen kan vara ofryst (bakgrundsjobbet går var 30:e
    minut, så mellan midnatt och första passet är den fortfarande live), och
    dagens redan passerade timmar är utfört arbete som en malländring annars
    skulle rita om. Taket gör att en oväntat stor backfill (t.ex. första
    deployen) lämnas till bakgrundsjobbet i stället för att låsa ett
    användaranrop.
    """
    result = materialize_pending_days(db, max_days=REQUEST_PATH_MAX_DAYS)
    result["elapsed"] = materialize_elapsed_hours(db)
    return result


def _earliest_relevant_date(db: Session) -> date | None:
    """Äldsta datum som kan ha schemadata: äldsta cell eller äldsta person."""
    earliest_cell = db.execute(
        select(ScheduleCell.year, ScheduleCell.week, ScheduleCell.weekday)
        .order_by(ScheduleCell.year, ScheduleCell.week, ScheduleCell.weekday)
        .limit(1)
    ).first()
    cell_date: date | None = None
    if earliest_cell is not None:
        try:
            cell_date = date.fromisocalendar(
                int(earliest_cell.year), int(earliest_cell.week), int(earliest_cell.weekday)
            )
        except ValueError:
            cell_date = None

    earliest_created = db.execute(select(Person.created_at).order_by(Person.created_at).limit(1)).scalar()
    created_date: date | None = None
    if earliest_created is not None:
        if getattr(earliest_created, "tzinfo", None) is not None:
            created_date = earliest_created.astimezone(LOCAL_TIMEZONE).date()
        else:
            created_date = earliest_created.date()

    candidates = [candidate for candidate in (cell_date, created_date) if candidate is not None]
    return min(candidates) if candidates else None


def materialize_pending_days(db: Session, *, now=None, max_days: int | None = None) -> dict:
    """Materialisera alla ofrysta datum till och med gårdagen. Commit per dag.

    Första körningen (ingen frysgräns) backfyller hela historiken från äldsta
    relevanta datum. Finns varken schemadata eller personer fryses gårdagen
    direkt så gränsen kommer på plats.

    ``max_days`` används av request-vägarna: ligger fler dagar och väntar än så
    hoppas jobbet över och lämnas till bakgrundsjobbet, så en registerändring
    aldrig drar igång en flera minuter lång backfill inne i ett HTTP-anrop.
    """
    today = _local_today(now)
    target_end = today - timedelta(days=1)
    horizon = get_schedule_freeze_horizon(db)
    if horizon is None:
        start = _earliest_relevant_date(db) or target_end
        logger.info(
            "Schemafrysning initieras: backfyller %s..%s.",
            start.isoformat(),
            target_end.isoformat(),
        )
    else:
        start = horizon + timedelta(days=1)
    if start > target_end:
        return {"status": "current", "days": 0, "cells_created": 0}
    pending_days = (target_end - start).days + 1
    if max_days is not None and pending_days > max_days:
        logger.info(
            "Schemafrysning uppskjuten till bakgrundsjobbet: %d dagar väntar (tak %d).",
            pending_days,
            max_days,
        )
        return {"status": "deferred", "days": 0, "cells_created": 0, "pending_days": pending_days}

    days = 0
    cells_created = 0
    current = start
    while current <= target_end:
        try:
            result = materialize_schedule_day(db, current, now=now)
            db.commit()
        except IntegrityError:
            # Skyddsnät bakom radlåset: skulle två processer ändå hinna skriva
            # samma dag vinner den första och den andra hoppar vidare. Att låta
            # felet bubbla vore värre - då stannar hela frysningen.
            db.rollback()
            set_cached_freeze_horizon(db, None)
            logger.warning(
                "Schemafrysning: %s materialiserades redan av en annan process.",
                current.isoformat(),
            )
            current += timedelta(days=1)
            continue
        if result["status"] == "materialized":
            days += 1
            cells_created += int(result["cells_created"])
        current += timedelta(days=1)
    logger.info(
        "Schemafrysning klar till %s: %d dagar, %d materialiserade celler.",
        target_end.isoformat(),
        days,
        cells_created,
    )
    return {"status": "materialized", "days": days, "cells_created": cells_created}


_scheduler_started = threading.Event()


def run_schedule_freeze_scheduler(
    *,
    interval_seconds: int = SCHEDULER_INTERVAL_SECONDS,
    stop_event: threading.Event | None = None,
) -> None:
    """Bakgrundsloop: materialisera ofrysta dagar, sedan vila. Körs bakom ledarlåset."""
    from .database import SessionLocal

    if _scheduler_started.is_set():
        return
    _scheduler_started.set()
    while True:
        try:
            db = SessionLocal()
            try:
                materialize_pending_days(db)
                materialize_elapsed_hours(db)
                db.commit()
            finally:
                db.close()
        except Exception:
            logger.warning("Schemafrysningsjobbet misslyckades; försöker igen nästa pass.", exc_info=True)
        if stop_event is not None and stop_event.wait(interval_seconds):
            return
        if stop_event is None:
            time.sleep(interval_seconds)


def _cli(argv: list[str] | None = None) -> int:
    """Manuell körning: `python -m app.backend.schedule_freeze [--status]`."""
    import argparse

    from .database import SessionLocal

    parser = argparse.ArgumentParser(description="Schemafrysning: materialisera ofrysta dagar.")
    parser.add_argument("--status", action="store_true", help="Visa bara frysgränsen.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = SessionLocal()
    try:
        horizon = get_schedule_freeze_horizon(db)
        print(f"Frysgräns: {horizon.isoformat() if horizon else 'ej initierad'}")
        if args.status:
            return 0
        result = materialize_pending_days(db)
        print(
            f"Resultat: {result['status']}, {result['days']} dagar, "
            f"{result['cells_created']} materialiserade celler."
        )
        horizon = get_schedule_freeze_horizon(db)
        print(f"Ny frysgräns: {horizon.isoformat() if horizon else 'ej initierad'}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
