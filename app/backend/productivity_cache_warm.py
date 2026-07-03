"""Warm-orkestrering for produktivitetscacharna.

Bygger dagrapporten EN gang och matar bade person_productivity_daily
(Bemanning) och overview-report (Produktivitet) fran samma build. Bruten ut
fran productivity_sync for att halla den modulen under radgransen.

De tva cacharna bedoms fristaende: ar bada redan aktuella (signaturer stammer)
skippas bygget helt; annars byggs rapporten en gang och den eller de cachar som
ar inaktuella skrivs om.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from .person_productivity_cache import (
    build_person_productivity_report_from_files,
    materialize_person_productivity_daily,
    person_productivity_cache_is_current,
    productivity_cache_schedule_signature,
    productivity_snapshot_signature,
)
from .productivity_sync_paths import (
    overview_report_cache_is_current,
    write_overview_report_cache,
)


def ensure_person_and_overview_caches(
    db: Session,
    files: dict[str, Path],
    *,
    report_date: date,
    business_id: int | None,
    sync: dict[str, Any] | None = None,
    reference_dir: Path | str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Bygg dagrapporten en gang och persistera bada cacharna fran samma build."""
    snapshot_signature = productivity_snapshot_signature(sync)
    schedule_signature = productivity_cache_schedule_signature(
        db, report_date, business_id=business_id
    )

    person_current = not force and person_productivity_cache_is_current(
        db, report_date, business_id=business_id, sync=sync
    )
    overview_current = not force and overview_report_cache_is_current(
        report_date,
        business_id,
        snapshot_signature=snapshot_signature,
        schedule_signature=schedule_signature,
        reference_dir=reference_dir,
    )

    if person_current and overview_current:
        # Bada aktuella -> ingen ombyggnad, ingen overview_report-markering.
        return {
            "date": report_date.isoformat(),
            "status": "current",
            "rows": 0,
        }

    # Bygg dagrapporten EN gang och mata bada cacharna fran den.
    report = build_person_productivity_report_from_files(
        db,
        files,
        report_date=report_date,
        business_id=business_id,
        sync=sync,
    )

    if person_current:
        result: dict[str, Any] = {
            "date": report_date.isoformat(),
            "status": "current",
            "rows": 0,
        }
    else:
        result = materialize_person_productivity_daily(
            db,
            files,
            report_date=report_date,
            business_id=business_id,
            sync=sync,
            report=report,
        )

    if overview_current:
        result["overview_report"] = "current"
    else:
        write_overview_report_cache(
            report_date,
            business_id,
            jsonable_encoder(report),
            snapshot_signature=snapshot_signature,
            schedule_signature=schedule_signature,
            reference_dir=reference_dir,
        )
        result["overview_report"] = "materialized"

    return result
