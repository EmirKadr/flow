import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "app" / "alembic" / "versions"
ALEMBIC_VERSION_NUM_MAX_LENGTH = 32


def _literal_assignment(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"Saknar {name}")


def _as_revision_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)):
        return tuple(value)
    raise AssertionError(f"Ogiltig down_revision-typ: {type(value).__name__}")


def _docstring_field(docstring: str, label: str) -> str | None:
    prefix = f"{label}:"
    for line in docstring.splitlines():
        if line.strip().startswith(prefix):
            value = line.split(":", 1)[1].strip()
            return value or None
    return None


def _migration_specs() -> list[dict[str, object]]:
    specs = []
    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        revision = _literal_assignment(tree, "revision")
        down_revision = _as_revision_tuple(_literal_assignment(tree, "down_revision"))
        docstring = ast.get_docstring(tree) or ""
        specs.append(
            {
                "path": path,
                "revision": revision,
                "down_revision": down_revision,
                "doc_revision": _docstring_field(docstring, "Revision ID"),
                "doc_revises": _docstring_field(docstring, "Revises"),
            }
        )
    return specs


def test_alembic_revision_ids_fit_version_table():
    too_long = [
        f"{spec['revision']} ({spec['path'].name})"
        for spec in _migration_specs()
        if len(spec["revision"]) > ALEMBIC_VERSION_NUM_MAX_LENGTH
    ]

    assert too_long == []


def test_alembic_revision_ids_are_unique_and_documented():
    specs = _migration_specs()
    revisions = [spec["revision"] for spec in specs]
    duplicates = sorted({revision for revision in revisions if revisions.count(revision) > 1})

    assert duplicates == []
    for spec in specs:
        assert spec["doc_revision"] == spec["revision"], spec["path"].name
        if spec["down_revision"]:
            assert spec["doc_revises"] == ", ".join(spec["down_revision"]), spec["path"].name
        else:
            assert spec["doc_revises"] in {None, ""}, spec["path"].name


def test_alembic_revision_graph_is_connected_and_has_one_head():
    specs = _migration_specs()
    by_revision = {spec["revision"]: spec for spec in specs}
    all_revisions = set(by_revision)
    parent_revisions = {
        parent
        for spec in specs
        for parent in spec["down_revision"]
    }
    missing_parents = sorted(parent_revisions - all_revisions)
    root_revisions = sorted(
        spec["revision"]
        for spec in specs
        if not spec["down_revision"]
    )
    head_revisions = sorted(all_revisions - parent_revisions)

    assert missing_parents == []
    assert root_revisions == ["0001_initial"]
    assert len(head_revisions) == 1

    visited: set[str] = set()

    def walk(revision: str) -> None:
        if revision in visited:
            return
        visited.add(revision)
        for parent in by_revision[revision]["down_revision"]:
            walk(parent)

    walk(head_revisions[0])
    assert sorted(all_revisions - visited) == []
