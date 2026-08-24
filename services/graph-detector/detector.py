"""Risk aggregation and contract-safe signal generation."""

from datetime import UTC
from hashlib import sha256
from threading import RLock

from features import Evidence, extract_evidence
from graph_builder import active_transactions, build_graph
from graph_models import GraphSignal, Transaction


FEATURE_WEIGHTS = {
    "identity_change": 0.10,
    "unusual_amount": 0.17,
    "new_beneficiary": 0.08,
    "velocity": 0.10,
    "rapid_multi_hop": 0.30,
    "funds_forwarded": 0.18,
    "fan_in_out": 0.07,
}


def _risk_score(evidence: Evidence) -> float:
    weighted = sum(
        FEATURE_WEIGHTS[name] * value
        for name, value in evidence.score_by_feature.items()
    )
    # Several independent signals are more trustworthy than one isolated rule.
    corroboration = min(0.08, max(0, len(evidence.score_by_feature) - 2) * 0.02)
    return round(min(1.0, weighted + corroboration), 3)


def _anomaly_type(evidence: Evidence, risk_score: float) -> str:
    if not evidence.score_by_feature:
        return "no_suspicious_activity"
    if "rapid_multi_hop" in evidence.score_by_feature:
        return "rapid_mule_fund_movement"
    if "fan_in_out" in evidence.score_by_feature:
        return "unusual_fan_in_fan_out"
    if "identity_change" in evidence.score_by_feature and "unusual_amount" in evidence.score_by_feature:
        return "account_takeover_transfer"
    return "anomalous_transaction_activity" if risk_score >= 0.25 else "low_risk_activity"


def _signal_id(transactions: list[Transaction]) -> str:
    material = "|".join(
        item.transaction_id
        for item in sorted(transactions, key=lambda value: (value.timestamp, value.transaction_id))
    )
    return f"GRAPH-{sha256(material.encode('utf-8')).hexdigest()[:12].upper()}"


class GraphDetector:
    """Analyzer with a replaceable, thread-safe behavioral reference window."""

    def __init__(self, baseline_transactions: list[Transaction] | None = None):
        self._lock = RLock()
        self._baseline_transactions = list(baseline_transactions or [])

    @property
    def baseline_transactions(self) -> list[Transaction]:
        with self._lock:
            return list(self._baseline_transactions)

    def replace_baseline(self, transactions: list[Transaction]) -> None:
        with self._lock:
            self._baseline_transactions = list(transactions)

    def analyze(
        self,
        transactions: list[Transaction],
        baseline_transactions: list[Transaction] | None = None,
    ) -> GraphSignal:
        graph = build_graph(transactions)
        baseline = (
            self.baseline_transactions
            if baseline_transactions is None
            else list(baseline_transactions)
        )
        evidence = extract_evidence(transactions, baseline, graph)
        score = _risk_score(evidence)
        active = active_transactions(transactions)
        timestamp = max((item.timestamp for item in active), default=None)
        if timestamp is None:
            # Empty/cancelled-only batches still return a valid, deterministic
            # contract result instead of failing the orchestration pipeline.
            from datetime import datetime

            timestamp = datetime.now(UTC).replace(microsecond=0)

        return GraphSignal(
            signal_id=_signal_id(transactions),
            timestamp=timestamp,
            risk_score=score,
            anomaly_type=_anomaly_type(evidence, score),
            suspicious_accounts=sorted(evidence.accounts),
            suspicious_transactions=sorted(evidence.transactions),
            related_ips=sorted(evidence.ips),
            reasons=evidence.reasons or ["No suspicious graph or temporal behavior was observed."],
        )
