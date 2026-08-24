"""FastAPI entry point for the ARGUS orchestration prototype."""

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .correlation import correlate
from .detectors import DetectorGateway, DetectorUnavailable, get_detector_gateway
from .models import (
    AuditEvent,
    AnalysisRequest,
    AnalysisResponse,
    CorrelationRequest,
    DetectorStatus,
    Incident,
    IncidentStatus,
    PlatformMetrics,
)
from .policy import approve_containment
from .simulator import (
    load_attack_transactions,
    load_normal_transactions,
)
from .state import demo_state
from .storage import argus_store


app = FastAPI(
    title="ARGUS Orchestration API",
    version="1.0.0",
    description=(
        "Analyzes arbitrary financial and infrastructure telemetry, correlates "
        "explainable signals, persists incidents, and governs response approval."
    ),
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
    demo_state.incident = correlate(request, incident_id="INC-001")
    argus_store.save_transactions("DEMO-ATTACK", transactions)
    argus_store.save_signal(graph_signal)
    argus_store.save_signal(system_signal)
    argus_store.save_incident(demo_state.incident)
    return {
        "mode": "attack",
        "transactions": transactions,
        "graph_signal": graph_signal,
        "system_signal": system_signal,
        "detector_status": status,
        "incident": demo_state.incident,
    }


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_caller_data(
    request: AnalysisRequest,
    gateway: DetectorGateway = Depends(get_detector_gateway),
) -> AnalysisResponse:
    """Analyze arbitrary caller-supplied transactions and optional host telemetry."""

    try:
        graph_signal, system_signal, status = await gateway.analyze_payload(
            request.transactions,
            baseline_transactions=request.baseline_transactions,
            telemetry_events=request.telemetry_events,
            supplied_system_signal=request.system_signal,
            correlate_with_latest_system=request.correlate_with_latest_system,
            telemetry_host=request.telemetry_host,
            telemetry_service=request.telemetry_service,
        )
    except DetectorUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    analysis_id = f"ANL-{graph_signal.signal_id.removeprefix('GRAPH-')}"
    argus_store.save_transactions(analysis_id, request.transactions)
    argus_store.save_signal(graph_signal)

    incident = None
    if system_signal is not None:
        argus_store.save_signal(system_signal)
        incident = correlate(
            CorrelationRequest(
                graph_signal=graph_signal,
                system_signal=system_signal,
            )
        )
        argus_store.save_incident(incident)
        demo_state.incident = incident

    return AnalysisResponse(
        analysis_id=analysis_id,
        source_label=request.source_label,
        transactions=request.transactions,
        graph_signal=graph_signal,
        system_signal=system_signal,
        detector_status=status,
        incident=incident,
    )


@app.post("/api/signals/correlate", response_model=Incident)
def correlate_signals(request: CorrelationRequest) -> Incident:
    demo_state.incident = correlate(request)
    argus_store.save_signal(request.graph_signal)
    argus_store.save_signal(request.system_signal)
    argus_store.save_incident(demo_state.incident)
    return demo_state.incident


@app.get("/api/incidents", response_model=list[Incident])
def list_incidents(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Incident]:
    return argus_store.list_incidents(limit)


@app.get("/api/incidents/{incident_id}", response_model=Incident)
def get_incident(incident_id: str) -> Incident:
    incident = argus_store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.get("/api/platform/metrics", response_model=PlatformMetrics)
def platform_metrics() -> PlatformMetrics:
    return argus_store.metrics()


@app.post("/api/incidents/{incident_id}/approve")
def approve(incident_id: str, actor: str = "human-analyst") -> dict[str, object]:
    incident = (
        demo_state.incident
        if demo_state.incident is not None
        and demo_state.incident.incident_id == incident_id
        else argus_store.get_incident(incident_id)
    )
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.status is not IncidentStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"Incident cannot be approved while {incident.status.value}",
        )
    incident, audit_events = approve_containment(incident, actor)
    demo_state.incident = incident
    demo_state.audit_events.extend(audit_events)
    argus_store.save_incident(incident)
    argus_store.save_audit_events(incident_id, audit_events)
    return {"incident": incident, "audit_events": audit_events}


@app.get("/api/audit", response_model=list[AuditEvent])
def audit_log(incident_id: str | None = None) -> list[AuditEvent]:
    selected_id = incident_id or (
        demo_state.incident.incident_id if demo_state.incident is not None else None
    )
    return argus_store.list_audit_events(selected_id)
