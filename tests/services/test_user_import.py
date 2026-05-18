import io

import pytest
from fastapi import HTTPException
from openpyxl import Workbook, load_workbook

from app.backend.routers.users import build_user_import_template_excel, parse_user_import_excel


def workbook_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_build_user_import_template_excel_has_expected_headers():
    workbook = load_workbook(io.BytesIO(build_user_import_template_excel()))
    sheet = workbook.active

    assert [sheet["A1"].value, sheet["B1"].value, sheet["C1"].value, sheet["D1"].value] == [
        "anv\u00e4ndarnamn",
        "namn",
        "roller",
        "avdelning",
    ]


def test_parse_user_import_excel_accepts_template_headers_and_swedish_roles():
    content = workbook_bytes(
        [
            ["anv\u00e4ndarnamn", "namn", "roll", "avdelning"],
            ["anna", "Anna Andersson", "arbetsledare", ""],
            ["bo", "Bo Berg", "administrat\u00f6r", "GG"],
            ["viola", "Viola Visning", "visning", "Mestergruppen"],
            ["lina", "Lina Lager", "lagerkontorist", ""],
            ["arvid", "Arvid Artikel", "artikelplacerare", ""],
        ]
    )

    rows, errors = parse_user_import_excel(content)

    assert errors == []
    assert [(row.username, row.display_name, row.roles, row.area_name) for row in rows] == [
        ("anna", "Anna Andersson", ["leader"], None),
        ("bo", "Bo Berg", ["admin"], "GG"),
        ("viola", "Viola Visning", ["viewer"], "Mestergruppen"),
        ("lina", "Lina Lager", ["warehouse_clerk"], None),
        ("arvid", "Arvid Artikel", ["article_placer"], None),
    ]


def test_parse_user_import_excel_accepts_multiple_roles_in_one_cell():
    content = workbook_bytes(
        [
            ["username", "name", "roles"],
            ["mira", "Mira Multi", "admin, arbetsledare"],
        ]
    )

    rows, errors = parse_user_import_excel(content)

    assert errors == []
    assert rows[0].roles == ["admin", "leader"]


def test_parse_user_import_excel_collects_row_errors():
    content = workbook_bytes(
        [
            ["anv\u00e4ndarnamn", "namn", "roll"],
            [None, "Namnl\u00f6s", "arbetsledare"],
            ["cecilia", "Cecilia", "ok\u00e4nd"],
        ]
    )

    rows, errors = parse_user_import_excel(content)

    assert rows == []
    assert [error.row for error in errors] == [2, 3]
    assert "Anv\u00e4ndarnamn" in errors[0].error
    assert "Roll" in errors[1].error


def test_parse_user_import_excel_requires_expected_headers():
    with pytest.raises(HTTPException) as exc:
        parse_user_import_excel(workbook_bytes([["username", "name"], ["anna", "Anna"]]))

    assert exc.value.status_code == 400
