"""ASK-vy-diagnostik (superuser). Live-mätverktyg i Arkivstatus.

Probe:ar samma vyer × tenants mot 1–3 bas-URL:er (publik gateway vs interna
kluster-adresser) och rapporterar HTTP-status, radantal och svarstid per anrop
så hängningar och trasiga vyer/tenants/URL:er kan pekas ut. Read-only; anropar
bara ASK. Ligger i egen modul för att hålla routers/data_fetch.py under radtaket.
"""
from __future__ import annotations

from datetime import date, timedelta
import time

from fastapi import APIRouter, Depends, HTTPException, status
import requests

from ..config import settings
from ..data_fetch_service import (
    ARCHIVE_TO_LIVE,
    LIVE_ARCHIVE_PAIRS,
    load_catalog,
    _date_period_payload,
    _period_values_for_column,
    _preferred_date_column,
)
from ..deps import require_super_user
from ..external_data_client import (
    ExternalDataClient,
    ExternalDataClientError,
    data_source_base_url_for_tenant,
)
from ..models import User


router = APIRouter(prefix="/api/query-data", tags=["query-data-diagnostics"])


# Fast tenant-lista i UI (kryssrutor). Motsvarar de tenants referens-ögonblicks-
# bilden (~/Downloads/ask-vy-status.html) täckte.
_DIAG_TENANTS: tuple[str, ...] = (
    "aegir", "atria", "bragi", "everfresh", "frey", "idun", "itworks",
    "loki", "mestergruppen", "mi17", "njord", "tpnas", "trademax",
)

# Extra "övrigt"-vyer utöver arkiv/live-paren, som i referensen.
_DIAG_EXTRA_VIEWS: tuple[str, ...] = ("item_alias", "sort_conveyor_log")

_DIAG_URL_ENV = {
    1: "DATA_SOURCE_API_BASE_URL",
    2: "DATA_SOURCE_API_BASE_URL2",
    3: "DATA_SOURCE_API_BASE_URL3",
}

_DIAG_MAX_ROWS = 50  # slice per extrakt – vi vill bara se att vyn svarar, inte hela mängden


def _diag_base_url(url_index: int) -> str:
    return str(getattr(settings, _DIAG_URL_ENV.get(url_index, ""), "") or "").strip()


def _diag_view_ids() -> list[str]:
    """Diagnostikens vy-omfång: arkiv (dblog_*) + live (v_ask_* m.fl.) + övrigt."""
    seen: set[str] = set()
    ordered: list[str] = []
    for view_id in (*ARCHIVE_TO_LIVE.keys(), *LIVE_ARCHIVE_PAIRS.keys(), *_DIAG_EXTRA_VIEWS):
        if view_id not in seen:
            seen.add(view_id)
            ordered.append(view_id)
    return ordered


def _diag_view_window(view_id: str) -> tuple[str, int]:
    """Välj provdags-offset (dagar bakåt från idag). Arkiv- och live-vyer får OLIKA dag:

    - live (v_ask_*): en dag inom retention → today-1 (finns i live-vyn).
    - arkiv (dblog_*): en dag äldre än cutoff → today - retention - 1 (finns i arkivet).
    - övrigt: today-1.
    Returnerar (kind, offset_dagar).
    """
    if view_id in LIVE_ARCHIVE_PAIRS:
        return "live", 1
    if view_id in ARCHIVE_TO_LIVE:
        return "archive", int(ARCHIVE_TO_LIVE[view_id][0]) + 1
    return "other", 1


def _diag_view_spec(view_id: str, catalog, today: date) -> dict | None:
    """Bygg vyns provspec (datumkolumn + between-värden) eller None om vyn saknas i katalogen."""
    try:
        view = catalog.view(view_id)
    except Exception:
        return None
    kind, offset = _diag_view_window(view_id)
    probe_date = today - timedelta(days=offset)
    column = _preferred_date_column(view)
    period = _date_period_payload("diag", probe_date, probe_date)
    date_values = _period_values_for_column(period, column) if column is not None else None
    retention = None
    if kind == "live":
        retention = int(LIVE_ARCHIVE_PAIRS[view_id][0])
    elif kind == "archive":
        retention = int(ARCHIVE_TO_LIVE[view_id][0])
    return {
        "id": view_id,
        "kind": kind,
        "retention_days": retention,
        "date_column": column.id if column is not None else None,
        "date": probe_date.isoformat(),
        "date_values": date_values,
    }


@router.get("/archive-cache/diagnostics/config")
def diagnostics_config(_: User = Depends(require_super_user)) -> dict:
    """Allt frontend behöver för mätverktyget: URL-flikar, tenants och vy-omfång."""
    today = date.today()
    catalog = load_catalog()
    views = [
        spec
        for view_id in _diag_view_ids()
        if (spec := _diag_view_spec(view_id, catalog, today)) is not None
    ]
    urls = [
        {
            "index": index,
            "env_name": _DIAG_URL_ENV[index],
            "pattern": _diag_base_url(index),
            "configured": bool(_diag_base_url(index)),
        }
        for index in (1, 2, 3)
    ]
    return {
        "today": today.isoformat(),
        "urls": urls,
        "tenants": list(_DIAG_TENANTS),
        "views": views,
    }


def _diag_api_client(tenant: str, url_index: int) -> ExternalDataClient:
    """Som _api_client_or_503 men med vald bas-URL (index 1/2/3)."""
    base_url_raw = _diag_base_url(url_index)
    if not base_url_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{_DIAG_URL_ENV.get(url_index, 'URL')} är inte konfigurerad.",
        )
    try:
        base_url = data_source_base_url_for_tenant(base_url_raw, tenant)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
        response_row_cap=0,  # ingen auto-split – vi vill ha ett enda litet extrakt
    )


@router.get("/archive-cache/diagnostics/probe")
def diagnostics_probe(
    url: int,
    tenant: str,
    view: str,
    timeout: float | None = None,
    _: User = Depends(require_super_user),
) -> dict:
    """Ett litet extrakt (1 dag) för en vy × tenant × bas-URL. Klassar utfallet.

    Gör POST:en direkt via klientens session så exakt HTTP-status, timeout och
    anslutningsfel kan skiljas åt (klientens fetch_data slår ihop dem till ett
    generiskt fel). Ett anrop per cell → frontend streamar och ser var det hänger.
    """
    today = date.today()
    catalog = load_catalog()
    spec = _diag_view_spec(view, catalog, today)
    result: dict = {
        "url": url,
        "tenant": tenant,
        "view": view,
        "kind": spec["kind"] if spec else None,
        "date": spec["date"] if spec else None,
        "date_column": spec["date_column"] if spec else None,
        "ok": False,
        "http_status": None,
        "row_count": None,
        "elapsed_ms": None,
        "error": None,
    }
    if spec is None:
        result["error"] = "Vyn saknas i katalogen."
        return result

    client = _diag_api_client(tenant, url)
    call_timeout = float(timeout) if timeout and timeout > 0 else float(settings.DATA_SOURCE_TIMEOUT_SECONDS)

    filters: list[dict] = []
    if spec["date_column"] and spec["date_values"]:
        filters.append(ExternalDataClient.between(spec["date_column"], *spec["date_values"]))

    payload = {"userFilter": filters or None, "identifiers": None}
    started = time.perf_counter()
    try:
        path = client._view_data_path(view)
        response = client.session.post(
            client._url(path), json=payload, timeout=call_timeout, verify=client.verify
        )
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        result["http_status"] = response.status_code
        if response.ok:
            try:
                body = response.json()
                rows = body.get("rows") if isinstance(body, dict) else None
                result["row_count"] = len(rows[:_DIAG_MAX_ROWS]) if isinstance(rows, list) else 0
                result["ok"] = True
            except ValueError:
                result["error"] = "Ogiltig JSON i svaret."
        else:
            result["error"] = f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        result["error"] = f"Timeout efter {call_timeout:g} s"
    except requests.exceptions.ConnectionError as exc:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        result["error"] = f"Anslutningsfel: {type(exc).__name__}"
    except ExternalDataClientError as exc:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        result["error"] = str(exc)
    except requests.RequestException as exc:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result
