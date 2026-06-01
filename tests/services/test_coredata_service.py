from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.coredata_service import (
    build_coredata_status,
    classify_coredata_file,
    find_coredata_file,
    save_coredata_file,
)
from app.backend.models import CoreDataFile
from app.backend.routers import coredata as coredata_router


def write(path: Path, content: str = "Kolumn\nvarde\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sqlite_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_coredata_classification_prefers_longest_prefix():
    assert classify_coredata_file("dispatch_template-20260601140837.csv") == "dispatch_template"
    assert classify_coredata_file("item_option-20260525120000.csv") == "item_option"
    assert classify_coredata_file("item_attribute-20260525120000.csv") == "item_attribute"
    assert classify_coredata_file("item_security_info-20260526135153.csv") == "item_security_info"
    assert classify_coredata_file("item-20260525120000.csv") == "item"
    assert classify_coredata_file("location_cost-20260525120000.csv") == "location_cost"
    assert classify_coredata_file("location-20260525120000.csv") == "location"
    assert classify_coredata_file("lagerplats-20260601132425.csv") == "location"
    assert classify_coredata_file("lagerplatser-20260601132425.csv") == "location"
    assert classify_coredata_file("trans_agency-20260601140839.csv") == "trans_agency"
    assert classify_coredata_file("transportörer-20260601140839.csv") == "trans_agency"
    assert classify_coredata_file("agency.csv") == "trans_agency"


def test_coredata_save_replaces_same_file_type_only_for_business(tmp_path):
    old_stigamo = tmp_path / "coredata" / "Stigamo" / "item_option-20260101000000.csv"
    r3_existing = tmp_path / "coredata" / "r3" / "item_option-20260101000000.csv"
    source = tmp_path / "upload" / "item_option-20260525120000.csv"
    write(old_stigamo, "Artikel\tPack Klass\nA\tOLD\n")
    write(r3_existing, "Artikel\tPack Klass\nA\tR3\n")
    write(source, "Artikel\tPack Klass\nA\tNEW\n")

    saved = save_coredata_file(
        source_path=source,
        filename=source.name,
        file_type="item_option",
        reference_dir=tmp_path,
        business_code="STIGAMO",
    )

    assert saved["name"] == source.name
    assert not old_stigamo.exists()
    assert r3_existing.exists()
    assert find_coredata_file("item_option", tmp_path, "STIGAMO").read_text(encoding="utf-8").endswith("NEW\n")
    assert find_coredata_file("item_option", tmp_path, "R3") == r3_existing


def test_item_security_info_upload_replaces_previous_file_for_business(tmp_path):
    old_security = tmp_path / "coredata" / "Stigamo" / "item_security_info-20260526135153.csv"
    item_option = tmp_path / "coredata" / "Stigamo" / "item_option-20260525120000.csv"
    source = tmp_path / "upload" / "item_security_info-20260527101010.csv"
    write(old_security, "Artikel\tFarligt gods niv\u00e5\nA1\tDG\n")
    write(item_option, "Artikel\tPack Klass\nA1\tOLD\n")
    write(source, "Artikel\tFarligt gods niv\u00e5\nA2\tLQ\n")

    saved = save_coredata_file(
        source_path=source,
        filename=source.name,
        file_type="item_security_info",
        reference_dir=tmp_path,
        business_code="STIGAMO",
    )

    assert saved["name"] == source.name
    assert saved["kind"] == "coredata"
    assert not old_security.exists()
    assert item_option.exists()
    assert find_coredata_file("item_security_info", tmp_path, "STIGAMO").read_text(encoding="utf-8").endswith("A2\tLQ\n")


def test_coredata_save_does_not_delete_other_item_prefixes(tmp_path):
    item_option = tmp_path / "coredata" / "stigamo" / "item_option-20260101000000.csv"
    source = tmp_path / "upload" / "item-20260525120000.csv"
    write(item_option)
    write(source)

    save_coredata_file(
        source_path=source,
        filename=source.name,
        file_type="item",
        reference_dir=tmp_path,
        business_code="STIGAMO",
    )

    assert item_option.exists()
    assert find_coredata_file("item", tmp_path, "STIGAMO").name == source.name


def test_coredata_save_does_not_delete_other_location_prefixes(tmp_path):
    location_cost = tmp_path / "coredata" / "stigamo" / "location_cost-20260101000000.csv"
    source = tmp_path / "upload" / "location-20260525120000.csv"
    write(location_cost)
    write(source)

    save_coredata_file(
        source_path=source,
        filename=source.name,
        file_type="location",
        reference_dir=tmp_path,
        business_code="STIGAMO",
    )

    assert location_cost.exists()
    assert find_coredata_file("location", tmp_path, "STIGAMO").name == source.name


def test_coredata_status_is_business_scoped_and_uses_existing_directory_case(tmp_path):
    stigamo_file = tmp_path / "coredata" / "Stigamo" / "dimension-20260512082829.csv"
    location_file = tmp_path / "coredata" / "Stigamo" / "location-20260525171225.csv"
    location_cost_file = tmp_path / "coredata" / "Stigamo" / "location_cost-20260525171226.csv"
    dispatch_template_file = tmp_path / "coredata" / "Stigamo" / "dispatch_template-20260601140837.csv"
    trans_agency_file = tmp_path / "coredata" / "Stigamo" / "trans_agency-20260601140839.csv"
    write(stigamo_file)
    write(location_file)
    write(location_cost_file)
    write(dispatch_template_file)
    write(trans_agency_file)

    stigamo = build_coredata_status(tmp_path, business_code="STIGAMO")
    r3 = build_coredata_status(tmp_path, business_code="R3")

    assert stigamo["files"]["dimension"]["uploaded"] is True
    assert stigamo["files"]["dimension"]["name"] == stigamo_file.name
    assert stigamo["files"]["dimension"]["kind"] == "coredata"
    assert stigamo["files"]["location"]["uploaded"] is True
    assert stigamo["files"]["location_cost"]["uploaded"] is True
    assert stigamo["files"]["dispatch_template"]["uploaded"] is True
    assert stigamo["files"]["trans_agency"]["uploaded"] is True
    assert r3["files"]["dimension"]["uploaded"] is False
    assert r3["files"]["location"]["uploaded"] is False
    assert r3["files"]["location_cost"]["uploaded"] is False
    assert r3["files"]["dispatch_template"]["uploaded"] is False
    assert r3["files"]["trans_agency"]["uploaded"] is False


def test_coredata_postgres_row_becomes_source_of_truth(tmp_path):
    db = sqlite_session()
    old_file = tmp_path / "coredata" / "Stigamo" / "item_option-20260101000000.csv"
    r3_file = tmp_path / "coredata" / "R3" / "item_option-20260101000000.csv"
    source = tmp_path / "upload" / "item_option-20260601101010.csv"
    write(old_file, "Artikel\tPack Klass\nA\tOLD\n")
    write(r3_file, "Artikel\tPack Klass\nA\tR3\n")
    write(source, "Artikel\tPack Klass\nA\tDB\n")

    saved = save_coredata_file(
        source_path=source,
        filename=source.name,
        file_type="item_option",
        reference_dir=tmp_path,
        business_code="STIGAMO",
        db=db,
        uploaded_by=7,
    )
    db.commit()

    resolved = find_coredata_file("item_option", tmp_path, "STIGAMO", db=db)
    status = build_coredata_status(tmp_path, business_code="STIGAMO", db=db)

    assert saved["storage"] == "postgres"
    assert saved["name"] == source.name
    assert resolved.read_text(encoding="utf-8").endswith("DB\n")
    assert not old_file.exists()
    assert r3_file.exists()
    assert status["files"]["item_option"]["uploaded"] is True
    assert status["files"]["item_option"]["storage"] == "postgres"
    assert status["files"]["item_option"]["name"] == source.name
    row = db.query(CoreDataFile).one()
    assert row.business_code == "STIGAMO"
    assert row.file_type == "item_option"
    assert row.uploaded_by == 7


def test_coredata_postgres_replaces_same_type_only_for_business(tmp_path):
    db = sqlite_session()
    stigamo_old = tmp_path / "upload" / "item_option-20260101000000.csv"
    stigamo_new = tmp_path / "upload" / "item_option-20260601101010.csv"
    r3_source = tmp_path / "upload" / "item_option-r3-20260601101010.csv"
    write(stigamo_old, "Artikel\tPack Klass\nA\tSTIGAMO OLD\n")
    write(stigamo_new, "Artikel\tPack Klass\nA\tSTIGAMO NEW\n")
    write(r3_source, "Artikel\tPack Klass\nA\tR3\n")

    save_coredata_file(
        source_path=stigamo_old,
        filename=stigamo_old.name,
        file_type="item_option",
        reference_dir=tmp_path,
        business_code="STIGAMO",
        db=db,
    )
    save_coredata_file(
        source_path=r3_source,
        filename=r3_source.name,
        file_type="item_option",
        reference_dir=tmp_path,
        business_code="R3",
        db=db,
    )
    save_coredata_file(
        source_path=stigamo_new,
        filename=stigamo_new.name,
        file_type="item_option",
        reference_dir=tmp_path,
        business_code="STIGAMO",
        db=db,
    )
    db.commit()

    assert db.query(CoreDataFile).count() == 2
    assert find_coredata_file("item_option", tmp_path, "STIGAMO", db=db).read_text(encoding="utf-8").endswith("STIGAMO NEW\n")
    assert find_coredata_file("item_option", tmp_path, "R3", db=db).read_text(encoding="utf-8").endswith("R3\n")


def test_coredata_router_status_includes_business_article_max(monkeypatch, tmp_path):
    max_path = tmp_path / "r3" / "artikel_max.csv"
    write(max_path, "artikelnummer,max\nA1,12\n")

    def fake_business_paths(business_code):
        return {
            "observations_path": str(tmp_path / business_code.lower() / "observations.csv.gz"),
            "article_max_path": str(max_path),
        }

    monkeypatch.setattr(coredata_router.bridge, "business_allocation_data_paths", fake_business_paths)
    monkeypatch.setattr(
        coredata_router,
        "build_productivity_compiled_data_status",
        lambda business_code: {
            "productivity_pick_observations": {
                "key": "productivity_pick_observations",
                "name": "v_ask_pick_log_full_observations.csv.gz",
                "uploaded": True,
                "kind": "compiled_data",
            }
        },
    )

    status = coredata_router._coredata_status("R3")

    assert status["files"]["article_max"]["uploaded"] is True
    assert status["files"]["article_max"]["name"] == "artikel_max.csv"
    assert status["files"]["article_max"]["kind"] == "compiled_data"
    assert status["files"]["productivity_pick_observations"]["uploaded"] is True
    assert status["files"]["productivity_pick_observations"]["kind"] == "compiled_data"


def test_coredata_router_saves_article_max_to_business_path(monkeypatch, tmp_path):
    target = tmp_path / "r3" / "artikel_max.csv"
    old_variant = tmp_path / "r3" / "artikel_max-20260101.csv"
    source = tmp_path / "upload" / "artikel_max-20260525.csv"
    write(target, "artikelnummer,max\nOLD,1\n")
    write(old_variant, "artikelnummer,max\nOLD2,2\n")
    write(source, "artikelnummer,max\nNEW,3\n")

    def fake_business_paths(business_code):
        return {
            "observations_path": str(tmp_path / business_code.lower() / "observations.csv.gz"),
            "article_max_path": str(target),
        }

    monkeypatch.setattr(coredata_router.bridge, "business_allocation_data_paths", fake_business_paths)

    saved = coredata_router._save_article_max_file(
        source_path=source,
        filename=source.name,
        business_code="R3",
    )

    assert saved["name"] == "artikel_max.csv"
    assert saved["kind"] == "compiled_data"
    assert target.read_text(encoding="utf-8").endswith("NEW,3\n")
    assert not old_variant.exists()


def test_coredata_router_warms_location_cache_after_upload(monkeypatch, tmp_path):
    location_path = tmp_path / "coredata" / "stigamo" / "location-20260525.csv"
    write(location_path, "Lagerplats\tTyp\tMax pall\nUTL100\tU\t1\n")
    calls = []

    flows_module = SimpleNamespace(
        clear_prepared_location_cache=lambda: calls.append(("clear", None)),
        warm_prepared_locations=lambda path: calls.append(("warm", Path(path))),
    )
    monkeypatch.setattr(coredata_router.bridge, "require_available", lambda: (object(), flows_module))
    monkeypatch.setattr(
        coredata_router,
        "find_coredata_file",
        lambda file_type, business_code=None, **kwargs: location_path,
    )

    coredata_router._warm_coredata_caches("location", "STIGAMO")

    assert calls == [("clear", None), ("warm", location_path)]


def test_coredata_router_only_warms_location_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(coredata_router.bridge, "require_available", lambda: calls.append("load"))

    coredata_router._warm_coredata_caches("item", "STIGAMO")

    assert calls == []
