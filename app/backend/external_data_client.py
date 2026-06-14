"""Fetch-only client for the configured external data API.

Provider-specific endpoint paths, header names and credentials are intentionally
passed from environment-backed settings so the repository does not document the
private integration contract.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Optional, Union
from urllib.parse import urljoin

import requests

from .observability import add_span_attributes, start_span


class ExternalDataClientError(Exception):
    """Raised when the external data request or response cannot be handled."""


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
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.verify = ca_bundle.strip() if ca_bundle else verify_ssl
        self.view_data_path_template = view_data_path_template.strip()
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


__all__ = ["ExternalDataClient", "ExternalDataClientError"]
