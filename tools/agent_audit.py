"""Local development observability for coding agents.

The runtime OpenTelemetry layer explains what flow did while running. This tool
explains what an agent did while changing the repository: goal, branch, commit,
changed files, tests, and a local span-like event timeline.

Examples:
  python -m tools.agent_audit start --goal "Add OTel runtime tracing"
  python -m tools.agent_audit exec -- python -m pytest tests/services/test_observability.py
  python -m tools.agent_audit finish --summary "Tracing added and tests passed"
  python -m tools.agent_audit list
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
RUN_ID_RE = re.compile(r"^Agent-Run-Id:\s*([a-zA-Z0-9_.-]+)\s*$", re.MULTILINE)
TRAILER_RE = re.compile(r"^(Agent|Agent-Run-Id|Agent-Goal):\s*", re.MULTILINE)
SAFE_TEXT_RE = re.compile(r"[\r\n\t]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_to_sort_key(value: str | None) -> str:
    return str(value or "")


def clean_text(value: Any, *, limit: int = 500) -> str:
    text = SAFE_TEXT_RE.sub(" ", str(value or "")).strip()
    return text[: limit - 3] + "..." if len(text) > limit else text


def agent_dir() -> Path:
    return ROOT / "artifacts" / "agent_runs"


def runs_dir() -> Path:
    return agent_dir() / "runs"


def events_dir() -> Path:
    return agent_dir() / "events"


def otel_dir() -> Path:
    return agent_dir() / "otel"


def active_path() -> Path:
    return agent_dir() / "active.json"


def ensure_dirs() -> None:
    for path in (runs_dir(), events_dir(), otel_dir()):
        path.mkdir(parents=True, exist_ok=True)


def run_path(run_id: str) -> Path:
    return runs_dir() / f"{run_id}.json"


def event_path(run_id: str) -> Path:
    return events_dir() / f"{run_id}.jsonl"


def otel_path(run_id: str) -> Path:
    return otel_dir() / f"{run_id}.jsonl"


def git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def git_text(args: list[str], default: str = "") -> str:
    try:
        result = git(args)
    except Exception:
        return default
    if result.returncode != 0:
        return default
    return result.stdout.strip()


def git_path(name: str) -> Path:
    resolved = git_text(["rev-parse", "--git-path", name])
    return (ROOT / resolved) if resolved else (ROOT / ".git" / name)


def branch_name() -> str:
    return git_text(["branch", "--show-current"], default="unknown")


def head_sha() -> str:
    return git_text(["rev-parse", "HEAD"], default="")


def git_config(key: str, default: str = "") -> str:
    return git_text(["config", "--get", key], default=default)


def configured_agent(default: str = "codex") -> str:
    return os.getenv("AGENT_AUDIT_AGENT") or git_config("flow.agentAudit.agent", default) or default


def configured_auto() -> bool:
    value = os.getenv("AGENT_AUDIT_AUTO") or git_config("flow.agentAudit.auto", "true")
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def short_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(4)}"


def trace_id() -> str:
    return secrets.token_hex(16)


def span_id() -> str:
    return secrets.token_hex(8)


def json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def active_run_id() -> str | None:
    path = active_path()
    if not path.exists():
        return None
    try:
        payload = json_load(path)
    except Exception:
        return None
    run_id = str(payload.get("run_id") or "").strip()
    return run_id or None


def load_run(run_id: str) -> dict[str, Any]:
    return json_load(run_path(run_id))


def save_run(payload: dict[str, Any]) -> None:
    json_dump(run_path(str(payload["run_id"])), payload)


def repo_snapshot() -> dict[str, Any]:
    status = git_text(["status", "--porcelain=v1"])
    return {
        "branch": branch_name(),
        "head": head_sha(),
        "dirty": bool(status.strip()),
        "status_lines": status.splitlines()[:200],
    }


def status_files(lines: list[str]) -> list[str]:
    files: list[str] = []
    for line in lines:
        parts = line.strip().split(maxsplit=1)
        if len(parts) < 2:
            continue
        path = parts[1].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        if path:
            files.append(path)
    return files


def diff_snapshot(base_commit: str | None = None) -> dict[str, Any]:
    status = git_text(["status", "--porcelain=v1"])
    status_lines = status.splitlines()
    if base_commit:
        names = git_text(["diff", "--name-status", f"{base_commit}..HEAD"])
        stat = git_text(["diff", "--stat", f"{base_commit}..HEAD"])
        shortstat = git_text(["diff", "--shortstat", f"{base_commit}..HEAD"])
        numstat = git_text(["diff", "--numstat", f"{base_commit}..HEAD"])
        committed_files = [line.split("\t")[-1] for line in names.splitlines() if line.strip()]
        files = sorted(set(committed_files))
    else:
        unstaged_names = git_text(["diff", "--name-status"])
        staged_names = git_text(["diff", "--cached", "--name-status"])
        names = "\n".join(line for line in (staged_names, unstaged_names) if line.strip())
        stat = "\n".join(
            line
            for line in (git_text(["diff", "--cached", "--stat"]), git_text(["diff", "--stat"]))
            if line.strip()
        )
        shortstat = "\n".join(
            line
            for line in (git_text(["diff", "--cached", "--shortstat"]), git_text(["diff", "--shortstat"]))
            if line.strip()
        )
        numstat = "\n".join(
            line
            for line in (git_text(["diff", "--cached", "--numstat"]), git_text(["diff", "--numstat"]))
            if line.strip()
        )
        files = sorted({*status_files(status_lines), *[line.split("\t")[-1] for line in names.splitlines() if line.strip()]})
    return {
        "name_status": names.splitlines(),
        "files": files,
        "stat": stat,
        "shortstat": shortstat,
        "numstat": numstat.splitlines(),
        "working_tree_status": status_lines[:200],
    }


def commit_snapshot(commit: str = "HEAD") -> dict[str, Any]:
    return {
        "sha": git_text(["rev-parse", commit]),
        "subject": git_text(["log", "-1", "--format=%s", commit]),
        "author": git_text(["log", "-1", "--format=%an <%ae>", commit]),
        "date": git_text(["log", "-1", "--format=%aI", commit]),
        "shortstat": git_text(["show", "--shortstat", "--format=", commit]),
        "files": git_text(["show", "--name-only", "--format=", commit]).splitlines(),
    }


def write_span(run: dict[str, Any], name: str, attributes: dict[str, Any] | None = None, *, status: str = "ok") -> None:
    now = utc_now()
    attrs = {k: clean_text(v, limit=300) for k, v in (attributes or {}).items() if v is not None}
    append_jsonl(
        otel_path(str(run["run_id"])),
        {
            "trace_id": run.get("trace_id"),
            "span_id": span_id(),
            "parent_span_id": run.get("root_span_id"),
            "name": name,
            "kind": "internal",
            "start_time": now,
            "end_time": now,
            "status": status,
            "attributes": {
                "agent.name": run.get("agent"),
                "agent.run_id": run.get("run_id"),
                "git.branch": run.get("branch"),
                **attrs,
            },
        },
    )


def append_event(run: dict[str, Any], event_type: str, payload: dict[str, Any] | None = None, *, status: str = "ok") -> None:
    event = {
        "created_at": utc_now(),
        "event_type": event_type,
        "status": status,
        "payload": payload or {},
    }
    append_jsonl(event_path(str(run["run_id"])), event)
    run["event_count"] = int(run.get("event_count") or 0) + 1
    run["updated_at"] = event["created_at"]
    save_run(run)
    write_span(run, f"agent.{event_type}", payload, status=status)


def create_run(*, goal: str, agent: str, source: str = "manual", activate: bool = True) -> dict[str, Any]:
    ensure_dirs()
    snapshot = repo_snapshot()
    run = {
        "version": 1,
        "run_id": short_id(),
        "trace_id": trace_id(),
        "root_span_id": span_id(),
        "agent": clean_text(agent, limit=80),
        "goal": clean_text(goal, limit=600),
        "source": source,
        "status": "in_progress" if activate else "committing",
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "ended_at": None,
        "branch": snapshot["branch"],
        "base_commit": snapshot["head"],
        "start_dirty": snapshot["dirty"],
        "start_status_lines": snapshot["status_lines"],
        "event_count": 0,
        "commits": [],
        "tests": [],
        "summary": "",
        "risk": "",
        "diff": {},
    }
    save_run(run)
    append_event(run, "task_start", {"goal": run["goal"], "source": source, "base_commit": run["base_commit"]})
    if activate:
        json_dump(active_path(), {"run_id": run["run_id"], "started_at": run["started_at"]})
    return run


def update_run_diff(run: dict[str, Any]) -> dict[str, Any]:
    base = str(run.get("base_commit") or "")
    current_head = head_sha()
    diff = diff_snapshot(base if base and current_head and base != current_head else None)
    run["diff"] = diff
    run["changed_files"] = diff.get("files", [])
    return run


def finish_run(run_id: str, *, status: str, summary: str = "", risk: str = "") -> dict[str, Any]:
    run = load_run(run_id)
    update_run_diff(run)
    run["status"] = status
    run["summary"] = clean_text(summary, limit=1200)
    run["risk"] = clean_text(risk, limit=1200)
    run["ended_at"] = utc_now()
    save_run(run)
    append_event(
        run,
        "task_complete",
        {
            "status": status,
            "summary": run["summary"],
            "risk": run["risk"],
            "changed_files_count": len(run.get("changed_files") or []),
            "shortstat": (run.get("diff") or {}).get("shortstat", ""),
        },
        status=status,
    )
    if active_run_id() == run_id:
        active_path().unlink(missing_ok=True)
    return run


def record_test(run: dict[str, Any], command: str, exit_code: int, duration_ms: int) -> None:
    item = {
        "command": clean_text(command, limit=500),
        "exit_code": int(exit_code),
        "duration_ms": int(duration_ms),
        "recorded_at": utc_now(),
    }
    run.setdefault("tests", []).append(item)
    save_run(run)
    append_event(run, "test_run", item, status="ok" if exit_code == 0 else "error")


def command_start(args: argparse.Namespace) -> int:
    existing = active_run_id()
    if existing and not args.force:
        print(f"Active agent run already exists: {existing}")
        print("Use --force to replace the active marker, or finish the existing run first.")
        return 2
    run = create_run(goal=args.goal, agent=args.agent or configured_agent(), source="manual", activate=True)
    print(run["run_id"])
    return 0


def command_status(_args: argparse.Namespace) -> int:
    run_id = active_run_id()
    if not run_id:
        print("No active agent run.")
        return 1
    run = load_run(run_id)
    print(json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_record(args: argparse.Namespace) -> int:
    run_id = args.run_id or active_run_id()
    if not run_id:
        raise SystemExit("No active agent run. Use start first or pass --run-id.")
    run = load_run(run_id)
    payload = {}
    for item in args.attr or []:
        if "=" in item:
            key, value = item.split("=", 1)
            payload[key.strip()] = clean_text(value)
    if args.message:
        payload["message"] = clean_text(args.message, limit=1000)
    append_event(run, args.event, payload, status=args.status)
    print(run_id)
    return 0


def command_exec(args: argparse.Namespace) -> int:
    run_id = args.run_id or active_run_id()
    if not run_id:
        raise SystemExit("No active agent run. Use start first or pass --run-id.")
    if not args.command:
        raise SystemExit("Missing command after --")
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    command_text = " ".join(command)
    run = load_run(run_id)
    append_event(run, "command_start", {"command": command_text})
    started = time.perf_counter()
    completed = subprocess.run(command_text if args.shell else command, cwd=ROOT, shell=args.shell)
    duration_ms = round((time.perf_counter() - started) * 1000)
    run = load_run(run_id)
    record_test(run, command_text, completed.returncode, duration_ms)
    return completed.returncode


def command_finish(args: argparse.Namespace) -> int:
    run_id = args.run_id or active_run_id()
    if not run_id:
        raise SystemExit("No active agent run. Use start first or pass --run-id.")
    run = finish_run(run_id, status=args.status, summary=args.summary or "", risk=args.risk or "")
    print(json.dumps({
        "run_id": run["run_id"],
        "status": run["status"],
        "changed_files": len(run.get("changed_files") or []),
        "commits": [item.get("sha") for item in run.get("commits") or []],
    }, ensure_ascii=False, indent=2))
    return 0


def command_list(args: argparse.Namespace) -> int:
    ensure_dirs()
    runs = []
    for path in runs_dir().glob("*.json"):
        try:
            runs.append(json_load(path))
        except Exception:
            continue
    runs.sort(key=lambda item: iso_to_sort_key(item.get("started_at")), reverse=True)
    for run in runs[: args.limit]:
        commits = ",".join((commit.get("sha") or "")[:8] for commit in run.get("commits", []))
        print(f"{run.get('started_at','-')} {run.get('status','-'):12} {run.get('run_id','-')} {commits:12} {run.get('goal','')}")
    return 0


def command_show(args: argparse.Namespace) -> int:
    run = load_run(args.run_id)
    if args.format == "json":
        print(json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Run: {run['run_id']}")
        print(f"Agent: {run.get('agent')}")
        print(f"Status: {run.get('status')}")
        print(f"Goal: {run.get('goal')}")
        print(f"Branch: {run.get('branch')}")
        print(f"Base: {run.get('base_commit')}")
        print(f"Commits: {', '.join((item.get('sha') or '')[:8] for item in run.get('commits') or []) or '-'}")
        print(f"Changed files: {len(run.get('changed_files') or [])}")
        print(f"Summary: {run.get('summary') or '-'}")
    return 0


def commit_message_run_id(message: str) -> str | None:
    match = RUN_ID_RE.search(message)
    return match.group(1) if match else None


def append_trailers(message_path: Path, run: dict[str, Any]) -> None:
    text = message_path.read_text(encoding="utf-8", errors="replace")
    if commit_message_run_id(text):
        return
    if text and not text.endswith("\n"):
        text += "\n"
    if TRAILER_RE.search(text):
        text += "\n"
    text += (
        f"\nAgent: {clean_text(run.get('agent'), limit=80)}\n"
        f"Agent-Run-Id: {run['run_id']}\n"
        f"Agent-Goal: {clean_text(run.get('goal'), limit=180)}\n"
    )
    message_path.write_text(text, encoding="utf-8")


def pending_path() -> Path:
    return git_path("AGENT_AUDIT_PENDING")


def command_hook_prepare_commit_msg(args: argparse.Namespace) -> int:
    if not configured_auto():
        return 0
    message_path = Path(args.message_file)
    if not message_path.exists():
        return 0
    message_text = message_path.read_text(encoding="utf-8", errors="replace")
    message_run_id = commit_message_run_id(message_text)
    run_id = active_run_id()
    run = None
    if message_run_id:
        try:
            run = load_run(message_run_id)
        except Exception:
            run = None
    if run_id:
        try:
            run = load_run(run_id)
        except Exception:
            run = None
    if run is None:
        subject = next((line.strip() for line in message_text.splitlines() if line.strip() and not line.startswith("#")), "")
        run = create_run(
            goal=f"Commit: {subject or 'unspecified'}",
            agent=configured_agent(),
            source="git_hook_auto",
            activate=False,
        )
        json_dump(pending_path(), {"run_id": run["run_id"], "created_at": utc_now()})
    append_trailers(message_path, run)
    append_event(run, "commit_message_prepared", {"message_file": str(message_path.name)})
    return 0


def command_hook_post_commit(_args: argparse.Namespace) -> int:
    run_id = None
    message = git_text(["log", "-1", "--format=%B"])
    run_id = commit_message_run_id(message)
    if not run_id and pending_path().exists():
        try:
            run_id = str(json_load(pending_path()).get("run_id") or "")
        except Exception:
            run_id = None
    if not run_id:
        return 0
    try:
        run = load_run(run_id)
    except Exception:
        return 0
    commit = commit_snapshot("HEAD")
    known = {item.get("sha") for item in run.get("commits") or []}
    if commit["sha"] and commit["sha"] not in known:
        run.setdefault("commits", []).append(commit)
    if run.get("source") == "git_hook_auto":
        run["status"] = "committed"
        run["ended_at"] = utc_now()
        update_run_diff(run)
    save_run(run)
    append_event(run, "commit_created", {"commit": commit.get("sha"), "subject": commit.get("subject"), "shortstat": commit.get("shortstat")})
    pending_path().unlink(missing_ok=True)
    return 0


def command_install_hooks(args: argparse.Namespace) -> int:
    hooks_dir = ROOT / ".githooks"
    if not hooks_dir.exists():
        raise SystemExit(".githooks directory is missing.")
    git(["config", "core.hooksPath", ".githooks"], check=True)
    git(["config", "flow.agentAudit.auto", "true" if args.auto else "false"], check=True)
    git(["config", "flow.agentAudit.agent", args.agent or configured_agent()], check=True)
    print("Agent audit hooks installed for this repository.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--goal", required=True)
    start.add_argument("--agent", default="")
    start.add_argument("--force", action="store_true")
    start.set_defaults(func=command_start)

    status = sub.add_parser("status")
    status.set_defaults(func=command_status)

    record = sub.add_parser("record")
    record.add_argument("--run-id")
    record.add_argument("--event", default="note")
    record.add_argument("--status", default="ok", choices=("ok", "warn", "error", "blocked", "complete", "committed"))
    record.add_argument("--message")
    record.add_argument("--attr", action="append")
    record.set_defaults(func=command_record)

    execute = sub.add_parser("exec")
    execute.add_argument("--run-id")
    execute.add_argument("--shell", action="store_true")
    execute.add_argument("command", nargs=argparse.REMAINDER)
    execute.set_defaults(func=command_exec)

    finish = sub.add_parser("finish")
    finish.add_argument("--run-id")
    finish.add_argument("--status", default="complete", choices=("complete", "failed", "blocked", "committed"))
    finish.add_argument("--summary", default="")
    finish.add_argument("--risk", default="")
    finish.set_defaults(func=command_finish)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.set_defaults(func=command_list)

    show = sub.add_parser("show")
    show.add_argument("run_id")
    show.add_argument("--format", choices=("text", "json"), default="text")
    show.set_defaults(func=command_show)

    install = sub.add_parser("install-hooks")
    install.add_argument("--agent", default="")
    install.add_argument("--auto", action=argparse.BooleanOptionalAction, default=True)
    install.set_defaults(func=command_install_hooks)

    hook = sub.add_parser("hook")
    hook_sub = hook.add_subparsers(dest="hook_command", required=True)
    prepare = hook_sub.add_parser("prepare-commit-msg")
    prepare.add_argument("message_file")
    prepare.add_argument("source", nargs="?")
    prepare.add_argument("commit_sha", nargs="?")
    prepare.set_defaults(func=command_hook_prepare_commit_msg)
    post = hook_sub.add_parser("post-commit")
    post.set_defaults(func=command_hook_post_commit)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if shutil.which("git") is None:
        raise SystemExit("git is required for agent audit.")
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
