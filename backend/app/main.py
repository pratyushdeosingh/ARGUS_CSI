"""FastAPI entry point for the ARGUS orchestration prototype."""

from fastapi import FastAPI, HTTPException

from .correlation import correlate
from .models import AuditEvent, CorrelationRequest, Incident
from .policy import approve_containment
from .simulator import (
    load_attack_transactions,
    load_mock_signals,
    load_normal_transactions,
)
from .state import demo_state


app = FastAPI(
    title="ARGUS Orchestration API",
    version="0.1.0",
    description="Correlates financial graph and infrastructure signals.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/demo/normal")
def normal_state() -> dict[str, object]:
    demo_state.reset()
    return {
        "mode": "normal",
        "transactions": load_normal_transactions(),
        "incident": None,
    }


@app.post("/api/demo/simulate-attack")
def simulate_attack() -> dict[str, object]:
    graph_signal, system_signal = load_mock_signals()
    request = CorrelationRequest(
        graph_signal=graph_signal,
        system_signal=system_signal,
    )
    demo_state.incident = correlate(request)
    return {
        "mode": "attack",
        "transactions": load_attack_transactions(),
        "graph_signal": graph_signal,
        "system_signal": system_signal,
        "incident": demo_state.incident,
    }


@app.post("/api/signals/correlate", response_model=Incident)
def correlate_signals(request: CorrelationRequest) -> Incident:
    demo_state.incident = correlate(request)
    return demo_state.incident


@app.post("/api/incidents/{incident_id}/approve")
def approve(incident_id: str, actor: str = "human-analyst") -> dict[str, object]:
    if demo_state.incident is None or demo_state.incident.incident_id != incident_id:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident, audit_events = approve_containment(demo_state.incident, actor)
    demo_state.incident = incident
    demo_state.audit_events.extend(audit_events)
    return {"incident": incident, "audit_events": demo_state.audit_events}


@app.get("/api/audit", response_model=list[AuditEvent])
def audit_log() -> list[AuditEvent]:
    return demo_state.audit_events
