import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_desktop_main_smoke_command_runs_from_repo_root():
    result = subprocess.run(
        [sys.executable, "desktop/main.py", "--smoke-test"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
