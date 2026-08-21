"""FastAPI entry point for the ARGUS orchestration prototype."""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .correlation import correlate
from .detectors import DetectorGateway, DetectorUnavailable, get_detector_gateway
from .models import (
    AuditEvent,
    CorrelationRequest,
    DetectorStatus,
    Incident,
    IncidentStatus,
)
from .policy import approve_containment
from .simulator import (
    load_attack_transactions,
    load_normal_transactions,
)
from .state import demo_state


app = FastAPI(
    title="ARGUS Orchestration API",
    version="0.1.0",
    description="Correlates financial graph and infrastructure signals.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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


@app.get("/api/detectors/status", response_model=DetectorStatus)
async def detector_status(
    gateway: DetectorGateway = Depends(get_detector_gateway),
) -> DetectorStatus:
    return await gateway.status()


@app.post("/api/demo/simulate-attack")
async def simulate_attack(
    gateway: DetectorGateway = Depends(get_detector_gateway),
) -> dict[str, object]:
    transactions = load_attack_transactions()
    try:
        graph_signal, system_signal, status = await gateway.collect(transactions)
    except DetectorUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    request = CorrelationRequest(
        graph_signal=graph_signal,
        system_signal=system_signal,
    )
    demo_state.incident = correlate(request)
    return {
        "mode": "attack",
        "transactions": transactions,
        "graph_signal": graph_signal,
        "system_signal": system_signal,
        "detector_status": status,
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
    if demo_state.incident.status is not IncidentStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"Incident cannot be approved while {demo_state.incident.status.value}",
        )
    incident, audit_events = approve_containment(demo_state.incident, actor)
    demo_state.incident = incident
    demo_state.audit_events.extend(audit_events)
    return {"incident": incident, "audit_events": demo_state.audit_events}


@app.get("/api/audit", response_model=list[AuditEvent])
def audit_log() -> list[AuditEvent]:
    return demo_state.audit_events
