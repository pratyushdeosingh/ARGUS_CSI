"""Unified Transaction Risk Engine and Explainable AI for ARGUS CSI.

Integrates:
1. Rule-based heuristic graph detection
2. Temporal Graph Neural Network (TGNN)
3. Dedicated Mule Account detector
4. Dedicated Scam / Fan-out detector

Produces a unified, calibrated risk score (0-100), risk band, decision
(ALLOW, REVIEW, BLOCK), and grounded explainable AI narrative.
"""

from datetime import datetime, timezone
import logging
from typing import Any
import torch

from detector import GraphDetector, _risk_score
from features import extract_evidence
from graph_builder import build_graph
from history import BaseHistoryStore, InMemoryHistoryStore
from graph_models import (
    Decision,
    DetectorBreakdown,
    RiskBand,
    Transaction,
    TransactionScoreInput,
    TransactionScoreResponse,
    TransactionStatus,
)
from mule_detector import MuleDetector
from scam_detector import ScamDetector

logger = logging.getLogger(__name__)


class TransactionRiskEngine:
    """Real-time transaction risk scoring engine coordinating all ARGUS detectors."""

    def __init__(
        self,
        graph_detector: GraphDetector,
        history_store: BaseHistoryStore | None = None,
    ):
        self.graph_detector = graph_detector
        self.history_store = history_store or InMemoryHistoryStore()

        # Seed the state store with baseline transactions if empty
        if self.graph_detector.baseline_transactions:
            self.history_store.seed(self.graph_detector.baseline_transactions)

        self.mule_detector = MuleDetector(self.history_store)
        self.scam_detector = ScamDetector(
            self.history_store, baseline_transactions=self.graph_detector.baseline_transactions
        )

    def score_transaction(
        self, tx_input: TransactionScoreInput | Transaction
    ) -> TransactionScoreResponse:
        """Validate, evaluate, and score a transaction against all detectors.

        Steps:
        1. Validate and convert transaction
        2. Query relevant recent graph and account history
        3. Run heuristic rule-based detection
        4. Run TGNN temporal graph model
        5. Run dedicated Mule detector
        6. Run dedicated Scam detector
        7. Aggregate unified risk score and assign risk band / decision
        8. Synthesize grounded explainable AI factors
        9. Commit transaction to stateful history store
        """
        if isinstance(tx_input, Transaction):
            tx = tx_input
        else:
            tx = tx_input.to_transaction()

        sender = tx.source_account
        receiver = tx.destination_account

        # 1. Access recent subgraph transaction context around sender & receiver
        context = self.history_store.get_subgraph_transactions(
            [sender, receiver], hops=2, window_seconds=3600.0, as_of=tx.timestamp
        )

        # Merge with current transaction, ensuring unique and sorted
        tx_map = {t.transaction_id: t for t in context}
        tx_map[tx.transaction_id] = tx
        active_window = sorted(tx_map.values(), key=lambda t: (t.timestamp, t.transaction_id))

        # 2. Heuristic Rule-Based Detector
        graph = build_graph(active_window)
        evidence = extract_evidence(
            active_window, self.graph_detector.baseline_transactions, graph
        )
        rule_score_float = _risk_score(evidence)
        rules_100 = round(rule_score_float * 100.0, 1)

        # 3. Temporal Graph Neural Network (TGNN)
        self.graph_detector.tgnn.eval()
        with torch.no_grad():
            tgnn_score_tensor, node_scores = self.graph_detector.tgnn(active_window)
            tgnn_score_float = float(tgnn_score_tensor.item())
            tgnn_100 = round(tgnn_score_float * 100.0, 1)

        # 4. Dedicated Mule Detector
        mule_100, mule_reasons = self.mule_detector.evaluate_transaction(tx)

        # 5. Dedicated Scam Detector
        scam_100, scam_reasons = self.scam_detector.evaluate_transaction(tx)

        # 6. Unified Risk Aggregation
        # Base risk: balanced combination across specialist models
        base_risk = (
            0.30 * rules_100
            + 0.30 * tgnn_100
            + 0.20 * mule_100
            + 0.20 * scam_100
        )
        # Peak risk: highest individual detector score
        peak_risk = max(rules_100, tgnn_100, mule_100, scam_100)

        # Blend peak risk (ensuring prominent threat detection) and base risk
        blended = 0.55 * peak_risk + 0.45 * base_risk

        # Multi-detector corroboration bonus
        elevated_detectors = sum(
            1 for s in [rules_100, tgnn_100, mule_100, scam_100] if s >= 50.0
        )
        corroboration = 10.0 if elevated_detectors >= 3 else (5.0 if elevated_detectors == 2 else 0.0)

        if peak_risk >= 70.0:
            final_risk_score = round(min(100.0, max(peak_risk, blended + corroboration)))
        else:
            final_risk_score = round(min(100.0, max(0.0, blended + corroboration)))

        # 7. Assign Risk Band and Decision
        if final_risk_score >= 80 or peak_risk >= 85.0:
            final_risk_score = max(final_risk_score, 80.0)
            risk_band = RiskBand.SEVERE
            decision = Decision.BLOCK
        elif final_risk_score >= 60:
            risk_band = RiskBand.HIGH
            decision = Decision.BLOCK if peak_risk >= 75.0 else Decision.REVIEW
        elif final_risk_score >= 30:
            risk_band = RiskBand.MODERATE
            decision = Decision.REVIEW
        else:
            risk_band = RiskBand.LOW
            decision = Decision.ALLOW

        # 8. Synthesize Explainable Reasons & Top Factors
        all_reasons: list[str] = []

        # Include grounded rule reasons
        for r in evidence.reasons:
            if "No suspicious" not in r and r not in all_reasons:
                all_reasons.append(r)

        # Include mule reasons
        for r in mule_reasons:
            if r not in all_reasons:
                all_reasons.append(r)

        # Include scam reasons
        for r in scam_reasons:
            if r not in all_reasons:
                all_reasons.append(r)

        # Include TGNN reasons
        if tgnn_100 >= 35.0:
            if node_scores:
                highest_account = max(node_scores, key=node_scores.get)
                node_risk = node_scores[highest_account] * 100.0
                all_reasons.append(
                    f"Temporal GNN flagged anomalous temporal graph pattern (score: {tgnn_100}/100, "
                    f"highest risk node: {highest_account} at {node_risk:.0f}/100)."
                )
            else:
                all_reasons.append(
                    f"Temporal GNN flagged anomalous temporal graph pattern (score: {tgnn_100}/100)."
                )

        if not all_reasons:
            all_reasons = ["Normal transaction activity consistent with behavioral baseline."]

        # Rank top contributing detectors
        detector_ranking = sorted(
            [
                ("TGNN", tgnn_100),
                ("Rules", rules_100),
                ("Mule Detector", mule_100),
                ("Scam Detector", scam_100),
            ],
            key=lambda item: item[1],
            reverse=True,
        )
        top_factors = [f"{name} ({score:.0f}/100)" for name, score in detector_ranking if score >= 25.0]
        if not top_factors:
            top_factors = [f"{detector_ranking[0][0]} ({detector_ranking[0][1]:.0f}/100)"]

        # Human-readable synthesized explanation
        top_name, top_score = detector_ranking[0]
        explanation = (
            f"Transaction {tx.transaction_id} scored {final_risk_score}/100 ({risk_band.value}), "
            f"resulting in automated decision '{decision.value}'. "
            f"Primary risk driver was {top_name} ({top_score:.0f}/100). "
            f"Identified {len(all_reasons)} key behavioral indicator(s)."
        )

        # 9. Update stateful history store with the new transaction
        self.history_store.add_transaction(tx)

        return TransactionScoreResponse(
            transaction_id=tx.transaction_id,
            sender=sender,
            receiver=receiver,
            amount=tx.amount,
            currency=tx.currency,
            timestamp=tx.timestamp,
            risk_score=final_risk_score,
            risk_band=risk_band,
            decision=decision,
            detectors=DetectorBreakdown(
                rules=rules_100,
                tgnn=tgnn_100,
                mule=mule_100,
                scam=scam_100,
            ),
            top_factors=top_factors,
            reasons=all_reasons,
            explanation=explanation,
        )

    def reset(self) -> None:
        """Reset stateful store and re-seed baseline."""
        self.history_store.reset()
        if self.graph_detector.baseline_transactions:
            self.history_store.seed(self.graph_detector.baseline_transactions)
