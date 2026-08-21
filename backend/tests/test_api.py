from fastapi.testclient import TestClient

from backend.app.main import app


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
