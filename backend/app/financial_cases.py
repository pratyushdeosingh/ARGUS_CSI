"""Financial case admission policy, independent of cross-domain fusion rules.

V1: at least two completed payments, each crossing an existing graph/scam
alert threshold with nonempty detector evidence, connected by an account in
one session within fifteen minutes. A graph score qualifies only if its
suspicious transaction list includes this payment. REVIEW alone is insufficient.
No scenario label or synthetic truth influences admission or severity.
"""
from .config import Settings
from .models import GraphSignal, Transaction, TransactionScoreResponse, TransactionStatus


def financial_finding(transaction: Transaction, graph: GraphSignal | None,
                      scam: TransactionScoreResponse | None, settings: Settings) -> dict | None:
    if transaction.status != TransactionStatus.COMPLETED:
        return None
    graph_qualifies = bool(graph and graph.risk_score >= settings.fraud_alert_threshold
                           and transaction.transaction_id in graph.suspicious_transactions and graph.reasons)
    scam_qualifies = bool(scam and scam.detectors.scam >= settings.scam_alert_threshold and scam.reasons)
    if not (graph_qualifies or scam_qualifies):
        return None
    scores = {}
    evidence = []
    signal_ids = []
    if graph_qualifies:
        scores['graph'] = round(graph.risk_score * 100, 3)
        evidence.extend(graph.reasons)
        signal_ids.append(graph.signal_id)
    if scam_qualifies:
        scores['scam'] = scam.detectors.scam
        scores['combined'] = scam.risk_score
        evidence.extend(scam.reasons)
    return dict(transaction_id=transaction.transaction_id, timestamp=transaction.timestamp.isoformat(),
                accounts=[transaction.source_account, transaction.destination_account],
                risk_scores=scores, evidence=list(dict.fromkeys(evidence)), signal_ids=signal_ids)
