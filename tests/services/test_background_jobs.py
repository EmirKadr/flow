"""Tester för det centrala bakgrundsjobb-registret och dess koppling till main/healthcheck."""
import threading
import time

from app.backend import background
from app.backend import main as app_main
from app.backend.background import BackgroundJob
from app.backend.healthcheck_service import collect_background_jobs


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_inline_job_runs_and_records_status(monkeypatch):
    monkeypatch.setattr(background, "_STATUS", {})
    ran = []
    background.start_background_jobs(
        [BackgroundJob(name="inline_ok", run=lambda: ran.append(1), in_thread=False)]
    )
    assert ran == [1]
    status = background.background_job_status()["inline_ok"]
    assert status["state"] == "finished"
    assert status["error"] is None
    assert status["started_at"] and status["finished_at"]


def test_failing_job_is_contained_and_reported(monkeypatch):
    monkeypatch.setattr(background, "_STATUS", {})

    def boom():
        raise RuntimeError("smack")

    # Ett kraschande jobb får varken fälla uppstarten eller stoppa nästa jobb.
    ran = []
    background.start_background_jobs(
        [
            BackgroundJob(name="boom", run=boom, in_thread=False),
            BackgroundJob(name="after_boom", run=lambda: ran.append(1), in_thread=False),
        ]
    )
    assert ran == [1]
    status = background.background_job_status()
    assert status["boom"]["state"] == "error"
    assert "RuntimeError: smack" in status["boom"]["error"]
    assert status["after_boom"]["state"] == "finished"


def test_threaded_job_runs_as_daemon_thread(monkeypatch):
    monkeypatch.setattr(background, "_STATUS", {})
    seen = {}

    def record_thread():
        seen["thread"] = threading.current_thread()

    background.start_background_jobs([BackgroundJob(name="threaded", run=record_thread)])
    assert _wait_for(lambda: background.background_job_status().get("threaded", {}).get("state") == "finished")
    assert seen["thread"].daemon
    assert seen["thread"].name == "bg:threaded"


def test_main_registers_all_startup_jobs_via_lifespan():
    # Alla uppstartsjobb ska gå via registret; inga deprecated on_event-hooks kvar.
    names = [job.name for job in app_main.BACKGROUND_JOBS]
    assert names == [
        "allocation_observations_sync",
        "productivity_snapshot_scheduler",
        "archive_cache_scheduler",
        "demo_session_cleanup",
        "meta_media_retention_purge",
        "bug_reports_retention_purge",
        "schedule_freeze_scheduler",
    ]
    assert app_main.app.router.lifespan_context is not None
    assert not getattr(app_main.app.router, "on_startup", [])


def test_healthcheck_reports_background_job_states(monkeypatch):
    monkeypatch.setattr(background, "_STATUS", {})
    background.start_background_jobs(
        [
            BackgroundJob(name="fine", run=lambda: None, in_thread=False),
            BackgroundJob(
                name="broken",
                run=lambda: (_ for _ in ()).throw(RuntimeError("nej")),
                in_thread=False,
            ),
        ]
    )
    checks = []
    jobs = collect_background_jobs(checks)
    assert jobs["broken"]["state"] == "error"
    assert any(item["status"] == "warn" and "broken" in item["message"] for item in checks)
