"""Non-browser-kontrakt för e2e-undersökningsverktyget (tools/e2e/).

Testar den rena logiken utan att starta någon webbläsare: env-inläsning
(precedens + tomma värden), Credentials-maskering, Report-formatering
(md/json), scenario-registret och CLI:ns icke-browser-vägar (--list,
okänt scenario, saknade uppgifter).
"""
from __future__ import annotations

import json

from tools.e2e import env as env_mod
from tools.e2e import scenarios as scen_mod
from tools.e2e.report import Report
from tools.e2e.scenarios import SCENARIOS, Scenario, _slug


def test_load_env_files_skips_empty_and_respects_precedence(tmp_path, monkeypatch):
    a = tmp_path / ".env"
    b = tmp_path / "app.env"
    a.write_text("FLOW_E2E_USERNAME=\nFLOW_E2E_BASE_URL=https://a\n", encoding="utf-8")
    b.write_text("FLOW_E2E_USERNAME=frombfile\nFLOW_E2E_PASSWORD=secret\n", encoding="utf-8")
    for key in ("FLOW_E2E_USERNAME", "FLOW_E2E_PASSWORD", "FLOW_E2E_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    env_mod.load_env_files((a, b))
    import os
    # Tom placeholder i a skuggar inte det ifyllda värdet i b.
    assert os.environ["FLOW_E2E_USERNAME"] == "frombfile"
    assert os.environ["FLOW_E2E_PASSWORD"] == "secret"
    assert os.environ["FLOW_E2E_BASE_URL"] == "https://a"


def test_real_env_var_wins_over_file(tmp_path, monkeypatch):
    a = tmp_path / ".env"
    a.write_text("FLOW_E2E_USERNAME=fromfile\n", encoding="utf-8")
    monkeypatch.setenv("FLOW_E2E_USERNAME", "fromenv")
    env_mod.load_env_files((a,))
    import os
    assert os.environ["FLOW_E2E_USERNAME"] == "fromenv"


def test_resolve_credentials_none_when_missing(monkeypatch):
    monkeypatch.setattr(env_mod, "load_env_files", lambda *a, **k: None)
    for key in ("FLOW_E2E_USERNAME", "FLOW_E2E_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    assert env_mod.resolve_credentials() is None


def test_resolve_credentials_present_and_redacted(monkeypatch):
    monkeypatch.setattr(env_mod, "load_env_files", lambda *a, **k: None)
    monkeypatch.setenv("FLOW_E2E_USERNAME", "anna")
    monkeypatch.setenv("FLOW_E2E_PASSWORD", "hemligt")
    monkeypatch.setenv("FLOW_E2E_BASE_URL", "https://x/")
    creds = env_mod.resolve_credentials()
    assert creds is not None
    assert creds.base_url == "https://x"  # trailing slash strippas
    assert creds.username == "anna"
    # redacted() läcker aldrig lösenordet.
    assert "hemligt" not in creds.redacted()
    assert creds.redacted() == "anna@https://x"


def test_report_counts_and_write(tmp_path):
    report = Report(out_dir=tmp_path, title="T", base_url="https://x")
    report.add_screenshot("s1", tmp_path / "s1.png", "note")
    report.add_console("oversikt", [{"level": "error", "text": "boom"}, {"level": "warning", "text": "w"}])
    report.add_network("oversikt", [{"status": 500, "url": "https://x/api/y"}])
    report.add_assertion("finns knapp", True)
    report.add_assertion("saknas fel", False, "hittade fel")
    report.add_timing("oversikt", 123.4)
    report.add_finding("error", "nåt gick fel")

    c = report.counts()
    assert c["screenshots"] == 1
    assert c["console_errors"] == 2
    assert c["network_failures"] == 1
    assert c["assertions_total"] == 2 and c["assertions_failed"] == 1
    assert report.ok() is False  # en failad assertion + ett error-finding

    md_path, json_path = report.write()
    md = md_path.read_text(encoding="utf-8")
    assert "# T" in md and "PROBLEM" in md and "boom" in md and "500" in md
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["counts"]["console_errors"] == 2
    assert data["ok"] is False


def test_report_ok_when_clean(tmp_path):
    report = Report(out_dir=tmp_path)
    report.add_assertion("allt bra", True)
    assert report.ok() is True


def test_scenarios_registry_shape():
    expected = {"smoke", "inspect", "sweep", "bug-reports", "role-access", "business-filter"}
    assert expected <= set(SCENARIOS)
    for name, scenario in SCENARIOS.items():
        assert isinstance(scenario, Scenario)
        assert callable(scenario.func)
        assert scenario.description


def test_slug_is_filesystem_safe():
    assert _slug("/installningar.html?tab=role-access") == "installningar-html-tab-role-access"
    assert _slug("  ") == "sida"
    assert _slug("Ny Vy 3") == "ny-vy-3"


def test_default_pages_are_absolute_paths():
    assert all(p.startswith("/") for p in scen_mod.DEFAULT_PAGES)


def test_cli_list_returns_zero(capsys):
    from tools.e2e.__main__ import main
    assert main(["--list"]) == 0
    assert "smoke" in capsys.readouterr().out


def test_cli_unknown_scenario_returns_2(capsys):
    from tools.e2e.__main__ import main
    assert main(["does-not-exist"]) == 2


def test_cli_missing_credentials_returns_2(monkeypatch, capsys):
    from tools.e2e import __main__ as cli
    monkeypatch.setattr(cli, "resolve_credentials", lambda *a, **k: None)
    assert cli.main(["smoke"]) == 2
    assert "FLOW_E2E" in capsys.readouterr().out
