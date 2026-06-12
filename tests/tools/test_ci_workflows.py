from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_push_ci_runs_core_test_gates_against_postgres_render_simulation():
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")

    assert "postgres:16" in workflow
    assert "flow_test" in workflow
    assert "postgresql+psycopg://postgres:postgres@localhost:5432/flow_test" in workflow
    assert "Simulate Render build" in workflow
    assert "alembic upgrade head" in workflow
    assert workflow.index("alembic upgrade head") < workflow.index("python -m pytest")
    assert "python -m backend.seed" not in workflow
    assert "python -m pytest" in workflow
    assert "python -m playwright install --with-deps chromium" in workflow
    assert "node --check" in workflow
    assert "python desktop/main.py --smoke-test" in workflow


def test_render_production_build_does_not_run_seed():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "buildCommand:" in blueprint
    assert "pip install -r requirements.txt" in blueprint
    assert "alembic upgrade head" in blueprint
    assert blueprint.index("pip install -r requirements.txt") < blueprint.index("alembic upgrade head")
    assert "python -m backend.seed" not in blueprint


def test_render_sensitive_env_vars_are_secret_backed():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    sensitive_keys = [
        "SECRET_KEY",
        "RENDER_API_KEY",
        "RENDER_SERVICE_ID",
        "RENDER_OWNER_ID",
        "RENDER_POSTGRES_ID",
        "HEALTHCHECK_PUBLIC_URL",
        "EXCEL_API_TOKEN",
        "MINIMAX_API_KEY",
        "GEMINI_API_KEY",
        "DATA_SOURCE_API_BASE_URL",
        "DATA_SOURCE_API_KEY",
        "DATA_SOURCE_API_CLIENT",
        "DATA_SOURCE_API_KEY_HEADER",
        "DATA_SOURCE_API_CLIENT_HEADER",
        "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE",
        "DATA_SOURCE_CA_BUNDLE",
        "DATA_SOURCE_CATALOG_JSON",
    ]

    for key in sensitive_keys:
        marker = f"- key: {key}"
        start = blueprint.find(marker)
        assert start != -1, key
        next_key = blueprint.find("\n      - key:", start + len(marker))
        block = blueprint[start: next_key if next_key != -1 else len(blueprint)]
        assert "sync: false" in block or "generateValue: true" in block, key
        assert "\n        value:" not in block, key


def test_windows_release_is_blocked_by_tests_before_packaging():
    workflow = (ROOT / ".github" / "workflows" / "windows-release.yml").read_text(encoding="utf-8")

    assert workflow.index("Run pytest") < workflow.index("Build app package")
    assert workflow.index("Check frontend JavaScript syntax") < workflow.index("Build app package")
    assert workflow.index("Run desktop smoke test") < workflow.index("Build app package")
    assert "python -m playwright install chromium" in workflow
