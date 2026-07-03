"""MCP-protokoll: konstanter, konfiguration, fel och HTTP-session mot MCP-servern."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any

import httpx

from ..config import settings
from ..external_data_client import clean_data_source_tenant
from ..observability import add_span_attributes, start_span


try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


ROOT_DIR = Path(__file__).resolve().parents[3]
SERVER_NAME = "noeffect"
DEFAULT_TOKEN_ENV_TEMPLATE = "NOEFFECT_{tenant}_TOKEN"
CLIENT_NAME = "flow-mcp-view"
CLIENT_VERSION = "0.1.5"
MCP_LLM_OPENAI_API_KEY_ENV = "MCP_LLM_OPENAI_API_KEY"
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
MCP_PROVIDER_ORDER = ("deepseek", "nowaste", "openai", "gemini", "minimax")
MCP_PROVIDER_LABELS = {
    "deepseek": "DeepSeek",
    "nowaste": "NoWaste",
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

