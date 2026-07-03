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


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
