import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def super_user_listan_ar_kodens_default(monkeypatch):
    """Super User-listan får inte betyda olika saker lokalt och i CI.

    `app/backend/user_access.py:is_super_user` godkänner två vägar: rollen
    `super_user`, och ett användarnamn som råkar stå i `SUPER_USER_USERNAMES`.
    Den andra vägen pekar ut en PERSON i en driftmiljö — den är inte en roll,
    och den ska därför inte kunna smyga in i testsviten via miljön.

    `.github/workflows/test.yml` sätter `SUPER_USER_USERNAMES: admin,emikad,mikhal`.
    Ett test som seedar en användare vid namn `admin` för att pröva vad ROLLEN
    admin får, prövar alltså en Super User i CI och en vanlig admin lokalt —
    kodens default är `emikad,mikhal`. Samma svit testar då två olika saker i
    två miljöer, och skillnaden syns som rollfel som inte finns.

    Här pinnas listan till kodens default, så roller betyder samma sak överallt
    sviten körs. Ett test som vill pröva NAMNvägen sätter listan själv med
    monkeypatch — då står antagandet i testet i stället för i en workflow-fil.
    Browser- och desktoptesterna berörs inte: de startar servern i en subprocess
    med egen env (`tools/visual_smoke.py`).
    """
    from app.backend.config import Settings, settings

    monkeypatch.setattr(
        settings,
        "SUPER_USER_USERNAMES",
        Settings.model_fields["SUPER_USER_USERNAMES"].default,
    )
    monkeypatch.delenv("SUPER" "_ADMIN_USERNAMES", raising=False)
