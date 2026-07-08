from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import socket
from typing import Any, Literal
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_db
from ..public_dpak_agent import PublicDpakAgentError, run_public_dpak_agent
from ..public_dpak_service import dataset_status, public_dpak_business_code


router = APIRouter(prefix="/api/public/dpak-chat", tags=["public-dpak-chat"])
logger = logging.getLogger(__name__)
MAX_PUBLIC_DPAK_VOICE_BYTES = 3 * 1024 * 1024
MAX_PUBLIC_DPAK_VOICE_BASE64_CHARS = 4 * 1024 * 1024 + 512
THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


class PublicDpakModelProviderError(Exception):
    pass


class PublicDpakMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class PublicDpakVoiceAttachment(BaseModel):
    mime_type: str = Field(min_length=1, max_length=120)
    data_base64: str = Field(min_length=1, max_length=MAX_PUBLIC_DPAK_VOICE_BASE64_CHARS)
    duration_ms: int | None = Field(default=None, ge=0, le=180000)
    transcript: str | None = Field(default=None, max_length=4000)

    @field_validator("mime_type")
    @classmethod
    def _validate_mime_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized.startswith("audio/"):
            raise ValueError("Röstinspelningen måste vara ljud.")
        return normalized

    @field_validator("data_base64")
    @classmethod
    def _validate_data_base64(cls, value: str) -> str:
        normalized = value.strip()
        if "," in normalized and normalized.lower().startswith("data:"):
            normalized = normalized.split(",", 1)[1]
        try:
            decoded = base64.b64decode(normalized, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Röstinspelningen kunde inte läsas som base64.") from exc
        if len(decoded) > MAX_PUBLIC_DPAK_VOICE_BYTES:
            raise ValueError("Röstinspelningen är för stor.")
        return normalized

    @field_validator("transcript")
    @classmethod
    def _clean_transcript(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class PublicDpakChatRequest(BaseModel):
    messages: list[PublicDpakMessage] = Field(min_length=1)
    business_code: str | None = Field(default=None, max_length=50)
    token: str | None = Field(default=None, max_length=240)
    voice: PublicDpakVoiceAttachment | None = None


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


def _messages_payload_with_voice(payload: PublicDpakChatRequest) -> list[dict[str, str]]:
    messages = _messages_payload(payload.messages)
    if not payload.voice or not messages:
        return messages
    seconds = round((payload.voice.duration_ms or 0) / 1000)
    details = [
        "Röstinspelning bifogades i API-anropet.",
        f"Längd: {seconds} s.",
        f"Format: {payload.voice.mime_type}.",
    ]
    if payload.voice.transcript:
        details.append(f"Webbläsarens texttolkning: {payload.voice.transcript}")
    messages[-1]["content"] = f"{messages[-1]['content']}\n\n[{' '.join(details)}]"
    return messages


def _public_dpak_agent_api_key() -> str:
    return settings.PUBLIC_DPAK_AGENT_API_KEY.strip() or settings.MINIMAX_API_KEY.strip()


def _public_dpak_agent_api_url() -> str:
    return settings.PUBLIC_DPAK_AGENT_API_URL.strip() or settings.MINIMAX_API_URL.strip()


def _public_dpak_agent_model() -> str:
    return settings.PUBLIC_DPAK_AGENT_MODEL.strip() or settings.MINIMAX_MODEL.strip()


def _public_dpak_agent_timeout() -> int:
    return int(settings.PUBLIC_DPAK_AGENT_TIMEOUT_SECONDS or settings.MINIMAX_TIMEOUT_SECONDS)


def _public_dpak_agent_temperature() -> float | None:
    raw = settings.PUBLIC_DPAK_AGENT_TEMPERATURE.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise PublicDpakModelProviderError("PUBLIC_DPAK_AGENT_TEMPERATURE måste vara ett tal.")


def _public_dpak_agent_extra_body() -> dict[str, Any]:
    raw = settings.PUBLIC_DPAK_AGENT_EXTRA_BODY_JSON.strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PublicDpakModelProviderError("PUBLIC_DPAK_AGENT_EXTRA_BODY_JSON måste vara giltig JSON.") from exc
    if not isinstance(parsed, dict):
        raise PublicDpakModelProviderError("PUBLIC_DPAK_AGENT_EXTRA_BODY_JSON måste vara ett JSON-objekt.")
    return parsed


def _provider_error_detail(raw_body: str) -> str:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body[:500]
    if isinstance(payload, dict):
        detail = payload.get("error") or payload.get("detail") or payload.get("message")
        if isinstance(detail, dict):
            return str(detail.get("message") or detail)[:500]
        if detail:
            return str(detail)[:500]
    return raw_body[:500]


def _clean_provider_answer(answer: Any) -> str:
    if isinstance(answer, list):
        parts = [
            str(item.get("text") or item.get("content") or "")
            for item in answer
            if isinstance(item, dict)
        ]
        answer = "\n".join(part for part in parts if part)
    return THINK_BLOCK_RE.sub("", str(answer or "")).strip()


def _call_public_dpak_agent_model(payload: dict[str, Any]) -> str:
    api_key = _public_dpak_agent_api_key()
    if not api_key:
        raise PublicDpakModelProviderError("D-pak-agenten saknar modellnyckel i servermiljön.")
    request_payload = {**payload, "model": _public_dpak_agent_model()}
    request_payload.update(_public_dpak_agent_extra_body())
    body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _public_dpak_agent_api_url(),
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_public_dpak_agent_timeout()) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        raise PublicDpakModelProviderError(
            f"Modell-API svarade HTTP {exc.code}: {_provider_error_detail(raw_error)}"
        ) from exc
    except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
        raise PublicDpakModelProviderError("Modell-API svarade inte inom timeout.") from exc
    except Exception as exc:
        logger.exception("Public D-pak model request failed unexpectedly.")
        raise PublicDpakModelProviderError(f"Modell-anropet misslyckades: {type(exc).__name__}") from exc

    try:
        data = json.loads(raw)
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise PublicDpakModelProviderError("Modell-API svarade utan textinnehåll.") from exc
    cleaned = _clean_provider_answer(answer)
    if not cleaned:
        raise PublicDpakModelProviderError("Modell-API returnerade ett tomt svar.")
    return cleaned


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
    model_name = _public_dpak_agent_model()
    if not _public_dpak_agent_api_key():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="D-pak-agenten saknar PUBLIC_DPAK_AGENT_API_KEY eller MINIMAX_API_KEY i servermiljön.",
        )
    try:
        agent_result = run_public_dpak_agent(
            db,
            messages=_messages_payload_with_voice(payload),
            business_code=business,
            call_model=_call_public_dpak_agent_model,
            model_name=model_name,
            max_tokens=settings.PUBLIC_DPAK_AGENT_MAX_TOKENS,
            temperature=_public_dpak_agent_temperature(),
        )
    except PublicDpakModelProviderError as exc:
        logger.warning("Public D-pak model provider failed.", exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
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
        model=str(agent_result.get("model") or model_name),
        status=status_payload,
        warning=agent_result.get("warning"),
    )
