from __future__ import annotations

import json
import logging
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..deps import get_current_user, get_db
from ..models import Area, User
from ..settings_service import get_role_view_access
from ..user_access import (
    LEGACY_SUPER_USER_ROLE,
    ROLE_VIEW_IDS,
    SUPER_USER_ROLE,
    primary_role,
    role_view_access_level,
)


router = APIRouter(prefix="/api/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)

MAX_QUESTIONS_PER_SESSION = 10
SESSION_COUNT_KEY = "assistant_question_count"
MAX_DIALOG_MESSAGES = 21
MAX_CONTEXT_CHARS = 24000
MAX_DOC_CHARS = 5200
MAX_REPO_CONTEXT_CHARS = 14000
MAX_REPO_MATCHES = 12
ROOT_DIR = Path(__file__).resolve().parents[3]
WIKI_DIR = ROOT_DIR / "wiki"
THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.IGNORECASE | re.DOTALL)
CHALLENGE_RE = re.compile(
    r"(du har fel|stämmer inte|stammer inte|jo\b|visst|det finns visst|gör det visst|gor det visst|"
    r"gör de visst|gor de visst|kolla koden|kolla repot|hela repot|sök i repot|sok i repot|"
    r"sök igen|sok igen|är du säker|ar du saker)",
    re.IGNORECASE,
)
REPO_TEXT_SUFFIXES = {
    ".bat",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sql",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
REPO_TEXT_NAMES = {"AGENTS.md", "API_ROUTES.md", "Dockerfile", "render.yaml"}
REPO_EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "env",
    "node_modules",
    "release",
    "venv",
}
REPO_EXCLUDED_NAMES = {
    ".env",
    ".env.local",
    ".flow-cli-cookies.txt",
    "flow_local.db",
    "flow_local.db.syncing",
    "deploy_probe.sqlite",
}

BASE_WIKI_DOCS = [
    "index.md",
    "user-guide.md",
    "user-events.md",
    "error-reference.md",
    "troubleshooting-chat.md",
    "ui-map.md",
]

PAGE_WIKI_DOCS = {
    "/index.html": ["bemanning-schedule.md"],
    "/": ["bemanning-schedule.md"],
    "/overblick.html": ["overview-page.md"],
    "/personer.html": ["persons.md"],
    "/personimport.html": ["persons.md"],
    "/aktiviteter.html": ["activities-areas.md"],
    "/aktivitetimport.html": ["activities-areas.md"],
    "/anvandare.html": ["users-settings.md"],
    "/anvandarimport.html": ["users-settings.md"],
    "/verksamheter.html": ["users-settings.md"],
    "/installningar.html": ["users-settings.md"],
    "/historik.html": ["history-audit.md"],
    "/produktivitet.html": ["productivity.md"],
    "/uppladdningar.html": ["warehouse-tools.md"],
    "/bearbeta.html": ["warehouse-tools.md"],
    "/dela.html": ["warehouse-tools.md"],
}

PAGE_VIEW_IDS = {
    "/index.html": "schedule",
    "/": "schedule",
    "/overblick.html": "overview",
    "/personer.html": "persons",
    "/personimport.html": "personImport",
    "/aktiviteter.html": "activities",
    "/aktivitetimport.html": "activityImport",
    "/anvandare.html": "users",
    "/anvandarimport.html": "userImport",
    "/verksamheter.html": "businesses",
    "/installningar.html": "appSettings",
    "/historik.html": "analytics",
    "/produktivitet.html": "productivity",
    "/uppladdningar.html": "allocationUploads",
    "/bearbeta.html": "allocationProcess",
    "/dela.html": "allocationSplit",
}

ROLE_LABELS = {
    "admin": "Administratör",
    "leader": "Ledare",
    "staffing_manager": "Bemanningsansvarig",
    "viewer": "Visare",
    "warehouse_clerk": "Lagerkontorist",
    "article_placer": "Artikelplacerare",
    SUPER_USER_ROLE: "Super User",
    LEGACY_SUPER_USER_ROLE: "Super User",
}

VIEW_LABELS = {
    "schedule": "Bemanning",
    "overview": "Översikt",
    "productivity": "Produktivitet",
    "allocationUploads": "Uppladdningar",
    "allocationProcess": "Bearbeta",
    "allocationSplit": "Dela",
    "persons": "Personer",
    "personImport": "Personimport",
    "activities": "Aktiviteter",
    "activityImport": "Aktivitetsimport",
    "areas": "Områden",
    "analytics": "Historik",
    "users": "Användare",
    "userImport": "Användarimport",
    "appSettings": "Inställningar",
    "sidebarLayout": "Menyredigering",
    "roleAccess": "Vybehörigheter",
}

VIEW_CONTEXT_ORDER = [
    "schedule",
    "overview",
    "productivity",
    "allocationUploads",
    "allocationProcess",
    "allocationSplit",
    "persons",
    "personImport",
    "activities",
    "activityImport",
    "areas",
    "analytics",
    "users",
    "userImport",
    "appSettings",
    "sidebarLayout",
    "roleAccess",
]

SYSTEM_PROMPT_TEMPLATE = """Du är Apphjälpen för flow.

Du är en kunnig supportperson för användningen av appen. Ditt jobb är att hjälpa
personen som ställer frågor medan de använder programmet.

Regler:
- Svara alltid på svenska med korrekta å, ä och ö. Om källtexten saknar
  prickar/ringar, återställ dem i svaret: "är", "på", "frågor", "användare".
- Var konkret och handlingsinriktad. Ge steg om användaren frågar hur man gör.
- Chattpanelen är smal. Skriv för en liten dialogruta: korta stycken, korta
  punktlistor och tydliga delrubriker.
- Undvik markdown-tabeller. Om du vill jämföra orsak och lösning, skriv hellre
  som korta block med "Orsak:", "Kontroll:" och "Lösning:".
- Undvik stora markdownrubriker som ##. Använd hellre fet kort rubrik.
- Håll svaret så kort som frågan tillåter. Vid felsökning: börja med mest
  sannolik orsak och nästa konkreta steg.
- Wikin är huvudkälla och gräns. Om wikin inte säger att en funktion, knapp,
  vy eller export finns ska du svara "Nej, enligt wikin finns det inte" eller
  "Det är inte dokumenterat i wikin". Gissa inte fram möjliga knappar, API:er,
  /docs, exportvägar eller alternativa lösningar.
- Om användaren invänder och repo-sökning finns i kontexten ska du använda
  repo-sökningen för ett definitivt ja/nej. Säg tydligt om repo-sökningen
  hittade stöd eller inte.
- Om något kan bero på behörighet, roll, vyåtkomst, saknade filer, session eller
  serverfel ska du säga vilken kontroll användaren/admin ska göra.
- Använd användarkontexten nedan först när frågan gäller saknade menyer,
  knappar eller behörighet. Om kontexten säger att användaren saknar en vy,
  säg det direkt. Om kontexten säger `view` men inte `edit`, säg att
  användaren kan se men inte ändra.
- Om lösningen kräver sidan Användare, Vybehörigheter, rolländring, Super User,
  admin eller annan skyddad inställning: säg tydligt att en vanlig användare
  inte kan göra det själv. Formulera som "Be en admin/Super User kontrollera..."
  i stället för att instruera användaren att själv gå dit.
- Bearbeta är en egen sidebar-vy (`bearbeta.html`) och inte samma sak som Dela.
  Om Bearbeta saknas krävs normalt Super User eller vyåtkomst till
  `allocationProcess`; lagerroller har som standard Uppladdningar och Dela men
  inte Bearbeta.
- Om du behöver mer information: be om exakt vy, knapp, feltext/toast och om det
  gäller webb eller Windows-appen.
- Namn på knappar, vyer och feltexter ska matcha appen när de finns i kontexten.

Aktuell sida: {page_path}

Användarkontext:
{user_context}

Wikiutdrag och projektkunskap:
{wiki_context}

Repo-sökning:
{repo_context}
"""


class AssistantMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantChatRequest(BaseModel):
    messages: list[AssistantMessage] = Field(min_length=1, max_length=MAX_DIALOG_MESSAGES)
    page_path: str | None = Field(default=None, max_length=220)


class AssistantChatResponse(BaseModel):
    answer: str
    model: str
    remaining_questions: int


def _session_question_count(request: Request) -> int:
    try:
        return max(0, int(request.session.get(SESSION_COUNT_KEY, 0) or 0))
    except (TypeError, ValueError):
        return 0


def _last_user_question(messages: list[AssistantMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _query_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_åäöÅÄÖ-]{3,}", text.lower())
        if token not in {"och", "eller", "att", "det", "den", "som", "for", "med", "har", "hur", "varfor"}
    }


def _query_tokens_sv(text: str) -> set[str]:
    stop_words = {
        "och",
        "eller",
        "att",
        "det",
        "den",
        "som",
        "för",
        "for",
        "med",
        "har",
        "hur",
        "varför",
        "varfor",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_åäöÅÄÖ-]{3,}", text.lower())
        if token not in stop_words
    }


def should_search_repo(messages: list[AssistantMessage]) -> bool:
    return bool(CHALLENGE_RE.search(_last_user_question(messages)))


def _read_wiki_doc(filename: str) -> str:
    if "/" in filename or "\\" in filename:
        return ""
    path = WIKI_DIR / filename
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _ranked_wiki_docs(query: str, page_path: str | None) -> list[str]:
    wanted: list[str] = []
    for filename in BASE_WIKI_DOCS:
        if filename not in wanted:
            wanted.append(filename)
    for filename in PAGE_WIKI_DOCS.get(page_path or "", []):
        if filename not in wanted:
            wanted.append(filename)

    tokens = _query_tokens_sv(query)
    scored: list[tuple[int, str]] = []
    for path in sorted(WIKI_DIR.glob("*.md")) if WIKI_DIR.exists() else []:
        if path.name in wanted:
            continue
        text = _read_wiki_doc(path.name).lower()
        if not text:
            continue
        score = sum(text.count(token) for token in tokens)
        if score:
            scored.append((score, path.name))
    scored.sort(key=lambda item: (-item[0], item[1]))

    for _score, filename in scored[:6]:
        if filename not in wanted:
            wanted.append(filename)
    return wanted


def build_wiki_context(query: str, page_path: str | None = None) -> str:
    sections: list[str] = []
    total_chars = 0
    for filename in _ranked_wiki_docs(query, page_path):
        text = _read_wiki_doc(filename).strip()
        if not text:
            continue
        excerpt = text[:MAX_DOC_CHARS]
        remaining = MAX_CONTEXT_CHARS - total_chars
        if remaining <= 0:
            break
        if len(excerpt) > remaining:
            excerpt = excerpt[:remaining]
        sections.append(f"## {filename}\n{excerpt}")
        total_chars += len(excerpt)
    return "\n\n".join(sections) or "Wikin kunde inte lasas av backend."


def _repo_file_allowed(path: Path) -> bool:
    if path.name in REPO_EXCLUDED_NAMES:
        return False
    relative_parts = path.relative_to(ROOT_DIR).parts[:-1]
    if any(part in REPO_EXCLUDED_DIRS for part in relative_parts):
        return False
    return path.suffix.lower() in REPO_TEXT_SUFFIXES or path.name in REPO_TEXT_NAMES


def _repo_line_snippet(lines: list[str], index: int, radius: int = 2) -> str:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    return "\n".join(f"{line_no + 1}: {lines[line_no][:220]}" for line_no in range(start, end))


def build_repo_context(query: str) -> str:
    tokens = _query_tokens_sv(query)
    if not tokens:
        return "Repo-sökning kördes, men frågan gav inga sökbara ord."

    matches: list[tuple[int, str, str]] = []
    for path in ROOT_DIR.rglob("*"):
        if not path.is_file() or not _repo_file_allowed(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lowered = text.lower()
        score = sum(lowered.count(token) for token in tokens)
        if not score:
            continue
        lines = text.splitlines()
        hit_indexes = [
            index
            for index, line in enumerate(lines)
            if any(token in line.lower() for token in tokens)
        ][:3]
        snippets = "\n...\n".join(_repo_line_snippet(lines, index) for index in hit_indexes)
        rel_path = path.relative_to(ROOT_DIR).as_posix()
        matches.append((score, rel_path, snippets))

    if not matches:
        return "Repo-sökning kördes i textfilerna, men hittade inget stöd för användarens påstående."

    matches.sort(key=lambda item: (-item[0], item[1]))
    sections: list[str] = ["Repo-sökning kördes eftersom användaren invände eller bad om kodkontroll."]
    total_chars = len(sections[0])
    for score, rel_path, snippets in matches[:MAX_REPO_MATCHES]:
        section = f"## {rel_path} (träffpoäng {score})\n{snippets}"
        remaining = MAX_REPO_CONTEXT_CHARS - total_chars
        if remaining <= 0:
            break
        if len(section) > remaining:
            section = section[:remaining]
        sections.append(section)
        total_chars += len(section)
    return "\n\n".join(sections)


def _safe_user_roles(user: User) -> list[str]:
    raw_roles = getattr(user, "roles", None) if isinstance(getattr(user, "roles", None), list) else []
    roles: list[str] = []
    for role in [*raw_roles, getattr(user, "role", None)]:
        normalized = str(role or "").strip().lower()
        if normalized and normalized not in roles:
            roles.append(normalized)
    return roles or ["leader"]


def _safe_is_super_user(user: User, roles: list[str]) -> bool:
    if bool(getattr(user, "is_super_user", False)):
        return True
    if {SUPER_USER_ROLE, LEGACY_SUPER_USER_ROLE} & set(roles):
        return True
    username = str(getattr(user, "username", "") or "").strip().lower()
    return bool(username and username in settings.super_user_usernames)


def _role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def _view_label(view_id: str) -> str:
    return VIEW_LABELS.get(view_id, view_id)


def _format_view_list(view_ids: list[str]) -> str:
    if not view_ids:
        return "inga"
    return ", ".join(f"{_view_label(view_id)} (`{view_id}`)" for view_id in view_ids)


def build_user_context(
    user: User,
    role_access: dict | None = None,
    page_path: str | None = None,
    area_label: str | None = None,
) -> str:
    roles = _safe_user_roles(user)
    super_user = _safe_is_super_user(user, roles)
    primary = primary_role(roles)
    display_name = str(getattr(user, "display_name", "") or "").strip()
    username = str(getattr(user, "username", "") or "").strip()
    area_id = getattr(user, "area_id", None)
    password_setup = bool(getattr(user, "must_change_password", False)) or getattr(user, "password_hash", "set") is None
    current_view = PAGE_VIEW_IDS.get(page_path or "")

    view_levels: dict[str, str] = {}
    for view_id in VIEW_CONTEXT_ORDER:
        if view_id not in ROLE_VIEW_IDS:
            continue
        if super_user:
            level = "edit"
        else:
            level = role_view_access_level(user, role_access, view_id)
        view_levels[view_id] = level

    edit_views = [view_id for view_id, level in view_levels.items() if level == "edit"]
    view_only_views = [view_id for view_id, level in view_levels.items() if level == "view"]
    no_access_views = [view_id for view_id, level in view_levels.items() if level == "none"]

    lines = [
        "Supportkontext om inloggad användare. Använd endast för att anpassa svaret; dela inte onödiga personuppgifter.",
        "Känslig info som lösenord, hash, tokens, API-nycklar och sessionsdata skickas inte.",
        f"- Namn: {display_name or username or 'okänt'}",
        f"- Användarnamn: {username or 'okänt'}",
        f"- Primär roll: {_role_label(primary)} (`{primary}`)",
        f"- Roller: {', '.join(f'{_role_label(role)} (`{role}`)' for role in roles)}",
        f"- Super User: {'ja' if super_user else 'nej'}",
        f"- Aktiv användare: {'ja' if bool(getattr(user, 'is_active', True)) else 'nej'}",
        f"- Kräver lösenordsskapande: {'ja' if password_setup else 'nej'}",
        f"- Område: {area_label or (f'area_id {area_id}' if area_id is not None else 'inget område satt')}",
        f"- Vyer med edit: {_format_view_list(edit_views)}",
        f"- Vyer med view men inte edit: {_format_view_list(view_only_views)}",
        f"- Vyer utan åtkomst: {_format_view_list(no_access_views)}",
    ]
    if current_view:
        current_level = view_levels.get(current_view, "none")
        lines.append(f"- Aktuell sidas vybehörighet: {_view_label(current_view)} (`{current_view}`) = `{current_level}`")
    return "\n".join(lines)


def _minimax_error_detail(raw_body: str) -> str:
    if not raw_body:
        return "tomt felsvar"
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body[:500]
    if isinstance(payload, dict):
        detail = payload.get("error") or payload.get("detail") or payload.get("message")
        if isinstance(detail, dict):
            return str(detail.get("message") or detail)
        if detail:
            return str(detail)
    return raw_body[:500]


def _clean_minimax_answer(answer: str) -> str:
    return THINK_BLOCK_RE.sub("", answer).strip()


def _call_minimax(payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        settings.MINIMAX_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.MINIMAX_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MiniMax svarade HTTP {exc.code}: {_minimax_error_detail(raw_error)}",
        ) from exc
    except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="MiniMax kunde inte nas inom timeout.",
        ) from exc
    except Exception as exc:
        logger.exception("MiniMax request failed unexpectedly")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MiniMax-anropet misslyckades: {type(exc).__name__}",
        ) from exc

    try:
        data = json.loads(raw)
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MiniMax svar saknade textinnehall.",
        ) from exc

    answer = _clean_minimax_answer(str(answer or ""))
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MiniMax returnerade ett tomt svar.",
        )
    return answer


def build_minimax_payload(
    payload: AssistantChatRequest,
    user: User,
    role_access: dict | None = None,
    area_label: str | None = None,
) -> dict:
    messages = payload.messages[-MAX_DIALOG_MESSAGES:]
    page_path = payload.page_path or ""
    latest_question = _last_user_question(messages)
    wiki_context = build_wiki_context(latest_question, page_path)
    user_context = build_user_context(user, role_access, page_path, area_label)
    repo_context = build_repo_context(latest_question) if should_search_repo(messages) else (
        "Inte körd. Använd endast wikin och svara nej/inte dokumenterat om wikin saknar stöd."
    )
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        page_path=page_path or "okand",
        user_context=user_context,
        wiki_context=wiki_context,
        repo_context=repo_context,
    )
    return {
        "model": settings.MINIMAX_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            *[message.model_dump() for message in messages],
        ],
        "max_tokens": settings.MINIMAX_MAX_TOKENS,
        "temperature": 0.2,
        "reasoning_split": True,
    }


@router.post("/chat", response_model=AssistantChatResponse)
async def chat_with_assistant(
    payload: AssistantChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantChatResponse:
    if not settings.MINIMAX_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Appchatten saknar MINIMAX_API_KEY i servermiljon.",
        )
    if payload.messages[-1].role != "user":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Den senaste dialograden maste vara en anvandarfraga.",
        )

    used_questions = _session_question_count(request)
    if used_questions >= MAX_QUESTIONS_PER_SESSION:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Max 10 fragor per session. Klicka Rensa dialog for att borja om.",
        )

    try:
        area_label = None
        if getattr(user, "area_id", None) is not None:
            area = db.get(Area, user.area_id)
            if area is not None:
                area_label = f"{area.name} ({area.code})"
        try:
            role_access = get_role_view_access(db, business_id=getattr(user, "business_id", None))
        except TypeError:
            role_access = get_role_view_access(db)
        minimax_payload = build_minimax_payload(
            payload,
            user,
            role_access=role_access,
            area_label=area_label,
        )
    except Exception as exc:
        logger.exception("Assistant context build failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte bygga chatkontext: {type(exc).__name__}",
        ) from exc
    answer = await run_in_threadpool(_call_minimax, minimax_payload)
    used_questions += 1
    request.session[SESSION_COUNT_KEY] = used_questions
    return AssistantChatResponse(
        answer=answer,
        model=settings.MINIMAX_MODEL,
        remaining_questions=max(0, MAX_QUESTIONS_PER_SESSION - used_questions),
    )


@router.post("/clear")
def clear_assistant_dialog(request: Request, _user: User = Depends(get_current_user)) -> dict:
    request.session.pop(SESSION_COUNT_KEY, None)
    return {"ok": True}
