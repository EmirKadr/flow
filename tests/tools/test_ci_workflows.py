from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_push_ci_runs_core_test_gates_against_postgres_alembic_simulation():
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")

    assert "postgres:16" in workflow
    assert "flow_test" in workflow
    assert "postgresql+psycopg://postgres:postgres@localhost:5432/flow_test" in workflow
    assert "Simulate Alembic build" in workflow
    assert "alembic upgrade head" in workflow
    assert workflow.index("alembic upgrade head") < workflow.index("python -m pytest")
    assert "python -m backend.seed" not in workflow
    assert "python -m pytest" in workflow
    assert "python -m playwright install --with-deps chromium" in workflow
    assert "node --check" in workflow
    assert "python desktop/main.py --smoke-test" in workflow


def test_k8s_secret_example_uses_azure_sql_database_url():
    secret_example = (ROOT / "k8s" / "secret.example.yaml").read_text(encoding="utf-8")
    expected_prefix = "mssql+pyodbc://USER:PASS@SERVER.database.windows.net:1433/DBNAME"

    assert "--from-literal=DATABASE_URL='mssql+pyodbc://" in secret_example
    assert f'DATABASE_URL: "{expected_prefix}' in secret_example
    assert "postgresql+psycopg://USER:PASS@HOST:5432/flow" not in secret_example


def test_k8s_docs_explain_postgres_startup_mismatch():
    readme = (ROOT / "k8s" / "README.md").read_text(encoding="utf-8")
    deploy = (ROOT / "DEPLOY.md").read_text(encoding="utf-8")

    for document in (readme, deploy):
        assert "PostgreSQL: kör alembic upgrade head" in document
        assert "mssql+pyodbc://..." in document


def test_windows_release_is_blocked_by_tests_before_packaging():
    workflow = (ROOT / ".github" / "workflows" / "windows-release.yml").read_text(encoding="utf-8")

    assert workflow.index("Run pytest") < workflow.index("Build app package")
    assert workflow.index("Check frontend JavaScript syntax") < workflow.index("Build app package")
    assert workflow.index("Run desktop smoke test") < workflow.index("Build app package")
    assert "python -m playwright install chromium" in workflow
