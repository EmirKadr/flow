"""Forbygg-orkestrering for produktivitetscachen (idag + aktiva bolag).

Bruten ut fran productivity_sync for att halla den modulen under arkitektur-
kontraktets radgrans. Funktionerna anropar tillbaka in i productivity_sync via
en **lat** import (`from . import productivity_sync`) sa det inte blir en
cirkular import vid modulladdning - och sa att testernas monkeypatch pa
productivity_sync-attribut (t.ex. `_warm_person_productivity_daily_cache`,
`productivity_snapshot_status`) fortfarande slar igenom.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .business_scope import DEFAULT_BUSINESS_CODE
from .database import SessionLocal
from .models import Business
from .productivity_sync_paths import LOCAL_TZ

logger = logging.getLogger(__name__)

# Schemalaggaren toppar dagens snapshot var 30:e minut.
_PRODUCTIVITY_SYNC_INTERVAL_SECONDS = 30 * 60
# Tak for hur langt isar bolagens dagsbyggen sprids inom ett pass (staggering).
# Utan tak skulle interval/n ge orimligt glesa byggen vid fa bolag; med bygget
# nere pa ~1-2 s racker nagra sekunder for att undvika samtidig CPU-spik.
_TODAY_WARM_STAGGER_MAX_SECONDS = 60.0


def _active_business_codes(db: Session | None) -> list[str]:
    """Aktiva bolags koder i visningsordning; fallback [DEFAULT_BUSINESS_CODE]."""
    if db is None:
        return [DEFAULT_BUSINESS_CODE]
    try:
        rows = (
            db.query(Business.code)
            .filter(Business.is_active)
            .order_by(Business.sort_order, Business.id)
            .all()
        )
    except Exception:
        logger.warning("Kunde inte lista aktiva bolag for produktivitetsforbygge; anvander default.", exc_info=True)
        return [DEFAULT_BUSINESS_CODE]
    codes: list[str] = []
    seen: set[str] = set()
    for row in rows:
        code = str(row[0] or "").strip()
        key = code.lower()
        if code and key not in seen:
            seen.add(key)
            codes.append(code)
    return codes or [DEFAULT_BUSINESS_CODE]


def warm_today_for_businesses(
    *,
    now: datetime | None = None,
    business_codes: list[str] | None = None,
    reference_dir: Path | str | None = None,
    db: Session | None = None,
    stagger_seconds: float = 0.0,
) -> dict[str, Any]:
    """Forbygg IDAG:s produktivitetscache for varje aktivt bolag.

    Kors varje 30-min-pass sa dagens produktivitet redan ar byggd nar
    anvandaren oppnar den (inget on-demand-bygge for idag). Signaturvakten i
    _warm_person_productivity_daily_cache bygger bara om nar dagens snapshot
    faktiskt andrats sedan forra passet. `stagger_seconds` > 0 sprider bolagens
    byggen over passet sa de inte alla belastar podden samtidigt. Nar db=None
    oppnas en kortlivad session per bolag sa ingen DB-anslutning halls oppen
    over stagger-sovtiderna.
    """
    from . import productivity_sync as _psync  # lat import: bryter cirkeln

    current = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    day = current.date()
    if business_codes is None:
        probe = db if db is not None else SessionLocal()
        try:
            codes = _active_business_codes(probe)
        finally:
            if db is None:
                probe.close()
    else:
        codes = list(business_codes)

    results: list[dict[str, Any]] = []
    for index, code in enumerate(codes):
        if index and stagger_seconds > 0:
            time.sleep(stagger_seconds)
        session = db if db is not None else SessionLocal()
        try:
            status = _psync.productivity_snapshot_status(day, reference_dir=reference_dir)
            if not status.get("ready"):
                results.append({"business_code": code, "status": "snapshot_not_ready"})
                continue
            result = _psync._warm_person_productivity_daily_cache(
                session, day, reference_dir=reference_dir, business_code=code, sync=status,
            )
            entry: dict[str, Any] = {"business_code": code}
            if result is not None:
                entry.update(result)
            results.append(entry)
        finally:
            if db is None:
                session.close()
    return {
        "source": "today_warm",
        "date": day.isoformat(),
        "status": "ok",
        "businesses": results,
    }
