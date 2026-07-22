from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from .config import settings
from .observability import add_span_attributes, start_span


def _base_url() -> str:
    base = settings.OPENAI_API_BASE_URL.strip().rstrip("/")
    if not base.lower().startswith(("https://", "http://")):
        return "https://api.openai.com/v1"
    return base


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}"}


def _error_detail(response: requests.Response | None) -> str:
    if response is None:
        return ""
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
    except ValueError:
        message = None
    return f" HTTP {response.status_code}: {str(message or 'okant API-fel')[:300]}"


def _transcribe(audio_path: Path, filename: str, content_type: str) -> str:
    model = settings.META_TRANSCRIPTION_MODEL.strip() or "gpt-4o-transcribe"
    with audio_path.open("rb") as handle, start_span(
        "external.openai.transcription",
        {"external.provider": "openai", "llm.model": model, "meta.audio_size_bytes": audio_path.stat().st_size},
    ):
        try:
            response = requests.post(
                f"{_base_url()}/audio/transcriptions",
                headers=_headers(),
                data={
                    "model": model,
                    "language": "sv",
                    "response_format": "json",
                    "prompt": "Pall-ID och godsmarkning ar sjusiffriga nummer. Bevara alla siffror exakt.",
                },
                files={"file": (filename, handle, content_type)},
                timeout=(10, settings.META_ANALYSIS_TIMEOUT_SECONDS),
            )
            add_span_attributes({"external.http_status_code": response.status_code})
            response.raise_for_status()
            transcript = str(response.json().get("text") or "").strip()
        except requests.Timeout as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            raise RuntimeError("OpenAI-transkriberingen nåddes inte inom timeout.") from exc
        except (requests.RequestException, ValueError, AttributeError) as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            response = exc.response if isinstance(exc, requests.RequestException) else None
            raise RuntimeError(f"OpenAI-transkriberingen misslyckades.{_error_detail(response)}") from exc
    if not transcript:
        raise RuntimeError("Ljudfilen gav ingen transkriberad text.")
    return transcript


def _json_content(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("OpenAI returnerade inget analyssvar.")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise RuntimeError("OpenAI returnerade analyssvaret i oväntat format.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI kunde inte tolka Meta-transkriptionen som JSON.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI returnerade inte ett JSON-objekt för Meta-analysen.")
    return parsed


def _extract(transcript: str, instructions: str) -> dict[str, Any]:
    model = settings.META_ANALYSIS_TEXT_MODEL.strip() or "gpt-4o-mini"
    with start_span(
        "external.openai.meta_extract",
        {"external.provider": "openai", "llm.model": model, "llm.input_chars": len(transcript)},
    ):
        try:
            response = requests.post(
                f"{_base_url()}/chat/completions",
                headers={**_headers(), "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": f"Transkription:\n{transcript}"},
                    ],
                },
                timeout=(10, settings.META_ANALYSIS_TIMEOUT_SECONDS),
            )
            add_span_attributes({"external.http_status_code": response.status_code})
            response.raise_for_status()
            return _json_content(response.json())
        except requests.Timeout as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            raise RuntimeError("OpenAI-textanalysen nåddes inte inom timeout.") from exc
        except requests.RequestException as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            raise RuntimeError(f"OpenAI-textanalysen misslyckades.{_error_detail(exc.response)}") from exc


def analyze_audio_with_openai(
    *, audio_path: Path, filename: str, content_type: str, instructions: str
) -> dict[str, Any]:
    """Transkribera ljudet med GPT-4o Transcribe och extrahera Meta-fälten ur texten."""
    return _extract(_transcribe(audio_path, filename, content_type), instructions)
