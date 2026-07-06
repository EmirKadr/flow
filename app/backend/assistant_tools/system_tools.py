"""Tools för system och administration: användare, behörigheter, RFID, filer, hälsa.

Endast sanerad metadata exponeras — aldrig lösenordshashar, tokens eller filinnehåll.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..healthcheck_service import run_healthcheck
from ..models import Area, CoreDataFile, RfidDevice, RfidScanEvent, User
from ..settings_service import get_role_view_access
from ..user_access import is_super_user, normalize_user_roles
from .common import clamp_limit, parse_period_arg, resolve_business_id, truncation_note
from .registry import register_tool

_BUSINESS_PARAM = {
    "type": "string",
    "description": "Verksamhet som id, kod eller namn. Utelämna för användarens egen verksamhet.",
}
_PERIOD_PARAM = {
    "type": "string",
    "description": "Period bakåt i tiden: 1h, 24h, 7d eller 30d. Default 24h.",
}


@register_tool(
    name="list_users",
    title="Lista användare",
    description=(
        "Lista appens användarkonton med roller, område och aktiv-status. "
        "Innehåller aldrig lösenord eller sessionsdata."
    ),
    parameters={
        "type": "object",
        "properties": {
            "business": _BUSINESS_PARAM,
            "role": {"type": "string", "description": "Filtrera på roll, t.ex. admin eller leader."},
            "include_inactive": {"type": "boolean", "description": "Ta även med inaktiva konton."},
            "limit": {"type": "integer", "description": "Max antal rader (default 50, max 200)."},
        },
    },
    view_id="users",
)
def list_users_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    limit = clamp_limit(args.get("limit"))
    query = db.query(User).order_by(User.username)
    if business_id is not None:
        query = query.filter(User.business_id == business_id)
    if not args.get("include_inactive"):
        query = query.filter(User.is_active)
    role = str(args.get("role") or "").strip().lower()
    users = query.limit(500).all()
    if role:
        users = [entry for entry in users if role in normalize_user_roles(entry.roles, entry.role)]
    total = len(users)
    area_ids = {entry.area_id for entry in users if entry.area_id is not None}
    areas = {row.id: row for row in db.query(Area).filter(Area.id.in_(area_ids)).all()} if area_ids else {}
    rows = [
        {
            "id": entry.id,
            "username": entry.username,
            "display_name": entry.display_name,
            "roles": normalize_user_roles(entry.roles, entry.role),
            "is_super_user": is_super_user(entry),
            "business_id": entry.business_id,
            "area": areas[entry.area_id].code if entry.area_id in areas else None,
            "is_active": bool(entry.is_active),
        }
        for entry in users[:limit]
    ]
    result: dict[str, Any] = {"users": rows, "count": total}
    note = truncation_note(total, len(rows))
    if note:
        result["note"] = note
    return result


@register_tool(
    name="get_role_view_access_matrix",
    title="Vybehörigheter",
    description="Hämta behörighetsmatrisen roll -> vy -> nivå (edit/view/none) som styr sidebaren.",
    parameters={
        "type": "object",
        "properties": {"business": _BUSINESS_PARAM},
    },
    view_id="roleAccess",
)
def get_role_view_access_matrix_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    try:
        access = get_role_view_access(db, business_id=business_id)
    except TypeError:
        access = get_role_view_access(db)
    return {"role_view_access": access or {}}


@register_tool(
    name="list_rfid_devices",
    title="RFID-enheter",
    description="Lista RFID-enheter med modulnamn, kopplad aktivitet, aktiv-status och när de sågs senast.",
    parameters={
        "type": "object",
        "properties": {"business": _BUSINESS_PARAM},
    },
    view_id="analytics",
)
def list_rfid_devices_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    query = db.query(RfidDevice).order_by(RfidDevice.module_name)
    if business_id is not None:
        query = query.filter(RfidDevice.business_id == business_id)
    rows = [
        {
            "id": device.id,
            "module_name": device.module_name,
            "activity_id": device.activity_id,
            "is_active": bool(device.is_active),
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        }
        for device in query.limit(200).all()
    ]
    return {"devices": rows, "count": len(rows)}


@register_tool(
    name="rfid_scan_stats",
    title="RFID-statistik",
    description="Antal RFID-stämplingar per status (pending/applied/ignored m.fl.) under en period.",
    parameters={
        "type": "object",
        "properties": {"period": _PERIOD_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="analytics",
)
def rfid_scan_stats_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"))
    query = db.query(RfidScanEvent.status, func.count(RfidScanEvent.id)).filter(
        RfidScanEvent.scan_time >= since
    )
    if business_id is not None:
        query = query.filter(RfidScanEvent.business_id == business_id)
    rows = query.group_by(RfidScanEvent.status).order_by(func.count(RfidScanEvent.id).desc()).all()
    return {
        "period": period,
        "stats": [{"status": status, "count": int(count or 0)} for status, count in rows],
    }


@register_tool(
    name="list_coredata_files",
    title="Kärnfiler",
    description="Lista uppladdade kärnfiler (grunddata) med filtyp, storlek och senaste uppdatering. Aldrig filinnehåll.",
    parameters={
        "type": "object",
        "properties": {"business": _BUSINESS_PARAM},
    },
    view_id="allocationUploads",
)
def list_coredata_files_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    query = db.query(CoreDataFile).order_by(CoreDataFile.business_code, CoreDataFile.file_type)
    if business_id is not None:
        from ..models import Business

        business = db.get(Business, business_id)
        if business is not None:
            query = query.filter(CoreDataFile.business_code == business.code)
    rows = [
        {
            "business_code": entry.business_code,
            "file_type": entry.file_type,
            "filename": entry.filename,
            "size_bytes": int(entry.size_bytes or 0),
            "source": entry.source,
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        }
        for entry in query.limit(200).all()
    ]
    return {"files": rows, "count": len(rows)}


@register_tool(
    name="healthcheck_summary",
    title="Systemhälsa",
    description="Kör den lokala hälsokontrollen och returnera status per kontroll (app, databas, bakgrundsjobb).",
    view_id="analytics",
)
def healthcheck_summary_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    report = run_healthcheck(db=db)
    return {
        "status": report.get("status"),
        "generated_at": report.get("generated_at"),
        "checks": [
            {
                "name": check.get("name"),
                "status": check.get("status"),
                "message": check.get("message"),
            }
            for check in report.get("checks", [])
        ],
    }
