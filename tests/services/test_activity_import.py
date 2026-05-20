import io
import asyncio

import pytest
from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import Activity, Area, Person, ScheduleCell, User
from app.backend.routers.activities import (
    build_activity_import_template_excel,
    create_activity,
    delete_activity,
    download_import_template,
    import_activities,
    list_activities,
    parse_activity_import_excel,
    update_activity,
)
from app.backend.schemas import ActivityCreate, ActivityUpdate


def workbook_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


class FakeUpload:
    def __init__(self, content: bytes):
        self.content = content

    async def read(self) -> bytes:
        return self.content


@pytest.fixture()
def import_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def seed_activity_import_base(db):
    gg = Area(code="GG", name="Gastro Grönt", sort_order=1)
    mg = Area(code="MG", name="Mästergruppen", sort_order=2)
    summary = Activity(code="LEDIGT", label="Ledigt", color="#fee2e2", category="absence", sort_order=10)
    admin = User(username="admin", display_name="Admin", role="admin", roles=["admin"], is_active=True)
    staffing = User(
        username="staffing",
        display_name="Bemanningsansvarig",
        role="staffing_manager",
        roles=["staffing_manager"],
        is_active=True,
    )
    db.add_all([gg, mg, summary, admin, staffing])
    db.flush()
    return gg, mg, summary, admin, staffing


def test_build_activity_import_template_excel_has_expected_headers():
    workbook = load_workbook(io.BytesIO(build_activity_import_template_excel()))
    sheet = workbook.active

    assert [sheet["A1"].value, sheet["B1"].value, sheet["C1"].value, sheet["D1"].value, sheet["E1"].value] == [
        "etikett (obligatorisk)",
        "område (frivillig)",
        "summeras som (frivillig)",
        "sortering (frivillig)",
        None,
    ]


def test_parse_activity_import_excel_accepts_label_only():
    rows, errors = parse_activity_import_excel(
        workbook_bytes(
            [
                ["etikett", "område", "summeras som", "sortering"],
                ["GG Påfyllning", None, None, None],
            ]
        )
    )

    assert errors == []
    assert len(rows) == 1
    assert rows[0].label == "GG Påfyllning"
    assert rows[0].area is None
    assert rows[0].summary_activity is None
    assert rows[0].sort_order is None


def test_parse_activity_import_excel_accepts_optional_fields():
    rows, errors = parse_activity_import_excel(
        workbook_bytes(
            [
                ["etikett", "område", "summeras som", "sortering"],
                ["Frånvaro", "GG", "Ledigt", 20],
            ]
        )
    )

    assert errors == []
    assert len(rows) == 1
    assert rows[0].area == "GG"
    assert rows[0].summary_activity == "Ledigt"
    assert rows[0].sort_order == 20


def test_parse_activity_import_excel_ignores_legacy_category_and_color_columns():
    rows, errors = parse_activity_import_excel(
        workbook_bytes(
            [
                ["etikett", "kategori", "färg", "sortering"],
                ["Gammal mall", "frånvaro", "gul", 7],
            ]
        )
    )

    assert errors == []
    assert len(rows) == 1
    assert rows[0].label == "Gammal mall"
    assert rows[0].sort_order == 7


def test_parse_activity_import_excel_collects_row_errors():
    rows, errors = parse_activity_import_excel(
        workbook_bytes(
            [
                ["etikett", "sortering"],
                [None, 1],
                ["Fel sort", "1,5"],
            ]
        )
    )

    assert rows == []
    assert [error.row for error in errors] == [2, 3]
    assert "Etikett" in errors[0].error
    assert "heltal" in errors[1].error


def test_parse_activity_import_excel_requires_label_header():
    with pytest.raises(HTTPException) as exc:
        parse_activity_import_excel(workbook_bytes([["område"], ["GG"]]))

    assert exc.value.status_code == 400


def test_downloaded_activity_template_imports_mixed_optional_summary_and_sorting(import_db):
    _gg, _mg, summary, admin, _staffing = seed_activity_import_base(import_db)
    response = download_import_template(_admin=admin)

    assert response.headers["Content-Disposition"] == 'attachment; filename="stallen-importmall.xlsx"'
    workbook = load_workbook(io.BytesIO(response.body))
    sheet = workbook.active
    assert [sheet.cell(1, column).value for column in range(1, 5)] == [
        "etikett (obligatorisk)",
        "område (frivillig)",
        "summeras som (frivillig)",
        "sortering (frivillig)",
    ]

    sheet.append(["Test utan frivilligt", "GG", None, None])
    sheet.append(["Test med allt", "MG", "Ledigt", 42])
    sheet.append(["Test bara summeras", None, "Ledigt", None])
    sheet.append(["Test bara sortering", "GG", None, 77])
    stream = io.BytesIO()
    workbook.save(stream)

    result = asyncio.run(import_activities(file=FakeUpload(stream.getvalue()), db=import_db, admin=admin))

    assert result.created == 4
    assert result.skipped == 0
    assert result.errors == []

    imported = {
        activity.label: activity
        for activity in import_db.query(Activity).filter(Activity.label.like("Test %")).all()
    }
    assert set(imported) == {
        "Test utan frivilligt",
        "Test med allt",
        "Test bara summeras",
        "Test bara sortering",
    }
    assert imported["Test utan frivilligt"].summary_activity_id is None
    assert imported["Test utan frivilligt"].sort_order == 11
    assert imported["Test med allt"].summary_activity_id == summary.id
    assert imported["Test med allt"].sort_order == 42
    assert imported["Test bara summeras"].summary_activity_id == summary.id
    assert imported["Test bara summeras"].sort_order == 12
    assert imported["Test bara sortering"].summary_activity_id is None
    assert imported["Test bara sortering"].sort_order == 77

    for activity in imported.values():
        assert activity.category == "work"
        assert activity.color == "#ffffff"


def test_bemanningsansvarig_can_manage_activities(import_db):
    gg, _mg, _summary, _admin, staffing = seed_activity_import_base(import_db)

    response = download_import_template(_admin=staffing)
    assert response.headers["Content-Disposition"] == 'attachment; filename="stallen-importmall.xlsx"'

    created = create_activity(
        payload=ActivityCreate(label="Bemanning test", area_id=gg.id, sort_order=99),
        db=import_db,
        admin=staffing,
    )

    assert created.id is not None
    assert created.label == "Bemanning test"
    assert created.code.startswith("GG_BEMANNING_TEST")

    updated = update_activity(
        activity_id=created.id,
        payload=ActivityUpdate(label="Bemanning test uppdaterad"),
        db=import_db,
        admin=staffing,
    )

    assert updated.label == "Bemanning test uppdaterad"

    delete_activity(activity_id=created.id, db=import_db, admin=staffing)

    assert import_db.get(Activity, created.id) is None


def test_activity_delete_removes_inactive_legacy_activity_and_clears_references(import_db):
    gg, _mg, summary, _admin, staffing = seed_activity_import_base(import_db)
    legacy = Activity(
        code="GG_GAMMAL",
        label="Gammalt ställe",
        area_id=gg.id,
        summary_activity_id=summary.id,
        color="#ffffff",
        category="work",
        sort_order=99,
        is_active=False,
    )
    child = Activity(
        code="GG_BARN",
        label="Barnställe",
        area_id=gg.id,
        summary_activity_id=None,
        color="#ffffff",
        category="work",
        sort_order=100,
        is_active=True,
    )
    person = Person(name="Test Person", home_area_id=gg.id, competencies=[], home_activity_id=None)
    import_db.add_all([legacy, child, person])
    import_db.flush()
    child.summary_activity_id = legacy.id
    person.home_activity_id = legacy.id
    cell = ScheduleCell(
        year=2026,
        week=21,
        weekday=1,
        hour=7,
        minute_start=0,
        minute_end=60,
        person_id=person.id,
        activity_id=legacy.id,
    )
    import_db.add(cell)
    import_db.commit()

    labels = [activity.label for activity in list_activities(include_inactive=False, db=import_db)]
    assert "Gammalt ställe" in labels

    delete_activity(activity_id=legacy.id, db=import_db, admin=staffing)

    assert import_db.get(Activity, legacy.id) is None
    assert import_db.get(Person, person.id).home_activity_id is None
    assert import_db.get(Activity, child.id).summary_activity_id is None
    cleared_cell = import_db.get(ScheduleCell, cell.id)
    assert cleared_cell.activity_id is None
    assert cleared_cell.empty_override is True
