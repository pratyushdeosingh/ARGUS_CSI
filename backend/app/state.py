"""Small in-memory demo state. Replace with durable storage only if needed."""

from .models import AuditEvent, Incident


class DemoState:
    def __init__(self) -> None:
        self.incident: Incident | None = None
        self.audit_events: list[AuditEvent] = []

    def reset(self) -> None:
        self.incident = None
        self.audit_events = []


demo_state = DemoState()
