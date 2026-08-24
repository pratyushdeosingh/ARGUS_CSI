"""Shared typed models used by the ARGUS orchestration service.

Detector owners should preserve the JSON field names represented here. The
JSON Schemas in ``contracts/`` remain the language-neutral source of truth.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class IncidentStatus(str, Enum):
    MONITORING = "monitoring"
    AWAITING_APPROVAL = "awaiting_approval"
    CONTAINED = "contained"


class Severity(str, Enum):
    INFORMATIONAL = "informational"
    SUSPICIOUS = "suspicious"
    HIGH = "high"
    CRITICAL = "critical"


class Transaction(StrictModel):
    transaction_id: str
    timestamp: datetime
    source_account: str
    destination_account: str
    amount: float = Field(gt=0)
    currency: str = "INR"
    device_id: str
    ip_address: str
    status: TransactionStatus


class GraphSignal(StrictModel):
    signal_id: str
    source: Literal["graph_detector"] = "graph_detector"
    timestamp: datetime
    risk_score: float = Field(ge=0, le=1)
    anomaly_type: str
    suspicious_accounts: list[str]
    suspicious_transactions: list[str]
    related_ips: list[str]
    reasons: list[str]


class SystemSignal(StrictModel):
    signal_id: str
    source: Literal["ebpf_detector"] = "ebpf_detector"
    timestamp: datetime
    risk_score: float = Field(ge=0, le=1)
    host: str
    service: str
    process: str
    event_type: str
    related_ips: list[str]
    indicators: list[str]


class ResponseAction(StrictModel):
    action: str
    target: str
    approval_required: bool
    status: str = "recommended"


class Incident(StrictModel):
    incident_id: str
    timestamp: datetime
    verdict: str
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    financial_signal_id: str
    infrastructure_signal_id: str
    affected_accounts: list[str]
    summary: str
    evidence: list[str]
    recommended_actions: list[ResponseAction]
    status: IncidentStatus


class CorrelationRequest(StrictModel):
    graph_signal: GraphSignal
    system_signal: SystemSignal


class AuditEvent(StrictModel):
    timestamp: datetime
    action: str
    target: str
    actor: str
    result: str


class RawTelemetryEvent(StrictModel):
    timestamp: datetime
    event_type: Literal["process_exec", "file_open", "network_connect"]
    process: str
    details: dict[str, Any] = Field(default_factory=dict)


class DetectorComponentStatus(StrictModel):
    availability: Literal["online", "degraded", "offline"]
    origin: Literal["service", "last_known", "fixture", "none"]
    mode: Literal["live", "replay", "fixture", "unknown"] = "unknown"
    detail: str


class DetectorStatus(StrictModel):
    graph: DetectorComponentStatus
    system: DetectorComponentStatus


class AnalysisRequest(StrictModel):
    transactions: list[Transaction] = Field(min_length=1, max_length=5000)
    baseline_transactions: list[Transaction] = Field(default_factory=list, max_length=10000)
    telemetry_events: list[RawTelemetryEvent] = Field(default_factory=list, max_length=5000)
    system_signal: SystemSignal | None = None
    correlate_with_latest_system: bool = False
    telemetry_host: str = Field(default="payment-node-01", min_length=1, max_length=120)
    telemetry_service: str = Field(default="payment-api", min_length=1, max_length=120)
    source_label: str = Field(default="api", min_length=1, max_length=80)


class AnalysisResponse(StrictModel):
    analysis_id: str
    mode: Literal["analysis"] = "analysis"
    source_label: str
    transactions: list[Transaction]
    graph_signal: GraphSignal
    system_signal: SystemSignal | None
    detector_status: DetectorStatus
    incident: Incident | None


class PlatformMetrics(StrictModel):
    transactions_ingested: int
    signals_analyzed: int
    incidents_total: int
    incidents_open: int
    critical_incidents: int
    accounts_observed: int
    total_value_observed: float
    average_confidence: float
    severity_counts: dict[str, int]
