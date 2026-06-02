import gzip
from pathlib import Path

import pytest

from app.backend.productivity_service import (
    build_productivity_file_status,
    build_productivity_report,
    build_productivity_compiled_data_status,
    build_productivity_session_file_status,
    classify_productivity_file,
    ProductivitySourceError,
    productivity_compiled_log_path,
    read_productivity_targets,
    save_productivity_file,
    source_files_from_session_logs,
    update_productivity_compiled_log,
)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        import csv

        return list(csv.DictReader(handle))


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


def test_productivity_kpi_targets_are_scoped_per_business(tmp_path):
    stigamo_source = tmp_path / "stigamo-mal.csv"
    r3_source = tmp_path / "r3-mal.csv"
    new_source = tmp_path / "new-mal.csv"
    write(
        stigamo_source,
        """
Bolag\tLager\tFlÃ¶desnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar
GG\t404\tOUTBOUND\tManual_Pick\tStigamo mÃ¥l\t10\t0\t0
""",
    )
    write(
        r3_source,
        """
Bolag\tLager\tFlÃ¶desnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar
R3\t404\tOUTBOUND\tManual_Pick\tR3 mÃ¥l\t20\t0\t0
""",
    )
    write(
        new_source,
        """
Bolag\tLager\tFlÃ¶desnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar
NY\t404\tOUTBOUND\tManual_Pick\tNy verksamhet\t30\t0\t0
""",
    )

    save_productivity_file(
        source_path=stigamo_source,
        filename=stigamo_source.name,
        file_type="kpi",
        reference_dir=tmp_path,
        business_code="STIGAMO",
    )
    save_productivity_file(
        source_path=r3_source,
        filename=r3_source.name,
        file_type="kpi",
        reference_dir=tmp_path,
        business_code="R3",
    )
    save_productivity_file(
        source_path=new_source,
        filename=new_source.name,
        file_type="kpi",
        reference_dir=tmp_path,
        business_code="Ny verksamhet!",
    )

    stigamo = read_productivity_targets(tmp_path, business_code="STIGAMO")
    r3 = read_productivity_targets(tmp_path, business_code="R3")
    new = read_productivity_targets(tmp_path, business_code="Ny verksamhet!")

    assert stigamo["targets"][0]["description"] == "Stigamo mÃ¥l"
    assert r3["targets"][0]["description"] == "R3 mÃ¥l"
    assert new["targets"][0]["description"] == "Ny verksamhet"
    assert "stigamo" in [part.lower() for part in Path(stigamo["source"]["path"]).parts]
    assert "r3" in [part.lower() for part in Path(r3["source"]["path"]).parts]
    assert "ny_verksamhet" in [part.lower() for part in Path(new["source"]["path"]).parts]


def test_productivity_kpi_root_file_is_not_business_scoped_for_any_business(tmp_path):
    write(
        tmp_path / "v_ask_kpi_target-20260518080915.csv",
        """
Bolag\tLager\tFlÃ¶desnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar
GG\t404\tOUTBOUND\tManual_Pick\tLegacy Stigamo\t10\t0\t0
""",
    )

    with pytest.raises(ProductivitySourceError, match="stigamo"):
        read_productivity_targets(tmp_path, business_code="STIGAMO")
    with pytest.raises(ProductivitySourceError, match="r3"):
        read_productivity_targets(tmp_path, business_code="R3")


def test_productivity_kpi_prefers_coredata_business_directory_when_present(tmp_path):
    write(
        tmp_path / "stigamo" / "v_ask_kpi_target-20260518080915.csv",
        """
Bolag\tLager\tFlÃ¶desnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar
GG\t404\tOUTBOUND\tManual_Pick\tScoped fallback\t10\t0\t0
""",
    )
    write(
        tmp_path / "coredata" / "stigamo" / "v_ask_kpi_target-20260525120644.csv",
        """
Bolag\tLager\tFlÃ¶desnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar
GG\t404\tOUTBOUND\tManual_Pick\tCoredata Stigamo\t20\t0\t0
""",
    )

    targets = read_productivity_targets(tmp_path, business_code="STIGAMO")

    assert targets["targets"][0]["description"] == "Coredata Stigamo"
    assert "coredata" in [part.lower() for part in Path(targets["source"]["path"]).parts]


def test_productivity_session_status_uses_business_specific_kpi(tmp_path):
    write(
        tmp_path / "stigamo" / "v_ask_kpi_target-20260518080915.csv",
        "Bolag\tLager\tFlÃ¶desnamn\tProcessnamn\tBeskrivning\tRader\tKollin\tPallar",
    )

    stigamo_status = build_productivity_session_file_status({}, tmp_path, business_code="STIGAMO")
    r3_status = build_productivity_session_file_status({}, tmp_path, business_code="R3")

    assert stigamo_status["kpi_loaded"] is True
    assert r3_status["kpi_loaded"] is False


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


def test_compiled_pick_and_trans_logs_deduplicate_by_rowid(tmp_path):
    pick_first = tmp_path / "pick-first.csv"
    pick_second = tmp_path / "pick-second.csv"
    trans_first = tmp_path / "trans-first.csv"
    trans_second = tmp_path / "trans-second.csv"
    write(
        pick_first,
        """
Radid\tZon\tPlockat\tAnvändare\tÄndrad\tVikt\tBolag
1\tA\t3\tUSER1\t2026-05-18 08:10:00\t1\tGG
2\tB\t4\tUSER1\t2026-05-18 08:40:00\t1\tGG
""",
    )
    write(
        pick_second,
        """
Radid\tZon\tPlockat\tAnvändare\tÄndrad\tVikt\tBolag
2\tB\t4\tUSER1\t2026-05-18 08:40:00\t1\tGG
3\tS\t5\tUSER2\t2026-05-18 09:05:00\t2\tGG
3\tS\t5\tUSER2\t2026-05-18 09:05:00\t2\tGG
""",
    )
    write(
        trans_first,
        """
rowid\tTill\tAntal\tAnvändare\tTimestamp\tBolag
T1\tAS100\t9\tDEC1\t2026-05-18 10:30:00\tGG
""",
    )
    write(
        trans_second,
        """
rowid\tTill\tAntal\tAnvändare\tTimestamp\tBolag
T1\tAS100\t9\tDEC1\t2026-05-18 10:30:00\tGG
T2\tAS200\t6\tDEC2\t2026-05-18 11:00:00\tMG
""",
    )

    first_pick = update_productivity_compiled_log(pick_first, "pick", tmp_path, "R3")
    second_pick = update_productivity_compiled_log(pick_second, "pick", tmp_path, "R3")
    update_productivity_compiled_log(trans_first, "trans", tmp_path, "R3")
    second_trans = update_productivity_compiled_log(trans_second, "trans", tmp_path, "R3")

    assert first_pick["new_rows"] == 2
    assert second_pick["new_rows"] == 1
    assert second_pick["total_rows"] == 3
    assert second_trans["new_rows"] == 1

    pick_rows = read_gzip_csv(productivity_compiled_log_path("pick", tmp_path, "R3"))
    trans_rows = read_gzip_csv(productivity_compiled_log_path("trans", tmp_path, "R3"))
    assert [row["Radid"] for row in pick_rows] == ["1", "2", "3"]
    assert [row["rowid"] for row in trans_rows] == ["T1", "T2"]


def test_compiled_pallet_log_uses_timestamp_watermark_and_allows_new_duplicates(tmp_path):
    first = tmp_path / "pallet-first.csv"
    second = tmp_path / "pallet-second.csv"
    third = tmp_path / "pallet-third.csv"
    write(
        first,
        """
Typ\tAnvändare\tÄndrad\tBolag
220\tPACK1\t2026-05-18 13:00:00\tGG
220\tPACK2\t2026-05-18 14:00:00\tGG
""",
    )
    write(
        second,
        """
Typ\tAnvändare\tÄndrad\tBolag
220\tOLD\t2026-05-18 13:30:00\tGG
220\tSAME\t2026-05-18 14:00:00\tGG
220\tNEW1\t2026-05-18 15:00:00\tGG
220\tNEW1\t2026-05-18 15:00:00\tGG
""",
    )
    write(
        third,
        """
Typ\tAnvändare\tÄndrad\tBolag
220\tNEW1\t2026-05-18 15:00:00\tGG
""",
    )

    first_result = update_productivity_compiled_log(first, "pallet", tmp_path, "STIGAMO")
    second_result = update_productivity_compiled_log(second, "pallet", tmp_path, "STIGAMO")
    third_result = update_productivity_compiled_log(third, "pallet", tmp_path, "STIGAMO")

    assert first_result["new_rows"] == 2
    assert second_result["new_rows"] == 2
    assert third_result["new_rows"] == 0

    rows = read_gzip_csv(productivity_compiled_log_path("pallet", tmp_path, "STIGAMO"))
    assert [row["Användare"] for row in rows] == ["PACK1", "PACK2", "NEW1", "NEW1"]


def test_compiled_logs_do_not_create_empty_file_when_dedupe_key_is_missing(tmp_path):
    pick = tmp_path / "pick-without-rowid.csv"
    pallet = tmp_path / "pallet-without-timestamp.csv"
    write(
        pick,
        """
Zon\tPlockat\tAnvändare\tÄndrad\tBolag
A\t3\tUSER1\t2026-05-18 08:10:00\tGG
""",
    )
    write(
        pallet,
        """
Typ\tAnvändare\tBolag
220\tPACK1\tGG
""",
    )

    pick_result = update_productivity_compiled_log(pick, "pick", tmp_path, "R3")
    pallet_result = update_productivity_compiled_log(pallet, "pallet", tmp_path, "R3")

    assert pick_result["new_rows"] == 0
    assert pick_result["uploaded"] is False
    assert pick_result["skipped_reason"] == "saknar rowid/radid"
    assert pallet_result["new_rows"] == 0
    assert pallet_result["uploaded"] is False
    assert pallet_result["skipped_reason"] == "saknar timestamp"
    assert not productivity_compiled_log_path("pick", tmp_path, "R3").exists()
    assert not productivity_compiled_log_path("pallet", tmp_path, "R3").exists()


def test_compiled_status_lists_all_productivity_observation_files(tmp_path):
    status = build_productivity_compiled_data_status(tmp_path, "R3")

    assert set(status) == {
        "productivity_pick_observations",
        "productivity_trans_observations",
        "productivity_pallet_observations",
    }
    assert all(item["kind"] == "compiled_data" for item in status.values())
    assert all(item["uploaded"] is False for item in status.values())


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
