"""Orkestrering av MCP-frågor: kontext + tools + vald LLM-hjärna."""
from __future__ import annotations

import json
from typing import Any

from ..observability import add_span_attributes, start_span
from . import protocol, tooling
from .chat import (
    _call_gemini_generate_content,
    _candidate_content,
    _chat_completion_body,
    _chat_completion_for_provider,
    _deepseek_assistant_message,
    _deepseek_text_has_tool_markup,
    _extract_deepseek_text,
    _extract_deepseek_tool_calls,
    _extract_gemini_function_calls,
    _extract_gemini_text,
    _gemini_body,
    _initial_deepseek_messages,
    _initial_gemini_contents,
    _limit_tool_payload,
    _tool_exhausted_answer,
    openai_tool_declarations,
)
from .protocol import (
    MCP_PROVIDER_LABELS,
    MCP_TOOL_CALL_MAX_STEPS,
    MCP_TOOL_CALLS_PER_STEP_LIMIT,
    McpConfig,
    McpConfigError,
    McpContext,
    McpHttpSession,
    McpProtocolError,
    McpToolCallResult,
    mcp_config,
)
from .providers import (
    brain_configured,
    brain_missing,
    brain_model_name,
    brain_provider_name,
    deepseek_configured,
    deepseek_model_name,
    deepseek_reasoning_effort,
    deepseek_thinking_enabled,
    gemini_configured,
    mcp_brain_options,
    minimax_configured,
    normalize_thinking_mode,
    nowaste_configured,
    openai_configured,
)
from .tooling import (
    extract_tool_answer,
    gemini_function_declarations,
    summarize_prompts,
    summarize_resources,
    summarize_tools,
)


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
            "nowaste_configured": nowaste_configured(),
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
    session = protocol.McpHttpSession(config)
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
        "nowaste_configured": nowaste_configured(),
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
    context = await tooling.collect_mcp_context(config)
    session = protocol.McpHttpSession(config)
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
        elif selected_provider in {"nowaste", "openai", "minimax"}:
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
