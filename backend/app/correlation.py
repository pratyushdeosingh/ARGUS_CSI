"""Transparent signal-correlation logic for the hackathon prototype."""

from datetime import datetime, timezone

from .models import (
    CorrelationRequest,
    Incident,
    IncidentStatus,
    ResponseAction,
    Severity,
)


def _shared_evidence_bonus(request: CorrelationRequest) -> tuple[float, list[str]]:
    graph = request.graph_signal
    system = request.system_signal
    evidence: list[str] = []
    bonus = 0.0

    shared_ips = sorted(set(graph.related_ips) & set(system.related_ips))
    if shared_ips:
        bonus += 0.10
        evidence.append(f"Both detectors observed IP(s): {', '.join(shared_ips)}")

    time_gap = abs((graph.timestamp - system.timestamp).total_seconds())
    if time_gap <= 300:
        bonus += 0.05
        evidence.append(f"Signals occurred within {time_gap:.0f} seconds")

    return min(bonus, 0.15), evidence


def correlate(request: CorrelationRequest) -> Incident:
    graph = request.graph_signal
    system = request.system_signal
    bonus, linkage_evidence = _shared_evidence_bonus(request)
    confidence = min(
        graph.risk_score * 0.50 + system.risk_score * 0.35 + bonus,
        1.0,
    )

    if confidence >= 0.85:
        severity = Severity.CRITICAL
        status = IncidentStatus.AWAITING_APPROVAL
    elif confidence >= 0.70:
        severity = Severity.HIGH
        status = IncidentStatus.AWAITING_APPROVAL
    elif confidence >= 0.40:
        severity = Severity.SUSPICIOUS
        status = IncidentStatus.MONITORING
    else:
        severity = Severity.INFORMATIONAL
        status = IncidentStatus.MONITORING

    evidence = [*graph.reasons, *system.indicators, *linkage_evidence]
    summary = (
        "ARGUS correlated abnormal financial-network activity with suspicious "
        "payment-service behavior. The combined evidence indicates a coordinated "
        "account-takeover and infrastructure-compromise campaign."
    )

    actions = [
        ResponseAction(
            action="freeze_account",
            target=account,
            approval_required=True,
        )
        for account in graph.suspicious_accounts[:1]
    ]
    actions.extend(
        [
            ResponseAction(
                action="cancel_pending_transfers",
                target=graph.suspicious_accounts[0]
                if graph.suspicious_accounts
                else "unknown",
                approval_required=True,
            ),
            ResponseAction(
                action="isolate_service",
                target=system.service,
                approval_required=True,
            ),
        ]
    )

    return Incident(
        incident_id="INC-001",
        timestamp=datetime.now(timezone.utc),
        verdict="coordinated_financial_attack",
        severity=severity,
        confidence=round(confidence, 3),
        financial_signal_id=graph.signal_id,
        infrastructure_signal_id=system.signal_id,
        affected_accounts=graph.suspicious_accounts[:1],
        summary=summary,
        evidence=evidence,
        recommended_actions=actions,
        status=status,
    )
