"""Deterministic synthetic fraud and behavioral test scenarios for ARGUS CSI.

Implements all canonical scenarios:
1. NORMAL: Normal low-frequency, baseline-consistent transactions.
2. HIGH-VALUE FRAUD: Unusually large transaction compared with account history.
3. RAPID FORWARDING: A -> B -> C within a short time window.
4. MULE ACCOUNT: Multiple accounts -> Mule -> downstream accounts.
5. SCAM/FAN-OUT: One suspicious account -> many new counterparties.
6. SUSPICIOUS BURST: Many transactions within a very short time period.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from graph_models import Transaction, TransactionScoreInput, TransactionStatus


@dataclass
class FraudScenario:
    id: str
    name: str
    category: str
    description: str
    expected_band: str
    expected_decision: str
    setup_transactions: list[Transaction]
    eval_transaction: TransactionScoreInput


def get_all_scenarios() -> dict[str, FraudScenario]:
    """Build and return all deterministic synthetic fraud scenarios."""
    base_time = datetime(2026, 10, 19, 14, 0, 0, tzinfo=timezone.utc)

    # 1. NORMAL SCENARIO
    normal_setup = [
        Transaction(
            transaction_id="TX-NORM-01",
            timestamp=datetime(2026, 10, 19, 14, 5, 0, tzinfo=timezone.utc),
            source_account="ACC-101",
            destination_account="ACC-050",
            amount=1200.0,
            currency="INR",
            device_id="DEV-01",
            ip_address="203.0.113.10",
            status=TransactionStatus.COMPLETED,
        )
    ]
    normal_eval = TransactionScoreInput(
        transaction_id="TX-NORM-02",
        timestamp=datetime(2026, 10, 19, 14, 25, 0, tzinfo=timezone.utc),
        source_account="ACC-101",
        destination_account="ACC-050",
        amount=1350.0,
        currency="INR",
        device_id="DEV-01",
        ip_address="203.0.113.10",
        status=TransactionStatus.COMPLETED,
    )

    # 2. HIGH-VALUE FRAUD
    high_val_setup = [
        Transaction(
            transaction_id="TX-HV-01",
            timestamp=datetime(2026, 10, 19, 14, 0, 0, tzinfo=timezone.utc),
            source_account="ACC-HV-SRC",
            destination_account="ACC-HV-PAYEE",
            amount=1500.0,
            currency="INR",
            device_id="DEV-KNOWN",
            ip_address="203.0.113.55",
            status=TransactionStatus.COMPLETED,
        ),
        Transaction(
            transaction_id="TX-HV-02",
            timestamp=datetime(2026, 10, 19, 14, 10, 0, tzinfo=timezone.utc),
            source_account="ACC-HV-SRC",
            destination_account="ACC-HV-PAYEE",
            amount=1200.0,
            currency="INR",
            device_id="DEV-KNOWN",
            ip_address="203.0.113.55",
            status=TransactionStatus.COMPLETED,
        ),
    ]
    high_val_eval = TransactionScoreInput(
        transaction_id="TX-HV-TARGET",
        timestamp=datetime(2026, 10, 19, 14, 30, 0, tzinfo=timezone.utc),
        source_account="ACC-HV-SRC",
        destination_account="ACC-HV-UNKNOWN",
        amount=125000.0,  # >80x normal baseline
        currency="INR",
        device_id="DEV-SUSPICIOUS-NEW",
        ip_address="185.220.101.99",
        status=TransactionStatus.COMPLETED,
    )

    # 3. RAPID FORWARDING
    rf_setup = [
        Transaction(
            transaction_id="TX-RF-01",
            timestamp=datetime(2026, 10, 19, 14, 30, 0, tzinfo=timezone.utc),
            source_account="ACC-RF-A",
            destination_account="ACC-RF-B",
            amount=85000.0,
            currency="INR",
            device_id="DEV-RF-A",
            ip_address="198.51.100.11",
            status=TransactionStatus.COMPLETED,
        )
    ]
    rf_eval = TransactionScoreInput(
        transaction_id="TX-RF-02",
        timestamp=datetime(2026, 10, 19, 14, 30, 45, tzinfo=timezone.utc),  # 45 seconds later
        source_account="ACC-RF-B",
        destination_account="ACC-RF-C",
        amount=82000.0,  # 96.5% pass-through
        currency="INR",
        device_id="DEV-RF-B",
        ip_address="198.51.100.22",
        status=TransactionStatus.COMPLETED,
    )

    # 4. MULE ACCOUNT
    mule_setup = [
        Transaction(
            transaction_id="TX-MULE-IN-1",
            timestamp=datetime(2026, 10, 19, 14, 30, 0, tzinfo=timezone.utc),
            source_account="ACC-VICTIM-1",
            destination_account="ACC-MULE-501",
            amount=25000.0,
            currency="INR",
            device_id="DEV-V1",
            ip_address="198.51.100.101",
            status=TransactionStatus.COMPLETED,
        ),
        Transaction(
            transaction_id="TX-MULE-IN-2",
            timestamp=datetime(2026, 10, 19, 14, 31, 0, tzinfo=timezone.utc),
            source_account="ACC-VICTIM-2",
            destination_account="ACC-MULE-501",
            amount=25000.0,
            currency="INR",
            device_id="DEV-V2",
            ip_address="198.51.100.102",
            status=TransactionStatus.COMPLETED,
        ),
        Transaction(
            transaction_id="TX-MULE-IN-3",
            timestamp=datetime(2026, 10, 19, 14, 31, 45, tzinfo=timezone.utc),
            source_account="ACC-VICTIM-3",
            destination_account="ACC-MULE-501",
            amount=25000.0,
            currency="INR",
            device_id="DEV-V3",
            ip_address="198.51.100.103",
            status=TransactionStatus.COMPLETED,
        ),
        Transaction(
            transaction_id="TX-MULE-IN-4",
            timestamp=datetime(2026, 10, 19, 14, 32, 15, tzinfo=timezone.utc),
            source_account="ACC-VICTIM-4",
            destination_account="ACC-MULE-501",
            amount=25000.0,
            currency="INR",
            device_id="DEV-V4",
            ip_address="198.51.100.104",
            status=TransactionStatus.COMPLETED,
        ),
    ]
    # Total received: 100,000 INR from 4 distinct accounts
    # Forwarding 95,000 INR within 2 minutes
    mule_eval = TransactionScoreInput(
        transaction_id="TX-MULE-OUT-TARGET",
        timestamp=datetime(2026, 10, 19, 14, 33, 30, tzinfo=timezone.utc),
        source_account="ACC-MULE-501",
        destination_account="ACC-LAUNDERING-EXIT",
        amount=95000.0,
        currency="INR",
        device_id="DEV-MULE",
        ip_address="185.220.101.50",
        status=TransactionStatus.COMPLETED,
    )

    # 5. SCAM / FAN-OUT
    scam_setup = [
        Transaction(
            transaction_id="TX-SCAM-01",
            timestamp=datetime(2026, 10, 19, 14, 40, 0, tzinfo=timezone.utc),
            source_account="ACC-SCAM-700",
            destination_account="ACC-TARGET-A",
            amount=15000.0,
            currency="INR",
            device_id="DEV-SCAM",
            ip_address="185.220.101.70",
            status=TransactionStatus.COMPLETED,
        ),
        Transaction(
            transaction_id="TX-SCAM-02",
            timestamp=datetime(2026, 10, 19, 14, 40, 45, tzinfo=timezone.utc),
            source_account="ACC-SCAM-700",
            destination_account="ACC-TARGET-B",
            amount=15000.0,
            currency="INR",
            device_id="DEV-SCAM",
            ip_address="185.220.101.70",
            status=TransactionStatus.COMPLETED,
        ),
        Transaction(
            transaction_id="TX-SCAM-03",
            timestamp=datetime(2026, 10, 19, 14, 41, 30, tzinfo=timezone.utc),
            source_account="ACC-SCAM-700",
            destination_account="ACC-TARGET-C",
            amount=15000.0,
            currency="INR",
            device_id="DEV-SCAM",
            ip_address="185.220.101.70",
            status=TransactionStatus.COMPLETED,
        ),
        Transaction(
            transaction_id="TX-SCAM-04",
            timestamp=datetime(2026, 10, 19, 14, 42, 10, tzinfo=timezone.utc),
            source_account="ACC-SCAM-700",
            destination_account="ACC-TARGET-D",
            amount=15000.0,
            currency="INR",
            device_id="DEV-SCAM",
            ip_address="185.220.101.70",
            status=TransactionStatus.COMPLETED,
        ),
    ]
    scam_eval = TransactionScoreInput(
        transaction_id="TX-SCAM-05-TARGET",
        timestamp=datetime(2026, 10, 19, 14, 42, 50, tzinfo=timezone.utc),
        source_account="ACC-SCAM-700",
        destination_account="ACC-TARGET-E",  # 5th distinct new payee
        amount=15000.0,
        currency="INR",
        device_id="DEV-SCAM",
        ip_address="185.220.101.70",
        status=TransactionStatus.COMPLETED,
    )

    # 6. SUSPICIOUS BURST
    burst_setup = [
        Transaction(
            transaction_id="TX-BURST-01",
            timestamp=datetime(2026, 10, 19, 14, 50, 0, tzinfo=timezone.utc),
            source_account="ACC-BURST-800",
            destination_account="ACC-RECV-X",
            amount=30000.0,
            currency="INR",
            device_id="DEV-BURST",
            ip_address="198.51.100.80",
            status=TransactionStatus.COMPLETED,
        ),
        Transaction(
            transaction_id="TX-BURST-02",
            timestamp=datetime(2026, 10, 19, 14, 50, 20, tzinfo=timezone.utc),
            source_account="ACC-BURST-800",
            destination_account="ACC-RECV-Y",
            amount=30000.0,
            currency="INR",
            device_id="DEV-BURST",
            ip_address="198.51.100.80",
            status=TransactionStatus.COMPLETED,
        ),
        Transaction(
            transaction_id="TX-BURST-03",
            timestamp=datetime(2026, 10, 19, 14, 50, 40, tzinfo=timezone.utc),
            source_account="ACC-BURST-800",
            destination_account="ACC-RECV-Z",
            amount=30000.0,
            currency="INR",
            device_id="DEV-BURST",
            ip_address="198.51.100.80",
            status=TransactionStatus.COMPLETED,
        ),
    ]
    burst_eval = TransactionScoreInput(
        transaction_id="TX-BURST-TARGET",
        timestamp=datetime(2026, 10, 19, 14, 51, 0, tzinfo=timezone.utc),  # 4th transaction within 60s
        source_account="ACC-BURST-800",
        destination_account="ACC-RECV-W",
        amount=30000.0,
        currency="INR",
        device_id="DEV-BURST",
        ip_address="198.51.100.80",
        status=TransactionStatus.COMPLETED,
    )

    scenarios = {
        "normal": FraudScenario(
            id="normal",
            name="Normal Transaction",
            category="Legitimate",
            description="Routine, low-frequency transfer conforming to customer baseline.",
            expected_band="LOW",
            expected_decision="ALLOW",
            setup_transactions=normal_setup,
            eval_transaction=normal_eval,
        ),
        "high_value_fraud": FraudScenario(
            id="high_value_fraud",
            name="High-Value Fraud Anomaly",
            category="Account Takeover",
            description="Transfer amount >80x normal baseline to an unseen counterparty from a new device/IP.",
            expected_band="SEVERE",
            expected_decision="BLOCK",
            setup_transactions=high_val_setup,
            eval_transaction=high_val_eval,
        ),
        "rapid_forwarding": FraudScenario(
            id="rapid_forwarding",
            name="Rapid Multi-Hop Forwarding",
            category="Mule Chain",
            description="Account receives funds and forwards 96.5% to downstream party within 45 seconds.",
            expected_band="SEVERE",
            expected_decision="BLOCK",
            setup_transactions=rf_setup,
            eval_transaction=rf_eval,
        ),
        "mule_account": FraudScenario(
            id="mule_account",
            name="Mule Account (Fan-In & Pass-Through)",
            category="Money Mule",
            description="Account receives funds from 4 distinct accounts and forwards 95% within 2 minutes.",
            expected_band="SEVERE",
            expected_decision="BLOCK",
            setup_transactions=mule_setup,
            eval_transaction=mule_eval,
        ),
        "scam_fan_out": FraudScenario(
            id="scam_fan_out",
            name="Scam Fan-Out / Dispersal",
            category="Scam Disbursement",
            description="Account rapidly initiates payments to 5 new counterparties within 3 minutes.",
            expected_band="SEVERE",
            expected_decision="BLOCK",
            setup_transactions=scam_setup,
            eval_transaction=scam_eval,
        ),
        "suspicious_burst": FraudScenario(
            id="suspicious_burst",
            name="Suspicious Transaction Velocity Burst",
            category="Automated Fraud",
            description="High velocity clustering of 4 identical amount transfers within 60 seconds.",
            expected_band="SEVERE",
            expected_decision="BLOCK",
            setup_transactions=burst_setup,
            eval_transaction=burst_eval,
        ),
    }
    return scenarios
