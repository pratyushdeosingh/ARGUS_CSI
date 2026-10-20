"""Comprehensive unit and integration tests for real-time transaction scoring.

Covers:
- Valid transaction scoring
- Invalid transaction inputs
- Normal transaction baseline compliance
- High-value anomaly detection
- Rapid forwarding detection
- Mule account detection (fan-in, forwarding speed, turnover, retention)
- Scam / fan-out detection
- Risk aggregation and scoring weights
- Risk band assignments and decisions
- Grounded explainable AI outputs
- Temporal ordering influence
- Stateful history layer and sliding window
- Scenario execution APIs
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app import app, risk_engine
from history import InMemoryHistoryStore
from models import Decision, RiskBand, Transaction, TransactionScoreInput, TransactionStatus
from mule_detector import MuleDetector
from scam_detector import ScamDetector
from scenarios import get_all_scenarios


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_engine_state():
    """Ensure each test runs with a fresh, clean state."""
    risk_engine.reset()
    yield
    risk_engine.reset()


def test_valid_transaction_scoring_endpoint():
    """Verify POST /score-transaction returns all expected contract fields and types."""
    payload = {
        "transaction_id": "TX-TEST-001",
        "sender": "ACC-101",
        "receiver": "ACC-202",
        "amount": 2500.0,
        "timestamp": "2026-10-19T14:30:00Z",
    }
    response = client.post("/score-transaction", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["transaction_id"] == "TX-TEST-001"
    assert data["sender"] == "ACC-101"
    assert data["receiver"] == "ACC-202"
    assert data["amount"] == 2500.0
    assert "risk_score" in data
    assert 0 <= data["risk_score"] <= 100
    assert data["risk_band"] in ["LOW", "MODERATE", "HIGH", "SEVERE"]
    assert data["decision"] in ["ALLOW", "REVIEW", "BLOCK"]

    detectors = data["detectors"]
    assert set(detectors.keys()) == {"rules", "tgnn", "mule", "scam"}
    assert all(0 <= val <= 100 for val in detectors.values())

    assert isinstance(data["reasons"], list)
    assert len(data["reasons"]) > 0
    assert isinstance(data["top_factors"], list)
    assert isinstance(data["explanation"], str)


def test_invalid_transaction_input_rejected():
    """Verify invalid inputs (negative amounts, missing accounts) return 422."""
    # Negative amount
    bad_amount = {
        "transaction_id": "TX-BAD-1",
        "sender": "ACC-1",
        "receiver": "ACC-2",
        "amount": -500.0,
        "timestamp": "2026-10-19T14:30:00Z",
    }
    res = client.post("/score-transaction", json=bad_amount)
    assert res.status_code == 422

    # Missing destination
    missing_dest = {
        "transaction_id": "TX-BAD-2",
        "sender": "ACC-1",
        "amount": 500.0,
        "timestamp": "2026-10-19T14:30:00Z",
    }
    res = client.post("/score-transaction", json=missing_dest)
    assert res.status_code == 422


def test_normal_transaction_low_risk():
    """Verify normal low-frequency transaction yields LOW risk and ALLOW decision."""
    scenarios = get_all_scenarios()
    normal = scenarios["normal"]

    # Pre-seed baseline setup
    for tx in normal.setup_transactions:
        risk_engine.history_store.add_transaction(tx)

    result = risk_engine.score_transaction(normal.eval_transaction)

    assert result.risk_score < 30
    assert result.risk_band == RiskBand.LOW
    assert result.decision == Decision.ALLOW
    assert "Normal transaction activity" in result.reasons[0]


def test_high_value_anomaly_detection():
    """Verify an abnormal high-value transfer produces elevated risk and explanation."""
    scenarios = get_all_scenarios()
    scenario = scenarios["high_value_fraud"]

    for tx in scenario.setup_transactions:
        risk_engine.history_store.add_transaction(tx)

    result = risk_engine.score_transaction(scenario.eval_transaction)

    assert result.risk_score >= 60
    assert result.risk_band in [RiskBand.HIGH, RiskBand.SEVERE]
    assert result.decision in [Decision.REVIEW, Decision.BLOCK]
    assert any("higher than baseline" in r or "normal median" in r for r in result.reasons)


def test_rapid_forwarding_detection():
    """Verify rapid forwarding of funds A -> B -> C is detected within seconds."""
    scenarios = get_all_scenarios()
    scenario = scenarios["rapid_forwarding"]

    for tx in scenario.setup_transactions:
        risk_engine.history_store.add_transaction(tx)

    result = risk_engine.score_transaction(scenario.eval_transaction)

    assert result.risk_score >= 70
    assert result.risk_band in [RiskBand.HIGH, RiskBand.SEVERE]
    assert result.decision == Decision.BLOCK
    assert any("forwarded" in r.lower() or "rapid" in r.lower() for r in result.reasons)


def test_mule_account_detection():
    """Verify dedicated mule detector catches fan-in, turnover, and pass-through."""
    scenarios = get_all_scenarios()
    scenario = scenarios["mule_account"]

    for tx in scenario.setup_transactions:
        risk_engine.history_store.add_transaction(tx)

    result = risk_engine.score_transaction(scenario.eval_transaction)

    assert result.detectors.mule >= 65
    assert result.risk_score >= 75
    assert result.risk_band == RiskBand.SEVERE
    assert result.decision == Decision.BLOCK
    assert any("distinct senders" in r or "forwarded" in r or "turnover" in r for r in result.reasons)


def test_scam_fan_out_detection():
    """Verify dedicated scam detector catches rapid fan-out to multiple accounts."""
    scenarios = get_all_scenarios()
    scenario = scenarios["scam_fan_out"]

    for tx in scenario.setup_transactions:
        risk_engine.history_store.add_transaction(tx)

    result = risk_engine.score_transaction(scenario.eval_transaction)

    assert result.detectors.scam >= 60
    assert result.risk_score >= 70
    assert result.risk_band == RiskBand.SEVERE
    assert result.decision == Decision.BLOCK
    assert any("counterparties" in r or "fan-out" in r for r in result.reasons)


def test_suspicious_burst_detection():
    """Verify clustered burst transactions with identical amounts trigger alert."""
    scenarios = get_all_scenarios()
    scenario = scenarios["suspicious_burst"]

    for tx in scenario.setup_transactions:
        risk_engine.history_store.add_transaction(tx)

    result = risk_engine.score_transaction(scenario.eval_transaction)

    assert result.risk_score >= 70
    assert result.risk_band in [RiskBand.HIGH, RiskBand.SEVERE]
    assert result.decision == Decision.BLOCK
    assert any("frequency" in r.lower() or "burst" in r.lower() or "repeated" in r.lower() for r in result.reasons)


def test_temporal_ordering_affects_mule_risk():
    """Verify that chronological order of events alters mule risk calculation."""
    store_a = InMemoryHistoryStore()
    store_b = InMemoryHistoryStore()

    mule_a = MuleDetector(store_a)
    mule_b = MuleDetector(store_b)

    t1 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 19, 12, 1, 0, tzinfo=timezone.utc)

    # Order A: Inflow then Outflow (Mule pattern: received money then forwarded out)
    inflow = Transaction(
        transaction_id="TX-IN",
        timestamp=t1,
        source_account="ACC-IN",
        destination_account="ACC-MULE",
        amount=50000.0,
        currency="INR",
        device_id="DEV-1",
        ip_address="10.0.0.1",
        status=TransactionStatus.COMPLETED,
    )
    outflow = Transaction(
        transaction_id="TX-OUT",
        timestamp=t2,
        source_account="ACC-MULE",
        destination_account="ACC-EXIT",
        amount=48000.0,
        currency="INR",
        device_id="DEV-2",
        ip_address="10.0.0.2",
        status=TransactionStatus.COMPLETED,
    )

    store_a.add_transaction(inflow)
    score_a, _ = mule_a.evaluate_transaction(outflow)

    # Order B: Outflow happened first, then inflow (Not a forwarding chain)
    outflow_early = Transaction(
        transaction_id="TX-OUT",
        timestamp=t1,
        source_account="ACC-MULE",
        destination_account="ACC-EXIT",
        amount=48000.0,
        currency="INR",
        device_id="DEV-2",
        ip_address="10.0.0.2",
        status=TransactionStatus.COMPLETED,
    )
    inflow_late = Transaction(
        transaction_id="TX-IN",
        timestamp=t2,
        source_account="ACC-IN",
        destination_account="ACC-MULE",
        amount=50000.0,
        currency="INR",
        device_id="DEV-1",
        ip_address="10.0.0.1",
        status=TransactionStatus.COMPLETED,
    )

    store_b.add_transaction(outflow_early)
    score_b, _ = mule_b.evaluate_transaction(inflow_late)

    # Order A must show higher forwarding risk than Order B
    assert score_a > score_b


def test_in_memory_history_store_sliding_window():
    """Verify history store tracks transactions and respects sliding window filtering."""
    store = InMemoryHistoryStore()
    t0 = datetime(2026, 10, 19, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)

    tx_old = Transaction(
        transaction_id="TX-OLD",
        timestamp=t0,
        source_account="ACC-1",
        destination_account="ACC-2",
        amount=100.0,
        currency="INR",
        device_id="DEV-1",
        ip_address="10.0.0.1",
        status=TransactionStatus.COMPLETED,
    )
    tx_recent = Transaction(
        transaction_id="TX-RECENT",
        timestamp=t1,
        source_account="ACC-1",
        destination_account="ACC-2",
        amount=200.0,
        currency="INR",
        device_id="DEV-1",
        ip_address="10.0.0.1",
        status=TransactionStatus.COMPLETED,
    )

    store.add_transaction(tx_old)
    store.add_transaction(tx_recent)

    # Without window, returns all
    all_out = store.get_account_outgoing("ACC-1")
    assert len(all_out) == 2

    # With 1-hour window (3600s), only the recent transaction within 1h of t1 is returned
    recent_out = store.get_account_outgoing("ACC-1", window_seconds=3600.0)
    assert len(recent_out) == 1
    assert recent_out[0].transaction_id == "TX-RECENT"


def test_scenarios_api_list_and_run():
    """Verify scenario catalog API and run endpoint execute deterministically."""
    # List scenarios
    list_res = client.get("/api/scenarios")
    assert list_res.status_code == 200
    scenarios = list_res.json()
    assert len(scenarios) == 6
    scenario_ids = [s["id"] for s in scenarios]
    assert "normal" in scenario_ids
    assert "mule_account" in scenario_ids
    assert "scam_fan_out" in scenario_ids
    assert "high_value_fraud" in scenario_ids

    # Run each scenario and verify expected bands
    for s in scenarios:
        run_res = client.post(f"/api/scenarios/{s['id']}/run")
        assert run_res.status_code == 200
        data = run_res.json()
        assert "score_result" in data
        assert "visualization" in data
        score = data["score_result"]
        assert score["decision"] == s["expected_decision"]
        assert score["risk_band"] == s["expected_band"]


def test_html_demo_ui_endpoint():
    """Verify demo web interface is served at root and /demo."""
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "ARGUS CSI" in res_root.text
    assert "cytoscape" in res_root.text

    res_demo = client.get("/demo")
    assert res_demo.status_code == 200
    assert "Detector Breakdown" in res_demo.text
