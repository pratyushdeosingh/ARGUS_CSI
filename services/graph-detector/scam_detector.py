"""Dedicated Scam Behavioral Detector for ARGUS CSI.

Focuses on behavioral and graph anomalies associated with fraud and scam patterns:
- Rapid fan-out to multiple previously unseen counterparties
- Sudden bursts of outbound transactions
- Repeated or structured transaction amounts
- Abnormal transaction frequency
- Unusual temporal transaction clustering

NOTE: This is a prototype behavioral detector focused on graph/transaction dynamics,
not a semantic content classifier.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import statistics
from typing import Any

from history import BaseHistoryStore
from graph_models import Transaction, TransactionStatus


SCAM_WEIGHTS = {
    "fan_out": 0.30,            # High fan-out to distinct/unrelated counterparties
    "velocity_burst": 0.25,     # Abnormal transaction frequency / burst
    "repeated_amounts": 0.20,   # Repeated / structured amounts
    "volume_surge": 0.15,       # Amount surge relative to historical baseline
    "temporal_cluster": 0.10,   # Tight inter-transaction time clustering
}


@dataclass
class ScamScoreResult:
    """Detailed scam score result with component breakdowns and reasons."""
    account: str
    scam_score: float  # Heuristic 0-100 score
    fan_out_score: float
    velocity_burst_score: float
    repeated_amounts_score: float
    volume_surge_score: float
    temporal_cluster_score: float
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class ScamDetector:
    """Detects scam-like behavioral patterns in real-time transactions."""

    def __init__(self, history_store: BaseHistoryStore, baseline_transactions: list[Transaction] | None = None):
        self.history_store = history_store
        self.baseline_transactions = list(baseline_transactions or [])
        self._baseline_amounts_by_account: dict[str, list[float]] = {}
        for tx in self.baseline_transactions:
            if tx.status != TransactionStatus.CANCELLED:
                self._baseline_amounts_by_account.setdefault(tx.source_account, []).append(tx.amount)

    def evaluate_account(
        self, account: str, current_tx: Transaction | None = None, window_seconds: float = 1800.0
    ) -> ScamScoreResult:
        """Evaluate an account's recent outgoing activity for scam and fraud patterns."""
        outgoing = self.history_store.get_account_outgoing(account, window_seconds, as_of=current_tx.timestamp if current_tx else None)

        if current_tx and current_tx.status != TransactionStatus.CANCELLED:
            if current_tx.source_account == account and current_tx not in outgoing:
                outgoing = sorted([*outgoing, current_tx], key=lambda t: t.timestamp)

        active_outgoing = [t for t in outgoing if t.status != TransactionStatus.CANCELLED and (current_tx is None or t.currency == current_tx.currency)]
        reasons: list[str] = []

        distinct_receivers = {t.destination_account for t in active_outgoing}
        tx_count = len(active_outgoing)
        amounts = [t.amount for t in active_outgoing]

        # 1. High Fan-out Score (0-100)
        # Initiating transfers to multiple distinct counterparties
        dest_count = len(distinct_receivers)
        if dest_count >= 5:
            fan_out_score = 100.0
        elif dest_count == 4:
            fan_out_score = 80.0
        elif dest_count == 3:
            fan_out_score = 55.0
        elif dest_count == 2:
            fan_out_score = 25.0
        else:
            fan_out_score = 0.0

        if dest_count >= 3:
            window_minutes = max(1.0, round(window_seconds / 60.0))
            reasons.append(
                f"Account {account} initiated transactions with {dest_count} distinct counterparties "
                f"within {window_minutes:.0f} minutes (high fan-out)."
            )

        # 2. Velocity Burst Score (0-100)
        # Abnormal transaction frequency in short interval
        if tx_count >= 5:
            velocity_burst_score = 100.0
        elif tx_count == 4:
            velocity_burst_score = 80.0
        elif tx_count == 3:
            velocity_burst_score = 60.0
        elif tx_count == 2:
            velocity_burst_score = 25.0
        else:
            velocity_burst_score = 0.0

        if tx_count >= 3:
            reasons.append(
                f"Abnormal transaction frequency: {tx_count} outgoing transactions in active window."
            )

        # 3. Repeated / Structured Amounts Score (0-100)
        # Repeated identical or similar amounts indicative of mass smurfing or scam disbursements
        repeated_amounts_score = 0.0
        if tx_count >= 2:
            # Round amounts to handle tiny floating point variations
            rounded_amounts = [round(a, -1) for a in amounts]
            counts = Counter(rounded_amounts)
            most_common_amount, most_common_count = counts.most_common(1)[0]
            if most_common_count >= 3:
                repeated_amounts_score = 100.0
                reasons.append(
                    f"Repeated amount pattern: {most_common_count} transfers with identical or structured "
                    f"amount (~{most_common_amount:,.0f})."
                )
            elif most_common_count == 2 and tx_count >= 2:
                repeated_amounts_score = 70.0
                reasons.append(
                    f"Structured transactions: 2 transfers with matching amount ({most_common_amount:,.0f})."
                )

        # 4. Volume Surge Score (0-100)
        # Amount significantly exceeding account's normal baseline
        volume_surge_score = 0.0
        ratio = 1.0
        baseline_amounts = [t.amount for t in self.baseline_transactions
                            if t.source_account == account
                            and t.status != TransactionStatus.CANCELLED
                            and (current_tx is None or t.currency == current_tx.currency)]
        if baseline_amounts:
            baseline_median = statistics.median(baseline_amounts)
        else:
            # Use general baseline or active median
            all_baseline_amounts = [t.amount for t in self.baseline_transactions if t.status != TransactionStatus.CANCELLED and (current_tx is None or t.currency == current_tx.currency)]
            baseline_median = statistics.median(all_baseline_amounts) if all_baseline_amounts else 1000.0

        current_amount = current_tx.amount if current_tx else (amounts[-1] if amounts else 0.0)
        if current_amount > 0 and baseline_median > 0:
            ratio = current_amount / max(baseline_median, 1.0)
            if ratio >= 8.0:
                volume_surge_score = 100.0
                reasons.append(
                    f"Transaction amount ({current_amount:,.0f}) is {ratio:.1f}x higher than baseline median "
                    f"({baseline_median:,.0f})."
                )
            elif ratio >= 5.0:
                volume_surge_score = 80.0
                reasons.append(
                    f"Unusually high transaction volume: {ratio:.1f}x normal median."
                )
            elif ratio >= 3.0:
                volume_surge_score = 50.0
            elif ratio >= 2.0:
                volume_surge_score = 25.0

        # 5. Temporal Cluster Score (0-100)
        # Transactions sent with minimal seconds interval between them
        temporal_cluster_score = 0.0
        if tx_count >= 2:
            time_gaps = [
                (t2.timestamp - t1.timestamp).total_seconds()
                for t1, t2 in zip(active_outgoing, active_outgoing[1:])
            ]
            min_gap = min(time_gaps) if time_gaps else 9999.0
            if min_gap <= 30.0:
                temporal_cluster_score = 100.0
                reasons.append(
                    f"Suspicious temporal clustering: subsequent transfers sent within {min_gap:.0f} seconds."
                )
            elif min_gap <= 60.0:
                temporal_cluster_score = 75.0
            elif min_gap <= 120.0:
                temporal_cluster_score = 40.0

        # Weighted combination
        raw_score = (
            SCAM_WEIGHTS["fan_out"] * fan_out_score
            + SCAM_WEIGHTS["velocity_burst"] * velocity_burst_score
            + SCAM_WEIGHTS["repeated_amounts"] * repeated_amounts_score
            + SCAM_WEIGHTS["volume_surge"] * volume_surge_score
            + SCAM_WEIGHTS["temporal_cluster"] * temporal_cluster_score
        )

        # High-confidence pattern boosts
        if volume_surge_score == 100.0:
            raw_score = max(raw_score, 85.0)
        elif volume_surge_score >= 80.0:
            raw_score = max(raw_score, 75.0)

        if fan_out_score >= 80.0 and velocity_burst_score >= 80.0:
            raw_score = max(raw_score, 85.0)

        strong_indicators = sum(
            1
            for s in [fan_out_score, velocity_burst_score, repeated_amounts_score, volume_surge_score]
            if s >= 60.0
        )
        boost = 10.0 if strong_indicators >= 3 else (5.0 if strong_indicators == 2 else 0.0)
        final_scam_score = round(min(100.0, raw_score + boost), 1)

        metrics = {
            "distinct_counterparties": dest_count,
            "outgoing_count": tx_count,
            "amount_ratio_vs_baseline": ratio,
        }

        return ScamScoreResult(
            account=account,
            scam_score=final_scam_score,
            fan_out_score=fan_out_score,
            velocity_burst_score=velocity_burst_score,
            repeated_amounts_score=repeated_amounts_score,
            volume_surge_score=volume_surge_score,
            temporal_cluster_score=temporal_cluster_score,
            reasons=reasons,
            metrics=metrics,
        )

    def evaluate_transaction(self, transaction: Transaction) -> tuple[float, list[str]]:
        """Evaluate the source account of a transaction for scam behavior."""
        result = self.evaluate_account(transaction.source_account, current_tx=transaction)
        return result.scam_score, result.reasons
