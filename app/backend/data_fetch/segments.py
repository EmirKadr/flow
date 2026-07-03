"""Retention-/arkivsegmentering av hämtningsplaner (live- vs dblog-vyer)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from . import core
from .core import (
    DataCatalog,
    DataFetchPlanError,
    DataView,
    _date_period_payload,
    _period_values_for_column,
    _preferred_date_column,
)


# Live radnivå-vy -> (retention-dagar i operativa WManFrey, arkivvy-id i log_wmanfrey).
# Endast tabeller som har archive="true" i rensnings-/arkiveringsjobbet OCH bade en
# live- och en dblog-vy i katalogen. Se wiki/ask-datalagring.md.
LIVE_ARCHIVE_PAIRS: dict[str, tuple[int, str]] = {
    "v_ask_pick_log_full": (40, "dblog_pick_log"),
    "v_ask_trans_log": (60, "dblog_trans_log"),
    "v_ask_order_log": (80, "dblog_order_log"),
    "v_ask_palletloading_log": (60, "dblog_loading_log"),
    "dispatch_pallet_log": (14, "dblog_dispatch_pallet_log"),
    "v_ask_receive_log": (60, "dblog_receive_log"),
    "v_ask_correct_log": (60, "dblog_correct_log"),
    "v_ask_count_log": (90, "dblog_count_log"),
    "v_ask_login_log": (60, "dblog_login_log"),
    "v_ask_robot_pick_log": (30, "dblog_robot_pick_log"),
    "v_ask_pick_rest_log": (60, "dblog_pick_rest_log"),
    "v_ask_return_order_log": (60, "dblog_return_order_log"),
    "v_ask_trace_log": (60, "dblog_trace_log"),
    "v_ask_fill_rate_log": (30, "dblog_fill_rate_log"),
    "v_ask_pallet_rent_log_raw": (3, "dblog_pallet_rent_log_raw"),
}
ARCHIVE_TO_LIVE: dict[str, tuple[int, str]] = {
    archive_id: (days, live_id) for live_id, (days, archive_id) in LIVE_ARCHIVE_PAIRS.items()
}


def _parse_plan_date_bound(value: Any) -> date | None:
    """Tolka ett Between-gränsvärde (YYYYMMDD-int, ISO-datum eller ISO-datetime) som datum."""
    if isinstance(value, bool) or value is None:
        return None
    text = str(int(value)) if isinstance(value, (int, float)) else str(value).strip()
    if not text:
        return None
    digits = text.split("T", 1)[0].replace("-", "")
    if len(digits) >= 8 and digits[:8].isdigit():
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        except ValueError:
            return None
    return None


def _plan_date_window(plan: dict[str, Any], view: DataView) -> tuple[int, date, date] | None:
    """Hitta planens Between-datumfilter på vyns föredragna datumkolumn."""
    date_column = _preferred_date_column(view)
    if date_column is None:
        return None
    for index, item in enumerate(plan.get("filters") or []):
        if str(item.get("operator") or "") != "Between":
            continue
        if (item.get("id") or item.get("field")) != date_column.id:
            continue
        value = item.get("value")
        if not isinstance(value, list) or len(value) != 2:
            continue
        start = _parse_plan_date_bound(value[0])
        end = _parse_plan_date_bound(value[1])
        if start and end and start <= end:
            return index, start, end
    return None


def _segment_plan(
    plan: dict[str, Any],
    target_view: DataView,
    period_start: date,
    period_end: date,
    *,
    source_date_column_id: str | None,
) -> dict[str, Any]:
    """Bygg en minimal hämtningsplan för target_view begränsad till [start, end].

    Behåller bara filter vars kolumn finns i target_view och ersätter källans
    datumfilter med target_view:s egen datumkolumn för delperioden.
    """
    filters: list[dict[str, Any]] = []
    for item in plan.get("filters") or []:
        column_id = item.get("id") or item.get("field")
        operator = str(item.get("operator") or "")
        if operator == "Between" and column_id == source_date_column_id:
            continue
        if column_id in target_view.column_by_id:
            filters.append(dict(item))
    target_date_column = _preferred_date_column(target_view)
    if target_date_column is not None:
        period = _date_period_payload("segment", period_start, period_end)
        filters.append(
            {
                "id": target_date_column.id,
                "operator": "Between",
                "value": _period_values_for_column(period, target_date_column),
            }
        )
    identifiers = [
        row
        for row in (plan.get("identifiers") or [])
        if isinstance(row, dict) and row and all(key in target_view.column_by_id for key in row)
    ]
    return {
        "status": "ok",
        "view": target_view.id,
        "view_label": target_view.label,
        "filters": filters,
        "identifiers": identifiers,
    }


def build_retention_segments(
    plan: dict[str, Any],
    catalog: DataCatalog,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Avgör om planens datumperiod kräver arkivvyn och/eller live-vyn.

    Returnerar None när planen ska köras oförändrad (en vy), annars en dict med
    ``segments`` (1–2 hämtningsplaner att slå ihop), ``notice`` (svensk text till
    användaren) och ``fetched_views`` (vy-id som faktiskt hämtas).
    """
    if plan.get("status") != "ok":
        return None
    view_id = str(plan.get("view") or "")
    is_live = view_id in LIVE_ARCHIVE_PAIRS
    is_archive = view_id in ARCHIVE_TO_LIVE
    if not (is_live or is_archive):
        return None
    try:
        source_view = catalog.view(view_id)
    except DataFetchPlanError:
        return None
    window = _plan_date_window(plan, source_view)
    if window is None:
        return None
    _index, start, end = window
    source_date_id = getattr(_preferred_date_column(source_view), "id", None)
    today = today or core._app_now().date()

    def _label(view: DataView) -> str:
        return f"”{view.label}”"

    if is_live:
        days, archive_id = LIVE_ARCHIVE_PAIRS[view_id]
        try:
            archive_view = catalog.view(archive_id)
        except DataFetchPlanError:
            return None
        cutoff = today - timedelta(days=days)
        if start >= cutoff:
            return None  # hela perioden ryms i aktiv data
        if end < cutoff:
            segment = _segment_plan(plan, archive_view, start, end, source_date_column_id=source_date_id)
            notice = (
                f"{_label(source_view)} behålls bara ~{days} dagar i den aktiva databasen. "
                f"Hela perioden {start.isoformat()}–{end.isoformat()} hämtades därför från "
                f"arkivet {_label(archive_view)}. Kolumnerna skiljer sig från live-vyn, så "
                f"vissa fält kan vara tomma."
            )
            return {"segments": [segment], "notice": notice, "fetched_views": [archive_view.id]}
        live_segment = _segment_plan(plan, source_view, cutoff, end, source_date_column_id=source_date_id)
        archive_segment = _segment_plan(
            plan, archive_view, start, cutoff - timedelta(days=1), source_date_column_id=source_date_id
        )
        notice = (
            f"Perioden {start.isoformat()}–{end.isoformat()} spänner över gränsen för aktiv "
            f"data (~{days} dagar). Hämtade både {_label(source_view)} (från {cutoff.isoformat()}) "
            f"och arkivet {_label(archive_view)} (till {(cutoff - timedelta(days=1)).isoformat()}) "
            f"och slog ihop resultaten. Kolumnerna skiljer sig, så vissa fält kan vara tomma."
        )
        return {
            "segments": [live_segment, archive_segment],
            "notice": notice,
            "fetched_views": [source_view.id, archive_view.id],
        }

    days, live_id = ARCHIVE_TO_LIVE[view_id]
    try:
        live_view = catalog.view(live_id)
    except DataFetchPlanError:
        return None
    cutoff = today - timedelta(days=days)
    if end < cutoff:
        return None  # hela perioden ligger i arkivet, inget att lägga till
    archive_segment = _segment_plan(plan, source_view, start, end, source_date_column_id=source_date_id)
    live_start = max(start, cutoff)
    live_segment = _segment_plan(plan, live_view, live_start, end, source_date_column_id=source_date_id)
    notice = (
        f"Perioden {start.isoformat()}–{end.isoformat()} ligger delvis i den aktiva databasen "
        f"(~{days} dagar). Hämtade därför även {_label(live_view)} (från {live_start.isoformat()}) "
        f"utöver arkivet {_label(source_view)}. Kolumnerna skiljer sig, så vissa fält kan vara tomma."
    )
    return {
        "segments": [archive_segment, live_segment],
        "notice": notice,
        "fetched_views": [source_view.id, live_view.id],
    }
