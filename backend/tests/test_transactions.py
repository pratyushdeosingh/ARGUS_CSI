"""Automated tests for Phase 2 transaction ingestion API and storage."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.detectors import DetectorGateway, get_detector_gateway
from backend.app.main import app
from backend.app.models import (
    GraphSignal,
    IngestionStatus,
    SystemSignal,
    Transaction,
    TransactionStatus,
)
from backend.app.state import DemoState
from backend.app.storage import ArgusStore, get_argus_store
import httpx


@pytest.fixture
def isolated_store(tmp_path: Path):
    """Provides a fresh, isolated ArgusStore using an ephemeral test SQLite database."""
    test_db = tmp_path / "test_argus_ingestion.db"
    store = ArgusStore(test_db)
    app.dependency_overrides[get_argus_store] = lambda: store
    yield store
    app.dependency_overrides.clear()


@pytest.fixture
def client(isolated_store: ArgusStore):
    """FastAPI test client wired to the isolated store."""
    return TestClient(app)


def make_transaction_payload(
    transaction_id: str = "NORM-100001",
    timestamp: str = "2026-10-23T10:00:00Z",
    source_account: str = "ACC-101",
    destination_account: str = "ACC-205",
    amount: float = 1500.0,
    currency: str = "INR",
    device_id: str = "DEV-101",
    ip_address: str = "198.51.100.10",
    status: str = "completed",
) -> dict:
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


def test_valid_transaction_ingestion(client: TestClient) -> None:
    """A valid transaction is ingested successfully with HTTP 201."""
    payload = make_transaction_payload()
    response = client.post("/api/transactions", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "created"
    assert data["transaction_id"] == "NORM-100001"
    assert data["message"] == "Transaction ingested successfully"
    assert data["transaction"]["amount"] == 1500.0
    assert data["transaction"]["currency"] == "INR"


def test_invalid_transaction_input_missing_fields(client: TestClient) -> None:
    """Missing required contract fields return HTTP 422."""
    payload = make_transaction_payload()
    del payload["destination_account"]

    response = client.post("/api/transactions", json=payload)
    assert response.status_code == 422


def test_negative_and_zero_amounts_rejected(client: TestClient) -> None:
    """Zero and negative transaction amounts are rejected with HTTP 422."""
    zero_payload = make_transaction_payload(amount=0.0)
    res_zero = client.post("/api/transactions", json=zero_payload)
    assert res_zero.status_code == 422

    neg_payload = make_transaction_payload(amount=-50.0)
    res_neg = client.post("/api/transactions", json=neg_payload)
    assert res_neg.status_code == 422


def test_invalid_payment_status_rejected(client: TestClient) -> None:
    """Statuses outside pending, completed, cancelled are rejected with HTTP 422."""
    payload = make_transaction_payload(status="unknown_status")
    response = client.post("/api/transactions", json=payload)
    assert response.status_code == 422


def test_invalid_or_non_utc_timestamps_rejected(client: TestClient) -> None:
    """Timestamps without UTC timezone or malformed are rejected with HTTP 422."""
    # Non-UTC timezone offset (+05:30)
    ist_payload = make_transaction_payload(timestamp="2026-10-23T15:30:00+05:30")
    res_ist = client.post("/api/transactions", json=ist_payload)
    assert res_ist.status_code == 422

    # Naive timestamp without timezone
    naive_payload = make_transaction_payload(timestamp="2026-10-23T10:00:00")
    res_naive = client.post("/api/transactions", json=naive_payload)
    assert res_naive.status_code == 422

    # Invalid timestamp format
    invalid_ts = make_transaction_payload(timestamp="not-a-timestamp")
    res_inv = client.post("/api/transactions", json=invalid_ts)
    assert res_inv.status_code == 422


def test_duplicate_transaction_identical_data(client: TestClient, isolated_store: ArgusStore) -> None:
    """Submitting the exact same transaction ID and data returns HTTP 200 without duplication."""
    payload = make_transaction_payload(transaction_id="NORM-DUPLICATE-1")

    # First ingestion -> HTTP 201 Created
    res1 = client.post("/api/transactions", json=payload)
    assert res1.status_code == 201
    assert res1.json()["status"] == "created"

    # Second ingestion with identical payload -> HTTP 200 OK (already_received)
    res2 = client.post("/api/transactions", json=payload)
    assert res2.status_code == 200
    assert res2.json()["status"] == "already_received"
    assert "already received" in res2.json()["message"]

    # Verify no duplicate row was created in SQLite
    all_txs = isolated_store.list_transactions(limit=100)
    assert len(all_txs) == 1
    assert all_txs[0].transaction_id == "NORM-DUPLICATE-1"


def test_duplicate_transaction_conflicting_data(client: TestClient) -> None:
    """Submitting an existing transaction ID with conflicting fields returns HTTP 409 Conflict."""
    payload1 = make_transaction_payload(transaction_id="NORM-CONFLICT-1", amount=1500.0)
    res1 = client.post("/api/transactions", json=payload1)
    assert res1.status_code == 201

    # Conflict on amount
    payload2 = make_transaction_payload(transaction_id="NORM-CONFLICT-1", amount=9999.0)
    res2 = client.post("/api/transactions", json=payload2)
    assert res2.status_code == 409
    assert "already exists with different" in res2.json()["detail"]

    # Conflict on destination account
    payload3 = make_transaction_payload(
        transaction_id="NORM-CONFLICT-1", destination_account="ACC-DIFFERENT"
    )
    res3 = client.post("/api/transactions", json=payload3)
    assert res3.status_code == 409


def test_transaction_persistence_across_store_instances(tmp_path: Path) -> None:
    """Stored transactions persist across distinct ArgusStore instances pointing to the same file."""
    db_file = tmp_path / "persistence_test.db"
    store1 = ArgusStore(db_file)
    tx = Transaction(
        transaction_id="PERSIST-101",
        timestamp=datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc),
        source_account="ACC-101",
        destination_account="ACC-202",
        amount=2500.0,
        currency="INR",
        device_id="DEV-101",
        ip_address="198.51.100.10",
        status=TransactionStatus.COMPLETED,
    )
    status = store1.ingest_transaction(tx)
    assert status == IngestionStatus.CREATED

    # Instantiate new store object on same SQLite file
    store2 = ArgusStore(db_file)
    retrieved = store2.get_transaction("PERSIST-101")
    assert retrieved is not None
    assert retrieved == tx


def test_get_transactions_retrieval_and_empty(client: TestClient) -> None:
    """GET /api/transactions returns an empty list initially and all items after ingestion."""
    # Initially empty
    empty_res = client.get("/api/transactions")
    assert empty_res.status_code == 200
    assert empty_res.json() == []

    # Ingest two transactions
    client.post("/api/transactions", json=make_transaction_payload(transaction_id="TX-1"))
    client.post("/api/transactions", json=make_transaction_payload(transaction_id="TX-2"))

    list_res = client.get("/api/transactions")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 2


def test_pagination_and_ordering(client: TestClient) -> None:
    """Transactions are sorted timestamp DESC, transaction_id DESC with pagination limit/offset."""
    # Ingest transactions with staggered timestamps
    txs = [
        make_transaction_payload("TX-A", timestamp="2026-10-23T10:00:00Z"),
        make_transaction_payload("TX-B", timestamp="2026-10-23T10:01:00Z"),
        make_transaction_payload("TX-C", timestamp="2026-10-23T10:02:00Z"),
        make_transaction_payload("TX-D", timestamp="2026-10-23T10:03:00Z"),
        make_transaction_payload("TX-E", timestamp="2026-10-23T10:03:00Z"),  # tie-breaker with TX-D
    ]
    for tx in txs:
        res = client.post("/api/transactions", json=tx)
        assert res.status_code == 201

    # Page 1: limit 2, offset 0 -> newest first. TX-E and TX-D have same timestamp, TX-E > TX-D alphabetically
    page1 = client.get("/api/transactions?limit=2&offset=0")
    assert page1.status_code == 200
    ids_p1 = [item["transaction_id"] for item in page1.json()]
    assert ids_p1 == ["TX-E", "TX-D"]

    # Page 2: limit 2, offset 2
    page2 = client.get("/api/transactions?limit=2&offset=2")
    assert page2.status_code == 200
    ids_p2 = [item["transaction_id"] for item in page2.json()]
    assert ids_p2 == ["TX-C", "TX-B"]

    # Page 3: limit 2, offset 4
    page3 = client.get("/api/transactions?limit=2&offset=4")
    assert page3.status_code == 200
    ids_p3 = [item["transaction_id"] for item in page3.json()]
    assert ids_p3 == ["TX-A"]

    # Invalid pagination bounds
    assert client.get("/api/transactions?limit=0").status_code == 422
    assert client.get("/api/transactions?limit=201").status_code == 422
    assert client.get("/api/transactions?offset=-1").status_code == 422


def test_transaction_lookup_by_id(client: TestClient) -> None:
    """GET /api/transactions/{id} retrieves existing transaction or returns 404."""
    payload = make_transaction_payload(transaction_id="LOOKUP-101")
    client.post("/api/transactions", json=payload)

    found_res = client.get("/api/transactions/LOOKUP-101")
    assert found_res.status_code == 200
    assert found_res.json()["transaction_id"] == "LOOKUP-101"

    not_found_res = client.get("/api/transactions/NON-EXISTENT-ID")
    assert not_found_res.status_code == 404
    assert "not found" in not_found_res.json()["detail"].lower()


def test_existing_api_analyze_compatibility(client: TestClient, isolated_store: ArgusStore) -> None:
    """The existing /api/analyze endpoint works seamlessly alongside the ingestion API."""
    graph_sig = GraphSignal(
        signal_id="GRAPH-ANL-TEST",
        timestamp=datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc),
        risk_score=0.1,
        anomaly_type="no_suspicious_activity",
        suspicious_accounts=[],
        suspicious_transactions=[],
        related_ips=[],
        reasons=["Normal"],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=graph_sig.model_dump(mode="json"))

    settings = Settings(
        detector_mode="required",
        graph_detector_url="http://graph.test",
        ebpf_detector_url="http://ebpf.test",
        detector_timeout_seconds=1,
    )
    gateway = DetectorGateway(settings, DemoState(), httpx.MockTransport(handler))
    app.dependency_overrides[get_detector_gateway] = lambda: gateway

    batch = [
        make_transaction_payload(transaction_id=f"BATCH-TX-{i}")
        for i in range(3)
    ]
    try:
        response = client.post(
            "/api/analyze",
            json={
                "source_label": "batch-test",
                "transactions": batch,
            },
        )
    finally:
        app.dependency_overrides.pop(get_detector_gateway, None)

    assert response.status_code == 200
    data = response.json()
    assert data["analysis_id"] == "ANL-ANL-TEST"

    # Batch transactions were stored and can be retrieved
    stored = isolated_store.list_transactions(limit=10)
    assert len(stored) == 3


def test_platform_metrics_compatibility(client: TestClient) -> None:
    """Ingested transactions update the existing platform metrics accurately."""
    client.post(
        "/api/transactions",
        json=make_transaction_payload(
            transaction_id="MET-1", amount=1200.0, source_account="ACC-1", destination_account="ACC-2"
        ),
    )
    client.post(
        "/api/transactions",
        json=make_transaction_payload(
            transaction_id="MET-2", amount=800.0, source_account="ACC-2", destination_account="ACC-3"
        ),
    )

    metrics_res = client.get("/api/platform/metrics")
    assert metrics_res.status_code == 200
    metrics = metrics_res.json()
    assert metrics["transactions_ingested"] == 2
    assert metrics["total_value_observed"] == 2000.0
    assert metrics["accounts_observed"] == 3


def test_concurrent_duplicate_ingestion(client: TestClient) -> None:
    """Concurrent identical submissions handle idempotency safely without 500 errors."""
    payload = make_transaction_payload(transaction_id="CONCURRENT-1", amount=5000.0)

    def send():
        return client.post("/api/transactions", json=payload)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(send) for _ in range(12)]
        responses = [f.result() for f in futures]

    status_codes = [r.status_code for r in responses]
    # Exactly one request creates the record (201), the rest find it already received (200)
    assert status_codes.count(201) == 1
    assert status_codes.count(200) == 11
    assert all(code in (200, 201) for code in status_codes)
