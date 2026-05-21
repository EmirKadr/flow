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
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
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
        payload = {
            "userFilter": list(filters) if filters else None,
            "identifiers": self._identifiers_to_payload(identifiers),
        }
        path = self._view_data_path(view)

        response = self.session.post(
            self._url(path),
            json=payload,
            timeout=self.timeout,
        )
        return self._rows(response)

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
        return self.view_data_path_template.format(view=view)

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
            body = response.json()
        except requests.RequestException as exc:
            raise ExternalDataClientError("Extern datakälla kunde inte nås.") from exc
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
