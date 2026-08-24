from fastapi.testclient import TestClient

import api
from api import DetectorRuntime


def test_replay_api_flow(monkeypatch) -> None:
    monkeypatch.setattr(api, "runtime", DetectorRuntime(configured_mode="replay"))
    client = TestClient(api.app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["mode"] == "replay"
    assert client.get("/signals/latest").status_code == 404
    simulation = client.post("/simulate")
    assert simulation.status_code == 200
    assert simulation.json()["mode"] == "replay"
    assert simulation.json()["events_collected"] == 3
    signal = client.get("/signals/latest")
    assert signal.status_code == 200
    assert signal.json()["risk_score"] == 0.87
    assert signal.json()["source"] == "ebpf_detector"


def test_normal_scenario_stays_low_risk(monkeypatch) -> None:
    monkeypatch.setattr(api, "runtime", DetectorRuntime(configured_mode="replay"))
    client = TestClient(api.app)
    assert client.post("/simulate?scenario=normal").status_code == 200
    signal = client.get("/signals/latest").json()
    assert signal["risk_score"] == 0.03
    assert signal["event_type"] == "normal_payment_service_activity"
    assert signal["indicators"] == []


def test_strict_live_mode_reports_missing_prerequisite(monkeypatch) -> None:
    monkeypatch.setattr(api, "runtime", DetectorRuntime(configured_mode="live"))
    monkeypatch.setattr(api, "availability", lambda: (False, "test unavailable"))
    client = TestClient(api.app)
    response = client.post("/simulate")
    assert response.status_code == 503
    assert response.json()["detail"] == "test unavailable"


def test_analyzes_caller_supplied_telemetry_without_replay(monkeypatch) -> None:
    monkeypatch.setattr(api, "runtime", DetectorRuntime(configured_mode="replay"))
    client = TestClient(api.app)
    response = client.post(
        "/analyze-events",
        json={
            "host": "settlement-node-7",
            "service": "instant-payouts",
            "events": [
                {
                    "timestamp": "2026-08-24T10:00:00Z",
                    "event_type": "process_exec",
                    "process": "payout-worker",
                    "details": {"unexpected_child": True},
                },
                {
                    "timestamp": "2026-08-24T10:00:02Z",
                    "event_type": "network_connect",
                    "process": "payout-worker",
                    "details": {
                        "destination_ip": "185.220.101.10",
                        "suspicious_destination": True,
                    },
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["signal_id"].startswith("EBPF-")
    assert payload["signal_id"] != "EBPF-001"
    assert payload["host"] == "settlement-node-7"
    assert payload["service"] == "instant-payouts"
    assert payload["process"] == "payout-worker"
