"""Kontrakt för deploy-verifiering: k8s-probes och post-deploy-gaten.

Skyddar mot att hälsokontrollerna tyst försvinner ur deploykedjan — en deploy
utan probes/gate upptäcks annars först av en användare.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import requests

from tools import post_deploy_check

ROOT = Path(__file__).resolve().parents[2]


def test_k8s_deployment_keeps_health_probes():
    deployment = (ROOT / "k8s" / "deployment.yaml").read_text(encoding="utf-8")
    assert "livenessProbe" in deployment
    assert "readinessProbe" in deployment
    # Båda ska peka på det publika hälso-endpointet.
    assert deployment.count("path: /api/health") >= 2


def test_post_deploy_check_passes_on_200(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda url, timeout: SimpleNamespace(status_code=200)
    )
    assert post_deploy_check.main(["--base-url", "https://example.test"]) == 0


def test_post_deploy_check_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("boot")
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(post_deploy_check.time, "sleep", lambda _s: None)
    assert post_deploy_check.main(["--base-url", "https://example.test"]) == 0
    assert calls["n"] == 3


def test_post_deploy_check_fails_on_persistent_error(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda url, timeout: SimpleNamespace(status_code=503)
    )
    monkeypatch.setattr(post_deploy_check.time, "sleep", lambda _s: None)
    assert (
        post_deploy_check.main(["--base-url", "https://example.test", "--attempts", "3"]) == 1
    )
