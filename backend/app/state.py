"""Small in-memory demo state. Replace with durable storage only if needed."""

from .models import AuditEvent, GraphSignal, Incident, SystemSignal


class DemoState:
    def __init__(self) -> None:
        self.incident: Incident | None = None
        self.audit_events: list[AuditEvent] = []
        self.last_graph_signal: GraphSignal | None = None
        self.last_system_signal: SystemSignal | None = None

    def reset(self) -> None:
        self.incident = None
        self.audit_events = []


demo_state = DemoState()
