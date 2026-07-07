from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..deps import get_db
from ..public_dpak_service import answer_public_dpak_question, dataset_status, public_dpak_business_code
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


def _verify_public_token(token: str | None) -> None:
    expected = settings.PUBLIC_DPAK_LINK_TOKEN.strip()
    if expected and token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ogiltig publik länk.")


def _messages_payload(messages: list[PublicDpakMessage]) -> list[dict[str, str]]:
    return [message.model_dump() for message in messages]


def build_public_dpak_minimax_payload(
    messages: list[PublicDpakMessage],
    deterministic: dict[str, Any],
    status_payload: dict[str, Any],
) -> dict[str, Any]:
    system_prompt = """
Du svarar på svenska åt en publik D-pak-chatt för kunder.

Du får redan färdigräknade siffror, tabellrader och datatäckning från backend.
Ändra aldrig tal, datum, artikelnummer, leverantörsnamn eller tabellvärden.
Hitta inte på ny data och säg inte att du kan hämta mer data live.
Om tabellrader finns ska du bara sammanfatta dem kort; tabellen skickas separat av appen.
Svara kort, tydligt och utan markdown-tabell.
""".strip()
    user_payload = {
        "conversation": [message.model_dump() for message in messages[-30:]],
        "calculated": {
            "answer": deterministic.get("answer"),
            "table": deterministic.get("table") or [],
            "context": deterministic.get("context") or {},
        },
        "dataset_status": status_payload,
    }
    return {
        "model": settings.MINIMAX_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "max_tokens": max(settings.MINIMAX_MAX_TOKENS, 900),
        "temperature": 0.1,
        "reasoning_split": True,
    }


@router.get("/status")
def public_dpak_status(
    token: str | None = Query(default=None, max_length=240),
    business_code: str | None = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _verify_public_token(token)
    return dataset_status(db, public_dpak_business_code(business_code))


@router.post("/message", response_model=PublicDpakChatResponse)
async def public_dpak_message(
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
    deterministic = answer_public_dpak_question(
        db,
        messages=_messages_payload(payload.messages),
        business_code=business,
    )
    answer = str(deterministic.get("answer") or "")
    model = str(deterministic.get("model") or "deterministic-dpak")
    warning = None

    if settings.MINIMAX_API_KEY.strip():
        try:
            minimax_payload = build_public_dpak_minimax_payload(payload.messages, deterministic, status_payload)
            answer = await run_in_threadpool(_call_minimax, minimax_payload)
            model = settings.MINIMAX_MODEL
        except Exception as exc:
            logger.warning("Public D-pak MiniMax response failed; using deterministic answer.", exc_info=True)
            warning = f"MiniMax kunde inte formatera svaret ({type(exc).__name__})."

    return PublicDpakChatResponse(
        answer=answer,
        table=list(deterministic.get("table") or []),
        model=model,
        status=status_payload,
        warning=warning,
    )
