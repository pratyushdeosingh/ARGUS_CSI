"""Automated tests for Phase 3 — Real-Time Streaming and WebSocket Integration."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
import pytest
from fastapi.testclient import TestClient
import httpx

from backend.app.config import Settings, get_settings
from backend.app.detectors import DetectorGateway, get_detector_gateway
from backend.app.main import app
from backend.app.models import Transaction, TransactionStatus
from backend.app.storage import ArgusStore, get_argus_store
from backend.app.websocket_manager import (
    WebSocketManager,
    create_stream_event,
    get_websocket_manager,
)

# Import in-process GraphDetector for realistic in-memory testing
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GRAPH_DIR = ROOT / "services" / "graph-detector"
if str(GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPH_DIR))

from detector import GraphDetector  # type: ignore[import-not-found]
from graph_models import Transaction as GraphTx  # type: ignore[import-not-found]



@pytest.fixture
def isolated_store(tmp_path: Path):
    """Provides a fresh ArgusStore using an ephemeral test SQLite database."""
    test_db = tmp_path / "test_argus_streaming.db"
    store = ArgusStore(test_db)
    app.dependency_overrides[get_argus_store] = lambda: store
    yield store
    app.dependency_overrides.clear()


@pytest.fixture
def mock_graph_detector():
    """In-memory GraphDetector instance."""
    return GraphDetector([])


@pytest.fixture
def mock_gateway(mock_graph_detector: GraphDetector):
    """Provides a DetectorGateway backed by an in-process MockTransport."""
    from engine import TransactionRiskEngine
    risk_engine = TransactionRiskEngine(mock_graph_detector)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/analyze":
            body = json.loads(request.content)
            txs = [GraphTx.model_validate(x) for x in body]
            signal = mock_graph_detector.analyze(txs)
            return httpx.Response(200, json=signal.model_dump(mode="json"))
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
        analysis_window_minutes=15,
        analysis_max_transactions=100,
    )
    gateway = DetectorGateway(settings=settings, transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_detector_gateway] = lambda: gateway
    app.dependency_overrides[get_settings] = lambda: settings
    yield gateway
    if get_detector_gateway in app.dependency_overrides:
        del app.dependency_overrides[get_detector_gateway]
    if get_settings in app.dependency_overrides:
        del app.dependency_overrides[get_settings]


@pytest.fixture
def isolated_manager():
    """Fresh WebSocketManager per test."""
    manager = WebSocketManager()
    app.dependency_overrides[get_websocket_manager] = lambda: manager
    yield manager
    if get_websocket_manager in app.dependency_overrides:
        del app.dependency_overrides[get_websocket_manager]


@pytest.fixture
def client(isolated_store: ArgusStore, mock_gateway: DetectorGateway, isolated_manager: WebSocketManager):
    """FastAPI TestClient wired to isolated store, in-memory detector gateway, and clean manager."""
    return TestClient(app)


def make_transaction_payload(
    transaction_id: str = "TX-001",
    timestamp: str = "2026-10-23T10:00:00Z",
    source_account: str = "ACC-101",
    destination_account: str = "ACC-202",
    amount: float = 1200.0,
    currency: str = "INR",
    device_id: str = "DEV-101",
    ip_address: str = "192.168.1.10",
    status: str = "completed",
) -> dict[str, Any]:
    return {
        "transaction_id": transaction_id,
        "timestamp": timestamp,
        "source_account": source_account,
        "destination_account": destination_account,
        "amount": amount,
        "currency": currency,
        "device_id": device_id,
        "ip_address": ip_address,
        "status": status,
    }


def test_ws_connection_and_confirmation(client: TestClient) -> None:
    """Connecting to /ws/transactions immediately receives connection.established."""
    with client.websocket_connect("/ws/transactions") as ws:
        msg = ws.receive_json()
        assert msg["event_type"] == "connection.established"
        assert msg["event_id"].startswith("EVT-")
        assert "timestamp" in msg
        assert msg["data"]["status"] == "online"
        assert "Connected" in msg["data"]["message"]


def test_transaction_ingest_broadcasts_events(client: TestClient) -> None:
    """Ingesting a valid transaction broadcasts transaction.received and transaction.scored."""
    payload = make_transaction_payload(transaction_id="TX-STREAM-1")

    with client.websocket_connect("/ws/transactions") as ws:
        # 1. Welcome event
        welcome = ws.receive_json()
        assert welcome["event_type"] == "connection.established"

        # 2. Ingest transaction via HTTP
        response = client.post("/api/transactions", json=payload)
        assert response.status_code == 201

        # 3. Expect transaction.received
        evt1 = ws.receive_json()
        assert evt1["event_type"] == "transaction.received"
        assert evt1["data"]["transaction_id"] == "TX-STREAM-1"
        assert evt1["data"]["amount"] == 1200.0

        # 4. Expect transaction.scored
        evt2 = ws.receive_json()
        assert evt2["event_type"] == "transaction.scored"
        assert evt2["data"]["transaction_id"] == "TX-STREAM-1"
        assert "risk_score" in evt2["data"]
        assert "signal_id" in evt2["data"]
        assert "anomaly_type" in evt2["data"]

        # 5. Expect transaction.scam_scored
        evt3 = ws.receive_json()
        assert evt3["event_type"] == "transaction.scam_scored"
        assert evt3["data"]["transaction_id"] == "TX-STREAM-1"
        assert "scam_score" in evt3["data"]
        assert "normalized_scam_score" in evt3["data"]


def test_multiple_simultaneous_ws_clients(client: TestClient, isolated_manager: WebSocketManager) -> None:
    """Multiple simultaneously connected clients all receive broadcast events."""
    payload = make_transaction_payload(transaction_id="TX-MULTI-1")

    with client.websocket_connect("/ws/transactions") as ws1, client.websocket_connect("/ws/transactions") as ws2:
        assert isolated_manager.active_count == 2

        # Consume connection.established on both
        assert ws1.receive_json()["event_type"] == "connection.established"
        assert ws2.receive_json()["event_type"] == "connection.established"

        # Ingest
        res = client.post("/api/transactions", json=payload)
        assert res.status_code == 201

        # Both ws1 and ws2 receive transaction.received
        e1 = ws1.receive_json()
        e2 = ws2.receive_json()
        assert e1["event_type"] == "transaction.received"
        assert e2["event_type"] == "transaction.received"
        assert e1["data"]["transaction_id"] == "TX-MULTI-1"
        assert e2["data"]["transaction_id"] == "TX-MULTI-1"

        # Both ws1 and ws2 receive transaction.scored
        s1 = ws1.receive_json()
        s2 = ws2.receive_json()
        assert s1["event_type"] == "transaction.scored"
        assert s2["event_type"] == "transaction.scored"

        # Both ws1 and ws2 receive transaction.scam_scored
        sc1 = ws1.receive_json()
        sc2 = ws2.receive_json()
        assert sc1["event_type"] == "transaction.scam_scored"
        assert sc2["event_type"] == "transaction.scam_scored"


def test_ws_client_disconnection_handled_gracefully(client: TestClient, isolated_manager: WebSocketManager) -> None:
    """When one client disconnects, broadcasting to remaining clients continues without failure."""
    with client.websocket_connect("/ws/transactions") as ws1:
        assert ws1.receive_json()["event_type"] == "connection.established"

        # Open and immediately close second client
        with client.websocket_connect("/ws/transactions") as ws2:
            assert ws2.receive_json()["event_type"] == "connection.established"

        # Post transaction
        res = client.post("/api/transactions", json=make_transaction_payload(transaction_id="TX-DISC-1"))
        assert res.status_code == 201

        # ws1 receives events normally
        evt1 = ws1.receive_json()
        assert evt1["event_type"] == "transaction.received"
        evt2 = ws1.receive_json()
        assert evt2["event_type"] == "transaction.scored"
        evt3 = ws1.receive_json()
        assert evt3["event_type"] == "transaction.scam_scored"


def test_no_broadcast_on_duplicate_identical_transaction(client: TestClient) -> None:
    """Re-submitting an identical transaction (HTTP 200) does not broadcast duplicate events."""
    payload = make_transaction_payload(transaction_id="TX-DUP-1")

    with client.websocket_connect("/ws/transactions") as ws:
        assert ws.receive_json()["event_type"] == "connection.established"

        # 1. First submission (201 Created)
        res1 = client.post("/api/transactions", json=payload)
        assert res1.status_code == 201
        assert ws.receive_json()["event_type"] == "transaction.received"
        assert ws.receive_json()["event_type"] == "transaction.scored"
        assert ws.receive_json()["event_type"] == "transaction.scam_scored"

        # 2. Second submission (200 OK, already_received)
        res2 = client.post("/api/transactions", json=payload)
        assert res2.status_code == 200
        assert res2.json()["status"] == "already_received"

        # Verify no messages queued
        # We submit a new distinct transaction to ensure queue only contains the new transaction's events
        client.post("/api/transactions", json=make_transaction_payload(transaction_id="TX-NEW-2"))
        next_evt = ws.receive_json()
        assert next_evt["event_type"] == "transaction.received"
        assert next_evt["data"]["transaction_id"] == "TX-NEW-2"
        assert ws.receive_json()["event_type"] == "transaction.scored"
        assert ws.receive_json()["event_type"] == "transaction.scam_scored"


def test_no_broadcast_on_conflict_or_validation_failure(client: TestClient) -> None:
    """Conflicting transactions (409) and validation failures (422) do not broadcast."""
    valid_payload = make_transaction_payload(transaction_id="TX-CONF-1", amount=500.0)
    conflict_payload = make_transaction_payload(transaction_id="TX-CONF-1", amount=9999.0)
    invalid_payload = make_transaction_payload(transaction_id="TX-BAD", amount=-10.0)

    with client.websocket_connect("/ws/transactions") as ws:
        assert ws.receive_json()["event_type"] == "connection.established"

        # Ingest valid
        res = client.post("/api/transactions", json=valid_payload)
        assert res.status_code == 201
        assert ws.receive_json()["event_type"] == "transaction.received"
        assert ws.receive_json()["event_type"] == "transaction.scored"
        assert ws.receive_json()["event_type"] == "transaction.scam_scored"

        # Ingest conflict -> 409
        conf_res = client.post("/api/transactions", json=conflict_payload)
        assert conf_res.status_code == 409

        # Ingest invalid -> 422
        bad_res = client.post("/api/transactions", json=invalid_payload)
        assert bad_res.status_code == 422

        # Verify stream is unaffected by sending another valid transaction
        client.post("/api/transactions", json=make_transaction_payload(transaction_id="TX-AFTER-CONF"))
        nxt = ws.receive_json()
        assert nxt["event_type"] == "transaction.received"
        assert nxt["data"]["transaction_id"] == "TX-AFTER-CONF"
        assert ws.receive_json()["event_type"] == "transaction.scored"
        assert ws.receive_json()["event_type"] == "transaction.scam_scored"


def test_rolling_window_chronological_retrieval(isolated_store: ArgusStore) -> None:
    """ArgusStore.get_recent_transactions_window properly bounds, isolates and sorts chronologically."""
    base = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc)

    # Ingest 3 transactions 5 minutes apart in session "BATCH-A"
    t1 = Transaction(
        transaction_id="A-1",
        timestamp=datetime(2026, 10, 23, 9, 50, 0, tzinfo=timezone.utc),
        source_account="ACC-1",
        destination_account="ACC-2",
        amount=100.0,
        device_id="DEV-1",
        ip_address="1.1.1.1",
        status=TransactionStatus.COMPLETED,
    )
    t2 = Transaction(
        transaction_id="A-2",
        timestamp=datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc),
        source_account="ACC-2",
        destination_account="ACC-3",
        amount=200.0,
        device_id="DEV-2",
        ip_address="1.1.1.2",
        status=TransactionStatus.COMPLETED,
    )
    # Transaction outside 15-minute window (30 minutes earlier)
    t_old = Transaction(
        transaction_id="A-0",
        timestamp=datetime(2026, 10, 23, 9, 30, 0, tzinfo=timezone.utc),
        source_account="ACC-0",
        destination_account="ACC-1",
        amount=50.0,
        device_id="DEV-0",
        ip_address="1.1.1.0",
        status=TransactionStatus.COMPLETED,
    )
    # Transaction in different session "BATCH-B"
    t_b = Transaction(
        transaction_id="B-1",
        timestamp=datetime(2026, 10, 23, 9, 55, 0, tzinfo=timezone.utc),
        source_account="ACC-B1",
        destination_account="ACC-B2",
        amount=500.0,
        device_id="DEV-B",
        ip_address="2.2.2.2",
        status=TransactionStatus.COMPLETED,
    )

    isolated_store.ingest_transaction(t1, batch_id="BATCH-A")
    isolated_store.ingest_transaction(t2, batch_id="BATCH-A")
    isolated_store.ingest_transaction(t_old, batch_id="BATCH-A")
    isolated_store.ingest_transaction(t_b, batch_id="BATCH-B")

    # Window of 15 minutes up to 10:00:00 for BATCH-A
    window = isolated_store.get_recent_transactions_window(
        end_timestamp=base,
        window_minutes=15,
        batch_id="BATCH-A",
    )

    # Should contain A-1 and A-2 in chronological order, excluding A-0 (too old) and B-1 (different batch)
    assert len(window) == 2
    assert window[0].transaction_id == "A-1"
    assert window[1].transaction_id == "A-2"


def test_rolling_window_keeps_newest_payments_and_handles_mixed_timestamp_formats(isolated_store):
    from datetime import timedelta

    base = datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc)
    for index in range(5):
        tx = Transaction.model_validate(make_transaction_payload(
            transaction_id=f"WINDOW-{index}",
            timestamp=(base + timedelta(seconds=index, microseconds=500000)).isoformat(),
        ))
        # Batch analysis and streaming ingestion use different timestamp encodings.
        if index % 2:
            isolated_store.save_transactions("WINDOW", [tx])
        else:
            isolated_store.ingest_transaction(tx, "WINDOW")

    window = isolated_store.get_recent_transactions_window(
        end_timestamp=base + timedelta(seconds=4, microseconds=500000),
        max_count=2, batch_id="WINDOW",
    )
    assert [tx.transaction_id for tx in window] == ["WINDOW-3", "WINDOW-4"]
    assert isolated_store.get_transaction("WINDOW-4").timestamp.microsecond == 500000


def test_normal_dataset_low_risk_streaming(client: TestClient) -> None:
    """Streaming normal transactions produces low risk scores and no alerts."""
    normal_file = Path("data/generated/normal.json")
    if not normal_file.is_file():
        pytest.skip("data/generated/normal.json not found")

    normal_txs = json.loads(normal_file.read_text(encoding="utf-8"))[:5]

    with client.websocket_connect("/ws/transactions") as ws:
        assert ws.receive_json()["event_type"] == "connection.established"

        for tx in normal_txs:
            res = client.post("/api/transactions", json=tx)
            assert res.status_code == 201

            recv = ws.receive_json()
            assert recv["event_type"] == "transaction.received"

            scored = ws.receive_json()
            assert scored["event_type"] == "transaction.scored"
            assert scored["data"]["risk_score"] < 0.70

            scam = ws.receive_json()
            assert scam["event_type"] == "transaction.scam_scored"
            assert scam["data"]["scam_score"] < 70.0


def test_mule_dataset_triggers_fraud_alert(client: TestClient) -> None:
    """Streaming mule scenario transactions eventually triggers high-risk alert.created."""
    mule_file = Path("data/generated/mule.json")
    if not mule_file.is_file():
        pytest.skip("data/generated/mule.json not found")

    mule_txs = json.loads(mule_file.read_text(encoding="utf-8"))

    with client.websocket_connect("/ws/transactions") as ws:
        assert ws.receive_json()["event_type"] == "connection.established"

        alert_received = False
        for tx in mule_txs:
            res = client.post("/api/transactions", json=tx)
            assert res.status_code == 201

            recv = ws.receive_json()
            assert recv["event_type"] == "transaction.received"

            scored = ws.receive_json()
            assert scored["event_type"] == "transaction.scored"

            if scored["data"]["risk_score"] >= 0.70:
                alert = ws.receive_json()
                assert alert["event_type"] == "alert.created"
                assert alert["data"]["alert_id"].startswith("ALT-")
                assert alert["data"]["risk_score"] >= 0.70
                assert len(alert["data"]["suspicious_accounts"]) >= 4
                alert_received = True

            scam = ws.receive_json()
            assert scam["event_type"] == "transaction.scam_scored"

            if scam["data"]["scam_score"] >= 70.0:
                scam_alert = ws.receive_json()
                assert scam_alert["event_type"] == "scam_alert.created"
                assert scam_alert["data"]["alert_id"].startswith("ALT-SCAM-")

            if alert_received:
                break

        assert alert_received, "Expected mule chain to trigger alert.created event"


def test_graph_detector_failure_handled_gracefully(isolated_store: ArgusStore, isolated_manager: WebSocketManager) -> None:
    """When graph detector is unavailable, transaction.analysis_failed is broadcast without failing ingestion."""
    # Custom gateway that fails
    settings = Settings(
        detector_mode="auto",
        graph_detector_url="http://127.0.0.1:9999",  # unroutable port
        ebpf_detector_url="http://127.0.0.1:9999",
        detector_timeout_seconds=0.5,
    )
    failing_gateway = DetectorGateway(settings=settings)
    app.dependency_overrides[get_detector_gateway] = lambda: failing_gateway

    client = TestClient(app)
    payload = make_transaction_payload(transaction_id="TX-FAIL-DETECTOR")

    with client.websocket_connect("/ws/transactions") as ws:
        assert ws.receive_json()["event_type"] == "connection.established"

        res = client.post("/api/transactions", json=payload)
        # Payment must still be accepted and persisted!
        assert res.status_code == 201

        # Received event
        recv = ws.receive_json()
        assert recv["event_type"] == "transaction.received"

        # Analysis failed event
        failed_evt = ws.receive_json()
        assert failed_evt["event_type"] == "transaction.analysis_failed"
        assert failed_evt["data"]["transaction_id"] == "TX-FAIL-DETECTOR"
        assert "unavailable" in failed_evt["data"]["error"]

        # Scam scoring failed event
        scam_failed = ws.receive_json()
        assert scam_failed["event_type"] == "transaction.scam_scoring_failed"
        assert scam_failed["data"]["transaction_id"] == "TX-FAIL-DETECTOR"

    # Verify transaction was persisted in SQLite nonetheless
    stored = isolated_store.get_transaction("TX-FAIL-DETECTOR")
    assert stored is not None
    assert stored.amount == 1200.0


def test_replay_script_helpers(tmp_path: Path) -> None:
    """Verify replay_transactions.py loading, run_id transformation, and sorting."""
    from scripts.replay_transactions import apply_run_id, load_dataset

    # Test apply_run_id
    raw = {"transaction_id": "MULE-100001", "amount": 100}
    with_run = apply_run_id(raw, "DEMO99")
    assert with_run["transaction_id"] == "MULE-DEMO99-100001"

    # Test load_dataset sorting
    test_json = tmp_path / "test_data.json"
    test_json.write_text(
        json.dumps([
            {"transaction_id": "TX-2", "timestamp": "2026-10-23T10:05:00Z"},
            {"transaction_id": "TX-1", "timestamp": "2026-10-23T10:01:00Z"},
        ])
    )
    loaded = load_dataset(test_json)
    assert loaded[0]["transaction_id"] == "TX-1"
    assert loaded[1]["transaction_id"] == "TX-2"
