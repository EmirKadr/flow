import csv
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend import workflow_data
from app.backend.config import settings
from app.backend.data_fetch_service import DataCatalog, DataColumn, DataView
from app.backend.database import Base
from app.backend.external_data_client import ExternalDataClientError
from app.backend.models import AuditLog, Business, User
from app.backend.routers import workflow_data as workflow_data_router


class FakeExternalClient:
    def __init__(self, rows=None, error: Exception | None = None):
        self.rows = rows or []
        self.error = error
        self.views: list[str] = []
        self.filters: list[object] = []

    def fetch_data(self, view_id: str, filters=None, identifiers=None):
        self.views.append(view_id)
        self.filters.append(filters)
        if self.error is not None:
            raise self.error
        return list(self.rows)

    def fetch_all(self, view_id: str, filters=None, identifiers=None):
        # Speglar ExternalDataClient.fetch_all: workflow-vägen går nu via fetch_all.
        return self.fetch_data(view_id, filters=filters, identifiers=identifiers)


class FakeAuditDb:
    def __init__(self):
        self.items = []
        self.committed = False
        self.rolled_back = False

    def add(self, item):
        self.items.append(item)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _catalog_for(*view_ids: str, columns: tuple[str, ...] = ("article", "robot_ind", "automation_pick_qty", "pick_qty", "pick_loc")):
    views = {}
    for view_id in view_ids:
        views[view_id] = DataView(
            id=view_id,
            label_en=view_id,
            label_sv=view_id,
            columns=tuple(
                DataColumn(id=column, label_en=column, label_sv=column, order=index)
                for index, column in enumerate(columns)
            ),
        )
    return DataCatalog(views=views)


def test_allocation_api_source_maps_cover_api_first_order_and_saldo_flows():
    assert workflow_data.allocation_api_source_map("lyx") == {"saldo": "saldo"}
    assert workflow_data.allocation_api_source_map("hib-koppling") == {
        "details": "orders",
        "overview": "overview",
    }
    assert workflow_data.allocation_api_source_map("pafyllnadsprio") == {
        "orders": "orders",
        "saldo": "saldo",
        "overview": "overview",
    }


def test_productivity_api_source_map_includes_snapshot_sources():
    assert workflow_data.productivity_api_source_map() == {
        "pick": "pick",
        "trans": "trans",
        "pallet": "pallet",
        "receive": "receive",
        "order_log": "order_log",
        "sort": "sort",
        "base_pallet": "base_pallet",
        "kpi": "kpi",
    }


def test_workflow_api_client_uses_tenant_base_url(monkeypatch):
    captured = {}

    class FakeExternalDataClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(settings, "DATA_SOURCE_API_BASE_URL", "https://data-frey.example.test/api/")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY", "secret-key")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT", "secret-client")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_KEY_HEADER", "secret-key-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_API_CLIENT_HEADER", "secret-client-header")
    monkeypatch.setattr(settings, "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE", "secret/path/{view}/data")
    monkeypatch.setattr(workflow_data, "ExternalDataClient", FakeExternalDataClient)

    workflow_data._api_client(tenant="itworks")

    assert captured["base_url"] == "https://data-itworks.example.test/api/"


def test_fetch_source_materializes_api_rows_with_saldo_alias_headers(monkeypatch):
    client = FakeExternalClient(
        [
            {
                "article": "A100",
                "robot_ind": "Y",
                "automation_pick_qty": 12,
                "pick_qty": 5,
                "pick_loc": "P1",
            }
        ]
    )
    monkeypatch.setattr(
        workflow_data,
        "load_catalog",
        lambda: _catalog_for("v_ask_item_summary_stock_automation"),
    )
    monkeypatch.setattr(workflow_data, "_api_client", lambda: client)

    path, entry = workflow_data.fetch_source_to_temp("saldo")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t"))
        assert entry.status == "api"
        assert entry.row_count == 1
        assert client.views == ["v_ask_item_summary_stock_automation"]
        assert rows[0][-4:] == ["Robot", "Saldo autoplock", "Plocksaldo", "Plockplats"]
        assert rows[1][-4:] == ["Y", "12", "5", "P1"]
    finally:
        path.unlink(missing_ok=True)


def test_fetch_source_rejects_saldo_rows_without_robot_column(monkeypatch):
    monkeypatch.setattr(
        workflow_data,
        "load_catalog",
        lambda: _catalog_for("v_ask_item_summary_stock_automation"),
    )
    monkeypatch.setattr(workflow_data, "_api_client", lambda: FakeExternalClient([{"article": "A100"}]))

    with pytest.raises(workflow_data.WorkflowDataError) as excinfo:
        workflow_data.fetch_source_to_temp("saldo")

    assert "robot_ind" in str(excinfo.value)


def test_fetch_source_rejects_item_option_without_forecast_legacy_headers(monkeypatch):
    client = FakeExternalClient(
        [
            {
                "item_num": "A100",
                "company": "MG",
                "pick_zone": "A",
                "automated_robotpick": "Y",
            }
        ]
    )
    monkeypatch.setattr(
        workflow_data,
        "load_catalog",
        lambda: _catalog_for(
            "item_option",
            columns=("item_num", "company", "pick_zone", "automated_robotpick"),
        ),
    )
    monkeypatch.setattr(workflow_data, "_api_client", lambda: client)

    with pytest.raises(workflow_data.WorkflowDataError) as excinfo:
        workflow_data.fetch_source_to_temp("item_option")

    assert "not_stackable" in str(excinfo.value)
    assert "whole_pallet_near_miss_percent" in str(excinfo.value)


def test_fetch_source_materializes_item_option_forecast_legacy_headers(monkeypatch):
    client = FakeExternalClient(
        [
            {
                "item_num": "A100",
                "company": "MG",
                "pick_zone": "A",
                "automated_robotpick": "Y",
                "not_stackable": "Y",
                "whole_pallet_near_miss_percent": "12",
            }
        ]
    )
    monkeypatch.setattr(
        workflow_data,
        "load_catalog",
        lambda: DataCatalog(
            views={
                "item_option": DataView(
                    id="item_option",
                    label_en="item_option",
                    label_sv="item_option",
                    columns=(
                        DataColumn(id="item_num", label_en="item_num", label_sv="Artikel", order=0),
                        DataColumn(id="company", label_en="company", label_sv="Bolag", order=1),
                        DataColumn(id="pick_zone", label_en="pick_zone", label_sv="Plockzon", order=2),
                        DataColumn(
                            id="automated_robotpick",
                            label_en="automated_robotpick",
                            label_sv="Automatiserat robotplock",
                            order=3,
                        ),
                        DataColumn(
                            id="not_stackable",
                            label_en="not_stackable",
                            label_sv="Ej staplingsbar",
                            order=4,
                        ),
                        DataColumn(
                            id="whole_pallet_near_miss_percent",
                            label_en="whole_pallet_near_miss_percent",
                            label_sv="Helpalls avvikelse %",
                            order=5,
                        ),
                    ),
                )
            }
        ),
    )
    monkeypatch.setattr(workflow_data, "_api_client", lambda: client)

    path, _entry = workflow_data.fetch_source_to_temp("item_option")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t"))
        assert rows[0] == [
            "Artikel",
            "Bolag",
            "Plockzon",
            "Automatiserat robotplock",
            "Ej staplingsbar",
            "Helpalls avvikelse %",
        ]
        assert rows[1][-2:] == ["Y", "12"]
    finally:
        path.unlink(missing_ok=True)


def test_fetch_source_passes_filters_to_external_client(monkeypatch):
    client = FakeExternalClient(
        [
            {
                "article": "A100",
                "robot_ind": "Y",
                "automation_pick_qty": 1,
                "pick_qty": 1,
                "pick_loc": "P1",
            }
        ]
    )
    filters = [{"field": "timestamp", "operator": "between", "value": ["2026-06-08", "2026-06-09"]}]
    monkeypatch.setattr(
        workflow_data,
        "load_catalog",
        lambda: _catalog_for("v_ask_item_summary_stock_automation"),
    )
    monkeypatch.setattr(workflow_data, "_api_client", lambda: client)

    path, _entry = workflow_data.fetch_source_to_temp("saldo", filters=filters)

    try:
        assert client.filters == [filters]
    finally:
        path.unlink(missing_ok=True)


def test_resolve_sources_uses_upload_fallback_and_sanitizes_audit(monkeypatch, tmp_path):
    fallback = tmp_path / "saldo.csv"
    fallback.write_text("Artikel\tSaldo\nA100\t1\n", encoding="utf-8")
    monkeypatch.setattr(
        workflow_data,
        "load_catalog",
        lambda: _catalog_for("v_ask_item_summary_stock_automation"),
    )
    monkeypatch.setattr(
        workflow_data,
        "_api_client",
        lambda: FakeExternalClient(error=ExternalDataClientError("sensitive provider detail")),
    )

    resolution = workflow_data.resolve_sources({"saldo": "saldo"}, {"saldo": fallback}, required_keys={"saldo"})

    assert resolution.files["saldo"] == fallback
    assert resolution.audit_entries == [
        {
            "key": "saldo",
            "view": "v_ask_item_summary_stock_automation",
            "status": "upload_fallback",
            "rows": 0,
        }
    ]
    assert "sensitive" not in str(resolution.audit_entries)
    assert "provider detail" not in str(resolution.audit_entries)


def test_resolve_sources_skips_optional_source_when_api_and_fallback_are_missing(monkeypatch):
    monkeypatch.setattr(
        workflow_data,
        "load_catalog",
        lambda: _catalog_for("v_ask_customer_order_details_all", columns=("order_no",)),
    )
    monkeypatch.setattr(
        workflow_data,
        "_api_client",
        lambda: FakeExternalClient(error=ExternalDataClientError("Extern datakälla kunde inte nås.")),
    )

    resolution = workflow_data.resolve_sources({"details": "orders"}, {}, required_keys=set())

    assert resolution.files == {}
    assert resolution.audit_entries == [
        {
            "key": "details",
            "view": "v_ask_customer_order_details_all",
            "status": "optional_skipped",
            "rows": 0,
        }
    ]


def test_resolve_sources_marks_required_source_missing(monkeypatch):
    monkeypatch.setattr(
        workflow_data,
        "load_catalog",
        lambda: _catalog_for("v_ask_order_overview", columns=("shipment",)),
    )
    monkeypatch.setattr(
        workflow_data,
        "_api_client",
        lambda: FakeExternalClient(error=ExternalDataClientError("Extern datakälla kunde inte nås.")),
    )

    with pytest.raises(workflow_data.WorkflowDataError) as excinfo:
        workflow_data.resolve_sources({"overview": "overview"}, {}, required_keys={"overview"})

    assert "Ladda upp Orderöversikt" in str(excinfo.value)
    assert excinfo.value.audit_entries == [
        {
            "key": "overview",
            "view": "v_ask_order_overview",
            "status": "missing",
            "rows": 0,
        }
    ]


def test_workflow_source_payload_sanitizes_paths():
    payload = workflow_data_router._workflow_source_payload(
        workflow_data_router.WorkflowSourceRequest(feature="allocation", flow_id="lyx", source_key="saldo"),
        status_text="error",
        message=r"C:\Users\someone\secret\orders.csv kunde inte hamtas",
    )

    assert payload["message"].startswith("[path]")
    assert "C:\\Users" not in payload["message"]
    assert "orders.csv" not in payload["message"]


def test_workflow_source_endpoint_audits_success(monkeypatch, tmp_path):
    db = FakeAuditDb()
    user = SimpleNamespace(id=7, business_id=3)
    source_path = tmp_path / "saldo.csv"
    source_path.write_text("Artikel\tSaldo\nA100\t1\n", encoding="utf-8")
    entry = workflow_data.WorkflowSourceEntry(
        key="saldo",
        label="Saldo",
        view="v_stock",
        status="api",
        row_count=1,
    )
    monkeypatch.setattr(workflow_data_router, "_assert_workflow_source_allowed", lambda payload, user, db: None)
    monkeypatch.setattr(workflow_data_router, "fetch_source_to_temp", lambda source_key: (source_path, entry))

    response = workflow_data_router.workflow_source(
        workflow_data_router.WorkflowSourceRequest(feature="allocation", flow_id="lyx", source_key="saldo"),
        user=user,
        db=db,
    )

    assert response.headers["x-flow-source-rows"] == "1"
    audit = db.items[0]
    assert db.committed is True
    assert audit.entity_type == "workflow_source"
    assert audit.action == "source_fetch"
    assert audit.business_id == 3
    assert audit.user_id == 7
    assert audit.new_value == {
        "feature": "allocation",
        "flow_id": "lyx",
        "source_key": "saldo",
        "status": "ok",
        "view": "v_stock",
        "row_count": 1,
    }


def test_workflow_source_endpoint_audits_fetch_failure(monkeypatch):
    db = FakeAuditDb()
    user = SimpleNamespace(id=8, business_id=4)
    monkeypatch.setattr(workflow_data_router, "_assert_workflow_source_allowed", lambda payload, user, db: None)

    def fail_fetch(source_key):
        raise workflow_data.WorkflowDataError(
            r"C:\secret\provider\orders.csv kunde inte hamtas",
            status_code=502,
        )

    monkeypatch.setattr(workflow_data_router, "fetch_source_to_temp", fail_fetch)

    with pytest.raises(HTTPException) as excinfo:
        workflow_data_router.workflow_source(
            workflow_data_router.WorkflowSourceRequest(feature="allocation", flow_id="lyx", source_key="saldo"),
            user=user,
            db=db,
        )

    assert excinfo.value.status_code == 502
    audit = db.items[0]
    assert audit.entity_type == "workflow_source"
    assert audit.action == "source_fetch_failed"
    assert audit.business_id == 4
    assert audit.user_id == 8
    assert audit.new_value["status"] == "error"
    assert audit.new_value["status_code"] == 502
    assert audit.new_value["message"].startswith("[path]")
    assert "secret" not in audit.new_value["message"]
    assert "orders.csv" not in audit.new_value["message"]


def test_workflow_source_audit_writes_sanitized_history_event():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        business = Business(code="STIGAMO", name="Stigamo", sort_order=1, is_active=True)
        session.add(business)
        session.flush()
        user = User(
            username="admin",
            role="admin",
            roles=["admin"],
            business_id=business.id,
            is_active=True,
        )
        session.add(user)
        session.commit()

        workflow_data_router._audit_workflow_source(
            session,
            user,
            action="source_fetch",
            payload={
                "feature": "allocation",
                "flow_id": "lyx",
                "source_key": "saldo",
                "status": "ok",
                "row_count": 12,
            },
        )

        audit = session.query(AuditLog).filter_by(entity_type="workflow_source", action="source_fetch").one()
        assert audit.business_id == business.id
        assert audit.user_id == user.id
        assert audit.new_value["source_key"] == "saldo"
        assert audit.new_value["row_count"] == 12
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
