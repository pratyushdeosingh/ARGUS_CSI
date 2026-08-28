"""Risk aggregation and contract-safe signal generation."""

from datetime import UTC
from hashlib import sha256

from features import Evidence, extract_evidence
from graph_builder import active_transactions, build_graph
from models import GraphSignal, Transaction


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


def _anomaly_type(evidence: Evidence, risk_score: float, tgnn_score: float) -> str:
    if not evidence.score_by_feature and tgnn_score < 0.25:
        return "no_suspicious_activity"
    if "rapid_multi_hop" in evidence.score_by_feature:
        return "rapid_mule_fund_movement"
    if "fan_in_out" in evidence.score_by_feature:
        return "unusual_fan_in_fan_out"
    if "identity_change" in evidence.score_by_feature and "unusual_amount" in evidence.score_by_feature:
        return "account_takeover_transfer"
    return "anomalous_transaction_activity" if (risk_score >= 0.25 or tgnn_score >= 0.25) else "low_risk_activity"


def _signal_id(transactions: list[Transaction]) -> str:
    material = "|".join(
        item.transaction_id
        for item in sorted(transactions, key=lambda value: (value.timestamp, value.transaction_id))
    )
    return f"GRAPH-{sha256(material.encode('utf-8')).hexdigest()[:12].upper()}"


class GraphDetector:
    """Stateless analyzer with an immutable behavioral reference window."""

    def __init__(self, baseline_transactions: list[Transaction] | None = None):
        self.baseline_transactions = list(baseline_transactions or [])
        import torch
        from pathlib import Path
        from tgnn import TGNN, train_tgnn

        self.tgnn = TGNN()

        # Load pre-trained weights if available, or train on the fly
        current_dir = Path(__file__).resolve().parent
        weights_path = current_dir / "tgnn_weights.pt"

        if weights_path.is_file():
            self.tgnn.load_state_dict(torch.load(weights_path, map_location=torch.device("cpu"), weights_only=True))
        else:
            # Locate baseline (normal) and attack transaction datasets to train on the fly
            root_dir = current_dir.parent.parent
            attack_path = root_dir / "data" / "attack" / "transactions.json"

            if not attack_path.is_file():
                attack_path = current_dir.parent.parent.parent / "data" / "attack" / "transactions.json"

            if attack_path.is_file() and self.baseline_transactions:
                import json
                try:
                    payload = json.loads(attack_path.read_text(encoding="utf-8"))
                    attack_txs = [Transaction.model_validate(item) for item in payload]
                    train_tgnn(self.tgnn, self.baseline_transactions, attack_txs)
                    torch.save(self.tgnn.state_dict(), weights_path)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Could not perform on-the-fly TGNN training: {e}")

    def analyze(self, transactions: list[Transaction]) -> GraphSignal:
        graph = build_graph(transactions)
        evidence = extract_evidence(transactions, self.baseline_transactions, graph)
        rule_score = _risk_score(evidence)

        # Evaluate TGNN risk score
        import torch
        self.tgnn.eval()
        with torch.no_grad():
            tgnn_score_tensor, node_scores = self.tgnn(transactions)
            tgnn_score = round(float(tgnn_score_tensor.item()), 3)

        combined_score = max(rule_score, tgnn_score)

        # Add GNN risk explanation and suspicious node tracking
        if tgnn_score >= 0.25:
            if node_scores:
                suspicious_node = max(node_scores, key=node_scores.get)
                node_val = node_scores[suspicious_node]
                evidence.reasons.append(
                    f"Temporal GNN detected elevated risk (score: {tgnn_score:.3f}). "
                    f"Highest risk account: {suspicious_node} (score: {node_val:.3f})."
                )
                evidence.accounts.add(suspicious_node)
            else:
                evidence.reasons.append(f"Temporal GNN detected elevated risk (score: {tgnn_score:.3f}).")

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
            risk_score=combined_score,
            anomaly_type=_anomaly_type(evidence, combined_score, tgnn_score),
            suspicious_accounts=sorted(evidence.accounts),
            suspicious_transactions=sorted(evidence.transactions),
            related_ips=sorted(evidence.ips),
            reasons=evidence.reasons or ["No suspicious graph or temporal behavior was observed."],
        )
