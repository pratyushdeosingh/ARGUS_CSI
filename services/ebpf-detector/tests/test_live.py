"""Opt-in Linux test that exercises the real bpftrace-to-API path."""

import os

import pytest
from fastapi.testclient import TestClient

import api
from api import DetectorRuntime
from collector.bpftrace import availability


@pytest.mark.skipif(
    os.getenv("ARGUS_RUN_LIVE_EBPF_TEST") != "1",
    reason="set ARGUS_RUN_LIVE_EBPF_TEST=1 on a privileged Linux host",
)
def test_live_api_collects_all_canonical_evidence(monkeypatch) -> None:
    live_available, reason = availability()
    assert live_available, reason

    monkeypatch.setattr(api, "runtime", DetectorRuntime(configured_mode="live"))
    client = TestClient(api.app)
    simulation = client.post("/simulate")
    assert simulation.status_code == 200, simulation.text
    assert simulation.json()["mode"] == "live"

    signal = client.get("/signals/latest")
    assert signal.status_code == 200
    payload = signal.json()
    assert payload["risk_score"] == 0.87
    assert payload["related_ips"] == ["185.220.101.10"]
    assert payload["indicators"] == [
        "Unexpected child process",
        "Sensitive configuration file accessed",
        "Connection to suspicious external IP",
    ]
