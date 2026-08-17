"""Shared typed models used by the ARGUS orchestration service.

Detector owners should preserve the JSON field names represented here. The
JSON Schemas in ``contracts/`` remain the language-neutral source of truth.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

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
