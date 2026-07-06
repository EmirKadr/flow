import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# In-process-servrar i browser-/desktop-tester får inte starta schemaläggare
# som gör riktiga nätverksanrop och håller produktivitetssyncens lås över
# andra tester i samma pytest-process.
os.environ.setdefault("FLOW_DISABLE_BACKGROUND_JOBS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

REPO_ROOT = Path(__file__).resolve().parent.parent

# Tempkataloger som test-/agentkörningar lämnar efter sig i repo-roten.
# Sätt FLOW_KEEP_TEST_ARTIFACTS=1 för att behålla dem (t.ex. för att
# inspektera skärmdumpar efter en visuell körning).
_SESSION_TEMP_DIR_GLOBS = (
    "tmp_screenshots",
    ".pytest-tmp*",
    ".pytest-label-editor-browser-temp",
)


def pytest_collection_modifyitems(config, items):
    """Auto-märk Playwright-tester med `browser` utifrån fixturanvändning.

    Markören styr var testerna körs: pre-push kör `-m "not browser"` (snabbt,
    deterministiskt lokalt), CI är gate för browsertesterna. Auto-märkning på
    fixturnamn i stället för manuell pytestmark gör att en ny browserfil
    aldrig kan glömma markören."""
    for item in items:
        fixtures = getattr(item, "fixturenames", ())
        if "chromium_browser" in fixtures:
            item.add_marker(pytest.mark.browser)


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("FLOW_KEEP_TEST_ARTIFACTS") == "1":
        return
    import shutil

    for pattern in _SESSION_TEMP_DIR_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
