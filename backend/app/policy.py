"""Human-approval policy for simulated containment actions."""

from datetime import datetime, timezone

from .models import AuditEvent, Incident, IncidentStatus


def approve_containment(incident: Incident, actor: str) -> tuple[Incident, list[AuditEvent]]:
    audit_events: list[AuditEvent] = []
    for action in incident.recommended_actions:
        action.status = "executed"
        audit_events.append(
            AuditEvent(
                timestamp=datetime.now(timezone.utc),
                action=action.action,
                target=action.target,
                actor=actor,
                result="simulated_success",
            )
        )

    incident.status = IncidentStatus.CONTAINED
    return incident, audit_events
