"""Dedicated Mule Account Behavioral Detector for ARGUS CSI.

Identifies money mule patterns where an account receives funds from multiple
parties and rapidly forwards those funds downstream with low retention.

NOTE: This is an explainable behavioral prototype detector, not a production
supervised ML classifier.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from history import BaseHistoryStore
from graph_models import Transaction, TransactionStatus


# Heuristic feature weights (sum to 1.00)
MULE_WEIGHTS = {
    "fan_in": 0.25,              # Multiple distinct accounts sending money to one account
    "forwarding_speed": 0.25,    # Money received and transferred out shortly afterward
    "turnover": 0.20,            # High turnover / pass-through of funds
    "counterparty_diversity": 0.15,  # Many disparate counterparties
    "temporal_burst": 0.15,      # High transaction burst within short time window
}


@dataclass
class MuleScoreResult:
    """Detailed mule evaluation results with score and feature breakdown."""
    account: str
    mule_score: float  # Heuristic 0-100 score
    fan_in_score: float
    forwarding_speed_score: float
    turnover_score: float
    counterparty_diversity_score: float
    temporal_burst_score: float
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class MuleDetector:
    """Evaluates mule behavioral characteristics using account history and graph topology."""

    def __init__(self, history_store: BaseHistoryStore):
        self.history_store = history_store

    def evaluate_account(
        self, account: str, current_tx: Transaction | None = None, window_seconds: float = 3600.0
    ) -> MuleScoreResult:
        """Evaluate an account's recent behavioral history for mule patterns."""
        incoming = self.history_store.get_account_incoming(account, window_seconds, as_of=current_tx.timestamp if current_tx else None)
        outgoing = self.history_store.get_account_outgoing(account, window_seconds, as_of=current_tx.timestamp if current_tx else None)

        # Include current transaction in consideration if relevant
        if current_tx and current_tx.status != TransactionStatus.CANCELLED:
            if current_tx.destination_account == account and current_tx not in incoming:
                incoming = sorted([*incoming, current_tx], key=lambda t: t.timestamp)
            elif current_tx.source_account == account and current_tx not in outgoing:
                outgoing = sorted([*outgoing, current_tx], key=lambda t: t.timestamp)

        active_incoming = [t for t in incoming if t.status != TransactionStatus.CANCELLED and (current_tx is None or t.currency == current_tx.currency)]
        active_outgoing = [t for t in outgoing if t.status != TransactionStatus.CANCELLED and (current_tx is None or t.currency == current_tx.currency)]

        distinct_senders = {t.source_account for t in active_incoming}
        distinct_receivers = {t.destination_account for t in active_outgoing}
        total_in_vol = sum(t.amount for t in active_incoming)
        total_out_vol = sum(t.amount for t in active_outgoing)
        all_txs = sorted(active_incoming + active_outgoing, key=lambda t: t.timestamp)

        reasons: list[str] = []

        # 1. Incoming Fan-in Score (0-100)
        # Mule accounts collect funds from several victims or accounts
        sender_count = len(distinct_senders)
        if sender_count >= 5:
            fan_in_score = 100.0
        elif sender_count == 4:
            fan_in_score = 80.0
        elif sender_count == 3:
            fan_in_score = 60.0
        elif sender_count == 2:
            fan_in_score = 30.0
        else:
            fan_in_score = 0.0

        if sender_count >= 3:
            reasons.append(
                f"Account {account} received funds from {sender_count} distinct senders."
            )

        # 2. Forwarding Speed Score (0-100)
        # Funds received and forwarded out shortly afterwards
        forwarding_speed_score = 0.0
        fastest_forward_gap: float | None = None
        forwarded_ratio_fast = 0.0

        for in_tx in active_incoming:
            subsequent_outs = [out for out in active_outgoing if out.timestamp >= in_tx.timestamp]
            if subsequent_outs:
                first_out = min(subsequent_outs, key=lambda t: t.timestamp)
                gap_seconds = (first_out.timestamp - in_tx.timestamp).total_seconds()
                if fastest_forward_gap is None or gap_seconds < fastest_forward_gap:
                    fastest_forward_gap = gap_seconds
                    forwarded_ratio_fast = (first_out.amount / in_tx.amount) * 100.0

        if fastest_forward_gap is not None:
            if fastest_forward_gap <= 60:
                forwarding_speed_score = 100.0
            elif fastest_forward_gap <= 180:
                forwarding_speed_score = 85.0
            elif fastest_forward_gap <= 300:
                forwarding_speed_score = 70.0
            elif fastest_forward_gap <= 600:
                forwarding_speed_score = 45.0
            elif fastest_forward_gap <= 1800:
                forwarding_speed_score = 25.0
            else:
                forwarding_speed_score = 10.0

            if fastest_forward_gap <= 300 and total_in_vol > 0:
                reasons.append(
                    f"Rapid forwarding: funds forwarded within {fastest_forward_gap:.0f} seconds of receipt."
                )

        # 3. Turnover / Pass-Through Score (0-100)
        # Account retains little to none of the incoming money
        turnover_score = 0.0
        if total_in_vol > 0 and total_out_vol > 0:
            pass_through_pct = (total_out_vol / total_in_vol) * 100.0
            retention_pct = max(0.0, 100.0 - pass_through_pct)

            if 70.0 <= pass_through_pct <= 125.0:
                # Highly indicative pass-through (leaving small cut or exact forward)
                deviation = abs(pass_through_pct - 100.0)
                turnover_score = max(70.0, 100.0 - (deviation * 1.2))
                reasons.append(
                    f"High turnover pass-through: forwarded {min(pass_through_pct, 100.0):.1f}% of received funds "
                    f"(incoming: {total_in_vol:,.0f}, outgoing: {total_out_vol:,.0f}, retained: {retention_pct:.1f}%)."
                )
            elif 50.0 <= pass_through_pct < 70.0:
                turnover_score = 50.0
            elif pass_through_pct > 125.0:
                turnover_score = 40.0
            else:
                turnover_score = 15.0

        # 4. Counterparty Diversity Score (0-100)
        # Many unrelated counterparties with no repeat history
        counterparty_diversity_score = 0.0
        unique_counterparties = distinct_senders | distinct_receivers
        total_tx_count = len(all_txs)
        if total_tx_count >= 3:
            diversity_ratio = len(unique_counterparties) / total_tx_count
            if diversity_ratio >= 0.8:
                counterparty_diversity_score = min(100.0, diversity_ratio * 100.0)
                if len(unique_counterparties) >= 4:
                    reasons.append(
                        f"High counterparty diversity: interacted with {len(unique_counterparties)} "
                        f"distinct accounts across {total_tx_count} transfers."
                    )
            elif diversity_ratio >= 0.6:
                counterparty_diversity_score = 50.0

        # 5. Temporal Burst Score (0-100)
        # Inflows and outflows clustered in a very tight window
        temporal_burst_score = 0.0
        if len(all_txs) >= 2:
            span_seconds = (all_txs[-1].timestamp - all_txs[0].timestamp).total_seconds()
            if span_seconds <= 300 and len(all_txs) >= 3:
                temporal_burst_score = min(100.0, 60.0 + len(all_txs) * 10.0)
                reasons.append(
                    f"Burst activity: {len(all_txs)} transactions occurred within {span_seconds:.0f} seconds."
                )
            elif span_seconds <= 600 and len(all_txs) >= 3:
                temporal_burst_score = 50.0
            elif len(all_txs) >= 2 and span_seconds <= 120:
                temporal_burst_score = 40.0

        # Weighted combination
        raw_score = (
            MULE_WEIGHTS["fan_in"] * fan_in_score
            + MULE_WEIGHTS["forwarding_speed"] * forwarding_speed_score
            + MULE_WEIGHTS["turnover"] * turnover_score
            + MULE_WEIGHTS["counterparty_diversity"] * counterparty_diversity_score
            + MULE_WEIGHTS["temporal_burst"] * temporal_burst_score
        )

        # High-confidence rapid forwarding pass-through (strong indicator even with single upstream sender)
        if forwarding_speed_score >= 85.0 and turnover_score >= 70.0:
            raw_score = max(raw_score, 85.0)

        # Corroboration boost if multiple strong mule indicators fired
        strong_indicators = sum(
            1
            for s in [fan_in_score, forwarding_speed_score, turnover_score, temporal_burst_score]
            if s >= 60.0
        )
        boost = 10.0 if strong_indicators >= 3 else (5.0 if strong_indicators == 2 else 0.0)
        final_mule_score = round(min(100.0, raw_score + boost), 1)

        metrics = {
            "distinct_senders_count": sender_count,
            "distinct_receivers_count": len(distinct_receivers),
            "fastest_forward_gap_seconds": fastest_forward_gap,
            "incoming_volume": total_in_vol,
            "outgoing_volume": total_out_vol,
            "pass_through_percentage": (total_out_vol / total_in_vol * 100.0) if total_in_vol > 0 else 0.0,
        }

        return MuleScoreResult(
            account=account,
            mule_score=final_mule_score,
            fan_in_score=fan_in_score,
            forwarding_speed_score=forwarding_speed_score,
            turnover_score=turnover_score,
            counterparty_diversity_score=counterparty_diversity_score,
            temporal_burst_score=temporal_burst_score,
            reasons=reasons,
            metrics=metrics,
        )

    def evaluate_transaction(self, transaction: Transaction) -> tuple[float, list[str]]:
        """Evaluate both sender and receiver of a transaction for mule characteristics.

        Returns:
            Tuple of (mule_score: 0-100, reasons: list[str])
        """
        # Receiver might be an incoming collection mule or staging mule
        recv_result = self.evaluate_account(transaction.destination_account, current_tx=transaction)
        # Sender might be the forwarding mule routing out funds
        send_result = self.evaluate_account(transaction.source_account, current_tx=transaction)

        best_result = max([recv_result, send_result], key=lambda r: r.mule_score)
        reasons = list(best_result.reasons)

        # Check direct link if sender recently received money
        return best_result.mule_score, reasons
