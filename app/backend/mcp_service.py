from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import urllib.parse
from typing import Any

import httpx

from .config import settings
from .external_data_client import clean_data_source_tenant
from .observability import add_span_attributes, start_span


try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


ROOT_DIR = Path(__file__).resolve().parents[2]
SERVER_NAME = "noeffect"
DEFAULT_TOKEN_ENV_TEMPLATE = "NOEFFECT_{tenant}_TOKEN"
CLIENT_NAME = "flow-mcp-view"
CLIENT_VERSION = "0.1.5"
PROTOCOL_VERSIONS = ("2025-06-18", "2024-11-05")
MCP_CONTEXT_RESOURCE_LIMIT = 16
MCP_CONTEXT_PROMPT_LIMIT = 8
MCP_CONTEXT_ITEM_CHAR_LIMIT = 6000
MCP_CONTEXT_TOTAL_CHAR_LIMIT = 48000
MCP_TOOL_RESULT_CHAR_LIMIT = 36000
MCP_TOOL_CALL_MAX_STEPS = 6
MCP_TOOL_CALLS_PER_STEP_LIMIT = 4
QUESTION_FIELDS = ("question", "query", "prompt", "text", "message", "input", "q", "search")
SAFE_TOOL_NAME_RE = re.compile(r"(ask|answer|chat|find|get|help|list|lookup|query|read|search)", re.IGNORECASE)
READ_ONLY_TOOL_NAME_RE = re.compile(
    r"(aggregate|column|get|list|lookup|query|read|schema|search|view)",
    re.IGNORECASE,
)
UNSAFE_TOOL_NAME_RE = re.compile(
    r"(clear|create|delete|deploy|exec|execute|insert|move|patch|post|put|remove|rename|reset|run|save|send|set|sync|update|upload|write)",
    re.IGNORECASE,
)
TEXTUAL_TOOL_CALL_RE = re.compile(r"(<\s*\|\s*DSML\s*\|)|(</\s*\|\s*DSML\s*\|)|(tool_calls)|(invoke name=)", re.IGNORECASE)
MCP_PROVIDER_ORDER = ("deepseek", "openai", "gemini", "minimax")
MCP_PROVIDER_LABELS = {
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "minimax": "MiniMax",
}


class McpConfigError(RuntimeError):
    def __init__(self, missing: list[str]) -> None:
        super().__init__("MCP-servern är inte konfigurerad.")
        self.missing = missing


class McpProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class McpConfig:
    url: str
    token_env_var: str
    token: str
    timeout_seconds: float
    tenant: str
    server: str = SERVER_NAME

    @property
    def missing(self) -> list[str]:
        missing: list[str] = []
        if not self.tenant:
            missing.append("business_tenant")
        if not self.url:
            missing.append("NOEFFECT_MCP_URL_TEMPLATE")
        if not self.token:
            missing.append(self.token_env_var or "NOEFFECT_MCP_TOKEN_ENV_TEMPLATE")
        return missing

    @property
    def ready(self) -> bool:
        return not self.missing


@dataclass(frozen=True)
class McpToolSummary:
    name: str
    title: str
    description: str
    input_fields: list[str]
    supports_question: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "input_fields": self.input_fields,
            "supports_question": self.supports_question,
        }


@dataclass(frozen=True)
class McpToolCallResult:
    answer: str
    tool: str
    tool_title: str
    content_items: int
    is_error: bool = False
    model: str = ""
    provider: str = ""
    thinking_mode: str = "none"
    tool_calls: int = 0
    tools_used: list[str] | None = None


@dataclass(frozen=True)
class McpContext:
    text: str
    content_items: int
    resources: list[dict[str, Any]]
    prompts: list[dict[str, Any]]
    tools: list[dict[str, Any]]


def _load_project_mcp_entry() -> dict[str, Any]:
    if tomllib is None:
        return {}
    path = ROOT_DIR / ".codex" / "config.toml"
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    servers = data.get("mcp_servers") or {}
    if not isinstance(servers, dict):
        return {}
    entry = servers.get(SERVER_NAME) or {}
    return entry if isinstance(entry, dict) else {}


def _format_tenant_template(template: str, tenant: str, *, uppercase: bool = False) -> str:
    text = str(template or "").strip()
    if not text:
        return ""
    value = tenant.upper() if uppercase else tenant
    return text.replace("{TENANT}", tenant.upper()).replace("{tenant}", value)


def mcp_url_for_tenant(url_template: str, tenant: object) -> str:
    configured = str(url_template or "").strip()
    cleaned_tenant = clean_data_source_tenant(tenant)
    if not configured or not cleaned_tenant:
        return configured
    return _format_tenant_template(configured, cleaned_tenant).rstrip("/")


def mcp_token_env_var_for_tenant(env_template: str, tenant: object) -> str:
    configured = str(env_template or DEFAULT_TOKEN_ENV_TEMPLATE).strip()
    cleaned_tenant = clean_data_source_tenant(tenant)
    if not configured or not cleaned_tenant:
        return configured
    return _format_tenant_template(configured, cleaned_tenant, uppercase=True)


def mcp_authorization_header(token: str) -> str:
    value = str(token or "").strip()
    if not value:
        return ""
    return value if value.lower().startswith("bearer ") else f"Bearer {value}"


def _strip_env_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _env_file_value(name: str) -> str:
    key = str(name or "").strip()
    if not key:
        return ""
    for path in (ROOT_DIR / ".env", ROOT_DIR / "app" / ".env"):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            env_key, raw_value = line.split("=", 1)
            if env_key.strip() == key:
                return _strip_env_quotes(raw_value)
    return ""


def mcp_config(tenant: object = None) -> McpConfig:
    local_entry = _load_project_mcp_entry()
    cleaned_tenant = clean_data_source_tenant(tenant) or ""
    token_template = str(
        settings.NOEFFECT_MCP_TOKEN_ENV_TEMPLATE
        or local_entry.get("bearer_token_env_var")
        or DEFAULT_TOKEN_ENV_TEMPLATE
    ).strip()
    token_env_var = mcp_token_env_var_for_tenant(token_template, cleaned_tenant)
    url_template = str(
        settings.NOEFFECT_MCP_URL_TEMPLATE
        or local_entry.get("url_template")
        or local_entry.get("url")
        or ""
    ).strip()
    url = mcp_url_for_tenant(url_template, cleaned_tenant)
    token = os.getenv(token_env_var, "") or _env_file_value(token_env_var)
    return McpConfig(
        url=url,
        token_env_var=token_env_var,
        token=str(token or "").strip(),
        timeout_seconds=max(1.0, float(settings.NOEFFECT_MCP_TIMEOUT_SECONDS or 30)),
        tenant=cleaned_tenant,
    )


def _json_payloads_from_sse(text: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    data_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if data_lines:
                try:
                    payload = json.loads("\n".join(data_lines))
                    if isinstance(payload, dict):
                        payloads.append(payload)
                except json.JSONDecodeError:
                    pass
                data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if data_lines:
        try:
            payload = json.loads("\n".join(data_lines))
            if isinstance(payload, dict):
                payloads.append(payload)
        except json.JSONDecodeError:
            pass
    return payloads


def _response_payload(response: httpx.Response, request_id: int | None) -> dict[str, Any] | None:
    if response.status_code == 202 or not response.content:
        return None
    content_type = response.headers.get("content-type", "").lower()
    if "text/event-stream" in content_type:
        payloads = _json_payloads_from_sse(response.text)
    else:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise McpProtocolError("MCP-servern svarade med ett okänt format.") from exc
        payloads = payload if isinstance(payload, list) else [payload]

    if request_id is not None:
        for payload in payloads:
            if isinstance(payload, dict) and payload.get("id") == request_id:
                return payload
    for payload in payloads:
        if isinstance(payload, dict):
            return payload
    return None


def _rpc_error_message(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if not isinstance(error, dict):
        return "MCP-servern returnerade ett fel."
    message = str(error.get("message") or "MCP-servern returnerade ett fel.").strip()
    code = error.get("code")
    return f"{message} (kod {code})" if code is not None else message


class McpHttpSession:
    def __init__(self, config: McpConfig) -> None:
        self.config = config
        self.session_id = ""
        self.protocol_version = PROTOCOL_VERSIONS[0]
        self._next_id = 1
        self._client = httpx.AsyncClient(timeout=config.timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    async def _post(self, body: dict[str, Any], *, request_id: int | None = None) -> dict[str, Any] | None:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Authorization": mcp_authorization_header(self.config.token),
            "Content-Type": "application/json",
            "MCP-Protocol-Version": self.protocol_version,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        with start_span("mcp.http", {"mcp.method": body.get("method") or "", "mcp.has_session": bool(self.session_id)}):
            try:
                response = await self._client.post(self.config.url, headers=headers, json=body)
            except httpx.TimeoutException as exc:
                add_span_attributes({"mcp.error_type": type(exc).__name__})
                raise McpProtocolError("MCP-servern svarade inte i tid.") from exc
            except httpx.HTTPError as exc:
                add_span_attributes({"mcp.error_type": type(exc).__name__})
                raise McpProtocolError("MCP-servern kunde inte nås.") from exc
        if response.status_code >= 400:
            add_span_attributes({"mcp.http_status_code": response.status_code})
            raise McpProtocolError(f"MCP-servern svarade HTTP {response.status_code}.")
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self.session_id = session_id
        payload = _response_payload(response, request_id)
        if payload and payload.get("error"):
            raise McpProtocolError(_rpc_error_message(payload))
        return payload

    async def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload = await self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
            request_id=request_id,
        )
        result = payload.get("result") if payload else None
        return result if isinstance(result, dict) else {}

    async def optional_rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return await self.rpc(method, params)
        except McpProtocolError:
            return {}

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._post({"jsonrpc": "2.0", "method": method, "params": params or {}}, request_id=None)

    async def initialize(self) -> None:
        last_error: Exception | None = None
        for protocol_version in PROTOCOL_VERSIONS:
            self.protocol_version = protocol_version
            try:
                await self.rpc(
                    "initialize",
                    {
                        "protocolVersion": protocol_version,
                        "capabilities": {},
                        "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
                    },
                )
                await self.notify("notifications/initialized")
                return
            except McpProtocolError as exc:
                last_error = exc
                self.session_id = ""
        if last_error is not None:
            raise last_error

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self.rpc("tools/list")
        tools = result.get("tools")
        return [tool for tool in tools if isinstance(tool, dict)] if isinstance(tools, list) else []

    async def list_tools_optional(self) -> list[dict[str, Any]]:
        result = await self.optional_rpc("tools/list")
        tools = result.get("tools")
        return [tool for tool in tools if isinstance(tool, dict)] if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.rpc("tools/call", {"name": name, "arguments": arguments})

    async def list_resources(self) -> list[dict[str, Any]]:
        result = await self.optional_rpc("resources/list")
        resources = result.get("resources")
        return [resource for resource in resources if isinstance(resource, dict)] if isinstance(resources, list) else []

    async def read_resource(self, uri: str) -> dict[str, Any]:
        return await self.optional_rpc("resources/read", {"uri": uri})

    async def list_prompts(self) -> list[dict[str, Any]]:
        result = await self.optional_rpc("prompts/list")
        prompts = result.get("prompts")
        return [prompt for prompt in prompts if isinstance(prompt, dict)] if isinstance(prompts, list) else []

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.optional_rpc("prompts/get", {"name": name, "arguments": arguments or {}})


def _input_schema(tool: dict[str, Any]) -> dict[str, Any]:
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    return schema if isinstance(schema, dict) else {}


def _schema_properties(tool: dict[str, Any]) -> dict[str, Any]:
    properties = _input_schema(tool).get("properties") or {}
    return properties if isinstance(properties, dict) else {}


def _tool_title(tool: dict[str, Any]) -> str:
    return str(tool.get("title") or tool.get("name") or "").strip()


def _tool_description(tool: dict[str, Any]) -> str:
    return str(tool.get("description") or "").strip()


def _safe_question_tool(tool: dict[str, Any]) -> bool:
    name = str(tool.get("name") or "")
    text = f"{name} {_tool_description(tool)}"
    if UNSAFE_TOOL_NAME_RE.search(name) and not SAFE_TOOL_NAME_RE.search(name):
        return False
    properties = _schema_properties(tool)
    has_question_field = any(field in properties for field in QUESTION_FIELDS)
    has_safe_name = bool(SAFE_TOOL_NAME_RE.search(text))
    return has_question_field and has_safe_name


def summarize_tool(tool: dict[str, Any]) -> McpToolSummary:
    properties = _schema_properties(tool)
    return McpToolSummary(
        name=str(tool.get("name") or "").strip(),
        title=_tool_title(tool),
        description=_tool_description(tool)[:500],
        input_fields=sorted(str(key) for key in properties)[:20],
        supports_question=_safe_question_tool(tool),
    )


def summarize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        summary.as_dict()
        for summary in (summarize_tool(tool) for tool in tools)
        if summary.name
    ]


def _read_only_tool(tool: dict[str, Any]) -> bool:
    name = str(tool.get("name") or "")
    text = f"{name} {_tool_description(tool)}"
    if not name:
        return False
    if UNSAFE_TOOL_NAME_RE.search(name) and not READ_ONLY_TOOL_NAME_RE.search(name):
        return False
    return bool(READ_ONLY_TOOL_NAME_RE.search(text))


def _clean_gemini_schema(schema: Any, *, top_level: bool = False) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}} if top_level else {"type": "string"}
    schema_type = schema.get("type") or ("object" if schema.get("properties") else "string")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), schema_type[0] if schema_type else "string")
    schema_type = str(schema_type or "string").lower()
    if top_level and schema_type != "object":
        schema_type = "object"

    cleaned: dict[str, Any] = {"type": schema_type}
    description = str(schema.get("description") or "").strip()
    if description:
        cleaned["description"] = description[:1000]
    if isinstance(schema.get("enum"), list) and schema["enum"]:
        cleaned["enum"] = [item for item in schema["enum"] if isinstance(item, (str, int, float, bool))][:100]
    if schema_type == "object":
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        cleaned["properties"] = {
            str(key): _clean_gemini_schema(value)
            for key, value in properties.items()
            if str(key).strip()
        }
        required = schema.get("required")
        if isinstance(required, list):
            allowed = set(cleaned["properties"])
            cleaned["required"] = [str(item) for item in required if str(item) in allowed]
    elif schema_type == "array":
        cleaned["items"] = _clean_gemini_schema(schema.get("items") if isinstance(schema.get("items"), dict) else {})
    return cleaned


def _gemini_function_declaration(tool: dict[str, Any]) -> dict[str, Any] | None:
    name = str(tool.get("name") or "").strip()
    if not name or not _read_only_tool(tool):
        return None
    schema = _clean_gemini_schema(_input_schema(tool), top_level=True)
    description = _tool_description(tool) or f"MCP read-only tool {name}."
    return {
        "name": name,
        "description": description[:1000],
        "parameters": schema,
    }


def gemini_function_declarations(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    declarations = [
        declaration
        for declaration in (_gemini_function_declaration(tool) for tool in tools)
        if declaration is not None
    ]
    return declarations[:128]


def _resource_title(resource: dict[str, Any]) -> str:
    return str(resource.get("title") or resource.get("name") or resource.get("uri") or "").strip()


def _resource_description(resource: dict[str, Any]) -> str:
    return str(resource.get("description") or "").strip()


def summarize_resource(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _resource_title(resource)[:200],
        "description": _resource_description(resource)[:500],
        "mime_type": str(resource.get("mimeType") or resource.get("mime_type") or "").strip()[:120],
    }


def summarize_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        summary
        for summary in (summarize_resource(resource) for resource in resources)
        if summary["title"] or summary["description"] or summary["mime_type"]
    ]


def _prompt_arguments(prompt: dict[str, Any]) -> list[dict[str, Any]]:
    arguments = prompt.get("arguments")
    return [argument for argument in arguments if isinstance(argument, dict)] if isinstance(arguments, list) else []


def _prompt_supports_empty_arguments(prompt: dict[str, Any]) -> bool:
    return not any(bool(argument.get("required")) for argument in _prompt_arguments(prompt))


def summarize_prompt(prompt: dict[str, Any]) -> dict[str, Any]:
    arguments = _prompt_arguments(prompt)
    return {
        "name": str(prompt.get("name") or "").strip()[:160],
        "title": str(prompt.get("title") or prompt.get("name") or "").strip()[:200],
        "description": str(prompt.get("description") or "").strip()[:500],
        "input_fields": [str(argument.get("name") or "").strip() for argument in arguments if argument.get("name")][:20],
        "supports_empty_arguments": _prompt_supports_empty_arguments(prompt),
    }


def summarize_prompts(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        summary
        for summary in (summarize_prompt(prompt) for prompt in prompts)
        if summary["name"] or summary["title"]
    ]


def _question_tool_score(tool: dict[str, Any]) -> int:
    name = str(tool.get("name") or "")
    text = f"{name} {_tool_description(tool)}"
    properties = _schema_properties(tool)
    score = 0
    if _safe_question_tool(tool):
        score += 100
    if name.lower() in {"ask", "answer", "chat", "query", "search"}:
        score += 20
    if any(field in properties for field in ("question", "query", "prompt")):
        score += 12
    if SAFE_TOOL_NAME_RE.search(text):
        score += 5
    return score


def select_question_tool(tools: list[dict[str, Any]], requested_tool: str | None = None) -> dict[str, Any]:
    safe_tools = [tool for tool in tools if _safe_question_tool(tool)]
    if requested_tool:
        for tool in safe_tools:
            if str(tool.get("name") or "") == requested_tool:
                return tool
        raise McpProtocolError("Valt MCP-verktyg kan inte användas för frågor i den här vyn.")
    if not safe_tools:
        raise McpProtocolError("MCP-servern saknar ett säkert fråga- eller sökverktyg.")
    return max(safe_tools, key=_question_tool_score)


def _schema_default(schema: dict[str, Any]) -> Any:
    if "default" in schema:
        return schema["default"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    return None


def arguments_for_question(tool: dict[str, Any], question: str) -> dict[str, Any]:
    schema = _input_schema(tool)
    properties = _schema_properties(tool)
    required = [str(item) for item in schema.get("required") or []]
    target_field = next((field for field in QUESTION_FIELDS if field in properties), "")
    if not target_field:
        raise McpProtocolError("MCP-verktyget saknar ett textfält för frågan.")

    arguments: dict[str, Any] = {target_field: question}
    missing_required: list[str] = []
    for field in required:
        if field == target_field:
            continue
        prop = properties.get(field)
        default = _schema_default(prop if isinstance(prop, dict) else {})
        if default is None:
            missing_required.append(field)
        else:
            arguments[field] = default
    if missing_required:
        joined = ", ".join(missing_required)
        raise McpProtocolError(f"MCP-verktyget kräver fler fält: {joined}.")
    return arguments


def _content_item_text(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    if isinstance(item.get("text"), str):
        return item["text"]
    if "resource" in item:
        resource = item.get("resource")
        if isinstance(resource, dict):
            if isinstance(resource.get("text"), str):
                return resource["text"]
            if resource.get("uri"):
                return f"Resurs: {resource.get('uri')}"
        return json.dumps(resource, ensure_ascii=False, default=str)
    if "json" in item:
        return json.dumps(item.get("json"), ensure_ascii=False, indent=2, default=str)
    return json.dumps(item, ensure_ascii=False, indent=2, default=str)


def extract_tool_answer(result: dict[str, Any]) -> tuple[str, int, bool]:
    content = result.get("content")
    parts = [_content_item_text(item).strip() for item in content] if isinstance(content, list) else []
    parts = [part for part in parts if part]
    if not parts and isinstance(result.get("structuredContent"), (dict, list)):
        parts.append(json.dumps(result.get("structuredContent"), ensure_ascii=False, indent=2, default=str))
    if not parts and result:
        parts.append(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    answer = "\n\n".join(parts).strip()
    return answer, len(content) if isinstance(content, list) else 0, bool(result.get("isError"))


def _resource_content_text(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item or "").strip()
    if isinstance(item.get("text"), str):
        return item["text"].strip()
    if "blob" in item:
        mime_type = str(item.get("mimeType") or item.get("mime_type") or "binart innehall").strip()
        return f"[{mime_type} hoppades over eftersom MCP-resursen inte ar text.]"
    return _content_item_text(item).strip()


def extract_resource_text(result: dict[str, Any]) -> tuple[str, int]:
    contents = result.get("contents")
    parts = [_resource_content_text(item) for item in contents] if isinstance(contents, list) else []
    parts = [part for part in parts if part]
    if not parts and isinstance(result.get("content"), list):
        parts = [_resource_content_text(item) for item in result["content"]]
        parts = [part for part in parts if part]
    if not parts and isinstance(result.get("text"), str):
        parts.append(result["text"].strip())
    return "\n\n".join(parts).strip(), len(contents) if isinstance(contents, list) else len(parts)


def extract_prompt_text(result: dict[str, Any]) -> tuple[str, int]:
    messages = result.get("messages")
    parts: list[str] = []
    if isinstance(result.get("description"), str):
        parts.append(result["description"].strip())
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip()
            content = _content_item_text(message.get("content")).strip()
            if content:
                parts.append(f"{role}: {content}" if role else content)
    return "\n\n".join(part for part in parts if part).strip(), len(messages) if isinstance(messages, list) else len(parts)


def _trim_context_item(text: str, remaining: int) -> str:
    limit = max(0, min(MCP_CONTEXT_ITEM_CHAR_LIMIT, remaining))
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 80)].rstrip()}\n\n[Avkortat i Flow innan LLM-anropet.]"


def _context_label(title: str, fallback: str) -> str:
    text = str(title or fallback or "").strip()
    return text[:200] if text else "MCP-kontext"


async def collect_mcp_context(config: McpConfig) -> McpContext:
    session = McpHttpSession(config)
    try:
        await session.initialize()
        tools = await session.list_tools_optional()
        resources = await session.list_resources()
        prompts = await session.list_prompts()
        parts: list[str] = []
        content_items = 0
        remaining = MCP_CONTEXT_TOTAL_CHAR_LIMIT

        for resource in resources[:MCP_CONTEXT_RESOURCE_LIMIT]:
            uri = str(resource.get("uri") or "").strip()
            if not uri:
                continue
            result = await session.read_resource(uri)
            text, count = extract_resource_text(result)
            if not text:
                continue
            label = _context_label(_resource_title(resource), "MCP-resurs")
            block = f"### MCP resource: {label}\n{text}"
            trimmed = _trim_context_item(block, remaining)
            if not trimmed:
                break
            parts.append(trimmed)
            remaining -= len(trimmed)
            content_items += max(1, count)
            if remaining <= 0:
                break

        if remaining > 0:
            empty_prompts = [prompt for prompt in prompts if _prompt_supports_empty_arguments(prompt)]
            for prompt in empty_prompts[:MCP_CONTEXT_PROMPT_LIMIT]:
                name = str(prompt.get("name") or "").strip()
                if not name:
                    continue
                result = await session.get_prompt(name)
                text, count = extract_prompt_text(result)
                if not text:
                    continue
                label = _context_label(str(prompt.get("title") or name), "MCP-prompt")
                block = f"### MCP prompt: {label}\n{text}"
                trimmed = _trim_context_item(block, remaining)
                if not trimmed:
                    break
                parts.append(trimmed)
                remaining -= len(trimmed)
                content_items += max(1, count)
                if remaining <= 0:
                    break

        return McpContext(
            text="\n\n".join(parts).strip(),
            content_items=content_items,
            resources=summarize_resources(resources),
            prompts=summarize_prompts(prompts),
            tools=summarize_tools(tools),
        )
    finally:
        await session.close()


def gemini_configured() -> bool:
    return bool(settings.GEMINI_API_KEY.strip())


def _csv_values(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _model_options(default_model: str, configured: str) -> list[str]:
    values = [default_model, *_csv_values(configured)]
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def gemini_model_name(model: str | None = None) -> str:
    return (str(model or settings.GEMINI_MODEL).strip() or "gemini-2.5-pro").removeprefix("models/")


def openai_configured() -> bool:
    return bool(settings.OPENAI_API_KEY.strip())


def openai_model_name(model: str | None = None) -> str:
    return str(model or settings.OPENAI_MODEL).strip() or "gpt-4o-mini"


def minimax_configured() -> bool:
    return bool(settings.MINIMAX_API_KEY.strip())


def minimax_model_name(model: str | None = None) -> str:
    return str(model or settings.MINIMAX_MODEL).strip() or "MiniMax-M2.7"


def deepseek_configured() -> bool:
    return bool(settings.DEEPSEEK_API_KEY.strip())


def deepseek_model_name(model: str | None = None) -> str:
    return str(model or settings.DEEPSEEK_MODEL).strip() or "deepseek-v4-pro"


def deepseek_thinking_enabled() -> bool:
    return bool(settings.DEEPSEEK_THINKING_ENABLED)


def deepseek_reasoning_effort() -> str:
    configured = str(settings.DEEPSEEK_REASONING_EFFORT or "").strip().lower()
    if configured in {"max", "xhigh"}:
        return "max"
    return "high"


def _deepseek_base_url() -> str:
    return settings.DEEPSEEK_API_BASE_URL.strip().rstrip("/") or "https://api.deepseek.com"


def _deepseek_chat_url() -> str:
    return f"{_deepseek_base_url()}/chat/completions"


def _provider_configured(provider: str) -> bool:
    if provider == "deepseek":
        return deepseek_configured()
    if provider == "openai":
        return openai_configured()
    if provider == "gemini":
        return gemini_configured()
    if provider == "minimax":
        return minimax_configured()
    return False


def _provider_missing(provider: str) -> list[str]:
    if provider == "deepseek":
        return [] if deepseek_configured() else ["DEEPSEEK_API_KEY"]
    if provider == "openai":
        return [] if openai_configured() else ["OPENAI_API_KEY"]
    if provider == "gemini":
        return [] if gemini_configured() else ["GEMINI_API_KEY"]
    if provider == "minimax":
        return [] if minimax_configured() else ["MINIMAX_API_KEY"]
    return ["MCP_LLM_PROVIDER"]


def _default_provider() -> str:
    configured = str(settings.MCP_LLM_PROVIDER or "auto").strip().lower()
    if configured in MCP_PROVIDER_ORDER:
        return configured
    return next((provider for provider in MCP_PROVIDER_ORDER if _provider_configured(provider)), "deepseek")


def brain_provider_name(requested_provider: str | None = None) -> str:
    requested = str(requested_provider or "").strip().lower().removesuffix("_tools")
    if requested in MCP_PROVIDER_ORDER:
        return requested
    return _default_provider()


def brain_configured(provider: str | None = None) -> bool:
    return _provider_configured(brain_provider_name(provider))


def brain_missing(provider: str | None = None) -> list[str]:
    return _provider_missing(brain_provider_name(provider))


def provider_model_options(provider: str) -> list[str]:
    if provider == "deepseek":
        return _model_options(deepseek_model_name(), settings.MCP_DEEPSEEK_MODELS)
    if provider == "openai":
        return _model_options(openai_model_name(), settings.MCP_OPENAI_MODELS)
    if provider == "gemini":
        return _model_options(gemini_model_name(), settings.MCP_GEMINI_MODELS)
    if provider == "minimax":
        return _model_options(minimax_model_name(), settings.MCP_MINIMAX_MODELS)
    return []


def brain_model_name(
    provider: str | None = None,
    requested_model: str | None = None,
) -> str:
    selected_provider = brain_provider_name(provider)
    options = provider_model_options(selected_provider)
    requested = str(requested_model or "").strip()
    if requested and requested in options:
        return requested
    if selected_provider == "deepseek":
        return deepseek_model_name()
    if selected_provider == "openai":
        return openai_model_name()
    if selected_provider == "gemini":
        return gemini_model_name()
    if selected_provider == "minimax":
        return minimax_model_name()
    return options[0] if options else ""


def provider_thinking_modes(provider: str) -> list[dict[str, str]]:
    modes = [{"value": "none", "label": "Ingen thinking"}]
    if provider == "deepseek":
        modes.extend([
            {"value": "high", "label": "Thinking"},
            {"value": "max", "label": "Deep thinking"},
        ])
    return modes


def normalize_thinking_mode(provider: str, requested: str | None = None) -> str:
    if provider != "deepseek":
        return "none"
    text = str(requested or "").strip().lower()
    if text in {"max", "deep", "deep_thinking", "deep-thinking", "xhigh"}:
        return "max"
    if text in {"high", "thinking", "enabled"}:
        return "high"
    if requested is None and deepseek_thinking_enabled():
        return deepseek_reasoning_effort()
    return "none"


def mcp_brain_options() -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for provider in MCP_PROVIDER_ORDER:
        configured = _provider_configured(provider)
        if not configured:
            continue
        default_thinking = normalize_thinking_mode(provider, None)
        options.append({
            "id": provider,
            "label": MCP_PROVIDER_LABELS.get(provider, provider.title()),
            "configured": configured,
            "models": provider_model_options(provider),
            "default_model": brain_model_name(provider),
            "thinking_modes": provider_thinking_modes(provider),
            "default_thinking": default_thinking,
        })
    return options


def _gemini_base_url() -> str:
    return settings.GEMINI_API_BASE_URL.strip().rstrip("/") or "https://generativelanguage.googleapis.com"


def _gemini_generate_url(model: str | None = None) -> str:
    model_path = f"models/{gemini_model_name(model)}"
    return f"{_gemini_base_url()}/v1beta/{urllib.parse.quote(model_path, safe='/')}:generateContent"


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            parts = candidate.get("content", {}).get("parts", []) if isinstance(candidate.get("content"), dict) else []
            text_parts = [str(part.get("text") or "").strip() for part in parts if isinstance(part, dict)]
            text = "\n\n".join(part for part in text_parts if part).strip()
            if text:
                return text
    prompt_feedback = payload.get("promptFeedback") if isinstance(payload, dict) else None
    if isinstance(prompt_feedback, dict) and prompt_feedback.get("blockReason"):
        raise McpProtocolError(f"Gemini blockerade fragan: {prompt_feedback.get('blockReason')}.")
    return ""


def _extract_gemini_function_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates")
    calls: list[dict[str, Any]] = []
    if not isinstance(candidates, list):
        return calls
    for candidate in candidates[:1]:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            function_call = part.get("functionCall") if isinstance(part, dict) else None
            if isinstance(function_call, dict):
                calls.append({
                    "name": str(function_call.get("name") or "").strip(),
                    "args": function_call.get("args") if isinstance(function_call.get("args"), dict) else {},
                })
    return [call for call in calls if call["name"]]


def _candidate_content(payload: dict[str, Any]) -> dict[str, Any] | None:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    candidate = candidates[0]
    if not isinstance(candidate, dict):
        return None
    content = candidate.get("content")
    return content if isinstance(content, dict) else None


def _limit_tool_payload(payload: Any, max_chars: int = MCP_TOOL_RESULT_CHAR_LIMIT) -> Any:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return payload
    return {
        "truncated": True,
        "content": text[:max_chars],
        "note": "Tool-resultatet kortades av i Flow innan det skickades tillbaka till hjarnan.",
    }


def _gemini_system_text(has_tools: bool) -> str:
    tool_instructions = (
        "Du har MCP-tools for att hamta live-data fran Noeffect. "
        "For datafragor ska du anvanda tools innan du svarar. "
        "Börja normalt med search_views eller get_views, hamta schema/kolumner vid behov, "
        "och anvand sedan query_view eller aggregate_view for faktiska rader eller summeringar. "
        "Nar fragan galler mottagna/inlevererade artiklar ska du soka efter Varumottagningslogg, mottag eller receive_log. "
        "Anvand bara tools for lasning och be om forklaring om parametrar saknas."
        if has_tools
        else "Du har inga MCP-tools i detta anrop och far bara anvanda given MCP-kontext."
    )
    return (
        "Du ar Flow MCP-assistent. Svara pa svenska nar anvandaren skriver svenska. "
        "Anvand MCP-kontext och MCP-tools for faktauppgifter om Noeffect och aktuell tenant. "
        f"{tool_instructions} "
        "Om underlaget inte racker efter relevanta tool-forsok ska du saga exakt vad som saknas. "
        "Hall svaret praktiskt och namnge gärna vilken vy eller tool som anvandes."
    )


def _initial_user_text(question: str, context: McpContext, config: McpConfig, has_tools: bool) -> str:
    context_text = context.text or "Ingen textkontext kunde lasas fran MCP-resurser eller MCP-prompts."
    tool_text = (
        "MCP-tools ar tillgangliga. Anvand dem aktivt for datafragor."
        if has_tools
        else "Inga MCP-tools ar tillgangliga."
    )
    return (
        f"Tenant: {config.tenant or 'okand'}\n\n"
        f"{tool_text}\n\n"
        f"Fraga fran Flow-anvandaren:\n{question}\n\n"
        f"MCP-kontext:\n{context_text}"
    )


def _initial_gemini_contents(question: str, context: McpContext, config: McpConfig, has_tools: bool) -> list[dict[str, Any]]:
    return [{"role": "user", "parts": [{"text": _initial_user_text(question, context, config, has_tools)}]}]


def _initial_deepseek_messages(question: str, context: McpContext, config: McpConfig, has_tools: bool) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": _gemini_system_text(has_tools)},
        {"role": "user", "content": _initial_user_text(question, context, config, has_tools)},
    ]


def _gemini_body(
    *,
    contents: list[dict[str, Any]],
    declarations: list[dict[str, Any]] | None = None,
    force_tool: bool = False,
) -> dict[str, Any]:
    has_tools = bool(declarations)
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": _gemini_system_text(has_tools)}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.1 if has_tools else 0.2},
    }
    if declarations:
        body["tools"] = [{"functionDeclarations": declarations}]
        function_calling_config: dict[str, Any] = {
            "mode": "ANY" if force_tool else "AUTO",
        }
        if force_tool:
            function_calling_config["allowedFunctionNames"] = [declaration["name"] for declaration in declarations]
        body["toolConfig"] = {
            "functionCallingConfig": function_calling_config,
        }
    return body


async def _gemini_generate_content(
    body: dict[str, Any],
    config: McpConfig,
    *,
    context_items: int = 0,
    model: str | None = None,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.GEMINI_API_KEY.strip(),
    }
    with start_span(
        "external.gemini.generate_content",
        {
            "external.provider": "gemini",
            "gemini.model": gemini_model_name(model),
            "mcp.context_items": context_items,
        },
    ):
        try:
            async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                response = await client.post(_gemini_generate_url(model), headers=headers, json=body)
        except httpx.TimeoutException as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            raise McpProtocolError("Gemini svarade inte i tid.") from exc
        except httpx.HTTPError as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            raise McpProtocolError("Gemini kunde inte nas.") from exc
    add_span_attributes({"external.http_status_code": response.status_code})
    if response.status_code >= 400:
        raise McpProtocolError(f"Gemini svarade HTTP {response.status_code}.")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise McpProtocolError("Gemini-svaret kunde inte tolkas som JSON.") from exc


async def _call_gemini_generate_content(
    body: dict[str, Any],
    config: McpConfig,
    *,
    context_items: int = 0,
    model: str | None = None,
) -> dict[str, Any]:
    if model:
        return await _gemini_generate_content(body, config, context_items=context_items, model=model)
    return await _gemini_generate_content(body, config, context_items=context_items)


def openai_tool_declarations(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": declaration}
        for declaration in gemini_function_declarations(tools)
    ]


def _chat_completion_body(
    *,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    thinking_mode: str = "none",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if provider == "deepseek" and thinking_mode in {"high", "max"}:
        body["thinking"] = {"type": "enabled"}
        body["reasoning_effort"] = thinking_mode
    elif provider == "deepseek":
        body["thinking"] = {"type": "disabled"}
        body["temperature"] = 0.1 if tools else 0.2
    else:
        body["temperature"] = 0.1 if tools else 0.2
    if provider == "minimax":
        body["max_tokens"] = max(int(settings.MINIMAX_MAX_TOKENS or 700), 1200)
    return body


def _deepseek_body(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    thinking_mode: str | None = None,
) -> dict[str, Any]:
    selected_thinking = normalize_thinking_mode("deepseek", thinking_mode)
    return _chat_completion_body(
        provider="deepseek",
        model=deepseek_model_name(model),
        messages=messages,
        tools=tools,
        thinking_mode=selected_thinking,
    )


def _chat_provider_url(provider: str) -> str:
    if provider == "deepseek":
        return _deepseek_chat_url()
    if provider == "openai":
        return f"{settings.OPENAI_API_BASE_URL.strip().rstrip('/') or 'https://api.openai.com/v1'}/chat/completions"
    if provider == "minimax":
        return settings.MINIMAX_API_URL.strip() or "https://api.minimax.io/v1/chat/completions"
    return ""


def _chat_provider_api_key(provider: str) -> str:
    if provider == "deepseek":
        return settings.DEEPSEEK_API_KEY.strip()
    if provider == "openai":
        return settings.OPENAI_API_KEY.strip()
    if provider == "minimax":
        return settings.MINIMAX_API_KEY.strip()
    return ""


async def _provider_chat_completion(
    provider: str,
    body: dict[str, Any],
    config: McpConfig,
    *,
    context_items: int = 0,
) -> dict[str, Any]:
    label = MCP_PROVIDER_LABELS.get(provider, provider.title())
    headers = {
        "Authorization": f"Bearer {_chat_provider_api_key(provider)}",
        "Content-Type": "application/json",
    }
    with start_span(
        f"external.{provider}.chat_completion",
        {
            "external.provider": provider,
            "llm.model": body.get("model") or "",
            "llm.thinking_mode": body.get("reasoning_effort") or "none",
            "mcp.context_items": context_items,
        },
    ):
        try:
            async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                response = await client.post(_chat_provider_url(provider), headers=headers, json=body)
        except httpx.TimeoutException as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            raise McpProtocolError(f"{label} svarade inte i tid.") from exc
        except httpx.HTTPError as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            raise McpProtocolError(f"{label} kunde inte nas.") from exc
    add_span_attributes({"external.http_status_code": response.status_code})
    if response.status_code >= 400:
        raise McpProtocolError(f"{label} svarade HTTP {response.status_code}.")
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise McpProtocolError(f"{label}-svaret kunde inte tolkas som JSON.") from exc
    return payload if isinstance(payload, dict) else {}


async def _deepseek_chat_completion(body: dict[str, Any], config: McpConfig, *, context_items: int = 0) -> dict[str, Any]:
    return await _provider_chat_completion("deepseek", body, config, context_items=context_items)


async def _chat_completion_for_provider(
    provider: str,
    body: dict[str, Any],
    config: McpConfig,
    *,
    context_items: int = 0,
) -> dict[str, Any]:
    if provider == "deepseek":
        return await _deepseek_chat_completion(body, config, context_items=context_items)
    return await _provider_chat_completion(provider, body, config, context_items=context_items)


def _deepseek_message(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    return message if isinstance(message, dict) else {}


def _extract_deepseek_text(payload: dict[str, Any]) -> str:
    content = _deepseek_message(payload).get("content")
    return str(content or "").strip()


def _deepseek_text_has_tool_markup(answer: str) -> bool:
    return bool(TEXTUAL_TOOL_CALL_RE.search(str(answer or "")))


def _tool_exhausted_answer(tool_calls: int, used_tool_names: list[str]) -> str:
    unique_tools = ", ".join(dict.fromkeys(used_tool_names)) or "inga tools"
    return (
        f"Jag fastnade efter {tool_calls} MCP-tool-anrop ({unique_tools}). "
        "Modellen forsokte gora ytterligare ett tool-anrop som text i stallet for via MCP, "
        "sa Flow stoppade svaret for att inte visa intern tool-syntax. "
        "Prova fragan igen mer styrt, till exempel med vyn `v_ask_receive_log`, eller stang av thinking-laget for snabbare MCP-fragor."
    )


def _extract_deepseek_tool_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_calls = _deepseek_message(payload).get("tool_calls")
    if not isinstance(raw_calls, list):
        return []
    calls: list[dict[str, Any]] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            continue
        function = raw_call.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        raw_arguments = function.get("arguments")
        if isinstance(raw_arguments, dict):
            arguments = raw_arguments
        elif isinstance(raw_arguments, str) and raw_arguments.strip():
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError:
                parsed = {}
            arguments = parsed if isinstance(parsed, dict) else {}
        else:
            arguments = {}
        calls.append({
            "id": str(raw_call.get("id") or "").strip(),
            "name": name,
            "args": arguments,
            "raw": raw_call,
        })
    return calls


def _deepseek_assistant_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    message = _deepseek_message(payload)
    if not message:
        return None
    allowed = ("role", "content", "reasoning_content", "tool_calls")
    assistant_message = {key: message.get(key) for key in allowed if key in message}
    assistant_message["role"] = "assistant"
    if "content" not in assistant_message:
        assistant_message["content"] = ""
    return assistant_message


async def ask_chat_provider_with_mcp_context(
    provider: str,
    question: str,
    context: McpContext,
    config: McpConfig,
    *,
    model: str,
    thinking_mode: str = "none",
) -> str:
    messages = _initial_deepseek_messages(question, context, config, has_tools=False)
    payload = await _chat_completion_for_provider(
        provider,
        _chat_completion_body(provider=provider, model=model, messages=messages, thinking_mode=thinking_mode),
        config,
        context_items=context.content_items,
    )
    answer = _extract_deepseek_text(payload)
    if not answer:
        raise McpProtocolError(f"{MCP_PROVIDER_LABELS.get(provider, provider.title())} returnerade inget textsvar.")
    return answer


async def ask_chat_provider_with_mcp_tools(
    provider: str,
    question: str,
    context: McpContext,
    session: McpHttpSession,
    config: McpConfig,
    tools: list[dict[str, Any]],
    *,
    model: str,
    thinking_mode: str = "none",
) -> tuple[str, int, int, list[str]]:
    declarations = openai_tool_declarations(tools)
    if not declarations:
        answer = await ask_chat_provider_with_mcp_context(
            provider,
            question,
            context,
            config,
            model=model,
            thinking_mode=thinking_mode,
        )
        return answer, 0, context.content_items, []

    allowed_tool_names = {
        str(declaration.get("function", {}).get("name") or "")
        for declaration in declarations
        if isinstance(declaration.get("function"), dict)
    }
    messages = _initial_deepseek_messages(question, context, config, has_tools=True)
    tool_calls = 0
    content_items = context.content_items
    used_tool_names: list[str] = []

    for _step in range(MCP_TOOL_CALL_MAX_STEPS):
        payload = await _chat_completion_for_provider(
            provider,
            _chat_completion_body(
                provider=provider,
                model=model,
                messages=messages,
                tools=declarations,
                thinking_mode=thinking_mode,
            ),
            config,
            context_items=content_items,
        )
        function_calls = _extract_deepseek_tool_calls(payload)
        if not function_calls:
            answer = _extract_deepseek_text(payload)
            if answer:
                if _deepseek_text_has_tool_markup(answer):
                    return _tool_exhausted_answer(tool_calls, used_tool_names), tool_calls, content_items, used_tool_names
                return answer, tool_calls, content_items, used_tool_names
            raise McpProtocolError(f"{MCP_PROVIDER_LABELS.get(provider, provider.title())} returnerade inget textsvar.")

        limited_calls = function_calls[:MCP_TOOL_CALLS_PER_STEP_LIMIT]
        assistant_message = _deepseek_assistant_message(payload)
        if assistant_message:
            if "tool_calls" in assistant_message:
                assistant_message["tool_calls"] = [call["raw"] for call in limited_calls]
            messages.append(assistant_message)

        for call in limited_calls:
            name = call["name"]
            args = call["args"]
            if name not in allowed_tool_names:
                response_payload: dict[str, Any] = {
                    "error": f"Tool {name} ar inte tillatet i MCP-vyn.",
                }
            else:
                with start_span("mcp.tool_call", {"mcp.tool": name}):
                    result = await session.call_tool(name, args)
                _, count, is_error = extract_tool_answer(result)
                content_items += max(1, count)
                tool_calls += 1
                used_tool_names.append(name)
                response_payload = {
                    "is_error": is_error,
                    "result": _limit_tool_payload(result),
                }
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(response_payload, ensure_ascii=False, default=str),
            })

    messages.append({
        "role": "user",
        "content": (
            "Svara nu utifran tool-resultaten ovan. "
            "Om resultatet inte racker, beskriv vilka tools som provades och vad som saknas."
        ),
    })
    payload = await _chat_completion_for_provider(
        provider,
        _chat_completion_body(provider=provider, model=model, messages=messages, tools=None, thinking_mode=thinking_mode),
        config,
        context_items=content_items,
    )
    answer = _extract_deepseek_text(payload)
    if answer:
        if used_tool_names:
            add_span_attributes({"mcp.tools_used": ",".join(sorted(set(used_tool_names)))[:500]})
        if _deepseek_text_has_tool_markup(answer):
            return _tool_exhausted_answer(tool_calls, used_tool_names), tool_calls, content_items, used_tool_names
        return answer, tool_calls, content_items, used_tool_names
    raise McpProtocolError(f"{MCP_PROVIDER_LABELS.get(provider, provider.title())} anvande MCP-tools men returnerade inget textsvar.")


async def ask_deepseek_with_mcp_context(
    question: str,
    context: McpContext,
    config: McpConfig,
    *,
    model: str | None = None,
    thinking_mode: str | None = None,
) -> str:
    return await ask_chat_provider_with_mcp_context(
        "deepseek",
        question,
        context,
        config,
        model=deepseek_model_name(model),
        thinking_mode=normalize_thinking_mode("deepseek", thinking_mode),
    )


async def ask_deepseek_with_mcp_tools(
    question: str,
    context: McpContext,
    session: McpHttpSession,
    config: McpConfig,
    tools: list[dict[str, Any]],
    *,
    model: str | None = None,
    thinking_mode: str | None = None,
) -> tuple[str, int, int, list[str]]:
    return await ask_chat_provider_with_mcp_tools(
        "deepseek",
        question,
        context,
        session,
        config,
        tools,
        model=deepseek_model_name(model),
        thinking_mode=normalize_thinking_mode("deepseek", thinking_mode),
    )


async def ask_gemini_with_mcp_context(
    question: str,
    context: McpContext,
    config: McpConfig,
    *,
    model: str | None = None,
) -> str:
    contents = _initial_gemini_contents(question, context, config, has_tools=False)
    payload = await _call_gemini_generate_content(
        _gemini_body(contents=contents),
        config,
        context_items=context.content_items,
        model=model,
    )
    answer = _extract_gemini_text(payload)
    if not answer:
        raise McpProtocolError("Gemini returnerade inget textsvar.")
    return answer


async def ask_gemini_with_mcp_tools(
    question: str,
    context: McpContext,
    session: McpHttpSession,
    config: McpConfig,
    tools: list[dict[str, Any]],
    *,
    model: str | None = None,
) -> tuple[str, int, int, list[str]]:
    declarations = gemini_function_declarations(tools)
    if not declarations:
        answer = await ask_gemini_with_mcp_context(question, context, config, model=model)
        return answer, 0, context.content_items, []

    allowed_tool_names = {declaration["name"] for declaration in declarations}
    contents = _initial_gemini_contents(question, context, config, has_tools=True)
    tool_calls = 0
    content_items = context.content_items
    used_tool_names: list[str] = []

    for step in range(MCP_TOOL_CALL_MAX_STEPS):
        payload = await _call_gemini_generate_content(
            _gemini_body(contents=contents, declarations=declarations, force_tool=(step == 0 and not context.text)),
            config,
            context_items=content_items,
            model=model,
        )
        function_calls = _extract_gemini_function_calls(payload)
        if not function_calls:
            answer = _extract_gemini_text(payload)
            if answer:
                return answer, tool_calls, content_items, used_tool_names
            raise McpProtocolError("Gemini returnerade inget textsvar.")

        model_content = _candidate_content(payload)
        if model_content:
            contents.append(model_content)

        response_parts: list[dict[str, Any]] = []
        for call in function_calls[:MCP_TOOL_CALLS_PER_STEP_LIMIT]:
            name = call["name"]
            args = call["args"]
            if name not in allowed_tool_names:
                response_payload: dict[str, Any] = {
                    "error": f"Tool {name} ar inte tillatet i MCP-vyn.",
                }
            else:
                with start_span("mcp.tool_call", {"mcp.tool": name}):
                    result = await session.call_tool(name, args)
                _, count, is_error = extract_tool_answer(result)
                content_items += max(1, count)
                tool_calls += 1
                used_tool_names.append(name)
                response_payload = {
                    "is_error": is_error,
                    "result": _limit_tool_payload(result),
                }
            response_parts.append({
                "functionResponse": {
                    "name": name,
                    "response": response_payload,
                }
            })

        if response_parts:
            contents.append({"role": "user", "parts": response_parts})

    contents.append({
        "role": "user",
        "parts": [
            {
                "text": (
                    "Svara nu utifran tool-resultaten ovan. "
                    "Om resultatet inte racker, beskriv vilka tools som provades och vad som saknas."
                )
            }
        ],
    })
    payload = await _call_gemini_generate_content(
        _gemini_body(contents=contents, declarations=None),
        config,
        context_items=content_items,
        model=model,
    )
    answer = _extract_gemini_text(payload)
    if answer:
        if used_tool_names:
            add_span_attributes({"mcp.tools_used": ",".join(sorted(set(used_tool_names)))[:500]})
        return answer, tool_calls, content_items, used_tool_names
    raise McpProtocolError("Gemini anvande MCP-tools men returnerade inget textsvar.")


async def list_mcp_tools(tenant: object = None) -> dict[str, Any]:
    config = mcp_config(tenant)
    missing = [*config.missing]
    missing.extend(brain_missing())
    provider = brain_provider_name()
    model = brain_model_name()
    thinking_mode = normalize_thinking_mode(provider, None)
    provider_options = mcp_brain_options()
    if not config.ready:
        return {
            "server": config.server,
            "tenant": config.tenant,
            "configured": False,
            "mcp_configured": False,
            "brain_configured": brain_configured(),
            "deepseek_configured": deepseek_configured(),
            "openai_configured": openai_configured(),
            "gemini_configured": gemini_configured(),
            "minimax_configured": minimax_configured(),
            "deepseek_thinking_enabled": deepseek_thinking_enabled(),
            "deepseek_reasoning_effort": deepseek_reasoning_effort(),
            "url_configured": bool(config.url),
            "token_configured": bool(config.token),
            "missing": missing,
            "brain": provider,
            "model": model,
            "thinking_mode": thinking_mode,
            "providers": provider_options,
            "tools": [],
            "resources": [],
            "prompts": [],
        }
    session = McpHttpSession(config)
    try:
        await session.initialize()
        tools = await session.list_tools_optional()
        resources = await session.list_resources()
        prompts = await session.list_prompts()
    finally:
        await session.close()
    return {
        "server": config.server,
        "tenant": config.tenant,
        "configured": not missing,
        "mcp_configured": True,
        "brain_configured": brain_configured(),
        "deepseek_configured": deepseek_configured(),
        "openai_configured": openai_configured(),
        "gemini_configured": gemini_configured(),
        "minimax_configured": minimax_configured(),
        "deepseek_thinking_enabled": deepseek_thinking_enabled(),
        "deepseek_reasoning_effort": deepseek_reasoning_effort(),
        "url_configured": True,
        "token_configured": True,
        "missing": missing,
        "brain": provider,
        "model": model,
        "thinking_mode": thinking_mode,
        "providers": provider_options,
        "tools": summarize_tools(tools),
        "resources": summarize_resources(resources),
        "prompts": summarize_prompts(prompts),
    }


async def ask_mcp(
    question: str,
    requested_tool: str | None = None,
    tenant: object = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    thinking_mode: str | None = None,
) -> McpToolCallResult:
    selected_provider = brain_provider_name(provider or requested_tool)
    selected_model = brain_model_name(selected_provider, model)
    selected_thinking = normalize_thinking_mode(selected_provider, thinking_mode)
    config = mcp_config(tenant)
    missing = [*config.missing]
    missing.extend(brain_missing(selected_provider))
    if missing:
        raise McpConfigError(missing)
    context = await collect_mcp_context(config)
    session = McpHttpSession(config)
    try:
        await session.initialize()
        tools = await session.list_tools_optional()
        if selected_provider == "deepseek":
            answer, tool_calls, content_items, tools_used = await ask_deepseek_with_mcp_tools(
                question,
                context,
                session,
                config,
                tools,
                model=selected_model,
                thinking_mode=selected_thinking,
            )
        elif selected_provider in {"openai", "minimax"}:
            answer, tool_calls, content_items, tools_used = await ask_chat_provider_with_mcp_tools(
                selected_provider,
                question,
                context,
                session,
                config,
                tools,
                model=selected_model,
                thinking_mode=selected_thinking,
            )
        else:
            answer, tool_calls, content_items, tools_used = await ask_gemini_with_mcp_tools(
                question,
                context,
                session,
                config,
                tools,
                model=selected_model,
            )
    finally:
        await session.close()
    add_span_attributes({
        "mcp.brain": selected_provider,
        "mcp.model": selected_model,
        "mcp.thinking_mode": selected_thinking,
        "mcp.context_items": content_items,
        "mcp.resources": len(context.resources),
        "mcp.prompts": len(context.prompts),
        "mcp.tool_calls": tool_calls,
        "mcp.tools_used": ",".join(sorted(set(tools_used)))[:500],
    })
    provider_title = MCP_PROVIDER_LABELS.get(selected_provider, selected_provider.title())
    used_tools = tool_calls > 0
    return McpToolCallResult(
        answer=answer,
        tool=f"{selected_provider}_tools" if used_tools else selected_provider,
        tool_title=f"{provider_title} {selected_model} + MCP tools" if used_tools else f"{provider_title} {selected_model}",
        content_items=content_items,
        is_error=False,
        model=selected_model,
        provider=selected_provider,
        thinking_mode=selected_thinking,
        tool_calls=tool_calls,
        tools_used=tools_used,
    )
