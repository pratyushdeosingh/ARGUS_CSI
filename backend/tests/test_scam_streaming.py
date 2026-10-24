"""Integration and streaming tests for dedicated scam detection in ARGUS CSI.

Verifies:
- WebSocket event emission (transaction.scam_scored and scam_alert.created)
- Raw (0-100) and normalized (0.0-1.0) score scales
- Explainable evidence and reasons consistency
- Idempotent duplicate suppression (no repeated scoring on already_received)
- Detector failure resilience (persistence guaranteed even if detector fails)
- Canonical demo compatibility
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
import pytest
from fastapi.testclient import TestClient
import httpx

from backend.app.config import Settings
from backend.app.detectors import DetectorGateway, get_detector_gateway
from backend.app.main import app
from backend.app.storage import ArgusStore, get_argus_store
from backend.app.websocket_manager import WebSocketManager, get_websocket_manager

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DIR = ROOT / "services" / "graph-detector"
if str(GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPH_DIR))

from detector import GraphDetector  # type: ignore[import-not-found]
from engine import TransactionRiskEngine  # type: ignore[import-not-found]
from graph_models import Transaction as GraphTx  # type: ignore[import-not-found]


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    return tmp_path / "test_scam_stream.db"


@pytest.fixture
def isolated_store(temp_db: Path) -> ArgusStore:
    store = ArgusStore(temp_db)
    app.dependency_overrides[get_argus_store] = lambda: store
    yield store
    if get_argus_store in app.dependency_overrides:
        del app.dependency_overrides[get_argus_store]


@pytest.fixture
def mock_graph_detector() -> GraphDetector:
    return GraphDetector([])


@pytest.fixture
def mock_gateway(mock_graph_detector: GraphDetector) -> DetectorGateway:
    risk_engine = TransactionRiskEngine(mock_graph_detector)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/assess-financial":
            from financial import assess_financial
            body = json.loads(request.content)
            txs = [GraphTx.model_validate(tx) for tx in body["transactions"]]
            return httpx.Response(200, json=assess_financial(mock_graph_detector, txs, []).model_dump(mode="json"))
        if request.url.path == "/analyze":
            body = json.loads(request.content)
            txs = [GraphTx.model_validate(x) for x in body]
            signal = mock_graph_detector.analyze(txs)
            return httpx.Response(200, json=signal.model_dump(mode="json"))
        if request.url.path == "/score-transaction-context":
            from contextual_scoring import ContextScoreRequest, score_context
            result = score_context(mock_graph_detector, ContextScoreRequest.model_validate(json.loads(request.content)))
            return httpx.Response(200, json=result.model_dump(mode="json"))
        if request.url.path == "/score-transaction":
            body = json.loads(request.content)
            tx = GraphTx.model_validate(body)
            engine_resp = risk_engine.score_transaction(tx)
            return httpx.Response(200, json=engine_resp.model_dump(mode="json"))
        return httpx.Response(404, json={"detail": "Not found"})

    settings = Settings(
        detector_mode="auto",
        graph_detector_url="http://mock-graph-detector:8001",
        ebpf_detector_url="http://mock-ebpf-detector:8002",
        detector_timeout_seconds=2.0,
        fraud_alert_threshold=0.70,
        scam_alert_threshold=70.0,
        analysis_window_minutes=15,
        analysis_max_transactions=100,
    )
    gateway = DetectorGateway(settings=settings, transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_detector_gateway] = lambda: gateway
    yield gateway
    if get_detector_gateway in app.dependency_overrides:
        del app.dependency_overrides[get_detector_gateway]


@pytest.fixture
def isolated_manager() -> WebSocketManager:
    manager = WebSocketManager()
    app.dependency_overrides[get_websocket_manager] = lambda: manager
    yield manager
    if get_websocket_manager in app.dependency_overrides:
        del app.dependency_overrides[get_websocket_manager]


@pytest.fixture
def client(isolated_store: ArgusStore, mock_gateway: DetectorGateway, isolated_manager: WebSocketManager) -> TestClient:
    return TestClient(app)


def _make_payload(tx_id: str, src: str, dst: str, amount: float = 1200.0, minutes_offset: int = 0) -> dict[str, Any]:
    base = datetime(2026, 10, 24, 15, 0, 0, tzinfo=timezone.utc)
    ts = (base.replace(minute=base.minute + minutes_offset)).isoformat().replace("+00:00", "Z")
    return {
        "transaction_id": tx_id,
        "timestamp": ts,
        "source_account": src,
        "destination_account": dst,
        "amount": amount,
        "currency": "INR",
        "device_id": f"DEV-{src}",
        "ip_address": "198.51.100.50",
        "status": "completed",
    }


# ==============================================================================
# Tests
# ==============================================================================


def test_transaction_scam_scored_websocket_delivery(client: TestClient) -> None:
    """Validate that newly ingested transactions broadcast a structured transaction.scam_scored event."""
    payload = _make_payload("TX-SCAM-TEST-1", "ACC-USER-1", "ACC-STORE-1", 1500.0)

    with client.websocket_connect("/ws/transactions") as ws:
        # Welcome
        assert ws.receive_json()["event_type"] == "connection.established"

        # Ingest
        res = client.post("/api/transactions", json=payload)
        assert res.status_code == 201

        # 1. transaction.received
        evt1 = ws.receive_json()
        assert evt1["event_type"] == "transaction.received"

        # 2. transaction.scored (graph detector)
        evt2 = ws.receive_json()
        assert evt2["event_type"] == "transaction.scored"

        # 3. transaction.scam_scored (specialist scam detector)
        evt3 = ws.receive_json()
        assert evt3["event_type"] == "transaction.scam_scored"

        data = evt3["data"]
        assert data["transaction_id"] == "TX-SCAM-TEST-1"
        assert "scam_score" in data
        assert "normalized_scam_score" in data
        assert "risk_score" in data
        assert "normalized_risk_score" in data
        assert data["risk_band"] in ["LOW", "MODERATE", "HIGH", "SEVERE"]
        assert data["decision"] in ["ALLOW", "REVIEW", "BLOCK"]
        assert "detector_breakdown" in data
        assert "reasons" in data
        assert len(data["reasons"]) > 0

        # Normalization verification
        assert data["normalized_scam_score"] == round(data["scam_score"] / 100.0, 3)
        assert data["normalized_risk_score"] == round(data["risk_score"] / 100.0, 3)


def test_scam_alert_emission_on_threshold_exceeded(client: TestClient) -> None:
    """Validate that when scam_score exceeds scam_alert_threshold, a scam_alert.created event is emitted."""
    account = "ACC-SCAMMER-999"

    with client.websocket_connect("/ws/transactions") as ws:
        assert ws.receive_json()["event_type"] == "connection.established"

        # Send 3 setup transfers to 3 different counterparties (scam_score remains < 70)
        for i in range(1, 4):
            p = _make_payload(f"TX-SCAM-SET-{i}", account, f"PAYEE-{i}", amount=1200.0, minutes_offset=i)
            client.post("/api/transactions?session_id=scam-fanout", json=p)
            # Drain events for setup transactions (fan-out < 4, scam_score < 70)
            assert ws.receive_json()["event_type"] == "transaction.received"
            assert ws.receive_json()["event_type"] == "transaction.scored"
            assert ws.receive_json()["event_type"] == "transaction.scam_scored"

        # 4th transfer triggers fan_out >= 4 and velocity >= 4 (scam_score boosted to >= 85.0)
        eval_payload = _make_payload("TX-SCAM-TRIGGER", account, "PAYEE-4", amount=1200.0, minutes_offset=4)
        res = client.post("/api/transactions?session_id=scam-fanout", json=eval_payload)
        assert res.status_code == 201

        assert ws.receive_json()["event_type"] == "transaction.received"
        assert ws.receive_json()["event_type"] == "transaction.scored"

        scam_scored = ws.receive_json()
        if scam_scored["event_type"] == "alert.created":
            scam_scored = ws.receive_json()
        assert scam_scored["event_type"] == "transaction.scam_scored"
        assert scam_scored["data"]["scam_score"] >= 70.0

        # Expect explainable scam alert
        alert = ws.receive_json()
        assert alert["event_type"] == "scam_alert.created"
        assert alert["data"]["alert_id"] == "ALT-SCAM-TX-SCAM-TRIGGER"
        assert alert["data"]["source_account"] == account
        assert alert["data"]["destination_account"] == "PAYEE-4"
        assert alert["data"]["scam_score"] >= 70.0
        assert alert["data"]["severity"] in ["high", "critical"]
        assert len(alert["data"]["supporting_evidence"]) > 0
        assert any("high fan-out" in r for r in alert["data"]["supporting_evidence"])


def test_idempotent_duplicate_suppression_for_scam_scoring(client: TestClient) -> None:
    """Re-submitting an identical transaction (HTTP 200) does not re-score or broadcast duplicate scam events."""
    payload = _make_payload("TX-IDEMPOTENT-SCAM-1", "ACC-IDEMP-A", "ACC-IDEMP-B", 2500.0)

    with client.websocket_connect("/ws/transactions") as ws:
        assert ws.receive_json()["event_type"] == "connection.established"

        # First ingestion
        res1 = client.post("/api/transactions", json=payload)
        assert res1.status_code == 201
        assert ws.receive_json()["event_type"] == "transaction.received"
        assert ws.receive_json()["event_type"] == "transaction.scored"
        assert ws.receive_json()["event_type"] == "transaction.scam_scored"

        # Idempotent retry: exactly identical data
        res2 = client.post("/api/transactions", json=payload)
        assert res2.status_code == 200
        assert res2.json()["status"] == "already_received"

        # Verify nothing was broadcast during the second request
        # Send a different transaction to verify queue only has the new transaction
        client.post("/api/transactions", json=_make_payload("TX-IDEMPOTENT-SCAM-2", "ACC-IDEMP-C", "ACC-IDEMP-D", 1000.0))
        next_evt = ws.receive_json()
        assert next_evt["event_type"] == "transaction.received"
        assert next_evt["data"]["transaction_id"] == "TX-IDEMPOTENT-SCAM-2"


def test_scam_detector_failure_resilience(isolated_store: ArgusStore, isolated_manager: WebSocketManager) -> None:
    """When specialist scoring fails, transaction is still safely persisted and failure event is broadcast."""
    def failing_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/assess-financial":
            from backend.app.models import Transaction, GraphSignal
            from backend.tests.financial_fixtures import assessment_for
            txs = [Transaction.model_validate(tx) for tx in json.loads(request.content)["transactions"]]
            graph = GraphSignal(signal_id="GRAPH-MOCK", timestamp=txs[-1].timestamp,
                                risk_score=0.05, anomaly_type="low_risk_activity",
                                suspicious_accounts=[], suspicious_transactions=[], related_ips=[], reasons=["Normal activity"])
            return httpx.Response(200, json=assessment_for(txs, graph).model_dump(mode="json"))
        if request.url.path == "/analyze":
            return httpx.Response(200, json={
                "signal_id": "GRAPH-MOCK",
                "source": "graph_detector",
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "risk_score": 0.05,
                "anomaly_type": "low_risk_activity",
                "suspicious_accounts": [],
                "suspicious_transactions": [],
                "related_ips": [],
                "reasons": ["Normal activity"],
            })
        if request.url.path in {"/score-transaction", "/score-transaction-context"}:
            return httpx.Response(500, json={"detail": "Internal detector error"})
        return httpx.Response(404)

    settings = Settings(
        detector_mode="auto",
        graph_detector_url="http://mock-detector:8001",
        ebpf_detector_url="http://mock-detector:8002",
        detector_timeout_seconds=1.0,
    )
    gateway = DetectorGateway(settings=settings, transport=httpx.MockTransport(failing_handler))
    app.dependency_overrides[get_detector_gateway] = lambda: gateway

    client = TestClient(app)
    payload = _make_payload("TX-SCAM-FAIL-1", "ACC-FAIL-A", "ACC-FAIL-B", 3000.0)

    with client.websocket_connect("/ws/transactions") as ws:
        assert ws.receive_json()["event_type"] == "connection.established"

        res = client.post("/api/transactions", json=payload)
        # HTTP 201 must still be returned!
        assert res.status_code == 201

        # transaction.received is emitted
        assert ws.receive_json()["event_type"] == "transaction.received"

        # transaction.scored is emitted
        assert ws.receive_json()["event_type"] == "transaction.scored"

        # failure event is emitted for scam scoring
        fail_evt = ws.receive_json()
        assert fail_evt["event_type"] == "transaction.scam_scoring_failed"
        assert fail_evt["data"]["transaction_id"] == "TX-SCAM-FAIL-1"

    # Transaction is reliably persisted in database
    persisted = isolated_store.get_transaction("TX-SCAM-FAIL-1")
    assert persisted is not None
    assert persisted.amount == 3000.0


def test_canonical_demo_simulate_attack_compatibility(client: TestClient) -> None:
    """Verify that canonical simulate-attack flow continues to function without regression."""
    res = client.post("/api/demo/simulate-attack")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "attack"
    assert "incident" in data
    assert data["incident"]["incident_id"] == "INC-001"
