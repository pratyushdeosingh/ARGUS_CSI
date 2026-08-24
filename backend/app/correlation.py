"""Explainable, data-driven correlation for financial and host signals."""

from datetime import timedelta
from hashlib import sha256

from .models import (
    CorrelationRequest,
    Incident,
    IncidentStatus,
    ResponseAction,
    Severity,
)


CORRELATION_WINDOW = timedelta(minutes=15)


def _shared_evidence_bonus(request: CorrelationRequest) -> tuple[float, list[str]]:
    graph = request.graph_signal
    system = request.system_signal
    evidence: list[str] = []
    bonus = 0.0

    shared_ips = sorted(set(graph.related_ips) & set(system.related_ips))
    if shared_ips:
        bonus += 0.10
        evidence.append(f"Both detectors observed IP(s): {', '.join(shared_ips)}")

    time_gap = abs(graph.timestamp - system.timestamp)
    if time_gap <= CORRELATION_WINDOW:
        freshness = 1 - (time_gap.total_seconds() / CORRELATION_WINDOW.total_seconds())
        bonus += 0.02 + (0.03 * freshness)
        evidence.append(f"Signals occurred within {time_gap.total_seconds():.0f} seconds")

    return min(bonus, 0.15), evidence


def _classify(confidence: float) -> tuple[Severity, IncidentStatus]:
    if confidence >= 0.85:
        return Severity.CRITICAL, IncidentStatus.AWAITING_APPROVAL
    if confidence >= 0.70:
        return Severity.HIGH, IncidentStatus.AWAITING_APPROVAL
    if confidence >= 0.40:
        return Severity.SUSPICIOUS, IncidentStatus.MONITORING
    return Severity.INFORMATIONAL, IncidentStatus.MONITORING


def _verdict(request: CorrelationRequest, confidence: float) -> str:
    anomaly = request.graph_signal.anomaly_type
    if confidence < 0.40:
        return "low_risk_cross_layer_observation"
    if "mule" in anomaly or "multi_hop" in anomaly:
        return "coordinated_financial_attack"
    if "fan_in" in anomaly or "fan_out" in anomaly:
        return "money_laundering_network_with_host_risk"
    if "account_takeover" in anomaly:
        return "account_takeover_with_infrastructure_compromise"
    return "cross_layer_financial_anomaly"


def _incident_id(request: CorrelationRequest) -> str:
    material = (
        f"{request.graph_signal.signal_id}|"
        f"{request.system_signal.signal_id}|"
        f"{request.graph_signal.timestamp.isoformat()}"
    )
    digest = sha256(material.encode("utf-8")).hexdigest()[:12].upper()
    return f"INC-{digest}"


def _actions(request: CorrelationRequest, severity: Severity) -> list[ResponseAction]:
    graph = request.graph_signal
    system = request.system_signal
    approval_required = severity in {Severity.HIGH, Severity.CRITICAL}

    if severity in {Severity.INFORMATIONAL, Severity.SUSPICIOUS}:
        targets = graph.suspicious_accounts[:3] or [system.service]
        return [
            ResponseAction(
                action="enhanced_monitoring",
                target=target,
                approval_required=False,
            )
            for target in targets
        ]

    actions: list[ResponseAction] = []
    if graph.suspicious_accounts:
        origin = graph.suspicious_accounts[0]
        actions.extend(
            [
                ResponseAction(
                    action="freeze_account",
                    target=origin,
                    approval_required=approval_required,
                ),
                ResponseAction(
                    action="cancel_pending_transfers",
                    target=origin,
                    approval_required=approval_required,
                ),
            ]
        )
    if system.risk_score >= 0.60:
        actions.append(
            ResponseAction(
                action="isolate_service",
                target=system.service,
                approval_required=approval_required,
            )
        )
    return actions


def correlate(
    request: CorrelationRequest, *, incident_id: str | None = None
) -> Incident:
    graph = request.graph_signal
    system = request.system_signal
    bonus, linkage_evidence = _shared_evidence_bonus(request)
    confidence = min(
        graph.risk_score * 0.50 + system.risk_score * 0.35 + bonus,
        1.0,
    )
    severity, status = _classify(confidence)
    verdict = _verdict(request, confidence)
    evidence = list(dict.fromkeys([*graph.reasons, *system.indicators, *linkage_evidence]))

    account_count = len(graph.suspicious_accounts)
    shared_count = len(set(graph.related_ips) & set(system.related_ips))
    summary = (
        f"ARGUS correlated {graph.anomaly_type.replace('_', ' ')} across "
        f"{account_count} account(s) with {system.event_type.replace('_', ' ')} "
        f"on {system.host}/{system.service}. {shared_count} shared network "
        f"indicator(s) and temporal proximity produced {confidence:.1%} confidence."
    )

    return Incident(
        incident_id=incident_id or _incident_id(request),
        timestamp=max(graph.timestamp, system.timestamp),
        verdict=verdict,
        severity=severity,
        confidence=round(confidence, 3),
        financial_signal_id=graph.signal_id,
        infrastructure_signal_id=system.signal_id,
        affected_accounts=graph.suspicious_accounts,
        summary=summary,
        evidence=evidence,
        recommended_actions=_actions(request, severity),
        status=status,
    )
