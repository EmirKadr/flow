from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_db
from ..public_dpak_agent import PublicDpakAgentError, run_public_dpak_agent
from ..public_dpak_service import dataset_status, public_dpak_business_code
from .assistant import _call_minimax


router = APIRouter(prefix="/api/public/dpak-chat", tags=["public-dpak-chat"])
logger = logging.getLogger(__name__)


class PublicDpakMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class PublicDpakChatRequest(BaseModel):
    messages: list[PublicDpakMessage] = Field(min_length=1)
    business_code: str | None = Field(default=None, max_length=50)
    token: str | None = Field(default=None, max_length=240)


class PublicDpakChatResponse(BaseModel):
    answer: str
    table: list[dict[str, Any]]
    model: str
    status: dict[str, Any]
    warning: str | None = None


def _verify_public_token(_token: str | None) -> None:
    return None


def _messages_payload(messages: list[PublicDpakMessage]) -> list[dict[str, str]]:
    return [message.model_dump() for message in messages]


@router.get("/status")
def public_dpak_status(
    token: str | None = Query(default=None, max_length=240),
    business_code: str | None = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _verify_public_token(token)
    return dataset_status(db, public_dpak_business_code(business_code))


@router.post("/message", response_model=PublicDpakChatResponse)
def public_dpak_message(
    payload: PublicDpakChatRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PublicDpakChatResponse:
    _verify_public_token(payload.token or request.query_params.get("token"))
    if payload.messages[-1].role != "user":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Den senaste dialograden måste vara en användarfråga.",
        )

    business = public_dpak_business_code(payload.business_code)
    status_payload = dataset_status(db, business)
    if not settings.MINIMAX_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="D-pak-agenten saknar MINIMAX_API_KEY i servermiljön.",
        )
    try:
        agent_result = run_public_dpak_agent(
            db,
            messages=_messages_payload(payload.messages),
            business_code=business,
            call_model=_call_minimax,
        )
    except PublicDpakAgentError as exc:
        logger.warning("Public D-pak raw agent failed.", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Public D-pak raw agent crashed.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"D-pak-agenten kunde inte analysera frågan ({type(exc).__name__}).",
        ) from exc

    return PublicDpakChatResponse(
        answer=str(agent_result.get("answer") or ""),
        table=list(agent_result.get("table") or []),
        model=str(agent_result.get("model") or settings.MINIMAX_MODEL),
        status=status_payload,
        warning=agent_result.get("warning"),
    )
