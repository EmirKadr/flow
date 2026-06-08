import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "app" / "alembic" / "versions"


def test_alembic_revision_ids_fit_version_table():
    too_long = []
    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r'^revision:\s*str\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert match, f"Saknar revision i {path.name}"
        revision = match.group(1)
        if len(revision) > 32:
            too_long.append(f"{revision} ({path.name})")

    assert too_long == []
