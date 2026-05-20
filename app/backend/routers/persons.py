import io
import unicodedata
from dataclasses import dataclass
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..deps import get_db, require_view_access
from ..models import Activity, Area, Person, User
from ..schemas import PersonCreate, PersonImportError, PersonImportResult, PersonOut, PersonUpdate

router = APIRouter(prefix="/api/persons", tags=["persons"])

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_IMPORT_BYTES = 5 * 1024 * 1024

HEADER_ALIASES = {
    "namn": "name",
    "name": "name",
    "person": "name",
    "personnamn": "name",
    "hemomrade": "home_area",
    "omrade": "home_area",
    "area": "home_area",
    "homearea": "home_area",
    "huvudstalle": "home_activity",
    "aktivitet": "home_activity",
    "homeactivity": "home_activity",
    "activity": "home_activity",
    "sortering": "sort_order",
    "sort": "sort_order",
    "sortorder": "sort_order",
}


@dataclass(frozen=True)
class ImportPersonRow:
    row_number: int
    name: str
    home_area: str | None
    home_activity: str | None
    sort_order: int | None


def _person_snapshot(person: Person) -> dict:
    return {
        "id": person.id,
        "name": person.name,
        "home_area_id": person.home_area_id,
        "home_activity_id": person.home_activity_id,
        "competencies": person.competencies,
        "comment": person.comment,
        "has_fixed_schedule": person.has_fixed_schedule,
        "is_active": person.is_active,
        "sort_order": person.sort_order,
    }


def _compact_key(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return "".join(ch for ch in without_marks.strip().lower() if ch.isalnum())


def _header_key(value: str | None) -> str:
    key = _compact_key(value)
    for marker in ("obligatorisk", "frivillig", "required", "optional"):
        if key.endswith(marker):
            return key[: -len(marker)]
    return key


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
        canonical = HEADER_ALIASES.get(_header_key(_cell_text(field)))
        if canonical:
            mapping[index] = canonical

    if "name" not in set(mapping.values()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Excel-filen måste ha kolumnen namn")
    return mapping


def _parse_sort_order(value: str, *, row_number: int, name: str) -> tuple[int | None, PersonImportError | None]:
    if not value:
        return None, None
    try:
        parsed = float(value.replace(",", "."))
    except ValueError:
        return None, PersonImportError(row=row_number, name=name or None, error="Sortering måste vara ett tal")
    if not parsed.is_integer():
        return None, PersonImportError(row=row_number, name=name or None, error="Sortering måste vara ett heltal")
    return int(parsed), None


def build_person_import_template_excel() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Personer"
    sheet.append(["namn (obligatorisk)", "hemområde (frivillig)", "huvudställe (frivillig)", "sortering (frivillig)"])
    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 24
    sheet.column_dimensions["C"].width = 28
    sheet.column_dimensions["D"].width = 14
    sheet.freeze_panes = "A2"

    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def parse_person_import_excel(content: bytes) -> tuple[list[ImportPersonRow], list[PersonImportError]]:
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
    rows: list[ImportPersonRow] = []
    errors: list[PersonImportError] = []

    for row_number, raw_row in enumerate(rows_iter, start=2):
        values = {
            canonical: _cell_text(raw_row[index] if index < len(raw_row) else None)
            for index, canonical in mapping.items()
        }
        if not any(values.values()):
            continue

        name = values.get("name", "").strip()
        if not name:
            errors.append(PersonImportError(row=row_number, error="Namn saknas"))
            continue
        if len(name) > 120:
            errors.append(PersonImportError(row=row_number, name=name, error="Namn får vara max 120 tecken"))
            continue

        sort_order, sort_error = _parse_sort_order(values.get("sort_order", ""), row_number=row_number, name=name)
        if sort_error is not None:
            errors.append(sort_error)
            continue

        rows.append(
            ImportPersonRow(
                row_number=row_number,
                name=name,
                home_area=values.get("home_area") or None,
                home_activity=values.get("home_activity") or None,
                sort_order=sort_order,
            )
        )

    return rows, errors


def _lookup_map(rows, *attrs: str) -> dict[str, object]:
    lookup: dict[str, object] = {}
    for row in rows:
        for attr in attrs:
            value = getattr(row, attr, None)
            key = _compact_key(str(value) if value is not None else "")
            if key:
                lookup.setdefault(key, row)
    return lookup


def _existing_person_names(db: Session) -> set[str]:
    return {_compact_key(name) for (name,) in db.query(Person.name).all()}


def _next_sort_order(db: Session) -> int:
    return int(db.query(func.max(Person.sort_order)).scalar() or 0) + 1


@router.get("", response_model=list[PersonOut])
def list_persons(
    include_inactive: bool = False,
    area_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_view_access("persons", "view")),
) -> list[Person]:
    q = db.query(Person)
    if not include_inactive:
        q = q.filter(Person.is_active.is_(True))
    if area_id is not None:
        q = q.filter(Person.home_area_id == area_id)
    return q.order_by(Person.sort_order, Person.name).all()


@router.get("/import-template")
def download_import_template(_user: User = Depends(require_view_access("personImport", "edit"))) -> Response:
    return Response(
        content=build_person_import_template_excel(),
        media_type=EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="personer-importmall.xlsx"'},
    )


@router.post("/import", response_model=PersonImportResult)
async def import_persons(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("personImport", "edit")),
) -> PersonImportResult:
    content = await file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Excel-filen är för stor")

    rows, errors = parse_person_import_excel(content)
    area_lookup = _lookup_map(db.query(Area).all(), "code", "name")
    activity_lookup = _lookup_map(db.query(Activity).all(), "code", "label")
    existing_names = _existing_person_names(db)
    seen_names: set[str] = set()
    next_sort = _next_sort_order(db)
    created = 0

    for row in rows:
        name_key = _compact_key(row.name)
        if name_key in seen_names:
            errors.append(PersonImportError(row=row.row_number, name=row.name, error="Dubblett i Excel-filen"))
            continue
        seen_names.add(name_key)

        if name_key in existing_names:
            errors.append(PersonImportError(row=row.row_number, name=row.name, error="Personen finns redan"))
            continue

        home_area_id = None
        if row.home_area:
            area = area_lookup.get(_compact_key(row.home_area))
            if area is None:
                errors.append(PersonImportError(row=row.row_number, name=row.name, error="Hemområde hittades inte"))
                continue
            home_area_id = area.id

        home_activity_id = None
        if row.home_activity:
            activity = activity_lookup.get(_compact_key(row.home_activity))
            if activity is None:
                errors.append(PersonImportError(row=row.row_number, name=row.name, error="Huvudställe hittades inte"))
                continue
            home_activity_id = activity.id
            if home_area_id is None:
                home_area_id = activity.area_id

        sort_order = row.sort_order if row.sort_order is not None else next_sort
        if row.sort_order is None:
            next_sort += 1

        person = Person(
            name=row.name,
            home_area_id=home_area_id,
            home_activity_id=home_activity_id,
            competencies=[],
            comment=None,
            is_active=True,
            sort_order=sort_order,
        )
        db.add(person)
        db.flush()

        audit_log(
            db,
            entity_type="person",
            entity_id=person.id,
            action="import_create",
            old_value=None,
            new_value=_person_snapshot(person),
            user_id=user.id,
        )
        existing_names.add(name_key)
        created += 1

    db.commit()
    return PersonImportResult(created=created, skipped=len(errors), errors=errors)


@router.post("", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(
    payload: PersonCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("persons", "edit")),
) -> Person:
    person = Person(**payload.model_dump())
    db.add(person)
    db.flush()
    audit_log(
        db,
        entity_type="person",
        entity_id=person.id,
        action="create",
        old_value=None,
        new_value=_person_snapshot(person),
        user_id=user.id,
    )
    db.commit()
    db.refresh(person)
    return person


@router.get("/{person_id}", response_model=PersonOut)
def get_person(person_id: int, db: Session = Depends(get_db), _user: User = Depends(require_view_access("persons", "view"))) -> Person:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")
    return person


@router.put("/{person_id}", response_model=PersonOut)
def update_person(
    person_id: int,
    payload: PersonUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("persons", "edit")),
) -> Person:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")
    before = _person_snapshot(person)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(person, key, value)
    audit_log(
        db,
        entity_type="person",
        entity_id=person.id,
        action="update",
        old_value=before,
        new_value=_person_snapshot(person),
        user_id=user.id,
    )
    db.commit()
    db.refresh(person)
    return person


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("persons", "edit")),
) -> None:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")
    before = _person_snapshot(person)
    person.is_active = False
    audit_log(
        db,
        entity_type="person",
        entity_id=person.id,
        action="deactivate",
        old_value=before,
        new_value=_person_snapshot(person),
        user_id=user.id,
    )
    db.commit()
