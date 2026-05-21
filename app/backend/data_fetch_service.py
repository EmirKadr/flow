from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .config import settings


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = ROOT_DIR / "data" / "external_data_catalog.json"
ALLOWED_OPERATORS = ("EQ", "NE", "GT", "GTE", "LT", "LTE", "Terms", "Between")
OPERATOR_ALIASES = {
    "eq": "EQ",
    "=": "EQ",
    "==": "EQ",
    "ne": "NE",
    "!=": "NE",
    "<>": "NE",
    "gt": "GT",
    ">": "GT",
    "gte": "GTE",
    ">=": "GTE",
    "lt": "LT",
    "<": "LT",
    "lte": "LTE",
    "<=": "LTE",
    "terms": "Terms",
    "in": "Terms",
    "one_of": "Terms",
    "between": "Between",
    "mellan": "Between",
}
STOP_WORDS = {
    "alla",
    "att",
    "och",
    "eller",
    "för",
    "for",
    "från",
    "fran",
    "hämta",
    "hamta",
    "med",
    "som",
    "till",
    "visa",
    "vyer",
    "vy",
}


class DataFetchConfigError(Exception):
    """Raised when the private external data catalog or API settings are missing."""


class DataFetchPlanError(Exception):
    """Raised when MiniMax returns a plan that cannot be safely executed."""


@dataclass(frozen=True)
class DataColumn:
    id: str
    label_en: str
    label_sv: str
    order: int

    @property
    def label(self) -> str:
        return self.label_sv or self.label_en or self.id


@dataclass(frozen=True)
class DataView:
    id: str
    label_en: str
    label_sv: str
    columns: tuple[DataColumn, ...]

    @property
    def label(self) -> str:
        return self.label_sv or self.label_en or self.id

    @property
    def column_by_id(self) -> dict[str, DataColumn]:
        return {column.id: column for column in self.columns}


@dataclass(frozen=True)
class DataCatalog:
    views: dict[str, DataView]

    def view(self, view_id: str) -> DataView:
        try:
            return self.views[view_id]
        except KeyError as exc:
            raise DataFetchPlanError(f"Okänd vy: {view_id}") from exc

    def candidate_views(self, prompt: str, limit: int = 12) -> list[DataView]:
        prompt_norm = _normalize(prompt)
        prompt_tokens = _tokens(prompt)
        scored: list[tuple[int, str, DataView]] = []
        for view in self.views.values():
            score = _match_score(prompt_norm, prompt_tokens, view.id, view.label_en, view.label_sv) * 4
            for column in view.columns:
                column_score = _match_score(prompt_norm, prompt_tokens, column.id, column.label_en, column.label_sv)
                if column_score:
                    score += min(column_score, 6)
            if score:
                scored.append((score, view.label.lower(), view))

        if not scored:
            return sorted(self.views.values(), key=lambda item: item.label.lower())[:limit]
        scored.sort(key=lambda item: (-item[0], item[1], item[2].id))
        return [view for _score, _label, view in scored[:limit]]


_CATALOG_CACHE: tuple[str, DataCatalog] | None = None


def clear_catalog_cache() -> None:
    global _CATALOG_CACHE
    _CATALOG_CACHE = None


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", " "))


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_åäöÅÄÖ-]{2,}", str(value or "").lower())
        if token not in STOP_WORDS
    }


def _match_score(prompt_norm: str, prompt_tokens: set[str], *values: object) -> int:
    score = 0
    for value in values:
        text = str(value or "")
        if not text:
            continue
        normalized = _normalize(text)
        if normalized and normalized in prompt_norm:
            score += 20
        score += 2 * len(prompt_tokens & _tokens(text))
        if str(value).lower() in prompt_norm:
            score += 8
    return score


def _catalog_source() -> tuple[str, str]:
    raw_json = settings.DATA_SOURCE_CATALOG_JSON.strip()
    if raw_json:
        return "env:DATA_SOURCE_CATALOG_JSON", raw_json

    configured_path = settings.DATA_SOURCE_CATALOG_PATH.strip()
    path = Path(configured_path) if configured_path else DEFAULT_CATALOG_PATH
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.is_file():
        raise DataFetchConfigError(
            "Extern datakatalog saknas. Skapa data/external_data_catalog.json med "
            "tools/build_external_data_catalog.py eller sätt DATA_SOURCE_CATALOG_JSON/DATA_SOURCE_CATALOG_PATH."
        )
    try:
        return str(path), path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DataFetchConfigError(f"Kunde inte läsa extern datakatalog: {exc}") from exc


def load_catalog() -> DataCatalog:
    global _CATALOG_CACHE
    source, raw = _catalog_source()
    signature = f"{source}:{hash(raw)}"
    if _CATALOG_CACHE and _CATALOG_CACHE[0] == signature:
        return _CATALOG_CACHE[1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataFetchConfigError("Extern datakatalog är inte giltig JSON.") from exc
    catalog = catalog_from_payload(payload)
    _CATALOG_CACHE = (signature, catalog)
    return catalog


def catalog_from_payload(payload: dict[str, Any]) -> DataCatalog:
    views_payload = payload.get("views") if isinstance(payload, dict) else None
    if not isinstance(views_payload, list):
        raise DataFetchConfigError("Extern datakatalog måste innehålla listan 'views'.")

    views: dict[str, DataView] = {}
    for view_payload in views_payload:
        if not isinstance(view_payload, dict):
            continue
        view_id = str(view_payload.get("id") or "").strip()
        if not view_id:
            continue
        columns: list[DataColumn] = []
        for column_payload in view_payload.get("columns") or []:
            if not isinstance(column_payload, dict):
                continue
            column_id = str(column_payload.get("id") or "").strip()
            if not column_id:
                continue
            columns.append(
                DataColumn(
                    id=column_id,
                    label_en=str(column_payload.get("label_en") or "").strip(),
                    label_sv=str(column_payload.get("label_sv") or "").strip(),
                    order=int(column_payload.get("order") or len(columns) + 1),
                )
            )
        columns.sort(key=lambda item: item.order)
        views[view_id] = DataView(
            id=view_id,
            label_en=str(view_payload.get("label_en") or "").strip(),
            label_sv=str(view_payload.get("label_sv") or "").strip(),
            columns=tuple(columns),
        )
    if not views:
        raise DataFetchConfigError("Extern datakatalog innehåller inga vyer.")
    return DataCatalog(views=views)


def catalog_summary(catalog: DataCatalog) -> dict[str, int]:
    return {
        "views": len(catalog.views),
        "columns": sum(len(view.columns) for view in catalog.views.values()),
    }


def build_catalog_context(prompt: str, catalog: DataCatalog, limit: int = 12) -> dict[str, Any]:
    views = []
    for view in catalog.candidate_views(prompt, limit=limit):
        views.append(
            {
                "view_id": view.id,
                "name_sv": view.label_sv,
                "name_en": view.label_en,
                "columns": [
                    {
                        "column_id": column.id,
                        "name_sv": column.label_sv,
                        "name_en": column.label_en,
                    }
                    for column in view.columns
                ],
            }
        )
    return {"operators": list(ALLOWED_OPERATORS), "candidate_views": views}


def build_data_fetch_minimax_payload(prompt: str, catalog_context: dict[str, Any]) -> dict[str, Any]:
    system_prompt = """
Du tolkar en användares svenska önskan till en säker fråga mot en extern datakälla.

Du får bara använda vyer och kolumner i katalogutdraget. Du får aldrig hitta på
endpoint, URL, API-nyckel, token, servernamn eller hemliga anslutningsuppgifter.
Du ska bara returnera JSON, utan markdown.

Välj exakt en view_id. Använd alltid tekniska column_id i output_columns,
filters och identifiers. Svenska namn i katalogen är alias för användaren.

Tillåtna filteroperatorer:
- EQ, NE, GT, GTE, LT, LTE
- Terms: value ska vara en lista
- Between: value ska vara en lista med två värden

Returnera detta format:
{
  "status": "ok",
  "view": "view_id",
  "output_columns": ["column_id"],
  "filters": [{"field": "column_id", "operator": "EQ", "value": "x"}],
  "identifiers": [],
  "reason": "kort svensk förklaring"
}

Om frågan är för otydlig, returnera:
{
  "status": "needs_clarification",
  "question": "kort fråga på svenska"
}
""".strip()
    return {
        "model": settings.MINIMAX_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "prompt": prompt,
                        "catalog": catalog_context,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "max_tokens": max(settings.MINIMAX_MAX_TOKENS, 1200),
        "temperature": 0.0,
        "reasoning_split": True,
    }


def parse_minimax_plan(raw_answer: str) -> dict[str, Any]:
    text = str(raw_answer or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise DataFetchPlanError("MiniMax returnerade inte ett JSON-objekt.")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise DataFetchPlanError("MiniMax returnerade ogiltig JSON.") from exc
    if not isinstance(payload, dict):
        raise DataFetchPlanError("MiniMax-planen måste vara ett JSON-objekt.")
    return payload


def _normalize_operator(value: object) -> str:
    key = str(value or "").strip()
    normalized = OPERATOR_ALIASES.get(key.lower())
    if normalized:
        return normalized
    if key in ALLOWED_OPERATORS:
        return key
    raise DataFetchPlanError(f"Otillåten filteroperator: {key}")


def _assert_column(view: DataView, column_id: str) -> DataColumn:
    column = view.column_by_id.get(column_id)
    if not column:
        raise DataFetchPlanError(f"Kolumnen '{column_id}' finns inte i vyn {view.id}.")
    return column


def _normalize_output_columns(raw: Any, view: DataView) -> list[str]:
    incoming = raw if isinstance(raw, list) else []
    result: list[str] = []
    for item in incoming:
        column_id = str(item or "").strip()
        if not column_id or column_id in result:
            continue
        _assert_column(view, column_id)
        result.append(column_id)
    if not result:
        result = [column.id for column in view.columns[:20]]
    return result


def _normalize_filters(raw: Any, view: DataView) -> list[dict[str, Any]]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise DataFetchPlanError("filters måste vara en lista.")
    filters: list[dict[str, Any]] = []
    for item in raw[:20]:
        if not isinstance(item, dict):
            raise DataFetchPlanError("Varje filter måste vara ett objekt.")
        field = str(item.get("field") or item.get("id") or item.get("column") or "").strip()
        if not field:
            raise DataFetchPlanError("Filter saknar field.")
        _assert_column(view, field)
        operator = _normalize_operator(item.get("operator"))
        value = item.get("value")
        if operator == "Terms" and not isinstance(value, list):
            value = [value]
        if operator == "Between":
            if not isinstance(value, list):
                value = [item.get("from"), item.get("to")]
            if len(value) != 2:
                raise DataFetchPlanError("Between-filter måste ha två värden.")
        filters.append({"id": field, "operator": operator, "value": value})
    return filters


def _normalize_identifiers(raw: Any, view: DataView) -> list[dict[str, Any]]:
    if raw in (None, "", []):
        return []
    items = [raw] if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise DataFetchPlanError("identifiers måste vara ett objekt eller en lista.")
    result: list[dict[str, Any]] = []
    for item in items[:20]:
        if not isinstance(item, dict):
            raise DataFetchPlanError("Varje identifierare måste vara ett objekt.")
        if "field" in item and "value" in item:
            item = {str(item["field"]): item["value"]}
        row: dict[str, Any] = {}
        for key, value in item.items():
            column_id = str(key or "").strip()
            if not column_id:
                continue
            _assert_column(view, column_id)
            row[column_id] = value
        if row:
            result.append(row)
    return result


def validate_plan_payload(payload: dict[str, Any], catalog: DataCatalog) -> dict[str, Any]:
    status = str(payload.get("status") or "ok").strip()
    if status == "needs_clarification":
        return {
            "status": "needs_clarification",
            "question": str(payload.get("question") or "Vilken vy och vilka filter vill du använda?").strip(),
        }
    if status != "ok":
        raise DataFetchPlanError("MiniMax-planen har okänd status.")

    view_id = str(payload.get("view") or payload.get("view_id") or "").strip()
    if not view_id:
        raise DataFetchPlanError("MiniMax-planen saknar view.")
    view = catalog.view(view_id)
    output_columns = _normalize_output_columns(
        payload.get("output_columns") or payload.get("columns"),
        view,
    )
    filters = _normalize_filters(payload.get("filters") or payload.get("userFilter"), view)
    identifiers = _normalize_identifiers(payload.get("identifiers"), view)
    selected_columns = [_assert_column(view, column_id) for column_id in output_columns]

    return {
        "status": "ok",
        "view": view.id,
        "view_label": view.label,
        "output_columns": output_columns,
        "output_column_labels": {column.id: column.label for column in selected_columns},
        "filters": filters,
        "identifiers": identifiers,
        "reason": str(payload.get("reason") or "").strip(),
    }


def _row_value(row: dict[str, Any], column_id: str) -> Any:
    if column_id in row:
        return row.get(column_id)
    lower_map = {str(key).lower(): key for key in row}
    actual_key = lower_map.get(column_id.lower())
    return row.get(actual_key) if actual_key is not None else None


def project_rows(rows: list[dict[str, Any]], output_columns: list[str], max_rows: int) -> list[dict[str, Any]]:
    limited = rows[: max(0, max_rows)]
    return [
        {column_id: _row_value(row, column_id) for column_id in output_columns}
        for row in limited
    ]


def columns_for_response(plan: dict[str, Any]) -> list[dict[str, str]]:
    labels = plan.get("output_column_labels") or {}
    return [
        {"id": column_id, "label": str(labels.get(column_id) or column_id)}
        for column_id in plan.get("output_columns", [])
    ]
