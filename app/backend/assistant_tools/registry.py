"""Register för apphjälpens read-only-tools.

Varje tool har behörighetsmetadata (view_id + min_level) som motsvarar
sidebarens vybehörigheter. Enforcement är avstängd tills
ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS sätts till true — då filtreras tools
per användarens vybehörighet med samma regler som sidorna.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..models import User
from ..user_access import can_access_view
from .common import ToolInputError

logger = logging.getLogger(__name__)

TOOL_RESULT_CHAR_LIMIT = 4000


@dataclass(frozen=True)
class AssistantTool:
    name: str
    title: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[Session, User, dict[str, Any]], Any]
    view_id: str
    min_level: str = "view"
    tags: tuple[str, ...] = field(default_factory=tuple)


_REGISTRY: dict[str, AssistantTool] = {}


def register_tool(
    *,
    name: str,
    title: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    view_id: str,
    min_level: str = "view",
    tags: tuple[str, ...] = (),
) -> Callable[[Callable[[Session, User, dict[str, Any]], Any]], Callable[[Session, User, dict[str, Any]], Any]]:
    def decorator(handler: Callable[[Session, User, dict[str, Any]], Any]):
        if name in _REGISTRY:
            raise ValueError(f"Tool-namnet '{name}' är redan registrerat.")
        schema = parameters or {"type": "object", "properties": {}}
        _REGISTRY[name] = AssistantTool(
            name=name,
            title=title,
            description=description,
            parameters=schema,
            handler=handler,
            view_id=view_id,
            min_level=min_level,
            tags=tags,
        )
        return handler

    return decorator


def all_tools() -> list[AssistantTool]:
    return sorted(_REGISTRY.values(), key=lambda tool: tool.name)


def tool_by_name(name: str) -> AssistantTool | None:
    return _REGISTRY.get(str(name or "").strip())


def allowed_tools_for(user: User, role_access: dict | None = None) -> list[AssistantTool]:
    """Tools användaren får köra. Utan enforcement: alla inloggade får alla tools."""
    tools = all_tools()
    if not settings.ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS:
        return tools
    return [tool for tool in tools if can_access_view(user, role_access, tool.view_id, tool.min_level)]


def openai_tool_declarations(tools: list[AssistantTool]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def _limit_result(payload: Any, max_chars: int = TOOL_RESULT_CHAR_LIMIT) -> Any:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return payload
    return {
        "truncated": True,
        "content": text[:max_chars],
        "note": "Tool-resultatet kortades av innan det skickades tillbaka till modellen.",
    }


def run_tool(
    db: Session,
    user: User,
    name: str,
    arguments: dict[str, Any] | None,
    *,
    allowed: list[AssistantTool] | None = None,
) -> dict[str, Any]:
    """Kör ett tool och returnera ett JSON-vänligt resultat, aldrig ett undantag."""
    tool = tool_by_name(name)
    permitted = allowed if allowed is not None else allowed_tools_for(user)
    if tool is None or tool not in permitted:
        return {"error": f"Tool '{name}' finns inte eller är inte tillgängligt."}
    args = arguments if isinstance(arguments, dict) else {}
    try:
        result = tool.handler(db, user, args)
    except ToolInputError as exc:
        return {"error": str(exc)}
    except HTTPException as exc:
        # T.ex. verksamhetsscope-404 från business_scope — förklara för modellen.
        return {"error": str(exc.detail)}
    except Exception as exc:  # noqa: BLE001 - modellen ska få ett städat fel, aldrig en stacktrace
        logger.exception("Assistant-tool %s misslyckades", name)
        try:
            db.rollback()
        except Exception:  # pragma: no cover - rollback är bara städning
            pass
        return {"error": f"Tool '{name}' misslyckades internt ({type(exc).__name__})."}
    return {"tool": name, "result": _limit_result(result)}
