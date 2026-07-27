import argparse
import json
import subprocess

from tools import agent_audit


def git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


# Miljovariabler som git exporterar till hooks (pre-push m.fl.). Arvs de av
# testets git-kommandon ateranvander `git init` det RIKTIGA repot i stallet
# for tmp-katalogen: fran en worktree ar GIT_DIR absolut och 2026-07-27 skrev
# sviten en "Initial commit" plus user.name "Agent Test" i arbetsrepot.
GIT_HOOK_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
)


def init_repo(tmp_path, monkeypatch):
    for var in GIT_HOOK_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "agent@example.test")
    git(tmp_path, "config", "user.name", "Agent Test")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-m", "Initial commit")
    monkeypatch.setattr(agent_audit, "ROOT", tmp_path)
    return tmp_path


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_init_repo_ignores_git_hook_environment(tmp_path, monkeypatch):
    """Testriggen far inte lacka in i det repo som kor sviten.

    Pre-push-hooken kor pytest med GIT_DIR exporterad av git. Utan sanering
    ateranvander init_repos `git init` det repot: 2026-07-27 fick en worktree
    en "Initial commit" pa sin branch och user.name "Agent Test" i delade
    .git/config. Har simuleras hookmiljon mot ett offer-repo och riggen ska
    anda skapa ett fristaende repo utan att rora offret."""
    victim = tmp_path / "victim"
    victim.mkdir()
    for var in GIT_HOOK_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    git(victim, "init")
    git(victim, "config", "user.email", "owner@example.test")
    git(victim, "config", "user.name", "Repo Owner")
    (victim / "data.txt").write_text("viktigt\n", encoding="utf-8")
    git(victim, "add", "data.txt")
    git(victim, "commit", "-m", "Owner commit")
    victim_head = git(victim, "rev-parse", "HEAD").stdout.strip()

    monkeypatch.setenv("GIT_DIR", str(victim / ".git"))

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    repo = init_repo(sandbox, monkeypatch)

    assert (repo / ".git").is_dir()
    assert git(repo, "rev-parse", "HEAD").stdout.strip() != victim_head
    assert git(victim, "rev-parse", "HEAD").stdout.strip() == victim_head
    assert git(victim, "config", "user.name").stdout.strip() == "Repo Owner"
    assert git(victim, "status", "--porcelain").stdout.strip() == ""


def test_agent_run_records_untracked_diff_events_and_spans(tmp_path, monkeypatch):
    repo = init_repo(tmp_path, monkeypatch)

    run = agent_audit.create_run(goal="Add local observability", agent="codex", activate=True)
    (repo / "feature.py").write_text("print('ok')\n", encoding="utf-8")
    agent_audit.append_event(run, "note", {"message": "created feature file"})

    finished = agent_audit.finish_run(run["run_id"], status="complete", summary="done")

    assert finished["status"] == "complete"
    assert "feature.py" in finished["changed_files"]
    assert not agent_audit.active_path().exists()
    assert {event["event_type"] for event in jsonl(agent_audit.event_path(run["run_id"]))} >= {
        "task_start",
        "note",
        "task_complete",
    }
    spans = jsonl(agent_audit.otel_path(run["run_id"]))
    assert {span["name"] for span in spans} >= {"agent.task_start", "agent.note", "agent.task_complete"}
    assert all(span["trace_id"] == run["trace_id"] for span in spans)


def test_prepare_and_post_commit_hooks_attach_agent_metadata(tmp_path, monkeypatch):
    repo = init_repo(tmp_path, monkeypatch)
    git(repo, "config", "flow.agentAudit.auto", "true")
    git(repo, "config", "flow.agentAudit.agent", "codex")
    (repo / "outside.txt").write_text("draft\n", encoding="utf-8")

    message_path = repo / "COMMIT_EDITMSG"
    message_path.write_text("Add hook coverage\n", encoding="utf-8")

    result = agent_audit.command_hook_prepare_commit_msg(
        argparse.Namespace(message_file=str(message_path), source=None, commit_sha=None)
    )

    message = message_path.read_text(encoding="utf-8")
    run_id = agent_audit.commit_message_run_id(message)
    assert result == 0
    assert run_id
    assert "Agent: codex" in message
    assert "Agent-Goal: Commit: Add hook coverage" in message

    run_files = set(agent_audit.runs_dir().glob("*.json"))
    assert (
        agent_audit.command_hook_prepare_commit_msg(
            argparse.Namespace(message_file=str(message_path), source=None, commit_sha=None)
        )
        == 0
    )
    assert set(agent_audit.runs_dir().glob("*.json")) == run_files

    (repo / "hooked.txt").write_text("tracked\n", encoding="utf-8")
    git(repo, "add", "hooked.txt")
    git(repo, "commit", "-F", str(message_path), "--no-verify")

    assert agent_audit.command_hook_post_commit(argparse.Namespace()) == 0

    run = agent_audit.load_run(run_id)
    assert run["status"] == "committed"
    assert run["commits"][0]["subject"] == "Add hook coverage"
    assert "hooked.txt" in run["changed_files"]
    assert "outside.txt" not in run["changed_files"]
    assert any("outside.txt" in line for line in run["diff"]["working_tree_status"])
