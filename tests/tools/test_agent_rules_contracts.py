from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_agent_rules_require_history_analysis_for_new_events():
    agents = read_text("AGENTS.md")
    wiki_agents = read_text("wiki/AGENTS.md")

    for text in (agents, wiki_agents):
        assert "Historik/Analys" in text
        assert "audit" in text
        assert "entity_type" in text
        assert "action" in text


def test_test_protocol_requires_full_chain_event_tests():
    protocol = read_text("TESTPROTOCOL.md")
    release = read_text("wiki/testing-release.md")

    for text in (protocol, release):
        assert "audit" in text
        assert "Historik/Analys-label" in text
        assert "manuell" in text.lower()
        assert "fel" in text
    assert "API/domantest" in protocol
    assert "API-/domantest" in release
