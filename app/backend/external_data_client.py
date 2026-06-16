"""Fetch-only client for the configured external data API.

Provider-specific endpoint paths, header names and credentials are intentionally
passed from environment-backed settings so the repository does not document the
private integration contract.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta
import logging
import re
from typing import Any, Optional, Union
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from .observability import add_span_attributes, start_span


logger = logging.getLogger(__name__)


class ExternalDataClientError(Exception):
    """Raised when the external data request or response cannot be handled."""


TENANT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$|^[a-z0-9]$")


def clean_data_source_tenant(value: object) -> str | None:
    tenant = str(value or "").strip().lower()
    if not tenant:
        return None
    if not TENANT_PATTERN.fullmatch(tenant):
        raise ValueError("Tenant far bara innehalla a-z, 0-9 och bindestreck")
    return tenant


def data_source_base_url_for_tenant(base_url: str, tenant: object) -> str:
    configured = str(base_url or "").strip()
    cleaned_tenant = clean_data_source_tenant(tenant)
    if not configured or not cleaned_tenant:
        return configured
    if "{tenant}" in configured:
        return configured.format(tenant=cleaned_tenant)

    parsed = urlsplit(configured)
    hostname = parsed.hostname or ""
    if not hostname:
        return configured
    labels = hostname.split(".")
    first_label = labels[0] if labels else ""
    if "-" not in first_label:
        return configured

    prefix = first_label.rsplit("-", 1)[0]
    labels[0] = f"{prefix}-{cleaned_tenant}"
    netloc = ".".join(labels)
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


class ExternalDataClient:
    """Fetch-only client for the configured external data endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        api_client: Optional[str] = None,
        api_key_header: Optional[str] = None,
        api_client_header: Optional[str] = None,
        view_data_path_template: str = "",
        timeout: float = 30,
        verify_ssl: bool = True,
        ca_bundle: Optional[str] = None,
        response_row_cap: int = 0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.verify = ca_bundle.strip() if ca_bundle else verify_ssl
        self.view_data_path_template = view_data_path_template.strip()
        self.response_row_cap = max(0, int(response_row_cap or 0))
        self.session = session or requests.Session()

        if api_key_header and api_key:
            self.session.headers[api_key_header] = api_key
        if api_client_header and api_client:
            self.session.headers[api_client_header] = api_client

    def fetch_data(
        self,
        view: str,
        filters: Optional[Sequence[Mapping[str, Any]]] = None,
        identifiers: Optional[Union[Sequence[Mapping[str, Any]], Mapping[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        with start_span(
            "external.data_source.fetch",
            {
                "external.provider": "data_source",
                "external.filter_count": len(filters or []),
                "external.has_identifiers": identifiers is not None,
            },
        ):
            payload = {
                "userFilter": list(filters) if filters else None,
                "identifiers": self._identifiers_to_payload(identifiers),
            }
            path = self._view_data_path(view)

            try:
                response = self.session.post(
                    self._url(path),
                    json=payload,
                    timeout=self.timeout,
                    verify=self.verify,
                )
                add_span_attributes({"external.http_status_code": response.status_code})
            except requests.RequestException as exc:
                add_span_attributes({"external.error_type": type(exc).__name__})
                raise ExternalDataClientError(
                    "Extern datakälla kunde inte nås. Kontrollera API-URL, nätåtkomst och datakällans status."
                ) from exc
            rows = self._rows(response)
            add_span_attributes({"external.row_count": len(rows)})
            return rows

    def fetch_all(
        self,
        view: str,
        filters: Optional[Sequence[Mapping[str, Any]]] = None,
        identifiers: Optional[Union[Sequence[Mapping[str, Any]], Mapping[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """Hämta hela resultatmängden, uppdelat i datumfönster när API:t kapar svaret.

        Detta är den delade vägen för alla flöden (Hämta data, Inställningar-uträkning,
        Produktivitet, Bearbeta) så ingen tyst trunkeras vid datakällans radtak.
        """
        return fetch_all_rows(
            self.fetch_data,
            view,
            list(filters) if filters else None,
            identifiers,
            response_row_cap=self.response_row_cap,
        )

    @staticmethod
    def eq(field: str, value: Any) -> dict[str, Any]:
        return {"id": field, "value": value, "operator": "EQ"}

    @staticmethod
    def ne(field: str, value: Any) -> dict[str, Any]:
        return {"id": field, "value": value, "operator": "NE"}

    @staticmethod
    def gt(field: str, value: Any) -> dict[str, Any]:
        return {"id": field, "value": value, "operator": "GT"}

    @staticmethod
    def gte(field: str, value: Any) -> dict[str, Any]:
        return {"id": field, "value": value, "operator": "GTE"}

    @staticmethod
    def lt(field: str, value: Any) -> dict[str, Any]:
        return {"id": field, "value": value, "operator": "LT"}

    @staticmethod
    def lte(field: str, value: Any) -> dict[str, Any]:
        return {"id": field, "value": value, "operator": "LTE"}

    @staticmethod
    def terms(field: str, *values: Any) -> dict[str, Any]:
        return {"id": field, "value": list(values), "operator": "Terms"}

    @staticmethod
    def between(field: str, left: Any, right: Any) -> dict[str, Any]:
        return {"id": field, "value": [left, right], "operator": "Between"}

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path)

    def _view_data_path(self, view: str) -> str:
        if not self.view_data_path_template:
            raise ExternalDataClientError("Extern datakälla saknar sökvägsmall.")
        try:
            return self.view_data_path_template.format(view=view)
        except (KeyError, IndexError, ValueError) as exc:
            raise ExternalDataClientError(
                "Extern datakällas sökvägsmall kunde inte byggas. Kontrollera DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE."
            ) from exc

    @staticmethod
    def _identifiers_to_payload(
        identifiers: Optional[Union[Sequence[Mapping[str, Any]], Mapping[str, Any]]],
    ) -> Optional[list[list[dict[str, Any]]]]:
        if identifiers is None:
            return None
        if isinstance(identifiers, Mapping):
            identifiers = [identifiers]
        return [
            [{"id": key, "value": value} for key, value in item.items()]
            for item in identifiers
        ]

    @staticmethod
    def _rows(response: requests.Response) -> list[dict[str, Any]]:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None) or response.status_code
            raise ExternalDataClientError(f"Extern datakälla svarade med HTTP {status_code}.") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise ExternalDataClientError("Extern datakälla returnerade ogiltig JSON.") from exc

        if not isinstance(body, dict):
            raise ExternalDataClientError("Extern datakälla returnerade inte ett JSON-objekt.")

        rows = body.get("rows")
        if rows is None:
            return []
        if not isinstance(rows, list):
            raise ExternalDataClientError("Extern datakälla returnerade inte en radlista.")
        return rows


FetchFn = Callable[..., list[dict[str, Any]]]


def _parse_date_bound(value: Any) -> date | None:
    """Tolka ett Between-gränsvärde (YYYYMMDD-int, ISO-datum eller ISO-datetime) som datum."""
    if isinstance(value, bool) or value is None:
        return None
    text = str(int(value)) if isinstance(value, (int, float)) else str(value).strip()
    if not text:
        return None
    digits = text.split("T", 1)[0].replace("-", "")
    if len(digits) >= 8 and digits[:8].isdigit():
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        except ValueError:
            return None
    return None


def _date_bound_kind(value: Any) -> str:
    """Avgör hur ett gränsvärde ska återskapas efter uppdelning."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "int"
    text = str(value or "")
    if "T" in text:
        return "iso_datetime"
    if "-" in text:
        return "iso_date"
    return "int_str"


def _format_date_bound(day: date, kind: str, *, is_upper: bool) -> object:
    if kind == "int":
        return int(day.strftime("%Y%m%d"))
    if kind == "int_str":
        return day.strftime("%Y%m%d")
    if kind == "iso_datetime":
        return f"{day.isoformat()}T{'23:59:59' if is_upper else '00:00:00'}"
    return day.isoformat()


def _find_date_between_filter(filters: Sequence[Mapping[str, Any]]) -> int | None:
    """Index för första Between-filtret vars båda gränser är datum, annars None."""
    for index, item in enumerate(filters):
        if str(item.get("operator") or "") != "Between":
            continue
        value = item.get("value")
        if not isinstance(value, list) or len(value) != 2:
            continue
        if _parse_date_bound(value[0]) and _parse_date_bound(value[1]):
            return index
    return None


def _fetch_window(
    fetch_fn: FetchFn,
    view: str,
    filters: list[dict[str, Any]],
    identifiers: Any,
    date_index: int,
    start: date,
    end: date,
    kind: str,
    cap: int,
) -> list[dict[str, Any]]:
    """Hämta ett datumfönster och dela upp rekursivt om svaret är avhugget."""
    windowed = [dict(item) for item in filters]
    windowed[date_index] = {
        **windowed[date_index],
        "value": [
            _format_date_bound(start, kind, is_upper=False),
            _format_date_bound(end, kind, is_upper=True),
        ],
    }
    rows = fetch_fn(view, filters=windowed or None, identifiers=identifiers)
    if len(rows) < cap:
        return rows
    if start >= end:
        raise ExternalDataClientError(
            f"Ett enskilt dygn ({start.isoformat()}) når datakällans tak på {cap} rader och "
            "kan inte delas upp mer på datum. Resultatet skulle bli ofullständigt."
        )
    half = (end - start).days // 2
    mid = start + timedelta(days=half)
    left = _fetch_window(fetch_fn, view, filters, identifiers, date_index, start, mid, kind, cap)
    right = _fetch_window(fetch_fn, view, filters, identifiers, date_index, mid + timedelta(days=1), end, kind, cap)
    return left + right


def fetch_all_rows(
    fetch_fn: FetchFn,
    view: str,
    filters: Optional[Sequence[Mapping[str, Any]]],
    identifiers: Any = None,
    *,
    response_row_cap: int = 0,
) -> list[dict[str, Any]]:
    """Hämta alla rader via ``fetch_fn``, uppdelat i datumfönster när svaret når radtaket.

    ``response_row_cap`` <= 0 stänger av uppdelningen (en enda hämtning). När taket nås
    men inget Between-datumfilter finns att dela på returneras de kapade raderna och en
    varning loggas, eftersom resultatet då kan vara ofullständigt.
    """
    filter_list = [dict(item) for item in (filters or [])]
    rows = fetch_fn(view, filters=filter_list or None, identifiers=identifiers)
    cap = max(0, int(response_row_cap or 0))
    if not cap or len(rows) < cap:
        return rows

    date_index = _find_date_between_filter(filter_list)
    if date_index is None:
        logger.warning(
            "Data fetch hit response cap (%s rows) for view=%s without a date filter to split on.",
            cap,
            view,
        )
        return rows

    bounds = filter_list[date_index].get("value")
    start = _parse_date_bound(bounds[0])
    end = _parse_date_bound(bounds[1])
    if start is None or end is None or start > end:
        return rows
    kind = _date_bound_kind(bounds[0])
    return _fetch_window(fetch_fn, view, filter_list, identifiers, date_index, start, end, kind, cap)


__all__ = [
    "ExternalDataClient",
    "ExternalDataClientError",
    "clean_data_source_tenant",
    "data_source_base_url_for_tenant",
    "fetch_all_rows",
]
