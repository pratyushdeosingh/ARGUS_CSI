"""Session-local specialist scoring for the ingestion adapter."""

from pydantic import Field

from detector import GraphDetector
from engine import TransactionRiskEngine
from graph_models import (
    StrictModel, Transaction, TransactionStatus, TransactionScoreResponse,
    DetectorBreakdown, Decision, RiskBand,
)


class ContextScoreRequest(StrictModel):
    transaction: Transaction
    history: list[Transaction] = Field(default_factory=list, max_length=5000)


def score_context(detector: GraphDetector, request: ContextScoreRequest) -> TransactionScoreResponse:
    tx = request.transaction
    if tx.status == TransactionStatus.CANCELLED:
        return TransactionScoreResponse(
            transaction_id=tx.transaction_id, timestamp=tx.timestamp,
            sender=tx.source_account, receiver=tx.destination_account, amount=tx.amount, currency=tx.currency,
            risk_score=0, risk_band=RiskBand.LOW, decision=Decision.ALLOW,
            detectors=DetectorBreakdown(rules=0, tgnn=0, mule=0, scam=0), top_factors=[],
            reasons=["Cancelled payment excluded from financial activity."],
            explanation="No payment-control action is executed; cancelled activity is excluded.",
        )
    baseline = [item for item in detector.baseline_transactions
                if item.timestamp < tx.timestamp and item.currency == tx.currency
                and item.transaction_id != tx.transaction_id]
    engine = TransactionRiskEngine(GraphDetector(baseline))
    for previous in sorted(request.history, key=lambda item: (item.timestamp, item.transaction_id)):
        if previous.transaction_id == tx.transaction_id:
            if previous != tx:
                raise ValueError("Context contains conflicting data for the current payment")
            continue
        if previous.timestamp <= tx.timestamp and previous.currency == tx.currency:
            engine.history_store.add_transaction(previous)
    return engine.score_transaction(tx)
