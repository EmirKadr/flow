from pathlib import Path

import pytest

from app.backend.productivity_service import (
    build_productivity_file_status,
    build_productivity_report,
    build_productivity_session_file_status,
    classify_productivity_file,
    ProductivitySourceError,
    read_productivity_targets,
    save_productivity_file,
    source_files_from_session_logs,
)


def write(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def test_productivity_file_status_shows_only_required_user_uploads(tmp_path):
    write(
        tmp_path / "v_ask_kpi_target-20260518080915.csv",
        "Bolag\tLager\tFlödesnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar",
    )

    status = build_productivity_file_status(tmp_path)

    assert status["ready"] is False
    assert set(status["files"]) == {"pick", "trans", "pallet"}
    assert status["missing"] == ["pick", "trans", "pallet"]

    for filename, content in (
        ("renamed_pick.csv", "Zon\tPlockat\tAnvändare\tÄndrad\tVikt\tBolag\nA\t1\tUSER\t2026-05-18 08:00:00\t1\tGG"),
        ("renamed_trans.csv", "Pallid\tFrån\tTill\tAntal\tTimestamp\n1\tA\tB\t1\t2026-05-18 08:00:00"),
        ("renamed_pallet.csv", "Plockpallsnr.\tPalltyp\tPallplacering\tTransnr.\tVikt\n1\t1\tM1\t1\t1"),
    ):
        source = tmp_path / filename
        write(source, content)
        sample = source.read_bytes()[:4096]
        file_type = classify_productivity_file(filename, sample)
        save_productivity_file(source_path=source, filename=filename, file_type=file_type, reference_dir=tmp_path)

    status = build_productivity_file_status(tmp_path)

    assert status["ready"] is True
    assert status["missing"] == []
    assert all(item["uploaded"] for item in status["files"].values())


def test_productivity_file_detection_accepts_hidden_kpi_target():
    sample = "Bolag\tLager\tFlödesnamn\tProcessnamn\tBeskrivning\tRader\tKollin\n".encode()

    assert classify_productivity_file("nytt-mal.csv", sample) == "kpi"


def test_productivity_targets_are_serializable(tmp_path):
    write(
        tmp_path / "v_ask_kpi_target-20260518080915.csv",
        """
Bolag\tLager\tFlödesnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar
GG\t404\tOUTBOUND\tManual_Pick\tManuellt plock\t10\t0\t0
""",
    )

    targets = read_productivity_targets(tmp_path)

    assert targets["source"]["name"].startswith("v_ask_kpi_target")
    assert targets["targets"] == [
        {
            "company": "GG",
            "process": "MANUAL_PICK",
            "description": "Manuellt plock",
            "rader": 10,
            "kollin": 0,
            "pallar": 0,
        }
    ]


def test_productivity_session_status_uses_local_logs_and_permanent_kpi(tmp_path):
    write(
        tmp_path / "v_ask_kpi_target-20260518080915.csv",
        "Bolag\tLager\tFlödesnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar",
    )
    log_files = {}

    status = build_productivity_session_file_status(log_files, tmp_path)

    assert status["ready"] is False
    assert status["kpi_loaded"] is True
    assert status["missing"] == ["pick", "trans", "pallet"]

    for key, filename in (
        ("pick", "local_pick.csv"),
        ("trans", "local_trans.csv"),
        ("pallet", "local_pallet.csv"),
    ):
        path = tmp_path / filename
        write(path, "Kolumn\nvärde")
        log_files[key] = path

    status = build_productivity_session_file_status(log_files, tmp_path)
    source_files = source_files_from_session_logs(log_files, tmp_path)

    assert status["ready"] is True
    assert status["missing"] == []
    assert source_files["pick"] == log_files["pick"]
    assert source_files["kpi"].name.startswith("v_ask_kpi_target")


def test_productivity_report_groups_pick_trans_and_pallet_logs(tmp_path):
    write(
        tmp_path / "v_ask_pick_log_full-20260518075529.csv",
        """
Zon\tPlockat\tAnvändare\tÄndrad\tVikt\tBolag
A\t3\tUSER1\t2026-05-18 08:10:00\t1,5\tGG
B\t4\tUSER1\t2026-05-18 08:40:00\t2,5\tGG
S\t5\tUSER1\t2026-05-18 09:05:00\t3,0\tGG
R\t7\tAUTO1\t2026-05-18 10:15:00\t1,0\tMG
Q\t2\tECOM1\t2026-05-18 11:00:00\t1,0\tMG
O\t1\tMGUSER\t2026-05-18 12:00:00\t1,0\tMG
""",
    )
    write(
        tmp_path / "v_ask_trans_log-20260518075534.csv",
        """
Till\tAntal\tAnvändare\tTimestamp\tBolag
AS100\t9\tDEC1\t2026-05-18 10:30:00\tGG
LC100\t4\tDEC1\t2026-05-18 10:45:00\tGG
AS200\t6\tDEC2\t2026-05-18 11:00:00\tMG
""",
    )
    write(
        tmp_path / "v_ask_palletloading_log-20260518075605.csv",
        """
Typ\tAnvändare\tÄndrad\tBolag
220\tPACK1\t2026-05-18 13:00:00\tGG
220\tPACK2\t2026-05-18 14:00:00\tMG
200\tPACK2\t2026-05-18 15:00:00\tMG
""",
    )
    write(
        tmp_path / "v_ask_kpi_target-20260518080915.csv",
        """
Bolag\tLager\tFlödesnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar
GG\t404\tOUTBOUND\tManual_Pick\tManuellt plock\t10\t0\t0
GG\t404\tOUTBOUND\tBulky_Pick\tSkrymmande Plock\t5\t0\t0
GG\t404\tOUTBOUND\tAutostore\tAutostore\t20\t0\t0
GG\t404\tINBOUND\tDecanting\tDekantering\t9\t0\t0
GG\t404\tOUTBOUND\tEcom_pack\tE - Handel pack\t0\t0\t2
MG\tJKP\tOUTBOUND\tManual_Pick\tManuellt plock\t10\t0\t0
MG\tJKP\tOUTBOUND\tBulky_Pick\tSkrymmande Plock\t4\t0\t0
MG\tJKP\tOUTBOUND\tE_Commerce\tE - Handel\t8\t0\t0
MG\tJKP\tINBOUND\tDecanting\tDekantering\t6\t0\t0
MG\tJKP\tOUTBOUND\tEcom_pack\tE - Handel pack\t0\t0\t2
""",
    )

    report = build_productivity_report(tmp_path)
    groups = {group["id"]: group for group in report["groups"]}
    sections = {
        section["id"]: section
        for group in report["groups"]
        for section in group["sections"]
    }
    section_groups = {
        section["id"]: group["id"]
        for group in report["groups"]
        for section in group["sections"]
    }

    assert {"gg", "as", "eh", "mg"} <= set(groups)
    assert section_groups["as_store_pick"] == "as"
    assert section_groups["gg_decanting"] == "as"
    assert section_groups["gg_ecom_pack"] == "eh"
    assert section_groups["mg_ecom_pick"] == "eh"

    gg_pick = sections["gg_pick_ab"]
    assert gg_pick["total_rows"] == 2
    assert gg_pick["rows"][0]["user"] == "USER1"
    assert gg_pick["rows"][0]["hourly"] == {"8": 2}
    assert gg_pick["rows"][0]["worked_hours"] == 1
    assert gg_pick["rows"][0]["rows_per_hour"] == 2
    assert gg_pick["rows"][0]["productivity_pct"] == 0.2
    assert gg_pick["rows"][0]["total_kolli"] == 12

    assert sections["gg_decanting"]["rows"][0]["user"] == "DEC1"
    assert sections["gg_decanting"]["rows"][0]["total_rows"] == 1
    assert sections["gg_decanting"]["rows"][0]["total_kolli"] == 13

    assert sections["gg_ecom_pack"]["rows"][0]["user"] == "PACK1"
    assert sections["gg_ecom_pack"]["rows"][0]["target_per_hour"] == 2
    assert sections["mg_ecom_pack"]["rows"][0]["user"] == "PACK2"
    assert sections["mg_ecom_pick"]["rows"][0]["user"] == "ECOM1"


def test_productivity_available_dates_only_include_dates_with_section_rows(tmp_path):
    write(
        tmp_path / "v_ask_pick_log_full-20260518075529.csv",
        """
Zon\tPlockat\tAnvandare\tAndrad\tVikt\tBolag
A\t3\tUSER1\t2026-05-18 08:10:00\t1,5\tGG
""",
    )
    write(
        tmp_path / "v_ask_trans_log-20260518075534.csv",
        """
Till\tAntal\tAnvandare\tTimestamp\tBolag
XX100\t9\tDEC1\t2026-05-17 10:30:00\tGG
""",
    )
    write(
        tmp_path / "v_ask_palletloading_log-20260518075605.csv",
        """
Typ\tAnvandare\tAndrad\tBolag
200\tPACK1\t2026-05-17 13:00:00\tGG
""",
    )
    write(
        tmp_path / "v_ask_kpi_target-20260518080915.csv",
        """
Bolag\tLager\tFlodesnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar
GG\t404\tOUTBOUND\tManual_Pick\tManuellt plock\t10\t0\t0
""",
    )

    report = build_productivity_report(tmp_path)

    assert report["date"] == "2026-05-18"
    assert report["available_dates"] == ["2026-05-18"]
    assert report["summary"]["total_rows"] == 1
    with pytest.raises(ProductivitySourceError, match="2026-05-17"):
        build_productivity_report(tmp_path, report_date="2026-05-17")
