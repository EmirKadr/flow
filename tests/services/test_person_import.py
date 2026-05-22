import io

import pytest
from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Activity, Area, Person, User
from app.backend.routers.persons import (
    build_person_import_template_excel,
    create_person,
    delete_person,
    import_person_rows,
    parse_person_import_excel,
    update_person,
)
from app.backend.schemas import PersonCreate, PersonImportRowInput, PersonImportRowsRequest, PersonUpdate


def workbook_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_build_person_import_template_excel_has_expected_headers():
    workbook = load_workbook(io.BytesIO(build_person_import_template_excel()))
    sheet = workbook.active

    assert [sheet.cell(1, column).value for column in range(1, 6)] == [
        "verksamhet (frivillig)",
        "namn (obligatorisk)",
        "hemomr\u00e5de (frivillig)",
        "huvudaktivitet (frivillig)",
        "sortering (frivillig)",
    ]


def test_parse_person_import_excel_accepts_name_only():
    rows, errors = parse_person_import_excel(
        workbook_bytes(
            [
                ["namn", "hemomr\u00e5de", "huvudaktivitet", "sortering"],
                ["Anna Andersson", None, None, None],
            ]
        )
    )

    assert errors == []
    assert len(rows) == 1
    assert rows[0].name == "Anna Andersson"
    assert rows[0].home_area is None
    assert rows[0].home_activity is None
    assert rows[0].sort_order is None


def test_parse_person_import_excel_accepts_optional_fields():
    rows, errors = parse_person_import_excel(
        workbook_bytes(
            [
                ["namn (obligatorisk)", "hemomr\u00e5de (frivillig)", "huvudst\u00e4lle (frivillig)", "sortering (frivillig)"],
                ["Bo Berg", "GG", "GG VM", 12],
            ]
        )
    )

    assert errors == []
    assert len(rows) == 1
    assert rows[0].home_area == "GG"
    assert rows[0].home_activity == "GG VM"
    assert rows[0].sort_order == 12


def test_parse_person_import_excel_collects_row_errors():
    rows, errors = parse_person_import_excel(
        workbook_bytes(
            [
                ["namn", "sortering"],
                [None, 1],
                ["Cecilia", "1,5"],
            ]
        )
    )

    assert rows == []
    assert [error.row for error in errors] == [2, 3]
    assert "Namn" in errors[0].error
    assert "heltal" in errors[1].error


def test_parse_person_import_excel_requires_name_header():
    with pytest.raises(HTTPException) as exc:
        parse_person_import_excel(workbook_bytes([["hemomr\u00e5de"], ["GG"]]))

    assert exc.value.status_code == 400


@pytest.fixture()
def person_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_create_person_rejects_duplicate_name(person_db):
    admin = User(username="admin", role="admin", roles=["admin"], is_active=True)
    person_db.add_all([admin, Person(name="Anna Andersson", competencies=[], is_active=True, sort_order=1)])
    person_db.flush()

    with pytest.raises(HTTPException) as exc:
        create_person(PersonCreate(name=" anna andersson "), db=person_db, user=admin)

    assert exc.value.status_code == 409


def test_import_person_rows_creates_from_direct_table(person_db):
    admin = User(username="admin", role="admin", roles=["admin"], is_active=True)
    area = Area(code="GG", name="Granngården", sort_order=1)
    person_db.add_all([admin, area])
    person_db.flush()
    activity = Activity(
        code="GG_PLOCK",
        label="GG Plock",
        area_id=area.id,
        color="#bfdbfe",
        category="work",
        sort_order=2,
        is_active=True,
    )
    person_db.add(activity)
    person_db.flush()

    result = import_person_rows(
        PersonImportRowsRequest(
            rows=[
                PersonImportRowInput(name="Mira Multi", home_area="GG", home_activity="GG Plock", sort_order="7"),
                PersonImportRowInput(name="Mira Multi", home_area="GG"),
            ]
        ),
        db=person_db,
        user=admin,
    )

    assert result.created == 1
    assert result.skipped == 1
    assert result.errors[0].row == 2
    assert result.errors[0].error == "Dubblett i tabellen"
    person = person_db.query(Person).filter(Person.name == "Mira Multi").one()
    assert person.home_area_id == area.id
    assert person.home_activity_id == activity.id
    assert person.sort_order == 7


def test_create_person_rejects_inactive_duplicate_name(person_db):
    admin = User(username="admin", role="admin", roles=["admin"], is_active=True)
    inactive = Person(name="Anton Holmqvist", competencies=[], is_active=False, sort_order=17)
    person_db.add_all([admin, inactive])
    person_db.flush()

    with pytest.raises(HTTPException) as exc:
        create_person(PersonCreate(name="Anton Holmqvist", sort_order=3), db=person_db, user=admin)

    assert exc.value.status_code == 409
    assert inactive.is_active is False
    assert person_db.query(Person).filter(Person.name == "Anton Holmqvist").count() == 1


def test_delete_person_removes_person(person_db):
    admin = User(username="admin", role="admin", roles=["admin"], is_active=True)
    person = Person(name="Bo Berg", competencies=[], is_active=False, sort_order=17)
    person_db.add_all([admin, person])
    person_db.flush()

    delete_person(person.id, db=person_db, user=admin)

    assert person_db.get(Person, person.id) is None


def test_update_person_rejects_duplicate_name(person_db):
    admin = User(username="admin", role="admin", roles=["admin"], is_active=True)
    anna = Person(name="Anna Andersson", competencies=[], is_active=True, sort_order=1)
    bo = Person(name="Bo Berg", competencies=[], is_active=True, sort_order=2)
    person_db.add_all([admin, anna, bo])
    person_db.flush()

    with pytest.raises(HTTPException) as exc:
        update_person(bo.id, PersonUpdate(name="Anna Andersson"), db=person_db, user=admin)

    assert exc.value.status_code == 409
