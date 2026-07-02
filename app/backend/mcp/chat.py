"""Provider-HTTP-anrop och meddelandebyggare för MCP-chatten."""
from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import settings
from ..observability import add_span_attributes, start_span
from .protocol import (
    MCP_PROVIDER_LABELS,
    MCP_TOOL_RESULT_CHAR_LIMIT,
    TEXTUAL_TOOL_CALL_RE,
    McpConfig,
    McpContext,
    McpProtocolError,
)
from .providers import (
    _deepseek_chat_url,
    _gemini_generate_url,
    _openai_base_url,
    deepseek_model_name,
    gemini_model_name,
    normalize_thinking_mode,
    nowaste_api_key,
    nowaste_base_url,
)
from .tooling import gemini_function_declarations


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
    if provider == "nowaste":
        return f"{nowaste_base_url()}/chat/completions"
    if provider == "openai":
        return f"{_openai_base_url()}/chat/completions"
    if provider == "minimax":
        return settings.MINIMAX_API_URL.strip() or "https://api.minimax.io/v1/chat/completions"
    return ""


def _chat_provider_api_key(provider: str) -> str:
    if provider == "deepseek":
        return settings.DEEPSEEK_API_KEY.strip()
    if provider == "nowaste":
        return nowaste_api_key()
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
