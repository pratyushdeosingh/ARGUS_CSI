"""FastAPI entry point for the ARGUS orchestration prototype."""

import asyncio
import logging

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
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
    IngestionStatus,
    PlatformMetrics,
    Transaction,
    TransactionIngestionResponse,
)
from .policy import approve_containment
from .simulator import (
    load_attack_transactions,
    load_normal_transactions,
)
from .state import demo_state
from .storage import ArgusStore, IngestionConflictError, argus_store, get_argus_store
from .websocket_manager import (
    WebSocketManager,
    create_stream_event,
    get_websocket_manager,
)


logger = logging.getLogger("argus.api")

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


@app.websocket("/ws/transactions")
async def websocket_transactions(
    websocket: WebSocket,
    manager: WebSocketManager = Depends(get_websocket_manager),
) -> None:
    """Real-time WebSocket endpoint for transaction ingestion and fraud alerts."""
    await manager.connect(websocket)
    welcome_event = create_stream_event(
        event_type="connection.established",
        data={
            "message": "Connected to ARGUS real-time transaction stream",
            "status": "online",
        },
    )
    await manager.send_personal(websocket, welcome_event)
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        await manager.disconnect(websocket)


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
    store: ArgusStore = Depends(get_argus_store),
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
    store.save_transactions("DEMO-ATTACK", transactions)
    store.save_signal(graph_signal)
    store.save_signal(system_signal)
    demo_state.incident = store.save_incident(demo_state.incident)
    return {
        "mode": "attack",
        "transactions": transactions,
        "graph_signal": graph_signal,
        "system_signal": system_signal,
        "detector_status": status,
        "incident": demo_state.incident,
    }


@app.post(
    "/api/transactions",
    response_model=TransactionIngestionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "model": TransactionIngestionResponse,
            "description": "Transaction already received with identical data",
        },
        201: {
            "model": TransactionIngestionResponse,
            "description": "Transaction ingested successfully",
        },
        409: {"description": "Conflict: Transaction ID already exists with different data"},
        422: {"description": "Validation error: invalid transaction payload"},
        500: {"description": "Internal server error during transaction ingestion"},
    },
)
async def ingest_transaction(
    transaction: Transaction,
    response: Response,
    session_id: str | None = Query(
        default=None,
        description="Optional session or run ID for isolating demonstration scenarios",
    ),
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    store: ArgusStore = Depends(get_argus_store),
    gateway: DetectorGateway = Depends(get_detector_gateway),
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    settings: Settings = Depends(get_settings),
) -> TransactionIngestionResponse:
    effective_batch = (
        session_id
        or x_session_id
        or (
            transaction.transaction_id.rsplit("-", 1)[0]
            if "-" in transaction.transaction_id
            else "INGESTED"
        )
    )

    try:
        result = await asyncio.to_thread(
            store.ingest_transaction, transaction, effective_batch
        )
    except IngestionConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest transaction due to an internal storage error",
        ) from error

    if result == IngestionStatus.ALREADY_RECEIVED:
        response.status_code = status.HTTP_200_OK
        return TransactionIngestionResponse(
            status=result,
            message="Transaction already received with identical data",
            transaction_id=transaction.transaction_id,
            transaction=transaction,
        )

    response.status_code = status.HTTP_201_CREATED

    # 1. Broadcast transaction.received
    received_event = create_stream_event(
        event_type="transaction.received",
        timestamp=transaction.timestamp,
        data=transaction.model_dump(mode="json"),
    )
    try:
        await ws_manager.broadcast(received_event)
    except Exception as err:
        logger.warning(f"Failed to broadcast transaction.received: {err}")

    # 2. Contextual rolling graph fraud analysis
    try:
        window_txs = await asyncio.to_thread(
            store.get_recent_transactions_window,
            end_timestamp=transaction.timestamp,
            window_minutes=settings.analysis_window_minutes,
            max_count=settings.analysis_max_transactions,
            batch_id=effective_batch,
        )
        graph_signal = await gateway.analyze_graph(window_txs)
        await asyncio.to_thread(store.save_signal, graph_signal)

        # 3. Broadcast transaction.scored
        scored_event = create_stream_event(
            event_type="transaction.scored",
            timestamp=transaction.timestamp,
            data={
                "transaction_id": transaction.transaction_id,
                "signal_id": graph_signal.signal_id,
                "risk_score": graph_signal.risk_score,
                "anomaly_type": graph_signal.anomaly_type,
                "suspicious_accounts": graph_signal.suspicious_accounts,
                "suspicious_transactions": graph_signal.suspicious_transactions,
                "reasons": graph_signal.reasons,
            },
        )
        try:
            await ws_manager.broadcast(scored_event)
        except Exception as err:
            logger.warning(f"Failed to broadcast transaction.scored: {err}")

        # 4. Check if high-risk fraud alert threshold is exceeded
        if graph_signal.risk_score >= settings.fraud_alert_threshold:
            alert_event = create_stream_event(
                event_type="alert.created",
                timestamp=transaction.timestamp,
                data={
                    "alert_id": f"ALT-{graph_signal.signal_id.removeprefix('GRAPH-')}",
                    "transaction_id": transaction.transaction_id,
                    "signal_id": graph_signal.signal_id,
                    "risk_score": graph_signal.risk_score,
                    "anomaly_type": graph_signal.anomaly_type,
                    "severity": "critical" if graph_signal.risk_score >= 0.85 else "high",
                    "suspicious_accounts": graph_signal.suspicious_accounts,
                    "suspicious_transactions": graph_signal.suspicious_transactions,
                    "supporting_evidence": graph_signal.reasons,
                    "message": (
                        f"Graph risk score {graph_signal.risk_score:.3f} "
                        f"exceeded threshold {settings.fraud_alert_threshold:.2f}"
                    ),
                },
            )
            try:
                await ws_manager.broadcast(alert_event)
            except Exception as err:
                logger.warning(f"Failed to broadcast alert.created: {err}")

    except Exception as error:
        logger.warning(
            f"Graph analysis failed for transaction {transaction.transaction_id}: {error}"
        )
        fail_event = create_stream_event(
            event_type="transaction.analysis_failed",
            timestamp=transaction.timestamp,
            data={
                "transaction_id": transaction.transaction_id,
                "error": f"Graph analysis unavailable: {str(error)}",
            },
        )
        try:
            await ws_manager.broadcast(fail_event)
        except Exception as err:
            logger.warning(f"Failed to broadcast transaction.analysis_failed: {err}")

    return TransactionIngestionResponse(
        status=result,
        message="Transaction ingested successfully",
        transaction_id=transaction.transaction_id,
        transaction=transaction,
    )



@app.get(
    "/api/transactions",
    response_model=list[Transaction],
    responses={
        200: {"description": "List of recently ingested transactions"},
        422: {"description": "Validation error: invalid limit or offset"},
    },
)
def list_transactions(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of transactions to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    store: ArgusStore = Depends(get_argus_store),
) -> list[Transaction]:
    return store.list_transactions(limit=limit, offset=offset)


@app.get(
    "/api/transactions/{transaction_id}",
    response_model=Transaction,
    responses={
        200: {"description": "Transaction details"},
        404: {"description": "Transaction not found"},
    },
)
def get_transaction(
    transaction_id: str,
    store: ArgusStore = Depends(get_argus_store),
) -> Transaction:
    transaction = store.get_transaction(transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' not found",
        )
    return transaction


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_caller_data(
    request: AnalysisRequest,
    gateway: DetectorGateway = Depends(get_detector_gateway),
    store: ArgusStore = Depends(get_argus_store),
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
    store.save_transactions(analysis_id, request.transactions)
    store.save_signal(graph_signal)

    incident = None
    if system_signal is not None:
        store.save_signal(system_signal)
        incident = correlate(
            CorrelationRequest(
                graph_signal=graph_signal,
                system_signal=system_signal,
            )
        )
        incident = store.save_incident(incident)
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
def correlate_signals(
    request: CorrelationRequest,
    store: ArgusStore = Depends(get_argus_store),
) -> Incident:
    demo_state.incident = correlate(request)
    store.save_signal(request.graph_signal)
    store.save_signal(request.system_signal)
    demo_state.incident = store.save_incident(demo_state.incident)
    return demo_state.incident


@app.get("/api/incidents", response_model=list[Incident])
def list_incidents(
    limit: int = Query(default=50, ge=1, le=200),
    store: ArgusStore = Depends(get_argus_store),
) -> list[Incident]:
    return store.list_incidents(limit)


@app.get("/api/incidents/{incident_id}", response_model=Incident)
def get_incident(
    incident_id: str,
    store: ArgusStore = Depends(get_argus_store),
) -> Incident:
    incident = store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.get("/api/platform/metrics", response_model=PlatformMetrics)
def platform_metrics(
    store: ArgusStore = Depends(get_argus_store),
) -> PlatformMetrics:
    return store.metrics()


@app.post("/api/incidents/{incident_id}/approve")
def approve(
    incident_id: str,
    actor: str = "human-analyst",
    store: ArgusStore = Depends(get_argus_store),
) -> dict[str, object]:
    incident = store.get_incident(incident_id)
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
    incident = store.save_incident(incident)
    store.save_audit_events(incident_id, audit_events)
    return {"incident": incident, "audit_events": audit_events}


@app.get("/api/audit", response_model=list[AuditEvent])
def audit_log(
    incident_id: str | None = None,
    store: ArgusStore = Depends(get_argus_store),
) -> list[AuditEvent]:
    selected_id = incident_id or (
        demo_state.incident.incident_id if demo_state.incident is not None else None
    )
    return store.list_audit_events(selected_id)
