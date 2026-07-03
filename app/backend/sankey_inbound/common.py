"""Delad grund för Sankey Inbound: konstanter, fel, dataklasser och progress."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from ..data_fetch_service import PACKAGE_ALIAS_VIEW


EXCLUDED_RECEIVE_TYPES = {"23", "45", "46", "47", "63", "81", "91", "100"}
ZEROING_RECEIVE_TYPE = "100"
BUFFER_UPDATE_RECEIVE_TYPE = "91"
INBOUND_LABEL_ROW_ID = "inbound_labels"
INBOUND_PURCHASE_LINE_ROW_ID = "inbound_article_rows"
OUTBOUND_STORE_ORDER_PREFIX = "TO"
OUTBOUND_ECOM_ORDER_PREFIX = "PR"
OUTBOUND_METRICS = (
    {"id": "store_picked_orders", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Plockade orders", "unit": "orders"},
    {"id": "store_picked_rows", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Plockade rader", "unit": "rader"},
    {"id": "store_picked_pcs", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Plockade pcs", "unit": "plockenheter"},
    {"id": "store_full_pallets", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Antal helpallar", "unit": "helpallar"},
    {"id": "store_loaded_pallets", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Utlastade pallar", "unit": "pallar"},
    {"id": "ecom_picked_orders", "branch": "ecom", "branch_label": "E-handel", "prefix": OUTBOUND_ECOM_ORDER_PREFIX, "label": "Plockade orders", "unit": "orders"},
    {"id": "ecom_picked_rows", "branch": "ecom", "branch_label": "E-handel", "prefix": OUTBOUND_ECOM_ORDER_PREFIX, "label": "Plockade rader", "unit": "rader"},
    {"id": "ecom_picked_pcs", "branch": "ecom", "branch_label": "E-handel", "prefix": OUTBOUND_ECOM_ORDER_PREFIX, "label": "Plockade pcs", "unit": "plockenheter"},
    {"id": "ecom_pallet", "branch": "ecom", "branch_label": "E-handel", "prefix": OUTBOUND_ECOM_ORDER_PREFIX, "label": "Antal helpallar", "unit": "helpallar"},
)

SANKEY_SOURCE_VIEWS = {
    "receive": "v_ask_receive_log",
    "trans": "v_ask_trans_log",
    "pick": "v_ask_pick_log_full",
    "dispatch": "dispatch_pallet_log",
    "buffer": "v_ask_article_buffertpallet",
    "kpi": "v_ask_kpi_target",
    "item_alias": PACKAGE_ALIAS_VIEW,
}

REQUIRED_SOURCE_KEYS = {"receive", "trans", "pick"}
DEGRADABLE_SOURCE_KEYS = {"pick"}
CURRENT_STATE_SOURCE_KEYS = {"buffer", "kpi", "item_alias"}
PRODUCTIVITY_SNAPSHOT_REUSE_SOURCE_KEYS = {"receive", "trans"}
PERIOD_ONLY_SOURCE_KEYS = {"dispatch"}
CLIENT_FILTER_PREBUILD_MAX_SOURCE_ROWS = 75_000
CLIENT_FILTER_PREBUILD_MAX_VIEWS = 512

# Naturliga steg i SSE-progressloggen: en hämtning per källa + ett bygg-steg.
ProgressCallback = Callable[[dict[str, Any]], None]


def _emit_progress(callback: ProgressCallback | None, **event: Any) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception:
        # Progressrapportering får aldrig fälla själva hämtningen.
        pass
SOURCE_LABELS = {
    "receive": "Varumottagningslogg",
    "trans": "Translogg",
    "pick": "Plocklogg Full",
    "dispatch": "Dispatchpallslogg",
    "buffer": "Buffertpall",
    "item_alias": "Item Alias",
    "kpi": "KPI-mål",
}

PROCESS_LABELS = {
    "RECEIVING": "Receiving",
    "DECANTING": "AutoStore / Decanting",
    "HBW": "HBW",
    "MANUAL_BUFFER": "Manual Buffer",
    "PUTAWAY_PICK": "Plockplats",
    "BUFFER_UPDATE": "Buffer Update",
}

PROCESS_DEFAULT_METRIC = {
    "RECEIVING": "rows",
    "DECANTING": "packages",
    "HBW": "pallets",
    "MANUAL_BUFFER": "pallets",
    "PUTAWAY_PICK": "pallets",
    "BUFFER_UPDATE": "pallets",
}

PROCESS_POINT_ALIASES = {
    "AUTOSTORE": "DECANTING",
    "AUTOSTORE / DECANTING": "DECANTING",
    "MANUAL BUFFER": "MANUAL_BUFFER",
    "PUTAWAY PICK": "PUTAWAY_PICK",
    "PICK_LOCATION": "PUTAWAY_PICK",
    "PLOCKPLATS": "PUTAWAY_PICK",
    "BUFFER UPDATE": "BUFFER_UPDATE",
}

OPEN_STATUS_LABELS = {
    "consumed": "Förverkad / plockad",
    "open_autostore": "Kvar i AutoStore",
    "open_hbw": "Kvar i HBW",
    "open_buffer": "Kvar i buffert",
    "open_pick_location": "Kvar på plockplats",
    "open_not_putaway": "Ej inlagrad / okänd",
}


class SankeyInboundError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502, source_status: list[dict] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.source_status = list(source_status or [])


@dataclass
class ProcessVisit:
    key: str
    label: str
    points: float
    source: str


@dataclass
class TraceBranch:
    id: str
    origin_id: str
    company: str
    warehouse: str
    item: str
    current_pall: str
    qty: float
    revenue: float
    label_fraction: float
    label_revenue: float = 0.0
    purchase_line_revenue: float = 0.0
    origin_pall: str = ""
    source_row_id: str = ""
    purchase_number: str = ""
    purchase_line: str = ""
    received_date: date | None = None
    trace_steps: list[str] = field(default_factory=list)
    processes: list[ProcessVisit] = field(default_factory=list)
    status: str = "open_not_putaway"
    location: str = ""
    consumed: bool = False
    active: bool = True
    confidence: str = "high"


@dataclass
class PickQueueEntry:
    branch_id: str | None
    qty: float

