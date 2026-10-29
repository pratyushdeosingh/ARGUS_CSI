"""Contract-valid detector responses for core policy tests, not a fraud model."""

from contracts.financial_models import FinancialAssessment, DetectorScores, ModelProvenance, PaymentScore


def assessment_for(transactions, graph):
    return FinancialAssessment(
        assessment_id="FIN-" + graph.signal_id.removeprefix("GRAPH-"),
        timestamp=graph.timestamp, risk_score=graph.risk_score,
        model=ModelProvenance(checkpoint_sha256="test-checkpoint"),
        transaction_scores=[PaymentScore(
            transaction_id=tx.transaction_id, timestamp=tx.timestamp, risk_score=graph.risk_score,
            detectors=DetectorScores(rules=graph.risk_score, ml=0, mule=0, scam=0),
            raw_ml_score=0, ml_used=False, reasons=graph.reasons,
            suspicious_accounts=graph.suspicious_accounts, suspicious_transactions=graph.suspicious_transactions,
        ) for tx in transactions],
        suspicious_accounts=graph.suspicious_accounts, suspicious_transactions=graph.suspicious_transactions,
        reasons=graph.reasons, edges=[], related_ips=graph.related_ips,
    )
