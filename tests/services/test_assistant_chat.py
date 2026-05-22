from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.backend.config import settings
from app.backend.deps import get_current_user
from app.backend.main import app
from app.backend.routers import assistant


@pytest.fixture(autouse=True)
def assistant_settings_without_database(monkeypatch):
    monkeypatch.setattr(assistant, "get_role_view_access", lambda _db: {})


def fake_user():
    return SimpleNamespace(
        id=1,
        username="anna",
        display_name="Anna",
        role="viewer",
        roles=["viewer"],
        area_id=None,
        is_active=True,
        must_change_password=False,
        password_hash="set",
    )


def test_assistant_chat_requires_minimax_key(monkeypatch):
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "")
    app.dependency_overrides[get_current_user] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "Hur kopierar jag en dag?"}]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "MINIMAX_API_KEY" in response.json()["detail"]


def test_assistant_chat_strips_minimax_thinking_blocks():
    answer = assistant._clean_minimax_answer("<think>internt resonemang</think>\n\nSynligt svar")

    assert answer == "Synligt svar"


def test_assistant_minimax_unexpected_error_becomes_gateway_error(monkeypatch):
    def fail(_request, timeout):
        raise RuntimeError("connection broke")

    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(assistant.urllib.request, "urlopen", fail)

    with pytest.raises(HTTPException) as exc_info:
        assistant._call_minimax({"messages": []})

    assert exc_info.value.status_code == 502
    assert "MiniMax-anropet misslyckades" in exc_info.value.detail


def test_assistant_prompt_is_strict_when_repo_search_is_not_triggered(monkeypatch):
    monkeypatch.setattr(assistant, "build_wiki_context", lambda query, page_path=None: "Wiki säger inget om export.")
    payload = assistant.AssistantChatRequest(
        page_path="/personer.html",
        messages=[assistant.AssistantMessage(role="user", content="Finns export?")],
    )

    minimax_payload = assistant.build_minimax_payload(payload, fake_user())
    system_prompt = minimax_payload["messages"][0]["content"]

    assert "korrekta å, ä och ö" in system_prompt
    assert "Om wikin inte säger" in system_prompt
    assert "Gissa inte fram möjliga knappar" in system_prompt
    assert "Användarkontext" in system_prompt
    assert "Primär roll: Visare (`viewer`)" in system_prompt
    assert "Bemanning (`schedule`), Översikt (`overview`)" in system_prompt
    assert "Repo-sökning:\nInte körd" in system_prompt


def test_assistant_prompt_adds_repo_context_when_user_challenges(monkeypatch):
    monkeypatch.setattr(assistant, "build_wiki_context", lambda query, page_path=None: "Wiki säger nej.")
    monkeypatch.setattr(assistant, "build_repo_context", lambda query: "Repo-sökning hittade app/frontend/export.js")
    payload = assistant.AssistantChatRequest(
        messages=[
            assistant.AssistantMessage(role="assistant", content="Nej, enligt wikin finns det inte."),
            assistant.AssistantMessage(role="user", content="Jo det finns visst, kolla hela repot."),
        ],
    )

    minimax_payload = assistant.build_minimax_payload(payload, fake_user())
    system_prompt = minimax_payload["messages"][0]["content"]

    assert assistant.should_search_repo(payload.messages)
    assert "Repo-sökning hittade app/frontend/export.js" in system_prompt
    assert "definitivt ja/nej" in system_prompt


def test_assistant_chat_sends_wiki_context_and_dialogue(monkeypatch):
    captured = {}

    def fake_call(payload):
        captured["payload"] = payload
        return "Klicka Kopiera dag och valj maldag."

    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(assistant, "_call_minimax", fake_call)
    app.dependency_overrides[get_current_user] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/assistant/chat",
            json={
                "page_path": "/index.html",
                "messages": [
                    {"role": "user", "content": "Var hittar jag kopiera?"},
                    {"role": "assistant", "content": "Det finns i Bemanning."},
                    {"role": "user", "content": "Hur funkar Kopiera dag?"},
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["answer"] == "Klicka Kopiera dag och valj maldag."
    assert response.json()["remaining_questions"] == 9
    messages = captured["payload"]["messages"]
    assert messages[0]["role"] == "system"
    assert "Wikiutdrag" in messages[0]["content"]
    assert "bemanning-schedule.md" in messages[0]["content"]
    assert "Undvik markdown-tabeller" in messages[0]["content"]
    assert "korrekta å, ä och ö" in messages[0]["content"]
    assert "Vyer med view men inte edit: Bemanning (`schedule`), Översikt (`overview`)" in messages[0]["content"]
    assert [message["role"] for message in messages[1:]] == ["user", "assistant", "user"]
    assert captured["payload"]["reasoning_split"] is True


def test_assistant_user_context_uses_configured_view_access():
    user = SimpleNamespace(
        id=2,
        username="lager1",
        display_name="Lager Ett",
        role="warehouse_clerk",
        roles=["warehouse_clerk"],
        area_id=1,
        is_active=True,
        must_change_password=False,
        password_hash="set",
    )
    context = assistant.build_user_context(
        user,
        role_access={"warehouse_clerk": {"allocationSplit": "none"}},
        page_path="/dela.html",
        area_label="Granngården (GG)",
    )

    assert "Lagerkontorist (`warehouse_clerk`)" in context
    assert "Område: Granngården (GG)" in context
    assert "Uppladdningar (`allocationUploads`)" in context
    assert "Dela (`allocationSplit`)" in context
    assert "Aktuell sidas vybehörighet: Dela (`allocationSplit`) = `none`" in context


def test_assistant_chat_session_limit_can_be_cleared(monkeypatch):
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(assistant, "_call_minimax", lambda _payload: "Svar")
    app.dependency_overrides[get_current_user] = fake_user
    try:
        client = TestClient(app)
        for index in range(10):
            response = client.post(
                "/api/assistant/chat",
                json={"messages": [{"role": "user", "content": f"Fraga {index}"}]},
            )
            assert response.status_code == 200

        blocked = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "En fraga till"}]},
        )
        assert blocked.status_code == 429

        clear = client.post("/api/assistant/clear")
        assert clear.status_code == 200

        response = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "Efter rensning"}]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["remaining_questions"] == 9
