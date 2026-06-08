import csv

import pytest

from app.backend import workflow_data
from app.backend.data_fetch_service import DataCatalog, DataColumn, DataView
from app.backend.external_data_client import ExternalDataClientError


class FakeExternalClient:
    def __init__(self, rows=None, error: Exception | None = None):
        self.rows = rows or []
        self.error = error
        self.views: list[str] = []

    def fetch_data(self, view_id: str):
        self.views.append(view_id)
        if self.error is not None:
            raise self.error
        return list(self.rows)


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
