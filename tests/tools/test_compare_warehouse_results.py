import json

import pytest

from tools import compare_warehouse_results as compare_tool


pd = pytest.importorskip("pandas")


def test_compare_warehouse_results_treats_export_noise_as_equal(tmp_path, capsys):
    pytest.importorskip("openpyxl")
    left = tmp_path / "flow.csv"
    right = tmp_path / "allokera.xlsx"
    left.write_text("Artikel,Best\u00e4llt,Tom\nA1,1.0,nan\nA2,2,\n", encoding="utf-8-sig")
    pd.DataFrame({"Artikel": ["A1", "A2"], "Best\u00e4llt": [1, 2], "Tom": ["", ""]}).to_excel(right, index=False)

    result = compare_tool.main(["--left", str(left), "--right", str(right), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["equal"] is True
    assert payload["cell_differences"] == 0


def test_compare_warehouse_results_reports_cell_differences(tmp_path, capsys):
    left = tmp_path / "flow.csv"
    right = tmp_path / "allokera.csv"
    left.write_text("Artikel,Ej Staplingsbar\nA1,0\nA2,1\n", encoding="utf-8-sig")
    right.write_text("Artikel,Ej Staplingsbar\nA1,1\nA2,1\n", encoding="utf-8-sig")

    result = compare_tool.main(["--left", str(left), "--right", str(right), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["equal"] is False
    assert payload["cell_differences"] == 1
    assert payload["differences_by_column"] == {"Ej Staplingsbar": 1}
    assert payload["sample_differences"][0] == {
        "row": 2,
        "column": "Ej Staplingsbar",
        "left": "0",
        "right": "1",
    }


def test_compare_warehouse_results_can_sort_and_ignore_columns(tmp_path):
    left = tmp_path / "flow.csv"
    right = tmp_path / "allokera.csv"
    left.write_text("Artikel,Antal,K\u00f6rning\nA2,2,flow\nA1,1,flow\n", encoding="utf-8-sig")
    right.write_text("Artikel,Antal,K\u00f6rning\nA1,1,allokera\nA2,2,allokera\n", encoding="utf-8-sig")

    result = compare_tool.compare_files(
        left,
        right,
        sort_by=["Artikel"],
        ignore_columns=["K\u00f6rning"],
    )

    assert result["equal"] is True
