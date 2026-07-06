"""Tool-loop för apphjälpens chatt: OpenAI-kompatibel function calling.

Loopen är providerneutral: den får en `call_model`-funktion som tar en
request-body och returnerar providerns JSON-svar. Tool-anrop körs via
registret (read-only, verksamhetsscopade) och resultaten skickas tillbaka
som `role=tool`-meddelanden tills modellen svarar med text.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..config import settings
from ..models import User
from ..observability import add_span_attributes, start_span
from .registry import AssistantTool, allowed_tools_for, openai_tool_declarations, run_tool


@dataclass
class ToolLoopResult:
    answer: str
    tool_calls: int = 0
    tools_used: list[str] = field(default_factory=list)
    tool_errors: int = 0
    steps: int = 1


def _response_message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    return message if isinstance(message, dict) else {}


def _parse_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    raw_calls = message.get("tool_calls")
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
        calls.append({"id": str(raw_call.get("id") or "").strip(), "name": name, "args": arguments})
    return calls


def _assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    allowed = ("role", "content", "reasoning_content", "tool_calls")
    result = {key: message.get(key) for key in allowed if key in message}
    result["role"] = "assistant"
    result.setdefault("content", "")
    return result


def run_tool_loop(
    db: Session,
    user: User,
    payload: dict[str, Any],
    *,
    call_model: Callable[[dict[str, Any]], dict[str, Any]],
    role_access: dict | None = None,
    tools: list[AssistantTool] | None = None,
) -> ToolLoopResult:
    """Kör chatten med tools tills modellen ger ett textsvar eller stegen tar slut."""
    available = tools if tools is not None else allowed_tools_for(user, role_access)
    body = dict(payload)
    if not settings.ASSISTANT_TOOLS_ENABLED or not available:
        response = call_model(body)
        return ToolLoopResult(answer=str(_response_message(response).get("content") or ""))

    body["messages"] = list(payload.get("messages") or [])
    body["tools"] = openai_tool_declarations(available)
    body["tool_choice"] = "auto"
    if body.get("max_tokens"):
        body["max_tokens"] = max(int(body["max_tokens"]), 1200)

    total_calls = 0
    tools_used: list[str] = []
    tool_errors = 0
    max_steps = max(1, int(settings.ASSISTANT_TOOLS_MAX_STEPS))
    calls_per_step = max(1, int(settings.ASSISTANT_TOOLS_MAX_CALLS_PER_STEP))

    for step in range(1, max_steps + 1):
        if step == max_steps:
            # Sista varvet: tvinga fram ett textsvar i stället för fler tool-anrop.
            body["tool_choice"] = "none"
        response = call_model(body)
        message = _response_message(response)
        calls = _parse_tool_calls(message) if body.get("tool_choice") != "none" else []
        if not calls:
            return ToolLoopResult(
                answer=str(message.get("content") or ""),
                tool_calls=total_calls,
                tools_used=list(dict.fromkeys(tools_used)),
                tool_errors=tool_errors,
                steps=step,
            )

        body["messages"].append(_assistant_message(message))
        for call in calls[:calls_per_step]:
            with start_span(
                "agent.tool_call",
                {"agent.tool_name": call["name"], "agent.tool_step": step},
            ):
                result = run_tool(db, user, call["name"], call["args"], allowed=available)
                failed = isinstance(result, dict) and "error" in result and "tool" not in result
                add_span_attributes({"agent.tool_failed": failed})
            total_calls += 1
            tools_used.append(call["name"])
            if failed:
                tool_errors += 1
            body["messages"].append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"] or call["name"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    # Ska inte nås: sista steget kör med tool_choice=none och returnerar ovan.
    return ToolLoopResult(
        answer="",
        tool_calls=total_calls,
        tools_used=list(dict.fromkeys(tools_used)),
        tool_errors=tool_errors,
        steps=max_steps,
    )
