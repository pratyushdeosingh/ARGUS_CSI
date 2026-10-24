"""Core adapters and financial-only case policy. Scores remain 0–1."""

from contracts.financial_models import FinancialAssessment
from .models import GraphSignal, Incident, IncidentStatus, ResponseAction, Severity


def assessment_signal(assessment: FinancialAssessment) -> GraphSignal:
    peak_mule = max(item.detectors.mule for item in assessment.transaction_scores)
    peak_scam = max(item.detectors.scam for item in assessment.transaction_scores)
    anomaly = ("rapid_mule_fund_movement" if peak_mule >= 0.70 else
               "scam_behavioural_pattern" if peak_scam >= 0.70 else
               "financial_behavioural_anomaly" if assessment.risk_score >= 0.40 else
               "low_risk_activity")
    return GraphSignal(
        signal_id="GRAPH-" + assessment.assessment_id.removeprefix("FIN-"),
        timestamp=assessment.timestamp, risk_score=assessment.risk_score,
        anomaly_type=anomaly, suspicious_accounts=assessment.suspicious_accounts,
        suspicious_transactions=assessment.suspicious_transactions,
        related_ips=assessment.related_ips, reasons=assessment.reasons,
    )


def financial_incident(assessment: FinancialAssessment, threshold: float = 0.70) -> Incident | None:
    if assessment.risk_score < threshold:
        return None
    signal = assessment_signal(assessment)
    from .correlation import _classify
    severity, status = _classify(assessment.risk_score)
    approval_required = status == IncidentStatus.AWAITING_APPROVAL
    return Incident(
        incident_id="INC-FIN-" + assessment.assessment_id.removeprefix("FIN-"),
        timestamp=assessment.timestamp, verdict=signal.anomaly_type,
        severity=severity,
        confidence=assessment.risk_score, financial_signal_id=signal.signal_id,
        case_type="financial", financial_assessment_id=assessment.assessment_id,
        transaction_ids=[item.transaction_id for item in assessment.transaction_scores],
        affected_accounts=assessment.suspicious_accounts,
        summary=(f"Financial fraud indicators in {len(assessment.transaction_scores)} payment(s); "
                 f"risk {assessment.risk_score:.3f}. Infrastructure evidence is not required. "
                 "This score is not a calibrated fraud probability."),
        evidence=assessment.reasons,
        recommended_actions=[ResponseAction(action="review_and_hold_payments" if approval_required else "enhanced_monitoring", target=account,
                                            approval_required=approval_required)
                             for account in assessment.suspicious_accounts[:3]],
        status=status,
    )
