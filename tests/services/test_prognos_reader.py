"""Tester för prognosläsaren i warehouse_tools.engine_core.io_utils.

Kundens RELEX-export har bytt layout: en datumrad har lagts till överst, vilket flyttat
rubrikerna en rad uppåt, och kolumn A innehåller nu Produktkod istället för en tom
indexkolumn. Läsaren letar därför upp rubrikraden dynamiskt istället för att slopa fasta
radnummer, och måste klara både gamla och nya varianter.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from warehouse_tools.engine_core.io_utils import read_prognos_xlsx


def _write_xlsx(path: Path, rows: list[list]) -> Path:
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    return path


def _old_format_rows() -> list[list]:
    """Gamla layouten: rad 0-1 skräp, rad 2 rubriker, rad 3 totalrad, rad 4+ data."""
    return [
        ["The information ... produced by RELEX Solutions.", None, None, None, None, None],
        ["Period start date", "2026-08-04", "Period end date", "2026-08-04", None, None],
        [None, "Product code", "Product name", "Antal styck", "Antal rader", "Antal butiker"],
        ["Total", "#", "#", 999, 99, 9],
        ["A1 (Artikel 1)", "A1", "Artikel 1", 10, 2, 3],
        ["A2 (Artikel 2)", "A2", "Artikel 2", 20, 4, 5],
    ]


def _new_format_rows() -> list[list]:
    """Nya layouten: rad 0 datumrad, rad 1 rubriker, rad 2 totalrad, rad 3+ data.

    "Projicerat antal" står en gång för totalen och sedan en gång per dag.
    """
    return [
        [None, None, None, None, None, "2026-8-4 Tue", "2026-8-5 Wed"],
        [
            "Produktkod",
            "Produktnam",
            "Kampanjstart",
            "Projicerat förhandspåfyllningsdatum",
            "Projicerat antal",
            "Projicerat antal",
            "Projicerat antal",
        ],
        ["#", "#", "#", "#", 30, 12, 18],
        ["A1", "Artikel 1", "2026-08-24", "#", 10, 4, 6],
        ["A2", "Artikel 2", "2026-08-24", "2026-08-10", 20, 8, 12],
    ]


def test_reads_new_format_with_date_row(tmp_path: Path) -> None:
    path = _write_xlsx(tmp_path / "prognos_ny.xlsx", _new_format_rows())

    out = read_prognos_xlsx(str(path))

    assert out["Artikelnummer"].tolist() == ["A1", "A2"]
    assert out["Beskrivning"].tolist() == ["Artikel 1", "Artikel 2"]
    assert out["Antal styck"].tolist() == [10, 20]


def test_new_format_picks_total_column_not_last_day(tmp_path: Path) -> None:
    """"Projicerat antal" är dubblerad; vänstraste träffen är totalen, inte sista dagen."""
    path = _write_xlsx(tmp_path / "prognos_total.xlsx", _new_format_rows())

    out = read_prognos_xlsx(str(path))

    # Totalkolumnen är 10/20, sista dagskolumnen är 6/12.
    assert out["Antal styck"].tolist() == [10, 20]
    assert out["Antal styck"].sum() == 30


def test_new_format_drops_total_row(tmp_path: Path) -> None:
    path = _write_xlsx(tmp_path / "prognos_totalrad.xlsx", _new_format_rows())

    out = read_prognos_xlsx(str(path))

    assert "#" not in set(out["Artikelnummer"])
    assert len(out) == 2


def test_still_reads_old_format(tmp_path: Path) -> None:
    path = _write_xlsx(tmp_path / "prognos_gammal.xlsx", _old_format_rows())

    out = read_prognos_xlsx(str(path))

    assert out["Artikelnummer"].tolist() == ["A1", "A2"]
    assert out["Antal styck"].tolist() == [10, 20]
    assert out["Antal rader"].tolist() == [2, 4]
    assert out["Antal butiker"].tolist() == [3, 5]


def test_reads_new_format_with_leading_location_columns(tmp_path: Path) -> None:
    """Butiksnivå-exporten har Location code/name före Produktkod och rubriker på rad 3."""
    rows = [
        ["The information ... produced by RELEX Solutions.", None, None, None, None, None, None, None],
        ["Period start date", "2025-10-23", "Period end date", "2025-11-23", None, None, None, None],
        ["Total", None, None, None, None, None, None, "2025-10-23 Thu"],
        [
            "Location code",
            "Location name",
            "Produktkod",
            "Produktnam",
            "Kampanjstart",
            "Projicerat förhandspåfyllningsdatum",
            "Projicerat antal",
            "Projicerat antal",
        ],
        ["#", "#", "#", "#", "2025-12-01", "#", 25, 25],
        ["101", "Butik Nord", "A1", "Artikel 1", "2025-12-01", "#", 10, 10],
        ["102", "Butik Syd", "A1", "Artikel 1", "2025-12-01", "#", 15, 15],
    ]
    path = _write_xlsx(tmp_path / "prognos_butik.xlsx", rows)

    out = read_prognos_xlsx(str(path))

    assert out["Artikelnummer"].tolist() == ["A1", "A1"]
    assert out["Antal styck"].sum() == 25


def test_empty_file_returns_empty_frame(tmp_path: Path) -> None:
    path = tmp_path / "tom.xlsx"
    pd.DataFrame().to_excel(path, header=False, index=False)

    out = read_prognos_xlsx(str(path))

    assert out.empty
    assert list(out.columns) == [
        "Artikelnummer",
        "Beskrivning",
        "Antal styck",
        "Antal rader",
        "Antal butiker",
    ]
