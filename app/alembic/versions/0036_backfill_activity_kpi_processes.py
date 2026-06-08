"""backfill activity kpi process mappings

Revision ID: 0036_activity_kpi_backfill
Revises: 0035_activity_kpi
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "0036_activity_kpi_backfill"
down_revision: Union[str, None] = "0035_activity_kpi"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


ACTIVITY_KPI_PROCESS_MAPPINGS: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    (("GG_PLOCK",), ("GG Pick",), "Manual_Pick, Campaign, Order_Split, Flammable"),
    (("GG_ART_PL",), ("GG Art. Pl",), "St\u00f6d"),
    (("GG_VM",), ("GG VM",), "HBW, Returns, Receiving"),
    (("GG_LKON",), ("GG Lkon",), "St\u00f6d"),
    (("GG_HELPALL",), ("GG Helpall",), "Full_Manual_Buffer"),
    (
        ("GG_PAFYLLNING",),
        ("GG P\u00e5fyllning",),
        "Refill_Manual_HBW, Putaway_Pick, Manual_Buffer, Buffer_Update, Refill_Manual_Rack, Buffer_Update",
    ),
    (("GG_SKRYMME",), ("GG Skrymme",), "Bulky_Pick"),
    (("GG_LOTSVARD",), ("GG Lotsv\u00e4rd",), "Notification"),
    (("GG_STOD",), ("GG St\u00f6d",), "St\u00f6d"),
    (("GG_LEDARE",), ("GG Ledare",), "St\u00f6d"),
    ((), ("SEN ANKOMST",), "absence"),
    (("GG_OP",), ("GG OP",), "St\u00f6d"),
    (("GG_VAS",), ("GG VAS",), "St\u00f6d"),
    (("GG_VK",), ("GG VK",), "St\u00f6d"),
    (("MG_PLOCK",), ("MG Pick",), "Manual_Pick, Flammable, Bulky_Pick, Campaign, Order_Split"),
    (("MG_ART_PL",), ("MG Art. Pl",), "St\u00f6d"),
    (("MG_VM",), ("MG VM",), "Returns, Receiving, Putaway_Pick"),
    (("MG_LKON",), ("MG Lkon",), "St\u00f6d"),
    (("MG_LOTS",), ("MG Lots",), "Notification"),
    (("MG_SKJUTARE",), ("MG Skjutare",), "Full_Manual_Buffer, Refill_Manual_Rack"),
    (("MG_SKRYMME",), ("MG Skrymme",), "Bulky_Pick"),
    (("MG_STOD",), ("MG St\u00f6d",), "St\u00f6d"),
    (("MG_VAS",), ("MG VAS",), "St\u00f6d"),
    (("MG_AL",), ("MG AL",), "St\u00f6d"),
    (("MG_PL",), ("MG PL",), "St\u00f6d"),
    (("AS_PLOCK",), ("AS Plock",), "Autostore"),
    (("AS_STOD",), ("AS St\u00f6d",), "St\u00f6d"),
    (("AS_DEK",), ("AS Dek",), "Decanting"),
    (("AS_UTLAST",), ("AS Utlast",), "Sort_Ecom, Sort_Store"),
    (("AS_VAS",), ("AS VAS",), "St\u00f6d"),
    (("LEDIG",), ("Ledig",), "absence"),
    (("SJUK",), ("Sjuk",), "absence"),
    (("VAB",), ("VAB",), "absence"),
    ((), ("Semester",), "absence"),
    ((), ("F\u00f6r\u00e4ldraledig",), "absence"),
    ((), ("AS Plock GG",), "Autostore"),
    ((), ("AS Dek GG",), "Decanting"),
    ((), ("AS Utlast GG",), "Sort_Ecom, Sort_Store"),
    ((), ("AS St\u00f6d GG",), "St\u00f6d"),
    ((), ("EH St\u00f6d GG",), "St\u00f6d"),
    ((), ("EH VAS GG",), "St\u00f6d"),
    ((), ("AS Plock MG",), "Autostore"),
    ((), ("AS Dek MG",), "Decanting"),
    ((), ("AS Utlast MG",), "Sort_Ecom, Sort_Store"),
    ((), ("AS St\u00f6d MG",), "St\u00f6d"),
    ((), ("EH St\u00f6d MG",), "St\u00f6d"),
    ((), ("EH Plock GG",), "E_Commerce"),
    ((), ("EH AS Plock GG",), "Autostore"),
    ((), ("EH Pack GG",), "Ecom_pack"),
    ((), ("EH Plock MG",), "E_Commerce"),
    ((), ("EH AS Plock MG",), "Autostore"),
    ((), ("EH Pack MG",), "Ecom_pack"),
)


def _set_activity_processes(connection, codes: tuple[str, ...], labels: tuple[str, ...], processes: str) -> None:
    for code in codes:
        connection.execute(
            sa.text(
                """
                UPDATE activities
                SET kpi_process_name = :processes
                WHERE code = :code
                  AND (kpi_process_name IS NULL OR trim(kpi_process_name) = '')
                """
            ),
            {"processes": processes, "code": code},
        )
    for label in labels:
        connection.execute(
            sa.text(
                """
                UPDATE activities
                SET kpi_process_name = :processes
                WHERE lower(trim(label)) = lower(trim(:label))
                  AND (kpi_process_name IS NULL OR trim(kpi_process_name) = '')
                """
            ),
            {"processes": processes, "label": label},
        )


def upgrade() -> None:
    connection = op.get_bind()
    for codes, labels, processes in ACTIVITY_KPI_PROCESS_MAPPINGS:
        _set_activity_processes(connection, codes, labels, processes)


def downgrade() -> None:
    # Data migration only. User edits after upgrade must not be inferred or reverted.
    pass
