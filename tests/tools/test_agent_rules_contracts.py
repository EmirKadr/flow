from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def normalized(path: str) -> str:
    return " ".join(read_text(path).split())


def test_agent_rules_require_history_analysis_for_new_events():
    agents = normalized("AGENTS.md")
    wiki_agents = normalized("wiki/AGENTS.md")

    for text in (agents, wiki_agents):
        assert "Historik/Analys" in text
        assert "audit" in text
        assert "entity_type" in text
        assert "action" in text
        assert "obligatorisk" in text
        assert "skapar, andrar, synkar eller tar emot data" in text


def test_test_protocol_requires_full_chain_event_tests():
    protocol = normalized("TESTPROTOCOL.md")
    release = normalized("wiki/testing-release.md")

    for text in (protocol, release):
        assert "audit" in text
        assert "Historik/Analys-label" in text
        assert "obligatorisk" in text
        assert "manuell" in text.lower()
        assert "fel" in text
        assert "read-only" in text
    assert "API/domantest" in protocol
    assert "API-/domantest" in release
    assert "auditposten sparas" in protocol
    assert "sparad audit-rad" in release
