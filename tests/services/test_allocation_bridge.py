import os
import asyncio
import io
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.backend import allocation_bridge as bridge
from app.backend.routers import allocation as allocation_router


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clear_allocation_sessions():
    bridge.SESSIONS.clear()
    yield
    bridge.SESSIONS.clear()


def fake_available(monkeypatch, *, flows_module=None, engine_module=None):
    engine = engine_module or SimpleNamespace(APP_VERSION="test", APP_TITLE="Allokering")
    flows = flows_module or SimpleNamespace(
        FLOW_BY_ID={},
        public_registry=lambda: [],
        public_pool=lambda: [],
    )
    monkeypatch.setattr(bridge, "require_available", lambda: (engine, flows))
    return engine, flows


def route_user(role: str):
    return SimpleNamespace(id=1, username=f"{role}-user", role=role, roles=[role], is_active=True)


def upload_file(filename: str, content: bytes) -> StarletteUploadFile:
    return StarletteUploadFile(file=io.BytesIO(content), filename=filename)


def business_user(user_id: int, business_id: int, role: str = "super_user"):
    return SimpleNamespace(
        id=user_id,
        username=f"user-{user_id}",
        role=role,
        roles=[role],
        business_id=business_id,
        is_active=True,
    )


class FakeQuery:
    def __init__(self, item):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.item

    def one_or_none(self):
        return self.item


class FakeBusinessScopeDb:
    def __init__(self, *, user_business_code="STIGAMO", focus_business_code="R3"):
        self.user_business = SimpleNamespace(id=10, code=user_business_code)
        self.focus_business = SimpleNamespace(id=20, code=focus_business_code)
        self.focus_area = SimpleNamespace(id=200, code=focus_business_code, business_id=self.focus_business.id)

    def get(self, model, object_id):
        name = getattr(model, "__name__", "")
        if name == "Business":
            if object_id == self.user_business.id:
                return self.user_business
            if object_id == self.focus_business.id:
                return self.focus_business
        if name == "Area" and object_id == self.focus_area.id:
            return self.focus_area
        return None

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "Area":
            return FakeQuery(self.focus_area)
        if name == "Business":
            return FakeQuery(self.focus_business)
        return FakeQuery(None)


def test_df_to_table_serializes_preview_without_nan_values():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        {
            "Artikel": ["A100", None],
            "Antal": [1.0, float("nan")],
        }
    )

    table = bridge.df_to_table(df, preview_limit=1)

    assert table == {
        "columns": ["Artikel", "Antal"],
        "rows": [["A100", "1"]],
        "row_count": 2,
        "truncated": True,
    }


def test_save_upload_can_reuse_content_addressed_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_DIR", tmp_path / "upload-cache")
    content = b"Artikel;Antal\nA1;2\n"

    first = asyncio.run(bridge.save_upload(upload_file("orders.csv", content), cache=True))
    second = asyncio.run(bridge.save_upload(upload_file("renamed.csv", content), cache=True))
    uncached = asyncio.run(bridge.save_upload(upload_file("orders.csv", content), cache=False))

    try:
        assert first == second
        assert first.is_file()
        assert first.read_bytes() == content
        assert first.parent == tmp_path / "upload-cache"
        assert uncached != first
    finally:
        uncached.unlink(missing_ok=True)


def test_save_upload_replaces_previous_cache_for_same_scoped_name(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_DIR", tmp_path / "upload-cache")
    cache_key = "user:1:orders:orders.csv"

    first = asyncio.run(bridge.save_upload(upload_file("orders.csv", b"Artikel;Antal\nA1;2\n"), cache=True, cache_key=cache_key))
    second = asyncio.run(bridge.save_upload(upload_file("orders.csv", b"Artikel;Antal\nA1;3\n"), cache=True, cache_key=cache_key))

    assert first != second
    assert not first.exists()
    assert second.is_file()
    assert second.read_bytes() == b"Artikel;Antal\nA1;3\n"


def test_upload_cache_cleanup_expires_old_files(tmp_path, monkeypatch):
    cache_dir = tmp_path / "upload-cache"
    cache_dir.mkdir()
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_DIR", cache_dir)
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_TTL_SECONDS", 10)
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_MAX_FILES", 10)
    expired = cache_dir / "expired.csv"
    fresh = cache_dir / "fresh.csv"
    expired.write_text("old", encoding="utf-8")
    fresh.write_text("fresh", encoding="utf-8")
    os.utime(expired, (100, 100))
    os.utime(fresh, (106, 106))

    bridge._cleanup_upload_cache(now=111)

    assert not expired.exists()
    assert fresh.exists()


def test_upload_cache_cleanup_caps_file_count(tmp_path, monkeypatch):
    cache_dir = tmp_path / "upload-cache"
    cache_dir.mkdir()
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_DIR", cache_dir)
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_TTL_SECONDS", 1000)
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_MAX_FILES", 2)
    files = [cache_dir / f"file-{index}.csv" for index in range(3)]
    for index, path in enumerate(files):
        path.write_text(str(index), encoding="utf-8")
        os.utime(path, (100 + index, 100 + index))

    bridge._cleanup_upload_cache(now=150)

    assert not files[0].exists()
    assert files[1].exists()
    assert files[2].exists()


def test_form_to_flow_payload_uses_cached_uploads_without_temp_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_DIR", tmp_path / "upload-cache")

    class FakeForm:
        def multi_items(self):
            return [
                ("orders", upload_file("orders.csv", b"Artikel;Antal\nA1;2\n")),
                ("chunk_size", "2000"),
            ]

    files, params, temp_paths = asyncio.run(bridge.form_to_flow_payload(FakeForm()))

    assert sorted(files) == ["orders"]
    assert files["orders"].is_file()
    assert files["orders"].parent == tmp_path / "upload-cache"
    assert params == {"chunk_size": "2000"}
    assert temp_paths == []


def test_process_area_filter_filters_gg_company_and_customer(tmp_path):
    pd = pytest.importorskip("pandas")
    source = tmp_path / "orders.csv"
    source.write_text(
        "Bolag\tKund\tArtikel\n"
        "GG\t6005\tA1\n"
        "GG\t1234\tA2\n"
        "MG\t1234\tA3\n"
        "GG\t6005.0\tA4\n",
        encoding="utf-8",
    )

    files, temp_paths, log = bridge.apply_process_area_filters({"orders": source}, "GG")
    try:
        filtered = pd.read_csv(files["orders"], dtype=str, sep="\t")
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)

    assert filtered["Artikel"].tolist() == ["A2"]
    assert log == [
        "Omradesfilter GG: Bolag=GG, Kundnr!=6005.",
        "orders: 4 -> 1 rader (Bolag, Kund).",
    ]


def test_process_area_filter_filters_mg_excluded_customers(tmp_path):
    pd = pytest.importorskip("pandas")
    source = tmp_path / "overview.csv"
    source.write_text(
        "company;custom_num;order_num\n"
        "MG;40002;O1\n"
        "MG;90002;O2\n"
        "MG;50000;O3\n"
        "GG;50000;O4\n",
        encoding="utf-8",
    )

    files, temp_paths, _log = bridge.apply_process_area_filters({"overview": source}, "MG")
    try:
        filtered = pd.read_csv(files["overview"], dtype=str, sep="\t")
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)

    assert filtered["order_num"].tolist() == ["O3"]


def test_process_area_filter_reuses_cached_filtered_file(tmp_path, monkeypatch):
    pd = pytest.importorskip("pandas")
    monkeypatch.setattr(bridge, "UPLOAD_CACHE_DIR", tmp_path / "upload-cache")
    source = tmp_path / "orders.csv"
    source.write_text(
        "Bolag\tKund\tArtikel\n"
        "GG\t6005\tA1\n"
        "GG\t1234\tA2\n",
        encoding="utf-8",
    )

    first_files, first_temp_paths, first_log = bridge.apply_process_area_filters({"orders": source}, "GG")
    second_files, second_temp_paths, second_log = bridge.apply_process_area_filters({"orders": source}, "GG")

    assert first_files["orders"] == second_files["orders"]
    assert first_temp_paths == []
    assert second_temp_paths == []
    assert first_log == second_log
    filtered = pd.read_csv(second_files["orders"], dtype=str, sep="\t")
    assert filtered["Artikel"].tolist() == ["A2"]

    source.write_text(
        "Bolag\tKund\tArtikel\n"
        "GG\t6005\tA1\n"
        "GG\t1234\tA333\n",
        encoding="utf-8",
    )
    third_files, _third_temp_paths, _third_log = bridge.apply_process_area_filters({"orders": source}, "GG")

    assert third_files["orders"] != first_files["orders"]


def test_process_area_filter_other_toggles_see_everything(tmp_path):
    source = tmp_path / "orders.csv"
    source.write_text("Bolag\tKund\tArtikel\nGG\t6005\tA1\n", encoding="utf-8")

    files, temp_paths, log = bridge.apply_process_area_filters({"orders": source}, "AS")

    assert files == {"orders": source}
    assert temp_paths == []
    assert log == []


def test_process_flow_visibility_matrix_defaults_to_all_flows(monkeypatch):
    assert bridge.process_flow_visible("allocate", "GG")
    monkeypatch.setitem(
        bridge.PROCESS_AREA_RULES,
        "GG",
        {
            "company": "GG",
            "exclude_customers": {"6005"},
            "label": "test",
            "visible_flow_ids": {"allocate"},
        },
    )

    assert bridge.process_flow_visible("allocate", "GG")
    assert not bridge.process_flow_visible("ordersaldo", "GG")


def test_process_matrix_override_controls_filter_and_visibility(tmp_path):
    pd = pytest.importorskip("pandas")
    source = tmp_path / "orders.csv"
    source.write_text(
        "Bolag\tKundnr\tArtikel\n"
        "GG\t6005\tA1\n"
        "GG\t7777\tA2\n"
        "MG\t7777\tA3\n",
        encoding="utf-8",
    )
    matrix = bridge.normalize_process_matrix(
        {
            "AS": {
                "company": "GG",
                "excludeCustomers": ["6005"],
                "visibleFlowIds": ["allocate"],
            }
        }
    )

    assert bridge.process_flow_visible("allocate", "AS", matrix)
    assert not bridge.process_flow_visible("ordersaldo", "AS", matrix)

    files, temp_paths, log = bridge.apply_process_area_filters({"orders": source}, "AS", matrix)
    try:
        filtered = pd.read_csv(files["orders"], dtype=str, sep="\t")
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)

    assert filtered["Artikel"].tolist() == ["A2"]
    assert log[:1] == ["Omradesfilter AS: Bolag=GG, Kundnr!=6005."]


def test_process_matrix_public_payload_exposes_editable_rules():
    flows = [{"id": "allocate", "label": "Allokering", "category": "Allokering"}]
    matrix = bridge.normalize_process_matrix(
        {"GG": {"company": "GG", "excludeCustomers": ["6005"], "visibleFlowIds": ["allocate", "hidden"]}},
        flows=flows,
    )

    payload = bridge.process_matrix_public_payload(matrix, flows=flows)

    assert payload["flows"] == flows
    assert {"code": "GG", "label": "GG"} in payload["areas"]
    assert payload["matrix"]["GG"] == {
        "company": "GG",
        "excludeCustomers": ["6005"],
        "visibleFlowIds": ["allocate"],
        "label": "Bolag=GG, Kundnr!=6005",
        "filterLabel": "Filter: Bolag GG, exkl. kundnr 6005",
    }


def test_process_matrix_empty_visible_flow_list_hides_all_flows():
    matrix = bridge.normalize_process_matrix({"GG": {"visibleFlowIds": []}})

    assert not bridge.process_flow_visible("allocate", "GG", matrix)
    assert bridge.process_matrix_storage_payload(matrix)["GG"]["visibleFlowIds"] == []


def test_allocation_result_session_is_limited_to_owner_user():
    owner = business_user(1, 10)
    other_same_business = business_user(2, 10)
    bridge.SESSIONS["sid"] = {"owner": allocation_router._session_owner_payload(owner)}

    allocation_router._assert_session_allowed("sid", owner)
    with pytest.raises(HTTPException) as exc_info:
        allocation_router._assert_session_allowed("sid", other_same_business)

    assert exc_info.value.status_code == 404


def test_allocation_run_flow_stores_session_owner(monkeypatch):
    user = business_user(7, 20)

    class FakeRequest:
        async def form(self):
            return object()

    async def fake_form_to_flow_payload(_form, **kwargs):
        assert kwargs == {"cache_scope": "user:7"}
        return {}, {}, []

    def fake_run_flow_handler(flow_id, files, params):
        bridge.SESSIONS["sid"] = {"flow_id": flow_id, "tables": {}, "labels": {}}
        return {"session_id": "sid", "tables": [], "summary": {}}

    monkeypatch.setattr(bridge, "form_to_flow_payload", fake_form_to_flow_payload)
    monkeypatch.setattr(bridge, "run_flow_handler", fake_run_flow_handler)
    monkeypatch.setattr(allocation_router, "_audit_allocation_event", lambda *args, **kwargs: None)

    result = asyncio.run(allocation_router.run_flow("allocate", FakeRequest(), user=user, db=object()))

    assert result["session_id"] == "sid"
    assert bridge.SESSIONS["sid"]["owner"] == {"user_id": 7, "business_id": 20}


def test_allocation_run_flow_uses_business_article_max_when_missing_upload(monkeypatch, tmp_path):
    user = business_user(7, 20)
    captured = {}

    class FakeDb:
        def get(self, model, object_id):
            return SimpleNamespace(code="R3")

    class FakeRequest:
        async def form(self):
            return object()

    async def fake_form_to_flow_payload(_form, **kwargs):
        assert kwargs == {"cache_scope": "user:7"}
        return {"orders": tmp_path / "orders.csv"}, {}, []

    def fake_business_paths(business_code):
        captured["business_code"] = business_code
        return {
            "observations_path": str(tmp_path / "r3" / "observations.csv.gz"),
            "article_max_path": str(tmp_path / "r3" / "artikel_max.csv"),
        }

    def fake_run_flow_handler(flow_id, files, params, *, default_max_csv_path=None):
        captured["flow_id"] = flow_id
        captured["files"] = dict(files)
        captured["default_max_csv_path"] = default_max_csv_path
        return {"flow_id": flow_id, "tables": [], "summary": {}}

    monkeypatch.setattr(bridge, "form_to_flow_payload", fake_form_to_flow_payload)
    monkeypatch.setattr(bridge, "business_allocation_data_paths", fake_business_paths)
    monkeypatch.setattr(bridge, "run_flow_handler", fake_run_flow_handler)
    monkeypatch.setattr(allocation_router, "_audit_allocation_event", lambda *args, **kwargs: None)

    result = asyncio.run(allocation_router.run_flow("ordersaldo", FakeRequest(), user=user, db=FakeDb()))

    assert result["flow_id"] == "ordersaldo"
    assert captured["business_code"] == "R3"
    assert captured["default_max_csv_path"] == str(tmp_path / "r3" / "artikel_max.csv")
    assert captured["files"] == {"orders": tmp_path / "orders.csv"}


def test_allocation_run_flow_uses_area_focus_business_for_super_user(monkeypatch, tmp_path):
    user = business_user(7, 10)
    captured = {}

    class FakeRequest:
        async def form(self):
            return object()

    async def fake_form_to_flow_payload(_form, **kwargs):
        assert kwargs == {"cache_scope": "user:7"}
        return {"orders": tmp_path / "orders.csv"}, {bridge.PROCESS_AREA_FOCUS_PARAM: "R3"}, []

    def fake_business_paths(business_code):
        captured["business_code"] = business_code
        return {
            "observations_path": str(tmp_path / business_code.lower() / "observations.csv.gz"),
            "article_max_path": str(tmp_path / business_code.lower() / "artikel_max.csv"),
        }

    def fake_run_flow_handler(flow_id, files, params, *, default_max_csv_path=None):
        captured["flow_id"] = flow_id
        captured["files"] = dict(files)
        captured["default_max_csv_path"] = default_max_csv_path
        return {"flow_id": flow_id, "tables": [], "summary": {}}

    monkeypatch.setattr(bridge, "form_to_flow_payload", fake_form_to_flow_payload)
    monkeypatch.setattr(bridge, "business_allocation_data_paths", fake_business_paths)
    monkeypatch.setattr(bridge, "run_flow_handler", fake_run_flow_handler)
    monkeypatch.setattr(allocation_router, "_audit_allocation_event", lambda *args, **kwargs: None)

    result = asyncio.run(allocation_router.run_flow("ordersaldo", FakeRequest(), user=user, db=FakeBusinessScopeDb()))

    assert result["flow_id"] == "ordersaldo"
    assert captured["business_code"] == "R3"
    assert captured["default_max_csv_path"] == str(tmp_path / "r3" / "artikel_max.csv")
    assert captured["files"] == {"orders": tmp_path / "orders.csv"}


def test_allocation_run_flow_uses_business_coredata_item_option(monkeypatch, tmp_path):
    user = business_user(7, 20)
    item_option_path = tmp_path / "coredata" / "r3" / "item_option-20260525120000.csv"
    item_option_path.parent.mkdir(parents=True, exist_ok=True)
    item_option_path.write_text("Artikel\tPack Klass\nA1\tX\n", encoding="utf-8")
    captured = {}

    class FakeDb:
        def get(self, model, object_id):
            return SimpleNamespace(code="R3")

    class FakeRequest:
        async def form(self):
            return object()

    async def fake_form_to_flow_payload(_form, **kwargs):
        assert kwargs == {"cache_scope": "user:7"}
        return {"orders": tmp_path / "orders.csv", "buffer": tmp_path / "buffer.csv"}, {}, []

    def fake_find_coredata_file(file_type, **kwargs):
        assert file_type == "item_option"
        assert kwargs["business_code"] == "R3"
        return item_option_path

    def fake_run_flow_handler(flow_id, files, params, *, default_max_csv_path=None):
        captured["flow_id"] = flow_id
        captured["files"] = dict(files)
        captured["default_max_csv_path"] = default_max_csv_path
        return {"flow_id": flow_id, "tables": [], "summary": {}}

    monkeypatch.setattr(bridge, "form_to_flow_payload", fake_form_to_flow_payload)
    monkeypatch.setattr(allocation_router, "find_coredata_file", fake_find_coredata_file)
    monkeypatch.setattr(bridge, "run_flow_handler", fake_run_flow_handler)
    monkeypatch.setattr(allocation_router, "_audit_allocation_event", lambda *args, **kwargs: None)

    result = asyncio.run(allocation_router.run_flow("allocate", FakeRequest(), user=user, db=FakeDb()))

    assert result["flow_id"] == "allocate"
    assert captured["files"]["items"] == item_option_path
    assert captured["files"]["orders"] == tmp_path / "orders.csv"
    assert captured["default_max_csv_path"] is None


def test_allocation_run_flow_filters_uploaded_files_from_area_focus(monkeypatch, tmp_path):
    pd = pytest.importorskip("pandas")
    user = business_user(7, 20)
    source = tmp_path / "orders.csv"
    source.write_text(
        "Bolag\tKund\tArtikel\n"
        "GG\t6005\tA1\n"
        "GG\t1234\tA2\n"
        "MG\t1234\tA3\n",
        encoding="utf-8",
    )
    captured = {}

    class FakeDb:
        def get(self, model, object_id):
            return SimpleNamespace(code="STIGAMO")

    class FakeRequest:
        async def form(self):
            return object()

    async def fake_form_to_flow_payload(_form, **kwargs):
        assert kwargs == {"cache_scope": "user:7"}
        return {"orders": source}, {bridge.PROCESS_AREA_FOCUS_PARAM: "GG"}, []

    def fake_run_flow_handler(flow_id, files, params, *, default_max_csv_path=None):
        captured["flow_id"] = flow_id
        captured["params"] = dict(params)
        captured["rows"] = pd.read_csv(files["orders"], dtype=str, sep="\t")["Artikel"].tolist()
        return {"flow_id": flow_id, "tables": [], "summary": {}, "log": ["handler log"]}

    monkeypatch.setattr(bridge, "form_to_flow_payload", fake_form_to_flow_payload)
    monkeypatch.setattr(bridge, "run_flow_handler", fake_run_flow_handler)
    monkeypatch.setattr(allocation_router, "_audit_allocation_event", lambda *args, **kwargs: None)

    result = asyncio.run(allocation_router.run_flow("vecka27-check", FakeRequest(), user=user, db=FakeDb()))

    assert result["flow_id"] == "vecka27-check"
    assert captured["params"] == {}
    assert captured["rows"] == ["A2"]
    assert result["log"][:2] == [
        "Omradesfilter GG: Bolag=GG, Kundnr!=6005.",
        "orders: 3 -> 1 rader (Bolag, Kund).",
    ]


def test_allocation_run_flow_uses_saved_process_matrix(monkeypatch, tmp_path):
    pd = pytest.importorskip("pandas")
    user = business_user(7, 20)
    source = tmp_path / "orders.csv"
    source.write_text(
        "Bolag\tKund\tArtikel\n"
        "GG\t6005\tA1\n"
        "GG\t1234\tA2\n"
        "MG\t1234\tA3\n",
        encoding="utf-8",
    )
    captured = {}

    class FakeDb:
        def get(self, model, object_id):
            return SimpleNamespace(code="STIGAMO")

    class FakeRequest:
        async def form(self):
            return object()

    async def fake_form_to_flow_payload(_form, **kwargs):
        assert kwargs == {"cache_scope": "user:7"}
        return {"orders": source}, {bridge.PROCESS_AREA_FOCUS_PARAM: "AS"}, []

    def fake_run_flow_handler(flow_id, files, params, *, default_max_csv_path=None):
        captured["flow_id"] = flow_id
        captured["rows"] = pd.read_csv(files["orders"], dtype=str, sep="\t")["Artikel"].tolist()
        return {"flow_id": flow_id, "tables": [], "summary": {}, "log": []}

    monkeypatch.setattr(bridge, "form_to_flow_payload", fake_form_to_flow_payload)
    monkeypatch.setattr(bridge, "run_flow_handler", fake_run_flow_handler)
    monkeypatch.setattr(
        allocation_router,
        "get_json_setting",
        lambda *args, **kwargs: {
            "AS": {
                "company": "GG",
                "excludeCustomers": ["6005"],
                "visibleFlowIds": ["vecka27-check"],
            }
        },
    )
    monkeypatch.setattr(allocation_router, "_audit_allocation_event", lambda *args, **kwargs: None)

    result = asyncio.run(allocation_router.run_flow("vecka27-check", FakeRequest(), user=user, db=FakeDb()))

    assert result["flow_id"] == "vecka27-check"
    assert captured["rows"] == ["A2"]
    assert result["area_filter"]["area_focus"] == "AS"


def test_run_flow_handler_passes_business_default_article_max(monkeypatch, tmp_path):
    captured = {}
    max_path = tmp_path / "artikel_max.csv"
    max_path.write_text("artikelnummer,max,pallid\nA1,12,P1\n", encoding="utf-8")

    def handler(files, params):
        captured["files"] = dict(files)
        captured["params"] = dict(params)
        return {"summary": {}, "tables": [], "log": []}

    monkeypatch.setattr(
        bridge,
        "_native_flows",
        lambda: SimpleNamespace(FLOW_BY_ID={"ordersaldo": {"handler": handler}}),
    )

    result = bridge.run_flow_handler(
        "ordersaldo",
        {},
        {},
        default_max_csv_path=max_path,
    )

    assert result["flow_id"] == "ordersaldo"
    assert captured["files"] == {}
    assert captured["params"] == {bridge.DEFAULT_MAX_CSV_PARAM: str(max_path)}


def test_run_flow_handler_stores_artifacts(monkeypatch):
    pd = pytest.importorskip("pandas")

    def handler(files, params):
        table = pd.DataFrame([{"Sändningsnr": "S1", "Predikterade pallplatser": 1.5}])
        return {
            "summary": {"Sändningar": 1},
            "tables": [("forecast", "Forecast", table)],
            "artifacts": {"forecast_json": {"rows": table.to_dict("records")}},
            "log": [],
        }

    monkeypatch.setattr(
        bridge,
        "_native_flows",
        lambda: SimpleNamespace(FLOW_BY_ID={"forecast": {"handler": handler}}),
    )

    result = bridge.run_flow_handler("forecast", {}, {})
    session = bridge.SESSIONS[result["session_id"]]

    assert result["artifact_keys"] == ["forecast_json"]
    assert session["artifacts"]["forecast_json"]["rows"][0]["Sändningsnr"] == "S1"


def test_run_flow_handler_returns_friendly_error_without_trace(monkeypatch):
    def handler(_files, _params):
        raise ValueError("No objects to concatenate")

    monkeypatch.setattr(
        bridge,
        "_native_flows",
        lambda: SimpleNamespace(FLOW_BY_ID={"forecast": {"handler": handler}}),
    )

    with pytest.raises(HTTPException) as exc_info:
        bridge.run_flow_handler("forecast", {}, {})

    detail = exc_info.value.detail
    assert exc_info.value.status_code == 400
    assert detail["error_code"] == "allocation_flow_failed"
    assert detail["error_type"] == "ValueError"
    assert "inga rader" in detail["message"]
    assert detail["technical_message"] == "No objects to concatenate"
    assert "trace" not in detail


def test_ytgenerering_attaches_forecast_dataframe_fast_path():
    pd = pytest.importorskip("pandas")
    user = business_user(1, 10)
    table = pd.DataFrame([{"Sändningsnr": "S1"}])
    bridge.SESSIONS["forecast-session"] = {
        "flow_id": "forecast",
        "tables": {"forecast": table},
        "artifacts": {"forecast_json": {"rows": [{"Sändningsnr": "S1"}]}},
        "owner": allocation_router._session_owner_payload(user),
    }
    params = {"forecast_session_id": "forecast-session"}

    allocation_router._attach_required_session_artifacts("ytgenerering", params, user)

    assert params["__forecast_df"] is table
    assert "__forecast_json" not in params


def test_ytgenerering_falls_back_to_forecast_json_artifact():
    user = business_user(1, 10)
    bridge.SESSIONS["forecast-session"] = {
        "flow_id": "forecast",
        "artifacts": {"forecast_json": {"rows": [{"Sändningsnr": "S1"}]}},
        "owner": allocation_router._session_owner_payload(user),
    }
    params = {"forecast_session_id": "forecast-session"}

    allocation_router._attach_required_session_artifacts("ytgenerering", params, user)

    assert '"S1"' in params["__forecast_json"]


def test_forecast_and_ytgenerering_coredata_defaults_are_business_scoped(monkeypatch, tmp_path):
    captured = []

    def fake_find_coredata_file(file_type, **kwargs):
        captured.append((file_type, kwargs["business_code"]))
        path = tmp_path / f"{file_type}.csv"
        path.write_text("x\n", encoding="utf-8")
        return path

    monkeypatch.setattr(allocation_router, "find_coredata_file", fake_find_coredata_file)

    forecast_defaults = allocation_router._business_coredata_default_files("forecast", {}, "R3")
    ytgenerering_defaults = allocation_router._business_coredata_default_files("ytgenerering", {}, "R3")

    assert set(forecast_defaults) == {
        "custom",
        "item",
        "item_alias",
        "dimension",
        "pallet_type",
        "item_option",
    }
    assert set(ytgenerering_defaults) == {"location"}
    assert ("location", "R3") in captured
    assert all(business_code == "R3" for _file_type, business_code in captured)


def test_update_observations_writes_to_user_business_paths(monkeypatch, tmp_path):
    upload_path = tmp_path / "buffer.csv"
    upload_path.write_text("Artikel,Pallid,Antal,Status\nA1,P1,10,30\n", encoding="utf-8")
    captured = {}
    user = business_user(8, 30)

    class FakeDb:
        def get(self, model, object_id):
            return SimpleNamespace(code="R3")

    async def fake_save_upload(_file):
        return upload_path

    def fake_business_paths(business_code):
        captured["path_business_code"] = business_code
        return {
            "observations_path": str(tmp_path / "r3" / "observations.csv.gz"),
            "article_max_path": str(tmp_path / "r3" / "artikel_max.csv"),
        }

    def fake_build(buffer_df, **kwargs):
        captured["buffer_df"] = buffer_df
        captured["build_kwargs"] = kwargs
        return SimpleNamespace(
            new_row_count=1,
            github_sent_rows=1,
            article_max_rows=1,
            article_max_changed_rows=1,
            article_max_increased_rows=1,
            article_max_decreased_rows=0,
            article_max_new_rows=1,
            article_max_removed_rows=0,
            article_max_changed_examples=[],
            pushed_to_github=True,
            observations_path=kwargs["observations_path"],
            article_max_path=kwargs["artikel_max_out"],
        )

    engine = SimpleNamespace(
        read_table=lambda path: {"path": path},
        build_observations_update_result=fake_build,
    )

    fake_available(monkeypatch, engine_module=engine)
    monkeypatch.setattr(bridge, "save_upload", fake_save_upload)
    monkeypatch.setattr(bridge, "business_allocation_data_paths", fake_business_paths)
    monkeypatch.setattr(allocation_router, "_audit_allocation_event", lambda *args, **kwargs: None)

    response = asyncio.run(
        allocation_router.update_observations(
            file=upload_file("buffer.csv", b""),
            user=user,
            db=FakeDb(),
        )
    )

    assert response["business_code"] == "R3"
    assert response["observations_path"] == str(tmp_path / "r3" / "observations.csv.gz")
    assert response["article_max_path"] == str(tmp_path / "r3" / "artikel_max.csv")
    assert captured["path_business_code"] == "R3"
    assert captured["buffer_df"] == {"path": str(upload_path)}
    assert captured["build_kwargs"] == {
        "observations_path": str(tmp_path / "r3" / "observations.csv.gz"),
        "artikel_max_out": str(tmp_path / "r3" / "artikel_max.csv"),
        "push_to_github": True,
        "business_code": "R3",
    }
    assert not upload_path.exists()


def test_update_observations_uses_area_focus_business_for_super_user(monkeypatch, tmp_path):
    upload_path = tmp_path / "buffer.csv"
    upload_path.write_text("Artikel,Pallid,Antal,Status\nA1,P1,10,30\n", encoding="utf-8")
    captured = {}
    user = business_user(8, 10)

    async def fake_save_upload(_file):
        return upload_path

    def fake_business_paths(business_code):
        captured["path_business_code"] = business_code
        return {
            "observations_path": str(tmp_path / business_code.lower() / "observations.csv.gz"),
            "article_max_path": str(tmp_path / business_code.lower() / "artikel_max.csv"),
        }

    def fake_build(buffer_df, **kwargs):
        captured["build_kwargs"] = kwargs
        return SimpleNamespace(
            new_row_count=1,
            github_sent_rows=1,
            article_max_rows=1,
            article_max_changed_rows=1,
            article_max_increased_rows=1,
            article_max_decreased_rows=0,
            article_max_new_rows=1,
            article_max_removed_rows=0,
            article_max_changed_examples=[],
            pushed_to_github=True,
            observations_path=kwargs["observations_path"],
            article_max_path=kwargs["artikel_max_out"],
        )

    engine = SimpleNamespace(
        read_table=lambda path: {"path": path},
        build_observations_update_result=fake_build,
    )

    fake_available(monkeypatch, engine_module=engine)
    monkeypatch.setattr(bridge, "save_upload", fake_save_upload)
    monkeypatch.setattr(bridge, "business_allocation_data_paths", fake_business_paths)
    monkeypatch.setattr(allocation_router, "_audit_allocation_event", lambda *args, **kwargs: None)

    response = asyncio.run(
        allocation_router.update_observations(
            file=upload_file("buffer.csv", b""),
            area_focus="R3",
            user=user,
            db=FakeBusinessScopeDb(),
        )
    )

    assert response["area_focus"] == "R3"
    assert response["business_code"] == "R3"
    assert response["observations_path"] == str(tmp_path / "r3" / "observations.csv.gz")
    assert response["article_max_path"] == str(tmp_path / "r3" / "artikel_max.csv")
    assert captured["path_business_code"] == "R3"
    assert captured["build_kwargs"]["business_code"] == "R3"
    assert not upload_path.exists()


def test_allocation_bridge_uses_vendored_warehouse_tools_by_default():
    assert bridge.warehouse_tools_dir() == ROOT / "warehouse_tools"
    assert (bridge.warehouse_tools_dir() / "vendor" / "allokering12.1.py").is_file()


def test_allocation_bridge_imports_warehouse_tools_when_started_from_app_root():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from backend import allocation_bridge as bridge; "
                "engine, flows = bridge.require_available(); "
                "print(engine.APP_VERSION, len(flows.FLOW_BY_ID))"
            ),
        ],
        cwd=ROOT / "app",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "12.1.5" in result.stdout


def test_allocation_catalog_loads_without_pandas_when_started_from_app_root():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import builtins\n"
                "real_import = builtins.__import__\n"
                "def guard(name, *args, **kwargs):\n"
                "    if name == 'pandas' or name.startswith('pandas.'):\n"
                "        raise ModuleNotFoundError(\"No module named 'pandas'\")\n"
                "    return real_import(name, *args, **kwargs)\n"
                "builtins.__import__ = guard\n"
                "from backend import allocation_bridge as bridge\n"
                "print(len(bridge.public_registry()), len(bridge.public_pool()))\n"
            ),
        ],
        cwd=ROOT / "app",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().split() == ["15", "10"]


def test_native_detector_recognizes_wms_csv_without_pandas(tmp_path):
    pick_log = tmp_path / "v_ask_pick_log_full-test.csv"
    pick_log.write_text("Pallid;Artikelnr;Plockat;Ordernr;Datum\nP1;A1;1;O1;2026-05-18\n", encoding="utf-8")

    assert bridge.detect_file_type(pick_log) == "wms_pick"


def test_native_detector_uses_ask_filename_hints_without_reading_headers(tmp_path):
    orders = tmp_path / "v_ask_customer_order_details_all-20260518075529.csv"
    orders.write_text("helt;okand;header\n1;2;3\n", encoding="utf-8")

    assert bridge.detect_file_type(orders) == "orders"


def test_native_detector_recognizes_current_upload_filename_hints(tmp_path):
    cases = {
        "item_option-20260519090653.csv": "item",
        "v_ask_article_bufferpallet-20260519090645.csv": "buffer",
        "v_ask_article_buffertpallet-20260519090645.csv": "buffer",
        "v_ask_booking_putaway-20260519090707.csv": "wms_booking",
        "v_ask_trans_log-20260519051930.csv": "wms_trans",
        "ej_inlagrade-20260519090707.csv": "not_putaway",
        "not_putaway-20260519090707.csv": "not_putaway",
        "Granngarden prognos kampanjplock +6v.xlsx": "campaign",
        "Prognos idag_1227934.xlsx": "prognos",
    }
    for filename, expected in cases.items():
        source = tmp_path / filename
        source.write_text("helt;okand;header\n1;2;3\n", encoding="utf-8")
        assert bridge.detect_file_type(source) == expected


def test_native_detector_recognizes_relex_forecast_workbooks(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    campaign = tmp_path / "relex-layout-c.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["The information and calculation results in this sheet were produced by RELEX Solutions."])
    sheet.append(["Period start date", "2025-10-23", "Period end date", "2025-11-23"])
    sheet.append(["Total", "2025-10-23 Thu", "2025-10-24 Fri"])
    sheet.append(["Location code", "Location name", "Produktkod", "Produktnam", "Kampanjstart", "Projicerat antal"])
    workbook.save(campaign)

    forecast = tmp_path / "relex-layout-p.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["The information and calculation results in this sheet were produced by RELEX Solutions."])
    sheet.append(["Period start date", "2025-10-01", "Period end date", "2025-10-01"])
    sheet.append(["Product code", "Product name", "Antal styck", "Antal rader", "Antal butiker"])
    workbook.save(forecast)

    assert bridge.detect_file_type(campaign) == "campaign"
    assert bridge.detect_file_type(forecast) == "prognos"


def test_catalog_routes_booking_putaway_to_not_putaway_pool():
    pool = {slot["key"]: slot for slot in bridge.public_pool()}
    allocate = next(flow for flow in bridge.public_registry() if flow["id"] == "allocate")
    inputs = {item["key"]: item for item in allocate["inputs"]}

    assert "wms_booking" in pool["not_putaway"]["detect"]
    assert "not_putaway" in pool["not_putaway"]["detect"]
    assert "wms_booking" in inputs["not_putaway"]["detect"]
    assert inputs["not_putaway"]["pool"] == "not_putaway"


def test_observations_update_reports_github_sent_rows_and_max_changes(tmp_path, monkeypatch):
    pd = pytest.importorskip("pandas")
    engine, _flows = bridge.require_available()
    observations_path = tmp_path / "observations.csv.gz"
    article_max_path = tmp_path / "artikel_max.csv"
    pd.DataFrame([
        {"artikelnummer": "A1", "pallid": "P1", "antal": "10"},
    ]).to_csv(observations_path, index=False, compression="gzip")
    pd.DataFrame([
        {"artikelnummer": "A1", "max": "10", "pallid": "P1"},
    ]).to_csv(article_max_path, index=False, encoding="utf-8-sig")

    sent = {}

    def fake_push(rows, business_code=None):
        sent["count"] = len(rows)
        sent["business_code"] = business_code
        return True

    monkeypatch.setitem(
        engine.build_observations_update_result.__globals__,
        "push_new_observations_to_github",
        fake_push,
    )
    buffer_df = pd.DataFrame([
        {"Artikel": "A1", "Pallid": "P2", "Antal": "12", "Status": "30"},
        {"Artikel": "B1", "Pallid": "P3", "Antal": "5", "Status": "30"},
    ])

    result = engine.build_observations_update_result(
        buffer_df,
        observations_path=str(observations_path),
        artikel_max_out=str(article_max_path),
        push_to_github=True,
    )

    assert result.new_row_count == 2
    assert result.github_sent_rows == 2
    assert sent["count"] == 2
    assert sent["business_code"] is None
    assert result.pushed_to_github is True
    assert result.article_max_rows == 2
    assert result.article_max_changed_rows == 1
    assert result.article_max_increased_rows == 1
    assert result.article_max_decreased_rows == 0
    assert result.article_max_new_rows == 1
    assert result.article_max_changed_examples[0]["artikelnummer"] == "A1"
    assert result.article_max_changed_examples[0]["before_max"] == "10"
    assert result.article_max_changed_examples[0]["after_max"] == "12"


def test_observations_paths_are_separate_per_business(tmp_path, monkeypatch):
    pd = pytest.importorskip("pandas")
    engine, _flows = bridge.require_available()
    legacy_engine = engine.engine
    monkeypatch.setattr(legacy_engine, "_bufferpall_runtime_dir", lambda: tmp_path)

    stigamo_observations = legacy_engine.business_observations_path("STIGAMO")
    stigamo_max = legacy_engine.business_artikel_max_path("STIGAMO")
    r3_observations = legacy_engine.business_observations_path("R3")
    r3_max = legacy_engine.business_artikel_max_path("R3")

    assert stigamo_observations == tmp_path / "observations.csv.gz"
    assert stigamo_max == tmp_path / "artikel_max.csv"
    assert r3_observations == tmp_path / "r3" / "observations.csv.gz"
    assert r3_max == tmp_path / "r3" / "artikel_max.csv"
    assert list(pd.read_csv(r3_observations, compression="gzip").columns) == [
        "artikelnummer",
        "pallid",
        "antal",
    ]
    assert r3_max.read_text(encoding="utf-8-sig").startswith("artikelnummer,max,pallid")


def test_allocation_bridge_imports_without_tkinter_on_headless_server():
    env = dict(**os.environ, WAREHOUSE_TOOLS_FORCE_HEADLESS_TK="1")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from backend import allocation_bridge as bridge; "
                "engine, flows = bridge.require_available(); "
                "print(engine.APP_VERSION, len(flows.FLOW_BY_ID))"
            ),
        ],
        cwd=ROOT / "app",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "12.1.5" in result.stdout


def test_allocation_bridge_imports_without_requests_update_dependency():
    env = dict(**os.environ, WAREHOUSE_TOOLS_FORCE_HEADLESS_TK="1")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import builtins\n"
                "real_import = builtins.__import__\n"
                "def guard(name, globals=None, locals=None, fromlist=(), level=0):\n"
                "    if level == 0 and (name == 'requests' or name.startswith('requests.')):\n"
                "        raise ModuleNotFoundError(\"No module named 'requests'\")\n"
                "    return real_import(name, globals, locals, fromlist, level)\n"
                "builtins.__import__ = guard\n"
                "from backend import allocation_bridge as bridge\n"
                "engine, flows = bridge.require_available()\n"
                "print(engine.APP_VERSION, len(flows.FLOW_BY_ID))\n"
            ),
        ],
        cwd=ROOT / "app",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "12.1.5" in result.stdout


def test_run_flow_handler_serializes_tables_and_keeps_session(monkeypatch):
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"Artikel": ["A100", ""], "Antal": [1, 2]})
    flows = SimpleNamespace(
        FLOW_BY_ID={
            "demo": {
                "handler": lambda files, params: {
                    "summary": {"files": sorted(files), "limit": params["limit"]},
                    "display_summary": {"Visad": "2 rader"},
                    "tables": [("main", "Demoresultat", df)],
                    "text": "klart",
                    "log": ["rad 1"],
                }
            }
        }
    )
    fake_available(monkeypatch, flows_module=flows)
    monkeypatch.setattr(bridge, "_catalog", lambda: SimpleNamespace(FLOW_BY_ID={"demo": {}}))

    result = bridge.run_flow_handler("demo", {"orders": object()}, {"limit": "10"})

    assert result["flow_id"] == "demo"
    assert result["summary"] == {"files": ["orders"], "limit": "10"}
    assert result["display_summary"] == {"Visad": "2 rader"}
    assert result["text"] == "klart"
    assert result["log"] == ["rad 1"]
    assert result["tables"][0]["key"] == "main"
    assert result["tables"][0]["label"] == "Demoresultat"
    assert result["tables"][0]["table"]["row_count"] == 2
    assert result["session_id"] in bridge.SESSIONS
    assert bridge.table_column_text(result["session_id"], "main", 0) == {"text": "A100"}


@pytest.mark.filterwarnings(
    "ignore:Workbook contains no default style, apply openpyxl's default:UserWarning:openpyxl.styles.stylesheet"
)
def test_run_overview_check_keeps_avvikelse_type_column_in_api_result():
    testdata = ROOT / "testdata" / "warehouse_tools"
    overview = next(iter(sorted(testdata.glob("v_ask_order_overview-*.csv"))), None)
    details = next(iter(sorted(testdata.glob("v_ask_customer_order_details_all-*.csv"))), None)
    if overview is None or details is None:
        pytest.skip("Aktuella orderoversiktsfiler saknas.")

    result = bridge.run_flow_handler("overview-check", {"overview": overview, "details": details}, {})
    orderkontroll = next(table for table in result["tables"] if table["key"] == "orderkontroll")

    assert orderkontroll["table"]["columns"][0] == "Avvikelsetyp"
    assert orderkontroll["table"]["rows"][0][0] == "HIB \u00f6ver status 31 utan butikss\u00e4ndning"
    assert list(bridge.SESSIONS[result["session_id"]]["tables"]["orderkontroll"].columns)[0] == "Avvikelsetyp"


def test_open_excel_result_writes_safe_xlsx_and_opens_path(monkeypatch):
    pd = pytest.importorskip("pandas")
    openpyxl = pytest.importorskip("openpyxl")
    opened = []
    bridge.SESSIONS["abc"] = {
        "flow_id": "prognos-report",
        "tables": {"report": pd.DataFrame({"Artikel": ["A1"], "Antal": [2]})},
        "labels": {"report": "Prognos vs Autoplock"},
    }
    monkeypatch.setattr(bridge, "open_path", lambda path: opened.append(Path(path)))

    result = bridge.open_excel_result(bridge.OpenAllocationExcelRequest(session_id="abc", key="report"))

    assert result["opened"] is True
    assert opened == [Path(result["path"])]
    assert opened[0].suffix == ".xlsx"
    assert "/" not in opened[0].name
    workbook = openpyxl.load_workbook(opened[0], read_only=True)
    try:
        assert workbook.sheetnames == ["Prognos vs Autoplock"]
        rows = list(workbook.active.iter_rows(values_only=True))
        assert rows[:2] == [("Artikel", "Antal"), ("A1", 2)]
    finally:
        workbook.close()


def test_open_excel_result_reports_open_failure(monkeypatch):
    pd = pytest.importorskip("pandas")
    bridge.SESSIONS["abc"] = {
        "flow_id": "allocate",
        "tables": {"result": pd.DataFrame({"Artikel": ["A1"]})},
        "labels": {"result": "Allokerade pallar"},
    }
    monkeypatch.setattr(bridge, "open_path", lambda _path: (_ for _ in ()).throw(OSError("boom")))

    with pytest.raises(HTTPException) as exc_info:
        bridge.open_excel_result(bridge.OpenAllocationExcelRequest(session_id="abc", key="result"))

    assert exc_info.value.status_code == 500
    assert "Kunde inte öppna Excel-filen automatiskt" in exc_info.value.detail


def test_download_result_formats_integer_like_floats_as_in_excel():
    pd = pytest.importorskip("pandas")
    bridge.SESSIONS["abc"] = {
        "flow_id": "allocate",
        "tables": {"result": pd.DataFrame({"Artikel": ["A1"], "Beställt": [1.0], "Tom": [float("nan")]})},
        "labels": {"result": "Allokerade pallar"},
    }

    response = bridge.download_result("abc", "result")

    content = Path(response.path).read_text(encoding="utf-8-sig")
    assert content == "Artikel,Beställt,Tom\nA1,1,\n"


def test_download_result_returns_exact_tab_separated_export_file():
    content = (
        "area_num\tcompany\torder_num\tpick_zone\n"
        "UTL100, UTL101\tMG\t1001\tA\n"
    )
    bridge.SESSIONS["abc"] = {
        "flow_id": "ytgenerering",
        "tables": {},
        "labels": {},
        "download_files": {
            "order_set_area_import": {
                "filename": "v_ask_order_overview_order_set_area_execute_command.csv",
                "content": content,
                "media_type": "text/csv",
            }
        },
    }

    response = bridge.download_result("abc", "order_set_area_import")

    assert Path(response.path).read_bytes().startswith(b"\xef\xbb\xbf")
    assert Path(response.path).read_text(encoding="utf-8-sig") == content
    assert "v_ask_order_overview_order_set_area_execute_command.csv" in response.headers["content-disposition"]


def test_run_split_values_uses_native_flow_without_legacy_runtime(monkeypatch):
    def fail_available():
        raise AssertionError("legacy allocation runtime should not load for split-values")

    monkeypatch.setattr(bridge, "require_available", fail_available)

    result = bridge.run_flow_handler("split-values", {}, {"values": "A\nB\nC\nD\nE", "chunk_size": "2"})

    assert result["summary"] == {"Antal värden": 5, "Antal kolumner": 3, "Per kolumn": 2}
    assert result["tables"][0]["table"] == {
        "columns": ["Kolumn 1", "Kolumn 2", "Kolumn 3"],
        "rows": [["A", "C", "E"], ["B", "D", ""]],
        "row_count": 2,
        "truncated": False,
    }
    assert bridge.table_column_text(result["session_id"], "report", 1) == {"text": "C\nD"}


def test_run_flow_handler_returns_404_for_unknown_flow(monkeypatch):
    fake_available(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        bridge.run_flow_handler("saknas", {}, {})

    assert exc_info.value.status_code == 404


def test_allocation_router_exposes_flow_registry_and_pool(monkeypatch):
    monkeypatch.setattr(bridge, "public_registry", lambda: [{"id": "allocering", "label": "Allokering"}])
    monkeypatch.setattr(bridge, "public_pool", lambda: [{"key": "orders", "label": "Bestallningslinjer"}])

    assert allocation_router.list_flows(user=route_user("super_user")) == {"flows": [{"id": "allocering", "label": "Allokering"}]}
    assert allocation_router.list_pool(user=route_user("super_user")) == {"pool": [{"key": "orders", "label": "Bestallningslinjer"}]}


def test_allocation_router_limits_lager_and_artikelplacering_to_self_service_flows(monkeypatch):
    monkeypatch.setattr(
        bridge,
        "public_registry",
        lambda: [
            {"id": "allocate", "label": "Allokering"},
            {"id": "split-values", "label": "Dela varden"},
        ],
    )
    monkeypatch.setattr(bridge, "public_pool", lambda: [{"key": "orders", "label": "Bestallningslinjer"}])

    for role in ("warehouse_clerk", "article_placer"):
        user = route_user(role)
        assert allocation_router.list_flows(user=user) == {
            "flows": [
                {"id": "split-values", "label": "Dela varden"},
            ]
        }
        assert allocation_router.list_pool(user=user) == {"pool": []}


def test_allocation_router_honors_bearbeta_view_access_for_lagerkontorist(monkeypatch):
    monkeypatch.setattr(
        bridge,
        "public_registry",
        lambda: [
            {"id": "allocate", "label": "Allokering"},
            {"id": "split-values", "label": "Dela varden"},
        ],
    )
    monkeypatch.setattr(bridge, "public_pool", lambda: [{"key": "orders", "label": "Bestallningslinjer"}])
    monkeypatch.setattr(
        allocation_router,
        "get_role_view_access",
        lambda _db, business_id=None: {"warehouse_clerk": {"allocationProcess": "edit"}},
    )

    user = route_user("warehouse_clerk")

    assert allocation_router.list_flows(user=user, db=object()) == {
        "flows": [
            {"id": "allocate", "label": "Allokering"},
            {"id": "split-values", "label": "Dela varden"},
        ]
    }
    assert allocation_router.list_pool(user=user, db=object()) == {"pool": [{"key": "orders", "label": "Bestallningslinjer"}]}


def test_allocation_health_reports_unavailable_without_crashing(monkeypatch):
    def fail():
        raise RuntimeError("saknas")

    monkeypatch.setattr(bridge, "public_registry", fail)
    monkeypatch.setattr(
        bridge,
        "unavailable_detail",
        lambda: {"available": False, "message": "Allokering saknas", "backend_dir": "x"},
    )

    assert allocation_router.health() == {
        "available": False,
        "message": "Allokering saknas",
        "backend_dir": "x",
    }
