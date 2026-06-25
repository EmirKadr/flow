from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import log_and_commit as audit_log_and_commit
from ..business_scope import default_business_tenant, user_business_id
from ..deps import get_db, require_view_access
from ..mcp_service import (
    McpConfigError,
    McpProtocolError,
    ask_mcp,
    brain_configured,
    brain_missing,
    brain_model_name,
    brain_provider_name,
    deepseek_configured,
    deepseek_reasoning_effort,
    deepseek_thinking_enabled,
    gemini_configured,
    list_mcp_tools,
    mcp_brain_options,
    minimax_configured,
    normalize_thinking_mode,
    openai_configured,
)
from ..models import Business, User
from ..observability import add_span_attributes, start_span


router = APIRouter(prefix="/api/mcp", tags=["mcp"])
logger = logging.getLogger(__name__)


class McpQuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    tool: str | None = Field(default=None, max_length=160)
    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=120)
    thinking_mode: str | None = Field(default=None, max_length=40)


class McpQuestionResponse(BaseModel):
    answer: str
    tool: str
    tool_title: str
    server: str
    tenant: str
    content_items: int
    model: str | None = None
    provider: str | None = None
    thinking_mode: str | None = None
    tool_calls: int = 0
    tools_used: list[str] = Field(default_factory=list)


def _mcp_tenant(db: Session, user: User) -> str:
    business_id = user_business_id(db, user)
    business = db.get(Business, business_id) if business_id is not None and hasattr(db, "get") else None
    tenant = str(getattr(business, "tenant", "") or "").strip().lower()
    if tenant:
        return tenant
    return str(default_business_tenant(getattr(business, "code", None)) or "").strip().lower()


def _audit_mcp_query(
    db: Session,
    user: User,
    action: str,
    payload: dict,
) -> None:
    audit_log_and_commit(
        db,
        entity_type="mcp_query",
        entity_id=0,
        action=action,
        old_value=None,
        new_value=payload,
        user_id=getattr(user, "id", None),
        business_id=getattr(user, "business_id", None),
        logger=logger,
        context=f"mcp query audit event action={action}",
    )


@router.get("/status")
async def mcp_status(
    user: User = Depends(require_view_access("mcp", "view")),
    db: Session = Depends(get_db),
) -> dict:
    tenant = _mcp_tenant(db, user)
    with start_span("mcp.status", {"mcp.tenant": tenant}):
        try:
            payload = await list_mcp_tools(tenant)
            add_span_attributes({
                "mcp.configured": bool(payload.get("configured")),
                "mcp.tools": len(payload.get("tools") or []),
                "mcp.resources": len(payload.get("resources") or []),
                "mcp.prompts": len(payload.get("prompts") or []),
                "mcp.brain": payload.get("brain") or "",
            })
            return payload
        except McpProtocolError as exc:
            add_span_attributes({"mcp.status": "error", "mcp.error_type": type(exc).__name__})
            missing = brain_missing()
            return {
                "server": "noeffect",
                "tenant": tenant,
                "configured": False,
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
                "brain": brain_provider_name(),
                "model": brain_model_name(),
                "thinking_mode": normalize_thinking_mode(brain_provider_name(), None),
                "providers": mcp_brain_options(),
                "tools": [],
                "resources": [],
                "prompts": [],
                "error": str(exc),
            }


@router.post("/query", response_model=McpQuestionResponse)
async def mcp_query(
    payload: McpQuestionRequest,
    user: User = Depends(require_view_access("mcp", "edit")),
    db: Session = Depends(get_db),
) -> McpQuestionResponse:
    question = payload.question.strip()
    tenant = _mcp_tenant(db, user)
    with start_span(
        "mcp.query",
        {"mcp.question_chars": len(question), "mcp.requested_tool": payload.tool or "", "mcp.tenant": tenant},
    ):
        try:
            result = await ask_mcp(
                question,
                payload.tool,
                tenant,
                provider=payload.provider,
                model=payload.model,
                thinking_mode=payload.thinking_mode,
            )
        except McpConfigError as exc:
            add_span_attributes({"mcp.status": "missing_config"})
            _audit_mcp_query(
                db,
                user,
                "query_failed",
                {
                    "server": "noeffect",
                    "tenant": tenant,
                    "status": "missing_config",
                    "missing": exc.missing,
                    "question_chars": len(question),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"MCP saknar {', '.join(exc.missing)} i servermiljön.",
            ) from exc
        except McpProtocolError as exc:
            add_span_attributes({"mcp.status": "error", "mcp.error_type": type(exc).__name__})
            _audit_mcp_query(
                db,
                user,
                "query_failed",
                {
                    "server": "noeffect",
                    "tenant": tenant,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "tool": payload.tool or brain_provider_name(),
                    "question_chars": len(question),
                },
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        if result.is_error:
            add_span_attributes({"mcp.status": "tool_error", "mcp.tool": result.tool})
            _audit_mcp_query(
                db,
                user,
                "query_failed",
                {
                    "server": "noeffect",
                    "tenant": tenant,
                    "status": "tool_error",
                    "tool": result.tool,
                    "model": result.model,
                    "provider": result.provider,
                    "thinking_mode": result.thinking_mode,
                    "tool_calls": result.tool_calls,
                    "tools_used": result.tools_used or [],
                    "question_chars": len(question),
                    "answer_chars": len(result.answer),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"MCP-verktyget {result.tool} returnerade ett fel.",
            )

        _audit_mcp_query(
            db,
            user,
            "query_success",
            {
                "server": "noeffect",
                "tenant": tenant,
                "status": "ok",
                "tool": result.tool,
                "model": result.model,
                "provider": result.provider,
                "thinking_mode": result.thinking_mode,
                "tool_calls": result.tool_calls,
                "tools_used": result.tools_used or [],
                "question_chars": len(question),
                "answer_chars": len(result.answer),
                "content_items": result.content_items,
            },
        )
        add_span_attributes({
            "mcp.status": "ok",
            "mcp.tool": result.tool,
            "mcp.answer_chars": len(result.answer),
        })
        return McpQuestionResponse(
            answer=result.answer,
            tool=result.tool,
            tool_title=result.tool_title,
            server="noeffect",
            tenant=tenant,
            content_items=result.content_items,
            model=result.model,
            provider=result.provider,
            thinking_mode=result.thinking_mode,
            tool_calls=result.tool_calls,
            tools_used=result.tools_used or [],
        )
