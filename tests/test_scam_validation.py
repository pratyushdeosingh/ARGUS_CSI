"""Comprehensive synthetic validation test suite for dedicated scam detection.

Covers:
- Positive scam scenarios (Rapid fan-out, velocity bursts, repeated amounts, volume surges)
- Negative legitimate scenarios (Normal transfers, cancelled payments, modest sparse history)
- Identified false-positive gap scenarios (Payroll, merchant settlements, refund batches, sparse history spikes)
- Explainable evidence verification for all positive signals.
"""

from datetime import datetime, timedelta, timezone
import pytest

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
GRAPH_DIR = ROOT / "services" / "graph-detector"
if str(GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPH_DIR))

from graph_models import (
    Transaction,
    TransactionStatus,
    TransactionScoreInput,
)
from history import InMemoryHistoryStore
from scam_detector import ScamDetector, SCAM_WEIGHTS


def _make_tx(
    tx_id: str,
    src: str,
    dst: str,
    amount: float,
    ts: datetime,
    status: TransactionStatus = TransactionStatus.COMPLETED,
    currency: str = "INR",
) -> Transaction:
    return Transaction(
        transaction_id=tx_id,
        timestamp=ts,
        source_account=src,
        destination_account=dst,
        amount=amount,
        currency=currency,
        device_id="DEV-001",
        ip_address="192.168.1.100",
        status=status,
    )


@pytest.fixture
def baseline_txs() -> list[Transaction]:
    """Baseline history where normal accounts have transactions around 1,000 INR."""
    base_time = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    return [
        _make_tx(f"BASE-{i}", "ACC-NORMAL", f"ACC-REC-{i}", 1000.0, base_time + timedelta(hours=i))
        for i in range(10)
    ]


@pytest.fixture
def scam_detector(baseline_txs: list[Transaction]) -> tuple[ScamDetector, InMemoryHistoryStore]:
    store = InMemoryHistoryStore()
    detector = ScamDetector(store, baseline_transactions=baseline_txs)
    return detector, store


# ==============================================================================
# Positive Scam Scenarios
# ==============================================================================


def test_positive_rapid_fan_out(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Validate rapid fan-out to 5 distinct recipients triggers max fan_out_score (100.0)."""
    detector, store = scam_detector
    t0 = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)
    account = "ACC-SCAM-FANOUT"

    # 4 setup transactions to 4 distinct counterparties
    for i in range(1, 5):
        tx = _make_tx(f"TX-FO-0{i}", account, f"DEST-FO-0{i}", 2000.0, t0 + timedelta(minutes=i))
        store.add_transaction(tx)

    # 5th transaction to a 5th distinct counterparty
    current_tx = _make_tx("TX-FO-05", account, "DEST-FO-05", 2000.0, t0 + timedelta(minutes=5))
    result = detector.evaluate_account(account, current_tx=current_tx)

    assert result.fan_out_score == 100.0
    assert result.velocity_burst_score == 100.0
    assert result.scam_score >= 85.0
    assert result.metrics["distinct_counterparties"] == 5
    assert any("high fan-out" in r for r in result.reasons)
    assert any("Abnormal transaction frequency" in r for r in result.reasons)


def test_positive_velocity_burst(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Validate rapid velocity burst of 5 transactions within a short window triggers velocity_burst_score (100.0)."""
    detector, store = scam_detector
    t0 = datetime(2026, 10, 24, 12, 10, 0, tzinfo=timezone.utc)
    account = "ACC-VELOCITY"

    # Rapid burst to the same 2 counterparties
    for i in range(1, 5):
        dest = f"DEST-VEL-{i % 2}"
        tx = _make_tx(f"TX-VEL-0{i}", account, dest, 1500.0, t0 + timedelta(seconds=i * 20))
        store.add_transaction(tx)

    current_tx = _make_tx("TX-VEL-05", account, "DEST-VEL-0", 1500.0, t0 + timedelta(seconds=100))
    result = detector.evaluate_account(account, current_tx=current_tx)

    assert result.velocity_burst_score == 100.0
    assert result.metrics["outgoing_count"] == 5
    assert any("Abnormal transaction frequency" in r for r in result.reasons)


def test_positive_repeated_amounts(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Validate 3 identical structured amounts trigger repeated_amounts_score (100.0)."""
    detector, store = scam_detector
    t0 = datetime(2026, 10, 24, 12, 20, 0, tzinfo=timezone.utc)
    account = "ACC-REPEATED"

    # 2 transfers of 15,000 INR
    tx1 = _make_tx("TX-REP-01", account, "DEST-R1", 15000.0, t0)
    tx2 = _make_tx("TX-REP-02", account, "DEST-R2", 15000.0, t0 + timedelta(minutes=2))
    store.add_transaction(tx1)
    store.add_transaction(tx2)

    # 3rd transfer of 15,000 INR (same rounded bucket)
    current_tx = _make_tx("TX-REP-03", account, "DEST-R3", 15000.0, t0 + timedelta(minutes=4))
    result = detector.evaluate_account(account, current_tx=current_tx)

    assert result.repeated_amounts_score == 100.0
    assert any("Repeated amount pattern" in r for r in result.reasons)


def test_positive_volume_surge(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Validate transaction exceeding baseline median by >= 8x triggers volume_surge_score (100.0) and high-confidence boost."""
    detector, store = scam_detector
    account = "ACC-NORMAL"  # Has baseline median of 1,000 INR
    t0 = datetime(2026, 10, 24, 12, 30, 0, tzinfo=timezone.utc)

    # Single transfer of 10,000 INR (10.0x baseline median)
    current_tx = _make_tx("TX-SURGE-01", account, "DEST-NEW", 10000.0, t0)
    result = detector.evaluate_account(account, current_tx=current_tx)

    assert result.volume_surge_score == 100.0
    assert result.metrics["amount_ratio_vs_baseline"] >= 8.0
    # Rule boost for 100% volume surge forces score >= 85.0
    assert result.scam_score >= 85.0
    assert any("higher than baseline median" in r for r in result.reasons)


def test_positive_temporal_clustering(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Validate rapid succession (< 30s) triggers temporal_cluster_score (100.0)."""
    detector, store = scam_detector
    account = "ACC-CLUSTER"
    t0 = datetime(2026, 10, 24, 12, 40, 0, tzinfo=timezone.utc)

    tx1 = _make_tx("TX-TC-01", account, "DEST-A", 1200.0, t0)
    store.add_transaction(tx1)

    # Second transfer 15 seconds later
    current_tx = _make_tx("TX-TC-02", account, "DEST-B", 1200.0, t0 + timedelta(seconds=15))
    result = detector.evaluate_account(account, current_tx=current_tx)

    assert result.temporal_cluster_score == 100.0
    assert any("Suspicious temporal clustering" in r for r in result.reasons)


# ==============================================================================
# Negative Legitimate Scenarios
# ==============================================================================


def test_negative_normal_first_time_beneficiary(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Validate a normal baseline-consistent transfer to a single new beneficiary produces 0 scam score."""
    detector, store = scam_detector
    account = "ACC-NORMAL"  # Baseline median 1,000 INR
    t0 = datetime(2026, 10, 24, 13, 0, 0, tzinfo=timezone.utc)

    # Single transaction to a new counterparty, amount normal (1,200 INR ~ 1.2x median)
    current_tx = _make_tx("TX-NORM-01", account, "DEST-FIRST-TIME", 1200.0, t0)
    result = detector.evaluate_account(account, current_tx=current_tx)

    assert result.fan_out_score == 0.0
    assert result.velocity_burst_score == 0.0
    assert result.volume_surge_score == 0.0
    assert result.repeated_amounts_score == 0.0
    assert result.temporal_cluster_score == 0.0
    assert result.scam_score == 0.0
    assert len(result.reasons) == 0


def test_negative_cancelled_payments_ignored(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Validate CANCELLED transactions are ignored and do NOT trigger fan-out or velocity burst."""
    detector, store = scam_detector
    account = "ACC-CANCELLED-TEST"
    t0 = datetime(2026, 10, 24, 13, 10, 0, tzinfo=timezone.utc)

    # 4 cancelled transactions to different counterparties
    for i in range(1, 5):
        tx = _make_tx(
            f"TX-CANC-0{i}",
            account,
            f"DEST-CANC-0{i}",
            1000.0,
            t0 + timedelta(minutes=i),
            status=TransactionStatus.CANCELLED,
        )
        store.add_transaction(tx)

    # 1 active completed transaction
    current_tx = _make_tx("TX-ACTIVE-01", account, "DEST-ACTIVE", 1000.0, t0 + timedelta(minutes=5))
    result = detector.evaluate_account(account, current_tx=current_tx)

    assert result.metrics["distinct_counterparties"] == 1
    assert result.metrics["outgoing_count"] == 1
    assert result.fan_out_score == 0.0
    assert result.velocity_burst_score == 0.0
    assert result.scam_score == 0.0


def test_negative_sparse_history_modest_amount(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Validate a brand-new account with no history sending a modest amount (< global fallback 1,000 INR) scores 0."""
    detector, store = scam_detector
    account = "ACC-BRAND-NEW"
    t0 = datetime(2026, 10, 24, 13, 20, 0, tzinfo=timezone.utc)

    # Transfer of 500 INR (ratio 0.5x vs fallback median 1000 INR)
    current_tx = _make_tx("TX-SPARSE-01", account, "DEST-FRIEND", 500.0, t0)
    result = detector.evaluate_account(account, current_tx=current_tx)

    assert result.volume_surge_score == 0.0
    assert result.fan_out_score == 0.0
    assert result.velocity_burst_score == 0.0
    assert result.scam_score == 0.0


# ==============================================================================
# Gap Analysis Scenarios (Characterizing False Positives)
# ==============================================================================


def test_gap_legitimate_payroll_activity(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Characterize Gap 1: Legitimate corporate payroll disbursement triggers high fan-out & velocity false positives.

    Documented Gap:
    A legitimate business disbursing salaries to 6 employees in 3 minutes triggers:
    - fan_out_score = 100.0
    - velocity_burst_score = 100.0
    - repeated_amounts_score = 100.0 (if salaries match standard brackets)
    - temporal_cluster_score = 100.0
    Resulting in a false-positive scam score >= 85.0.
    """
    detector, store = scam_detector
    corp_account = "CORP-PAYROLL-001"
    t0 = datetime(2026, 10, 24, 13, 30, 0, tzinfo=timezone.utc)

    # 5 previous salary transfers of 50,000 INR
    for i in range(1, 6):
        tx = _make_tx(f"TX-PAYROLL-{i}", corp_account, f"EMP-{i:03d}", 50000.0, t0 + timedelta(seconds=i * 20))
        store.add_transaction(tx)

    # 6th salary transfer
    current_tx = _make_tx("TX-PAYROLL-6", corp_account, "EMP-006", 50000.0, t0 + timedelta(seconds=120))
    result = detector.evaluate_account(corp_account, current_tx=current_tx)

    # Documents existing detector limitation:
    assert result.fan_out_score == 100.0
    assert result.velocity_burst_score == 100.0
    assert result.repeated_amounts_score == 100.0
    assert result.scam_score >= 85.0
    # Explainable reasons reflect why the heuristic was misled:
    assert any("high fan-out" in r for r in result.reasons)
    assert any("Repeated amount pattern" in r for r in result.reasons)


def test_gap_merchant_settlement_batches(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Characterize Gap 2: Merchant settlement batch to 5 vendors triggers fan-out false positive."""
    detector, store = scam_detector
    merchant_account = "MERCHANT-GATEWAY-01"
    t0 = datetime(2026, 10, 24, 13, 40, 0, tzinfo=timezone.utc)

    for i in range(1, 5):
        tx = _make_tx(f"TX-SETTLE-{i}", merchant_account, f"VENDOR-{i}", 25000.0 + i * 100, t0 + timedelta(seconds=i * 30))
        store.add_transaction(tx)

    current_tx = _make_tx("TX-SETTLE-5", merchant_account, "VENDOR-5", 28000.0, t0 + timedelta(seconds=150))
    result = detector.evaluate_account(merchant_account, current_tx=current_tx)

    assert result.fan_out_score == 100.0
    assert result.velocity_burst_score == 100.0
    assert result.scam_score >= 80.0


def test_gap_customer_refund_batches(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Characterize Gap 3: Customer service issuing 3 refunds of identical amount (e.g. 1,499 INR)."""
    detector, store = scam_detector
    merchant = "ECOMMERCE-STORE-01"
    t0 = datetime(2026, 10, 24, 13, 50, 0, tzinfo=timezone.utc)

    tx1 = _make_tx("TX-REF-01", merchant, "CUST-1", 1499.0, t0)
    tx2 = _make_tx("TX-REF-02", merchant, "CUST-2", 1499.0, t0 + timedelta(minutes=1))
    store.add_transaction(tx1)
    store.add_transaction(tx2)

    current_tx = _make_tx("TX-REF-03", merchant, "CUST-3", 1499.0, t0 + timedelta(minutes=2))
    result = detector.evaluate_account(merchant, current_tx=current_tx)

    assert result.repeated_amounts_score == 100.0
    assert result.fan_out_score == 55.0  # 3 distinct receivers
    assert result.velocity_burst_score == 60.0  # 3 outgoing transactions
    assert result.scam_score >= 50.0


def test_gap_sparse_history_spike(scam_detector: tuple[ScamDetector, InMemoryHistoryStore]) -> None:
    """Characterize Gap 4: New user without transaction history sending 9,000 INR triggers false positive volume surge.

    Because there is no prior baseline for this account, it falls back to the global default
    of 1,000 INR median. 9,000 INR is 9.0x (> 8x), triggering volume_surge_score = 100.0 and
    boosting raw score directly to >= 85.0.
    """
    detector, store = scam_detector
    new_user = "ACC-UNPROFILED-USER"
    t0 = datetime(2026, 10, 24, 14, 0, 0, tzinfo=timezone.utc)

    current_tx = _make_tx("TX-NEW-LAPTOP", new_user, "DEST-STORE", 9000.0, t0)
    result = detector.evaluate_account(new_user, current_tx=current_tx)

    assert result.volume_surge_score == 100.0
    assert result.scam_score >= 85.0
    assert any("higher than baseline median" in r for r in result.reasons)


def test_engine_scam_fan_out_scenario_end_to_end() -> None:
    """Validate end-to-end TransactionRiskEngine on canonical scam_fan_out scenario."""
    from detector import GraphDetector
    from engine import TransactionRiskEngine
    from scenarios import get_all_scenarios
    from graph_models import RiskBand, Decision

    scenarios = get_all_scenarios()
    scam_scenario = scenarios["scam_fan_out"]

    detector = GraphDetector([])
    engine = TransactionRiskEngine(detector)

    # Seed setup transactions into engine history store
    for tx in scam_scenario.setup_transactions:
        engine.history_store.add_transaction(tx)

    # Score eval transaction
    response = engine.score_transaction(scam_scenario.eval_transaction)

    assert response.risk_band == RiskBand.SEVERE
    assert response.decision == Decision.BLOCK
    assert response.risk_score >= 80.0
    assert response.detectors.scam >= 80.0
    assert len(response.reasons) > 0
    assert "Scam Detector" in " ".join(response.top_factors)

