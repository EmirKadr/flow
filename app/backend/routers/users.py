from __future__ import annotations

import io
import unicodedata
from dataclasses import dataclass
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .. import audit
from ..deps import get_db, require_admin, require_super_admin
from ..models import User
from ..schemas import UserAdminOut, UserCreate, UserImportError, UserImportResult, UserUpdate
from ..security import hash_password
from ..user_access import user_admin_out

router = APIRouter(prefix="/api/users", tags=["users"])

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_IMPORT_BYTES = 5 * 1024 * 1024

HEADER_ALIASES = {
    "anvandarnamn": "username",
    "username": "username",
    "user": "username",
    "namn": "display_name",
    "name": "display_name",
    "visningsnamn": "display_name",
    "displayname": "display_name",
    "roll": "role",
    "role": "role",
}

ROLE_ALIASES = {
    "admin": "admin",
    "administrator": "admin",
    "arbetsledare": "leader",
    "ledare": "leader",
    "leader": "leader",
}


@dataclass(frozen=True)
class ImportUserRow:
    row_number: int
    username: str
    display_name: str | None
    role: str


def _find_username_conflict(db: Session, username: str, *, exclude_user_id: int | None = None) -> User | None:
    query = db.query(User).filter(func.lower(User.username) == username.lower())
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.order_by(User.id.asc()).first()


def _active_admin_count(db: Session, *, exclude_user_id: int | None = None) -> int:
    query = db.query(func.count(User.id)).filter(User.role.in_(("admin", "super_admin")), User.is_active.is_(True))
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return int(query.scalar() or 0)


def _user_snapshot(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": bool(user.must_change_password or user.password_hash is None),
    }


def _compact_key(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return "".join(ch for ch in without_marks.strip().lower() if ch.isalnum())


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _header_mapping(headers: tuple[object, ...] | list[object] | None) -> dict[int, str]:
    if not headers:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Excel-filen saknar rubrikrad")

    mapping: dict[int, str] = {}
    for index, field in enumerate(headers):
        canonical = HEADER_ALIASES.get(_compact_key(_cell_text(field)))
        if canonical:
            mapping[index] = canonical

    missing = {"username", "display_name", "role"} - set(mapping.values())
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Excel-filen måste ha kolumnerna användarnamn, namn och roll",
        )
    return mapping


def _normalize_role(value: str) -> str | None:
    return ROLE_ALIASES.get(_compact_key(value))


def build_user_import_template_excel() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Användare"
    sheet.append(["användarnamn", "namn", "roll"])
    sheet.column_dimensions["A"].width = 24
    sheet.column_dimensions["B"].width = 28
    sheet.column_dimensions["C"].width = 18
    sheet.freeze_panes = "A2"

    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def parse_user_import_excel(content: bytes) -> tuple[list[ImportUserRow], list[UserImportError]]:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Excel-filen kunde inte läsas")

    sheet = workbook.worksheets[0]
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        headers = next(rows_iter)
    except StopIteration:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Excel-filen saknar rubrikrad")

    mapping = _header_mapping(headers)
    rows: list[ImportUserRow] = []
    errors: list[UserImportError] = []

    for row_number, raw_row in enumerate(rows_iter, start=2):
        values = {
            canonical: _cell_text(raw_row[index] if index < len(raw_row) else None)
            for index, canonical in mapping.items()
        }
        if not any(values.values()):
            continue

        username = values["username"]
        display_name = values["display_name"] or None
        role_value = values["role"]

        if not username:
            errors.append(UserImportError(row=row_number, error="Användarnamn saknas"))
            continue
        if len(username) > 50:
            errors.append(UserImportError(row=row_number, username=username, error="Användarnamn får vara max 50 tecken"))
            continue
        if display_name is not None and len(display_name) > 100:
            errors.append(UserImportError(row=row_number, username=username, error="Namn får vara max 100 tecken"))
            continue

        role = _normalize_role(role_value)
        if role is None:
            errors.append(
                UserImportError(
                    row=row_number,
                    username=username,
                    error="Roll måste vara admin eller arbetsledare",
                )
            )
            continue

        rows.append(ImportUserRow(row_number=row_number, username=username, display_name=display_name, role=role))

    return rows, errors


@router.get("", response_model=list[UserAdminOut])
def list_users(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[User]:
    query = db.query(User)
    if not include_inactive:
        query = query.filter(User.is_active.is_(True))
    users = query.order_by(case((User.role.in_(("admin", "super_admin")), 0), else_=1), User.username.asc()).all()
    return [user_admin_out(user) for user in users]


@router.get("/import-template")
def download_import_template(_admin: User = Depends(require_super_admin)) -> Response:
    return Response(
        content=build_user_import_template_excel(),
        media_type=EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="anvandare-importmall.xlsx"'},
    )


@router.post("/import", response_model=UserImportResult)
async def import_users(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> UserImportResult:
    content = await file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Excel-filen är för stor")

    rows, errors = parse_user_import_excel(content)
    seen: set[str] = set()
    created = 0

    for row in rows:
        username_key = row.username.lower()
        if username_key in seen:
            errors.append(UserImportError(row=row.row_number, username=row.username, error="Dubblett i Excel-filen"))
            continue
        seen.add(username_key)

        if _find_username_conflict(db, row.username):
            errors.append(UserImportError(row=row.row_number, username=row.username, error="Användarnamnet används redan"))
            continue

        user = User(
            username=row.username,
            password_hash=None,
            display_name=row.display_name,
            role=row.role,
            is_active=True,
            must_change_password=True,
        )
        db.add(user)
        db.flush()

        audit.log(
            db,
            entity_type="user",
            entity_id=user.id,
            action="import_create",
            old_value=None,
            new_value=_user_snapshot(user),
            user_id=admin.id,
        )
        created += 1

    db.commit()
    return UserImportResult(created=created, skipped=len(errors), errors=errors)


@router.post("", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserAdminOut:
    if _find_username_conflict(db, payload.username):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Användarnamnet används redan")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password) if payload.password else None,
        display_name=payload.display_name,
        role=payload.role,
        is_active=payload.is_active,
        must_change_password=payload.password is None,
    )
    db.add(user)
    db.flush()

    audit.log(
        db,
        entity_type="user",
        entity_id=user.id,
        action="create",
        old_value=None,
        new_value=_user_snapshot(user),
        user_id=admin.id,
    )

    db.commit()
    db.refresh(user)
    return user_admin_out(user)


@router.put("/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserAdminOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Användare hittades inte")

    if payload.username is not None and _find_username_conflict(db, payload.username, exclude_user_id=user_id):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Användarnamnet används redan")

    new_role = payload.role if payload.role is not None else user.role
    new_is_active = payload.is_active if payload.is_active is not None else user.is_active
    removes_admin_access = user.role == "admin" and (new_role != "admin" or not new_is_active)
    if removes_admin_access and _active_admin_count(db, exclude_user_id=user.id) == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Det måste finnas minst en aktiv administratör kvar",
        )

    before = _user_snapshot(user)
    updates = payload.model_dump(exclude_unset=True, exclude={"password"})
    for key, value in updates.items():
        setattr(user, key, value)
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        user.must_change_password = False

    audit.log(
        db,
        entity_type="user",
        entity_id=user.id,
        action="update",
        old_value=before,
        new_value=_user_snapshot(user),
        user_id=admin.id,
    )

    db.commit()
    db.refresh(user)
    return user_admin_out(user)
