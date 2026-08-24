from copy import deepcopy

from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


def test_health_reports_loaded_baseline():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "graph_detector",
        "version": "1.0.0",
        "baseline_transactions": 2,
    }


def test_analyze_returns_only_contract_fields(attack_payload):
    response = client.post("/analyze", json=attack_payload)

    assert response.status_code == 200
    assert set(response.json()) == {
        "signal_id",
        "source",
        "timestamp",
        "risk_score",
        "anomaly_type",
        "suspicious_accounts",
        "suspicious_transactions",
        "related_ips",
        "reasons",
    }


def test_analyze_rejects_unknown_fields(attack_payload):
    invalid = deepcopy(attack_payload)
    invalid[0]["secret_extra_field"] = True

    response = client.post("/analyze", json=invalid)

    assert response.status_code == 422


def test_analyze_rejects_non_utc_timestamp(attack_payload):
    invalid = deepcopy(attack_payload)
    invalid[0]["timestamp"] = "2026-08-17T21:00:00+05:30"

    response = client.post("/analyze", json=invalid)

    assert response.status_code == 422


def test_visualization_is_cytoscape_compatible(attack_payload):
    response = client.post("/visualize", json=attack_payload)

    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 4
    assert len(body["edges"]) == 3
    assert all(set(item) == {"data"} for item in body["nodes"] + body["edges"])
    assert all(item["data"]["suspicious"] for item in body["nodes"] + body["edges"])


def test_baseline_can_be_retrained_for_new_account_population(normal_payload):
    replacement = deepcopy(normal_payload)
    replacement[0]["source_account"] = "CUSTOM-001"
    replacement[0]["destination_account"] = "CUSTOM-002"

    response = client.post("/baseline/train", json=replacement)

    assert response.status_code == 200
    assert response.json()["baseline_transactions"] == len(replacement)
    assert response.json()["accounts_profiled"] >= 2
    assert client.get("/baseline").json() == response.json()


def test_contextual_analysis_does_not_mutate_shared_baseline(normal_payload, attack_payload):
    before = client.get("/baseline").json()

    response = client.post(
        "/analyze-context",
        json={
            "transactions": attack_payload,
            "baseline_transactions": normal_payload,
        },
    )

    assert response.status_code == 200
    assert response.json()["risk_score"] > 0.7
    assert client.get("/baseline").json() == before
