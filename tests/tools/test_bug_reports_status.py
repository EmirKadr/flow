"""Kontrakt för agenternas buggrapport-påminnelse (tools.bug_reports_status).

Skyddar: sammanfattningstexten som agenter visar Emir, att klara rapporter
inte räknas som öppna, och att verktyget avslutar mjukt (exit 0) när
inloggning saknas — påminnelsen får aldrig blockera arbetet.
"""
from __future__ import annotations

import requests

from tools import bug_reports_status


def test_summarize_counts_open_statuses_only():
    reports = [
        {"status": "new"},
        {"status": "new"},
        {"status": "seen"},
        {"status": "done"},
    ]
    text = bug_reports_status.summarize(reports)
    assert "3 öppna buggrapporter" in text
    assert "2 nya" in text
    assert "1 att göra" in text
    assert "Buggrapporter" in text


def test_summarize_empty_is_calm():
    assert "Inga öppna buggrapporter" in bug_reports_status.summarize([])
    assert "Inga öppna buggrapporter" in bug_reports_status.summarize([{"status": "done"}])


def test_main_soft_exits_on_missing_login(monkeypatch, capsys):
    response = requests.Response()
    response.status_code = 401

    def raise_unauthorized(args):
        raise requests.HTTPError(response=response)

    monkeypatch.setattr(bug_reports_status, "fetch_reports", raise_unauthorized)
    assert bug_reports_status.main([]) == 0
    assert "hoppades över" in capsys.readouterr().out

    # --strict ger exit 1 för CI-lägen som vill faila hårt.
    assert bug_reports_status.main(["--strict"]) == 1
