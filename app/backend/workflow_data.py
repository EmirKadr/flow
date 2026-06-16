from __future__ import annotations

import csv
from dataclasses import dataclass, field
import tempfile
from pathlib import Path
from typing import Any

from .config import settings
from .data_fetch_service import DataFetchConfigError, DataFetchPlanError, DataView, load_catalog
from .external_data_client import ExternalDataClient, ExternalDataClientError, data_source_base_url_for_tenant


class WorkflowDataError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502, entries: list[Any] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.entries = list(entries or [])

    @property
    def audit_entries(self) -> list[dict[str, Any]]:
        return [
            {
                "key": str(getattr(entry, "key", "")),
                "view": str(getattr(entry, "view", "")),
                "status": str(getattr(entry, "status", "")),
                "rows": int(getattr(entry, "row_count", 0) or 0),
            }
            for entry in self.entries
        ]


@dataclass(frozen=True)
class WorkflowSourceSpec:
    key: str
    label: str
    view: str
    required_columns: tuple[str, ...] = ()
    extra_headers: tuple[tuple[str, str], ...] = ()


@dataclass
class WorkflowSourceEntry:
    key: str
    label: str
    view: str
    status: str
    row_count: int = 0
    message: str = ""


@dataclass
class WorkflowResolution:
    files: dict[str, Path]
    temp_paths: list[Path] = field(default_factory=list)
    entries: list[WorkflowSourceEntry] = field(default_factory=list)

    @property
    def log_lines(self) -> list[str]:
        lines = []
        for entry in self.entries:
            if entry.status == "api":
                lines.append(f"{entry.label} hämtades från API ({entry.row_count} rader).")
            elif entry.status in {"upload_fallback", "local_ref_fallback"}:
                suffix = f" {entry.message}" if entry.message else ""
                lines.append(f"{entry.label}: API-hämtning misslyckades, använder fallback.{suffix}")
            elif entry.status == "optional_skipped":
                lines.append(f"{entry.label}: API-hämtning hoppades över (valfri källa saknas).")
            elif entry.status == "missing":
                lines.append(f"{entry.label}: extern datakälla saknas och ingen fallback finns.")
        return lines

    @property
    def audit_entries(self) -> list[dict[str, Any]]:
        return [
            {
                "key": entry.key,
                "view": entry.view,
                "status": entry.status,
                "rows": int(entry.row_count or 0),
            }
            for entry in self.entries
        ]


SOURCE_SPECS: dict[str, WorkflowSourceSpec] = {
    "buffer": WorkflowSourceSpec("buffer", "Buffertpall", "v_ask_article_buffertpallet"),
    "saldo": WorkflowSourceSpec(
        "saldo",
        "Saldo Inkl. Automation",
        "v_ask_item_summary_stock_automation",
        required_columns=("robot_ind",),
        extra_headers=(
            ("robot_ind", "Robot"),
            ("automation_pick_qty", "Saldo autoplock"),
            ("pick_qty", "Plocksaldo"),
            ("pick_loc", "Plockplats"),
        ),
    ),
    "orders": WorkflowSourceSpec("orders", "Detalj Kundorder (Alla)", "v_ask_customer_order_details_all"),
    "overview": WorkflowSourceSpec("overview", "Orderöversikt", "v_ask_order_overview"),
    "dispatch": WorkflowSourceSpec("dispatch", "Dispatchpallar", "v_ask_dispatch_pallet"),
    "custom_adr": WorkflowSourceSpec("custom_adr", "Alternativ Leveransadress", "v_ask_custom_adr"),
    "not_putaway": WorkflowSourceSpec("not_putaway", "Ej Inlagrade Artiklar", "v_ask_booking_putaway"),
    "custom": WorkflowSourceSpec("custom", "Kund", "custom"),
    "item": WorkflowSourceSpec("item", "Artiklar (Item)", "item"),
    "item_alias": WorkflowSourceSpec("item_alias", "Item Alias", "item_alias"),
    "dimension": WorkflowSourceSpec("dimension", "Dimensioner", "dimension"),
    "pallet_type": WorkflowSourceSpec("pallet_type", "Palltyp", "pallet_type"),
    "item_option": WorkflowSourceSpec(
        "item_option",
        "Item Option",
        "item_option",
        required_columns=(
            "not_stackable",
            "whole_pallet_near_miss_percent",
        ),
        extra_headers=(
            ("not_stackable", "Ej staplingsbar"),
            ("whole_pallet_near_miss_percent", "Helpalls avvikelse %"),
        ),
    ),
    "trans_agency": WorkflowSourceSpec("trans_agency", "Transportör", "trans_agency"),
    "location": WorkflowSourceSpec("location", "Lagerplatser", "location"),
    "item_security_info": WorkflowSourceSpec("item_security_info", "Artikel Säkerhetsinformation", "item_security_info"),
    "pick": WorkflowSourceSpec("pick", "Plocklogg Full", "v_ask_pick_log_full"),
    "trans": WorkflowSourceSpec("trans", "Translogg", "v_ask_trans_log"),
    "pallet": WorkflowSourceSpec("pallet", "Pallastningslogg", "v_ask_palletloading_log"),
    "receive": WorkflowSourceSpec("receive", "Varumottagningslogg", "v_ask_receive_log"),
    "order_log": WorkflowSourceSpec("order_log", "Orderlogg", "v_ask_order_log"),
    "sort": WorkflowSourceSpec("sort", "Sorteringslogg", "sort_conveyor_log"),
    "base_pallet": WorkflowSourceSpec("base_pallet", "Base pallet-logg", "v_ask_article_buffertpallet"),
    "kpi": WorkflowSourceSpec("kpi", "KPI-Mål", "v_ask_kpi_target"),
}


FORECAST_FLOW_API_SOURCES: dict[str, str] = {
    "orders": "orders",
    "overview": "overview",
    "buffer": "buffer",
    "custom": "custom",
    "item": "item",
    "item_alias": "item_alias",
    "dimension": "dimension",
    "pallet_type": "pallet_type",
    "item_option": "item_option",
    "trans_agency": "trans_agency",
}


ALLOCATION_FLOW_API_SOURCES: dict[str, dict[str, str]] = {
    "allocate": {
        "orders": "orders",
        "buffer": "buffer",
        "saldo": "saldo",
        "items": "item_option",
        "not_putaway": "not_putaway",
    },
    "prognos-report": {"saldo": "saldo", "buffer": "buffer"},
    "hib-koppling": {"details": "orders", "overview": "overview"},
    "overview-check": {"overview": "overview", "details": "orders"},
    "dispatch-check": {"overview": "overview", "dispatch": "dispatch", "details": "orders"},
    "goods-declaration": {
        "orders": "orders",
        "overview": "overview",
        "custom_adr": "custom_adr",
        "item_security_info": "item_security_info",
    },
    "ordersaldo": {"orders": "orders", "saldo": "saldo"},
    "lyx": {"saldo": "saldo"},
    "pafyllnadsprio": {"orders": "orders", "saldo": "saldo", "overview": "overview"},
    "forecast": FORECAST_FLOW_API_SOURCES,
    "ytgenerering": {**FORECAST_FLOW_API_SOURCES, "location": "location"},
}


PRODUCTIVITY_API_SOURCES: dict[str, str] = {
    "pick": "pick",
    "trans": "trans",
    "pallet": "pallet",
    "receive": "receive",
    "order_log": "order_log",
    "sort": "sort",
    "base_pallet": "base_pallet",
    "kpi": "kpi",
}


def allocation_api_source_map(flow_id: str) -> dict[str, str]:
    return dict(ALLOCATION_FLOW_API_SOURCES.get(str(flow_id or ""), {}))


def productivity_api_source_map() -> dict[str, str]:
    return dict(PRODUCTIVITY_API_SOURCES)


def source_spec(source_key: str) -> WorkflowSourceSpec:
    key = str(source_key or "").strip()
    if key == "details":
        key = "orders"
    try:
        return SOURCE_SPECS[key]
    except KeyError as exc:
        raise WorkflowDataError(f"Okänd API-källa: {source_key}", status_code=404) from exc


def source_public_metadata(source_key: str) -> dict[str, Any]:
    spec = source_spec(source_key)
    columns: list[dict[str, str]] = []
    try:
        view = load_catalog().view(spec.view)
        seen: set[str] = set()
        for column in view.columns:
            column_id = str(column.id or "").strip()
            if not column_id or column_id in seen:
                continue
            seen.add(column_id)
            columns.append({"id": column_id, "label": _column_label(column), "type": "String"})
        for column_id, label in spec.extra_headers:
            if column_id in seen:
                continue
            seen.add(column_id)
            columns.append({"id": column_id, "label": label, "type": "String"})
    except (DataFetchConfigError, DataFetchPlanError):
        columns = []
    return {
        "key": spec.key,
        "label": spec.label,
        "view": spec.view,
        "columns": columns,
    }


def api_config_missing() -> list[str]:
    required = (
        "DATA_SOURCE_API_BASE_URL",
        "DATA_SOURCE_API_KEY",
        "DATA_SOURCE_API_CLIENT",
        "DATA_SOURCE_API_KEY_HEADER",
        "DATA_SOURCE_API_CLIENT_HEADER",
        "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE",
    )
    return [name for name in required if not str(getattr(settings, name, "")).strip()]


def workflow_api_configured() -> bool:
    if api_config_missing():
        return False
    try:
        load_catalog()
    except DataFetchConfigError:
        return False
    return True


def sources_available(source_keys: list[str] | tuple[str, ...]) -> bool:
    if not workflow_api_configured():
        return False
    try:
        catalog = load_catalog()
        for key in source_keys:
            catalog.view(source_spec(key).view)
    except (DataFetchConfigError, DataFetchPlanError, WorkflowDataError):
        return False
    return True


def _api_client(tenant: str | None = None) -> ExternalDataClient:
    missing = api_config_missing()
    if missing:
        raise WorkflowDataError(
            f"Saknar {', '.join(missing)} i servermiljön.",
            status_code=503,
        )
    try:
        base_url = data_source_base_url_for_tenant(settings.DATA_SOURCE_API_BASE_URL, tenant)
    except ValueError as exc:
        raise WorkflowDataError(str(exc), status_code=503) from exc
    return ExternalDataClient(
        base_url=base_url,
        api_key=settings.DATA_SOURCE_API_KEY.strip() or None,
        api_client=settings.DATA_SOURCE_API_CLIENT.strip() or None,
        api_key_header=settings.DATA_SOURCE_API_KEY_HEADER.strip() or None,
        api_client_header=settings.DATA_SOURCE_API_CLIENT_HEADER.strip() or None,
        view_data_path_template=settings.DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE.strip(),
        timeout=settings.DATA_SOURCE_TIMEOUT_SECONDS,
        verify_ssl=settings.DATA_SOURCE_VERIFY_SSL,
        ca_bundle=settings.DATA_SOURCE_CA_BUNDLE.strip() or None,
        response_row_cap=int(getattr(settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 0) or 0),
    )


def _column_label(column: Any) -> str:
    label = str(getattr(column, "label_sv", "") or getattr(column, "label_en", "") or getattr(column, "id", "")).strip()
    return label or str(getattr(column, "id", "")).strip()


def _row_value(row: dict[str, Any], column_id: str) -> Any:
    if column_id in row:
        return row.get(column_id)
    lower = {str(key).lower(): key for key in row}
    actual = lower.get(str(column_id).lower())
    return row.get(actual) if actual is not None else ""

def _assert_required_columns(spec: WorkflowSourceSpec, rows: list[dict[str, Any]], view: DataView) -> None:
    catalog_columns = {str(column.id).lower() for column in view.columns}
    row_columns = {str(key).lower() for row in rows for key in row.keys()}
    missing = [
        column_id
        for column_id in spec.required_columns
        if (str(column_id).lower() not in row_columns if rows else str(column_id).lower() not in catalog_columns)
    ]
    if missing:
        raise WorkflowDataError(
            f"API-svaret för {spec.label} saknar kolumnen {', '.join(missing)}.",
            status_code=502,
        )

def _materialize_csv(spec: WorkflowSourceSpec, rows: list[dict[str, Any]], view: DataView) -> Path:
    _assert_required_columns(spec, rows, view)
    columns: list[tuple[str, str]] = [(column.id, _column_label(column)) for column in view.columns]
    existing = {(source_id, header) for source_id, header in columns}
    for source_id, header in spec.extra_headers:
        if (source_id, header) not in existing:
            columns.append((source_id, header))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{spec.key}.csv", mode="w", newline="", encoding="utf-8-sig")
    try:
        writer = csv.writer(tmp, delimiter="\t")
        writer.writerow([header for _source_id, header in columns])
        for row in rows:
            writer.writerow([_row_value(row, source_id) for source_id, _header in columns])
    finally:
        tmp.close()
    return Path(tmp.name)


def fetch_source_to_temp(
    source_key: str,
    filters: list[dict[str, Any]] | None = None,
    *,
    tenant: str | None = None,
) -> tuple[Path, WorkflowSourceEntry]:
    spec = source_spec(source_key)
    try:
        catalog = load_catalog()
        view = catalog.view(spec.view)
    except DataFetchConfigError as exc:
        raise WorkflowDataError(str(exc), status_code=503) from exc
    except DataFetchPlanError as exc:
        raise WorkflowDataError(str(exc), status_code=503) from exc
    try:
        client = _api_client(tenant=tenant) if tenant else _api_client()
        rows = client.fetch_all(spec.view, filters=filters)
    except ExternalDataClientError as exc:
        raise WorkflowDataError(str(exc), status_code=502) from exc
    path = _materialize_csv(spec, rows, view)
    return path, WorkflowSourceEntry(
        key=spec.key,
        label=spec.label,
        view=spec.view,
        status="api",
        row_count=len(rows),
    )


def _fallback_status(has_file: bool, *, local_ref: bool = False) -> str | None:
    if not has_file:
        return None
    return "local_ref_fallback" if local_ref else "upload_fallback"


def resolve_sources(
    source_map: dict[str, str],
    files: dict[str, Path],
    *,
    required_keys: set[str],
    local_ref_keys: set[str] | None = None,
    tenant: str | None = None,
) -> WorkflowResolution:
    resolved = dict(files)
    temp_paths: list[Path] = []
    entries: list[WorkflowSourceEntry] = []
    local_refs = local_ref_keys or set()
    for file_key, source_key in source_map.items():
        spec = source_spec(source_key)
        required = file_key in required_keys
        try:
            if tenant:
                path, entry = fetch_source_to_temp(source_key, tenant=tenant)
            else:
                path, entry = fetch_source_to_temp(source_key)
            resolved[file_key] = path
            temp_paths.append(path)
            entries.append(WorkflowSourceEntry(**{**entry.__dict__, "key": file_key}))
            continue
        except WorkflowDataError as exc:
            fallback = _fallback_status(file_key in files, local_ref=file_key in local_refs)
            if fallback:
                entries.append(
                    WorkflowSourceEntry(
                        key=file_key,
                        label=spec.label,
                        view=spec.view,
                        status=fallback,
                        message=str(exc),
                    )
                )
                continue
            if not required:
                entries.append(
                    WorkflowSourceEntry(
                        key=file_key,
                        label=spec.label,
                        view=spec.view,
                        status="optional_skipped",
                        message=str(exc),
                    )
                )
                continue
            entries.append(
                WorkflowSourceEntry(
                    key=file_key,
                    label=spec.label,
                    view=spec.view,
                    status="missing",
                    message=str(exc),
                )
            )
            for temp_path in temp_paths:
                temp_path.unlink(missing_ok=True)
            raise WorkflowDataError(
                f"{exc} Ladda upp {spec.label} och kör igen.",
                status_code=exc.status_code,
                entries=entries,
            ) from exc
    return WorkflowResolution(files=resolved, temp_paths=temp_paths, entries=entries)
