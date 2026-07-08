from __future__ import annotations

from datetime import date, datetime
import json
import re
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .config import settings
from .models import PublicDpakRawItemAlias, PublicDpakRawItemAttribute, PublicDpakRawPicklog
from .public_dpak_service import dataset_status, public_dpak_business_code


RAW_TABLES = {
    "picklog": PublicDpakRawPicklog,
    "item_alias": PublicDpakRawItemAlias,
    "item_attribute": PublicDpakRawItemAttribute,
}

ALLOWED_SQL_TABLES = {
    "public_dpak_raw_picklog",
    "public_dpak_raw_item_alias",
    "public_dpak_raw_item_attribute",
}

SQL_BLOCKLIST = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|execute|merge|vacuum|analyze|refresh|lock|set|reset)\b",
    re.IGNORECASE,
)

MAX_AGENT_STEPS = 7
MAX_SQL_ROWS = 80


class PublicDpakAgentError(Exception):
    pass


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return str(value)


def _clean_table_name(raw: str) -> str:
    value = raw.strip().strip('"').lower()
    if "." in value:
        value = value.rsplit(".", 1)[-1].strip('"')
    return value


def _cte_names(sql: str) -> set[str]:
    if not re.match(r"^\s*with\b", sql, re.IGNORECASE):
        return set()
    return {match.group(1).lower() for match in re.finditer(r"(?:with|,)\s+([a-zA-Z_][\w]*)\s+as\s*\(", sql, re.IGNORECASE)}


def _referenced_tables(sql: str) -> set[str]:
    return {
        _clean_table_name(match.group(1))
        for match in re.finditer(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*|\"[^\"]+\")", sql, re.IGNORECASE)
    }


def _uses_comma_table_list(sql: str) -> bool:
    return bool(
        re.search(
            r"\bfrom\b(?:(?!\bwhere\b|\bgroup\b|\border\b|\blimit\b|\boffset\b|\bunion\b|\bhaving\b).)*,",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
    )


def validate_raw_sql(sql: str) -> str:
    statement = str(sql or "").strip()
    if not statement:
        raise PublicDpakAgentError("SQL-frågan är tom.")
    if ";" in statement or "--" in statement or "/*" in statement or "*/" in statement:
        raise PublicDpakAgentError("SQL-frågan får inte innehålla kommentarer eller flera statements.")
    if not re.match(r"^\s*(select|with)\b", statement, re.IGNORECASE):
        raise PublicDpakAgentError("Endast SELECT/WITH-frågor är tillåtna.")
    if SQL_BLOCKLIST.search(statement):
        raise PublicDpakAgentError("SQL-frågan innehåller otillåtna kommandon.")
    if _uses_comma_table_list(statement):
        raise PublicDpakAgentError("Använd explicita JOIN mot tillåtna råtabeller, inte kommaseparerade FROM-listor.")
    ctes = _cte_names(statement)
    tables = _referenced_tables(statement)
    if not tables:
        raise PublicDpakAgentError("SQL-frågan måste läsa från minst en rå D-pak-tabell.")
    illegal = sorted(table for table in tables if table not in ALLOWED_SQL_TABLES and table not in ctes)
    if illegal:
        raise PublicDpakAgentError("Endast de tre råa D-pak-tabellerna får användas: " + ", ".join(illegal))
    return statement


def _columns_from_sample(row: Any) -> list[str]:
    data = getattr(row, "data", None) or {}
    if isinstance(data, dict):
        return list(data.keys())
    return []


def _distinct_values(db: Session, model, column, business_code: str, limit: int = 30) -> list[str]:
    rows = (
        db.query(column)
        .filter(model.business_code == business_code, column.is_not(None))
        .distinct()
        .order_by(column)
        .limit(limit)
        .all()
    )
    return [str(row[0]) for row in rows if row[0] not in (None, "")]


def list_files_tool(db: Session, business_code: str) -> dict[str, Any]:
    business = public_dpak_business_code(business_code)
    pick_count = db.query(func.count(PublicDpakRawPicklog.id)).filter(PublicDpakRawPicklog.business_code == business).scalar() or 0
    alias_count = db.query(func.count(PublicDpakRawItemAlias.id)).filter(PublicDpakRawItemAlias.business_code == business).scalar() or 0
    attr_count = db.query(func.count(PublicDpakRawItemAttribute.id)).filter(PublicDpakRawItemAttribute.business_code == business).scalar() or 0
    first_date, last_date = (
        db.query(func.min(PublicDpakRawPicklog.pick_date), func.max(PublicDpakRawPicklog.pick_date))
        .filter(PublicDpakRawPicklog.business_code == business)
        .one()
    )
    samples = {
        "picklog": db.query(PublicDpakRawPicklog).filter(PublicDpakRawPicklog.business_code == business).first(),
        "item_alias": db.query(PublicDpakRawItemAlias).filter(PublicDpakRawItemAlias.business_code == business).first(),
        "item_attribute": db.query(PublicDpakRawItemAttribute).filter(PublicDpakRawItemAttribute.business_code == business).first(),
    }
    return {
        "business_code": business,
        "files": [
            {
                "name": "picklog",
                "sql_table": "public_dpak_raw_picklog",
                "rows": int(pick_count),
                "date_range": {
                    "start": first_date.isoformat()[:10] if first_date else None,
                    "end": last_date.isoformat()[:10] if last_date else None,
                },
                "companies": _distinct_values(db, PublicDpakRawPicklog, PublicDpakRawPicklog.company, business),
                "zones": _distinct_values(db, PublicDpakRawPicklog, PublicDpakRawPicklog.zone, business),
                "source_views": _distinct_values(db, PublicDpakRawPicklog, PublicDpakRawPicklog.source_view, business),
                "indexed_columns": [
                    "business_code",
                    "pick_date",
                    "date_int",
                    "company",
                    "zone",
                    "order_num",
                    "customer_num",
                    "customer_desc",
                    "line_num",
                    "item_num",
                    "item_desc",
                    "location",
                    "pick_pall_num",
                    "qty_pre",
                    "qty_suf",
                    "data",
                ],
                "original_columns": _columns_from_sample(samples["picklog"]),
            },
            {
                "name": "item_alias",
                "sql_table": "public_dpak_raw_item_alias",
                "rows": int(alias_count),
                "indexed_columns": ["business_code", "item_num", "company", "alias", "unit", "factor", "data"],
                "original_columns": _columns_from_sample(samples["item_alias"]),
            },
            {
                "name": "item_attribute",
                "sql_table": "public_dpak_raw_item_attribute",
                "rows": int(attr_count),
                "indexed_columns": ["business_code", "item_num", "company", "name", "value", "data"],
                "original_columns": _columns_from_sample(samples["item_attribute"]),
            },
        ],
    }


def sample_file_tool(db: Session, business_code: str, file_name: str, limit: int = 5) -> dict[str, Any]:
    key = str(file_name or "").strip().lower().replace("-", "_")
    if key not in RAW_TABLES:
        raise PublicDpakAgentError("Okänd råfil. Använd picklog, item_alias eller item_attribute.")
    model = RAW_TABLES[key]
    rows = (
        db.query(model)
        .filter(model.business_code == public_dpak_business_code(business_code))
        .order_by(model.id)
        .limit(max(1, min(int(limit or 5), 20)))
        .all()
    )
    return {
        "file": key,
        "rows": [
            {
                "_meta": {
                    "id": row.id,
                    "source_file": getattr(row, "source_file", None),
                    "source_view": getattr(row, "source_view", None),
                    "row_index": getattr(row, "row_index", None),
                },
                **(row.data or {}),
            }
            for row in rows
        ],
    }


def run_sql_tool(db: Session, business_code: str, sql: str, max_rows: int | None = None) -> dict[str, Any]:
    statement = validate_raw_sql(sql)
    row_limit = max(1, min(int(max_rows or MAX_SQL_ROWS), 200))
    if db.get_bind() is not None and db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL statement_timeout = '8s'"))
    wrapped = f"SELECT * FROM ({statement}) AS public_dpak_agent_query LIMIT :__limit"
    result = db.execute(text(wrapped), {"__limit": row_limit})
    rows = [dict(row) for row in result.mappings().all()]
    safe_rows = [{str(key): _safe_value(value) for key, value in row.items()} for row in rows]
    return {
        "sql": statement,
        "max_rows": row_limit,
        "returned_rows": len(safe_rows),
        "rows": safe_rows,
        "note": "Resultatet är radbegränsat. Kör en COUNT eller GROUP BY för totalsiffror.",
    }


def calculation_reference_tool() -> dict[str, Any]:
    return {
        "rules": [
            "Räkna från råtabellerna vid frågetillfället, inte från färdiga fact-tabeller.",
            "D-pak-faktor hämtas från item_alias: per artikel används minsta Faktor > 1 där Enhet/unit inte är PAL.",
            "Leverantör hämtas från item_attribute där Namn/name = LastSupplierName, kopplat via Artikel/item_num.",
            "D-pak sålda per order+artikel = floor(sum(Plockat/qty_suf) / Faktor).",
            "Hela D-pak plockade per rad = floor(Plockat/qty_suf / Faktor), summerat per order+artikel.",
            "Onödigt brutna D-pak = D-pak sålda - hela D-pak plockade, när resultatet är > 0.",
            "Låda betyder Plockpallsnr/pick_pall_num.",
            "AUTOSTORE identifieras via Lokation/location = AUTOSTORE.",
            "Zon R är rader där Zon/zone = R.",
            "Bolag finns direkt i rå picklog som company och i originalraden som Bolag/company.",
        ],
        "sql_hints": [
            "Vanliga indexkolumner finns som company, zone, order_num, item_num, location, pick_pall_num, qty_suf.",
            "Originalraden finns i JSON-kolumnen data. I Postgres kan originalfält läsas med data ->> 'Bolag'.",
            "Filnamn/tabeller: public_dpak_raw_picklog, public_dpak_raw_item_alias, public_dpak_raw_item_attribute.",
            "Filtrera business_code = 'STIGAMO' när du skriver SQL.",
        ],
    }


def _tool_result(db: Session, business_code: str, action: dict[str, Any]) -> dict[str, Any]:
    tool = str(action.get("tool") or action.get("name") or "").strip()
    args = action.get("args") or action.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}
    if tool == "list_files":
        return list_files_tool(db, business_code)
    if tool == "sample_file":
        return sample_file_tool(db, business_code, str(args.get("file") or args.get("name") or ""), int(args.get("limit") or 5))
    if tool == "run_sql":
        return run_sql_tool(db, business_code, str(args.get("sql") or ""), args.get("max_rows"))
    if tool == "calculation_reference":
        return calculation_reference_tool()
    raise PublicDpakAgentError(f"Okänt verktyg: {tool}")


def _extract_json(raw: str) -> dict[str, Any]:
    text_value = str(raw or "").strip()
    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value, flags=re.IGNORECASE)
        text_value = re.sub(r"\s*```$", "", text_value)
    start = text_value.find("{")
    if start == -1:
        raise PublicDpakAgentError("MiniMax returnerade inte JSON.")
    try:
        parsed, _end = json.JSONDecoder().raw_decode(text_value[start:])
    except json.JSONDecodeError as exc:
        raise PublicDpakAgentError("MiniMax returnerade ogiltig JSON.") from exc
    if not isinstance(parsed, dict):
        raise PublicDpakAgentError("MiniMax JSON måste vara ett objekt.")
    return parsed


def _build_agent_payload(
    messages: list[dict[str, str]],
    business_code: str,
    db_status: dict[str, Any],
    tool_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    system_prompt = """
Du är en svensk dataanalys-agent för en publik D-pak-chatt.

Du får inte svara från magkänsla. Använd verktygen för att undersöka de tre råa underlagen:
- picklog
- item_alias
- item_attribute

Du ska inte anta att backend har förberäknat rätt svar. Om frågan kräver beräkning, kör SQL mot råtabellerna.
Om användaren frågar om bolag, zon, lokation, AUTOSTORE, plockpallsnr/lådor, artikel eller leverantör ska du först kontrollera rådata.

Svara alltid genom ett JSON-objekt, utan markdown runt JSON.

För att använda ett verktyg:
{"type":"tool","tool":"list_files","args":{}}
{"type":"tool","tool":"sample_file","args":{"file":"picklog","limit":5}}
{"type":"tool","tool":"calculation_reference","args":{}}
{"type":"tool","tool":"run_sql","args":{"sql":"select company, count(*) as rows from public_dpak_raw_picklog where business_code = 'STIGAMO' group by company"}}

När du är klar:
{"type":"final","answer":"kort svenskt svar","table":[{"Kolumn":"värde"}]}

Regler:
- Returnera exakt ett JSON-objekt per svar. Gör bara ett verktygsanrop åt gången.
- Använd bara tabellerna public_dpak_raw_picklog, public_dpak_raw_item_alias och public_dpak_raw_item_attribute.
- Filtrera business_code när du skriver SQL.
- Använd COUNT/GROUP BY för totalsiffror.
- Om du behöver definitioner för D-pak/brutna/leverantör/lådor, använd calculation_reference.
- Om svaret är en tabell, lägg den i final.table som JSON-rader.
- Hitta inte på data.
""".strip()
    return {
        "model": settings.MINIMAX_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "business_code": public_dpak_business_code(business_code),
                        "dataset_status": db_status,
                        "conversation": messages[-30:],
                        "tool_trace": tool_trace,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
        "max_tokens": max(settings.MINIMAX_MAX_TOKENS, 1400),
        "temperature": 0.0,
        "reasoning_split": True,
    }


def run_public_dpak_agent(
    db: Session,
    *,
    messages: list[dict[str, str]],
    business_code: str | None = None,
    call_model: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    business = public_dpak_business_code(business_code)
    tool_trace: list[dict[str, Any]] = []
    db_status = dataset_status(db, business)
    if not db_status.get("ready"):
        return {
            "answer": "D-pak-underlaget är inte klart ännu.",
            "table": [],
            "model": "raw-dpak-agent",
            "warning": None,
        }
    for step in range(1, MAX_AGENT_STEPS + 1):
        payload = _build_agent_payload(messages, business, db_status, tool_trace)
        parsed = _extract_json(call_model(payload))
        action_type = str(parsed.get("type") or ("tool" if parsed.get("tool") else "final")).strip().lower()
        if action_type == "final":
            answer = str(parsed.get("answer") or "").strip()
            table = parsed.get("table") if isinstance(parsed.get("table"), list) else []
            return {
                "answer": answer or "Jag hittade inget svar i råunderlaget.",
                "table": table[:80],
                "model": settings.MINIMAX_MODEL,
                "warning": None,
            }
        if action_type != "tool":
            raise PublicDpakAgentError("Agenten returnerade okänd åtgärdstyp.")
        try:
            result = _tool_result(db, business, parsed)
            tool_trace.append({"step": step, "tool_call": parsed, "tool_result": result})
        except Exception as exc:
            tool_trace.append({"step": step, "tool_call": parsed, "tool_error": str(exc)})
    return {
        "answer": "Jag hann inte analysera klart. Försök ställa frågan lite mer konkret.",
        "table": [],
        "model": settings.MINIMAX_MODEL,
        "warning": "Agenten nådde max antal verktygssteg.",
    }
