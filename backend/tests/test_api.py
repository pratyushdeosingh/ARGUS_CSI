import json

import httpx
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.detectors import DetectorGateway, get_detector_gateway
from backend.app.main import app
from backend.app.simulator import load_attack_transactions, load_mock_signals
from backend.app.state import DemoState


client = TestClient(app)


def test_health_and_normal_state() -> None:
    assert client.get("/health").json() == {"status": "ok"}

    response = client.get("/api/demo/normal")
    assert response.status_code == 200
    assert response.json()["mode"] == "normal"
    assert response.json()["incident"] is None


def test_attack_to_human_approved_containment(monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_DETECTOR_MODE", "fixture")
    attack_response = client.post("/api/demo/simulate-attack")
    assert attack_response.status_code == 200

    attack = attack_response.json()
    assert attack["incident"]["severity"] == "critical"
    assert attack["incident"]["status"] == "awaiting_approval"
    assert attack["graph_signal"]["risk_score"] == 0.92
    assert attack["system_signal"]["risk_score"] == 0.87
    assert attack["detector_status"]["graph"]["origin"] == "fixture"

    approval_response = client.post("/api/incidents/INC-001/approve")
    assert approval_response.status_code == 200

    approved = approval_response.json()
    assert approved["incident"]["status"] == "contained"
    assert len(approved["audit_events"]) == 3
    assert all(
        action["status"] == "executed"
        for action in approved["incident"]["recommended_actions"]
    )

    duplicate = client.post("/api/incidents/INC-001/approve")
    assert duplicate.status_code == 409
    assert len(client.get("/api/audit").json()) == 3


def test_fixture_detector_status(monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_DETECTOR_MODE", "fixture")
    response = client.get("/api/detectors/status")
    assert response.status_code == 200
    assert response.json()["graph"]["origin"] == "fixture"
    assert response.json()["system"]["mode"] == "fixture"


def test_arbitrary_data_analysis_creates_dynamic_investigation() -> None:
    graph, system = load_mock_signals()
    graph = graph.model_copy(
        update={
            "signal_id": "GRAPH-CUSTOM-TEST",
            "suspicious_accounts": ["CUSTOM-ORIGIN", "CUSTOM-MULE"],
        }
    )
    system = system.model_copy(
        update={
            "signal_id": "EBPF-CUSTOM-TEST",
            "host": "custom-host",
            "service": "custom-service",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/analyze-context":
            submitted = json.loads(request.content)
            assert len(submitted["baseline_transactions"]) == 1
            return httpx.Response(200, json=graph.model_dump(mode="json"))
        if request.url.path == "/analyze-events":
            return httpx.Response(200, json=system.model_dump(mode="json"))
        return httpx.Response(404)

    settings = Settings(
        detector_mode="required",
        graph_detector_url="http://graph.test",
        ebpf_detector_url="http://ebpf.test",
        detector_timeout_seconds=1,
    )
    gateway = DetectorGateway(settings, DemoState(), httpx.MockTransport(handler))
    app.dependency_overrides[get_detector_gateway] = lambda: gateway
    transactions = [
        item.model_copy(
            update={
                "transaction_id": f"CUSTOM-{index}",
                "source_account": "CUSTOM-ORIGIN" if index == 1 else item.source_account,
            }
        ).model_dump(mode="json")
        for index, item in enumerate(load_attack_transactions(), start=1)
    ]
    try:
        response = client.post(
            "/api/analyze",
            json={
                "source_label": "integration-test",
                "transactions": transactions,
                "baseline_transactions": [transactions[0]],
                "telemetry_events": [
                    {
                        "timestamp": "2026-08-17T15:31:18Z",
                        "event_type": "network_connect",
                        "process": "custom-worker",
                        "details": {
                            "destination_ip": "185.220.101.10",
                            "suspicious_destination": True,
                        },
                    }
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "analysis"
    assert payload["analysis_id"] == "ANL-CUSTOM-TEST"
    assert payload["incident"]["incident_id"].startswith("INC-")
    assert payload["incident"]["incident_id"] != "INC-001"
    assert payload["incident"]["affected_accounts"] == [
        "CUSTOM-ORIGIN",
        "CUSTOM-MULE",
    ]
