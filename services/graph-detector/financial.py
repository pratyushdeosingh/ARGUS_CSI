"""Request-scoped, deterministic specialist fusion. No live shared history writes."""

from hashlib import sha256
import json
from statistics import median
from pathlib import Path

import torch

from contracts.financial_models import (
    DetectorScores, FinancialAssessment, FinancialEdge, ModelProvenance, PaymentScore,
    FeatureSensitivity, ModelDiagnostic,
)
from detector import GraphDetector, _risk_score
from features import extract_evidence
from graph_builder import build_graph
from graph_models import Transaction, TransactionStatus
from history import InMemoryHistoryStore
from mule_detector import MuleDetector
from scam_detector import ScamDetector


_SERVICE_DIR = Path(__file__).resolve().parent
_POLICY_DIGEST = sha256(b"".join((_SERVICE_DIR / name).read_bytes() for name in [
    "financial.py", "features.py", "mule_detector.py", "scam_detector.py",
    "tgnn.py", "graph_builder.py", "history.py", "detector.py",
])).hexdigest()


def assess_financial(detector: GraphDetector, transactions: list[Transaction],
                     baseline: list[Transaction] | None = None) -> FinancialAssessment:
    ordered = sorted(transactions, key=lambda tx: (tx.timestamp, tx.transaction_id))
    if not ordered:
        raise ValueError("At least one payment is required")
    if baseline is None:
        baseline = [tx for tx in detector.baseline_transactions if tx.timestamp < ordered[0].timestamp]
    else:
        baseline = list(baseline)
        if any(tx.timestamp >= ordered[0].timestamp for tx in baseline):
            raise ValueError("Baseline history must precede the first payment being assessed")
    if len({tx.transaction_id for tx in ordered}) != len(ordered):
        raise ValueError("Duplicate transaction IDs in assessment")
    provenance = ModelProvenance(checkpoint_sha256=detector.checkpoint_sha256, policy_sha256=_POLICY_DIGEST)
    history = InMemoryHistoryStore()
    current_ids = {tx.transaction_id for tx in ordered}
    history.seed(tx for tx in baseline if tx.transaction_id not in current_ids)
    mule, scam = MuleDetector(history), ScamDetector(history, baseline)
    scores = []
    diagnostic_candidate = None
    accounts, suspicious_ids = set(), set()
    observed = {tx.transaction_id: tx for tx in [*baseline, *ordered]}
    for tx in ordered:
        if tx.status == TransactionStatus.CANCELLED:
            scores.append(PaymentScore(
                transaction_id=tx.transaction_id, timestamp=tx.timestamp, risk_score=0,
                detectors=DetectorScores(rules=0, ml=0, mule=0, scam=0),
                raw_ml_score=0, ml_used=False, reasons=["Cancelled payment excluded from money-flow scoring."],
                suspicious_accounts=[], suspicious_transactions=[],
            ))
            continue
        # One currency, no future evidence, and a bounded context for each payment.
        context = [item for item in history.get_recent_transactions(3600, as_of=tx.timestamp)
                   if item.currency == tx.currency and item.status != TransactionStatus.CANCELLED][-99:]
        window = [*context, tx]
        evidence = extract_evidence(window, baseline, build_graph(window))
        rule_score = _risk_score(evidence)
        with torch.no_grad():
            raw_ml = float(detector.tgnn(window)[0].item())
        mule_score, mule_reasons = mule.evaluate_transaction(tx)
        scam_score, scam_reasons = scam.evaluate_transaction(tx)
        raw_scam_score = scam_score / 100
        profile = [item for item in baseline if item.source_account == tx.source_account
                   and item.currency == tx.currency and item.status != TransactionStatus.CANCELLED]
        consistent_payee = (profile and tx.destination_account in {item.destination_account for item in profile}
                            and tx.amount <= 3 * median(item.amount for item in profile)
                            and tx.device_id in {item.device_id for item in profile}
                            and tx.ip_address in {item.ip_address for item in profile})
        if consistent_payee:
            scam_score = 0.0
            scam_reasons.append("Known beneficiary, baseline-scale amount and unchanged identity; scam promotion withheld.")
        independent = max(rule_score, mule_score / 100, scam_score / 100)
        ml_used = independent >= 0.40
        normalized = DetectorScores(rules=rule_score, ml=raw_ml if ml_used else 0,
                                    mule=mule_score / 100, scam=scam_score / 100)
        risk = round(max(normalized.model_dump().values()), 6)
        if ml_used and raw_ml > independent and (diagnostic_candidate is None or raw_ml > diagnostic_candidate[1]):
            diagnostic_candidate = (tx.transaction_id, raw_ml, window)
        reasons = list(dict.fromkeys([*evidence.reasons, *mule_reasons, *scam_reasons]))
        if ml_used:
            reasons.append(f"Demo-trained TGNN contribution {raw_ml:.3f}; independent behavioural evidence permits model use.")
        marked_accounts, marked_ids = set(evidence.accounts), set(evidence.transactions)
        if independent >= 0.40:
            marked_accounts.update([tx.source_account, tx.destination_account])
            marked_ids.add(tx.transaction_id)
        accounts.update(marked_accounts)
        suspicious_ids.update(marked_ids)
        scores.append(PaymentScore(
            transaction_id=tx.transaction_id, timestamp=tx.timestamp, risk_score=risk,
            detectors=normalized, raw_ml_score=raw_ml, raw_scam_score=raw_scam_score, ml_used=ml_used,
            reasons=reasons or ["No suspicious financial behaviour observed."],
            suspicious_accounts=sorted(marked_accounts), suspicious_transactions=sorted(marked_ids),
        ))
        history.add_transaction(tx)
    diagnostic = None
    if diagnostic_candidate is not None:
        tx_id, original, window = diagnostic_candidate
        sensitivities = []
        for index, name in enumerate(["log_sent_volume", "log_received_volume", "outgoing_count", "incoming_count"]):
            mask = [1.0] * 4
            mask[index] = 0.0
            with torch.no_grad():
                ablated = float(detector.tgnn(window, feature_mask=mask)[0].item())
            sensitivities.append(FeatureSensitivity(feature=name, score_without_feature=ablated,
                                                     score_difference=original - ablated))
        diagnostic = ModelDiagnostic(transaction_id=tx_id, raw_score=original,
                                     sensitivities=sorted(sensitivities, key=lambda item: abs(item.score_difference), reverse=True))
    material = json.dumps({"transactions": [tx.model_dump(mode="json") for tx in ordered],
                           "baseline": sorted((tx.model_dump(mode="json") for tx in baseline), key=lambda tx: tx["transaction_id"]),
                           "model": provenance.model_dump(), "policy": "financial.v1"}, sort_keys=True)
    return FinancialAssessment(
        assessment_id="FIN-" + sha256(material.encode()).hexdigest()[:16].upper(),
        timestamp=ordered[-1].timestamp, risk_score=max(score.risk_score for score in scores),
        model=provenance, transaction_scores=scores,
        suspicious_accounts=sorted(accounts), suspicious_transactions=sorted(suspicious_ids),
        reasons=list(dict.fromkeys(reason for score in scores for reason in score.reasons)),
        related_ips=sorted({tx.ip_address for tx in observed.values() if tx.transaction_id in suspicious_ids}),
        model_diagnostic=diagnostic,
        edges=[FinancialEdge(transaction_id=tx.transaction_id, source_account=tx.source_account,
                             destination_account=tx.destination_account, amount=tx.amount,
                             currency=tx.currency, suspicious=tx.transaction_id in suspicious_ids)
               for tx in sorted(observed.values(), key=lambda tx: (tx.timestamp, tx.transaction_id))
               if tx.status != TransactionStatus.CANCELLED],
    )
