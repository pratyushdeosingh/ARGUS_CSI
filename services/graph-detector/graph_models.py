"""Strict HTTP and detector models for the graph service."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Transaction(StrictModel):
    transaction_id: str
    timestamp: datetime
    source_account: str
    destination_account: str
    amount: float = Field(gt=0)
    currency: str
    device_id: str
    ip_address: str
    status: TransactionStatus

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a UTC offset")
        if value.utcoffset().total_seconds() != 0:
            raise ValueError("timestamp must be UTC")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


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


class TransactionBatch(RootModel[list[Transaction]]):
    """A root array keeps the HTTP shape identical to the shared contract."""


class HealthResponse(StrictModel):
    status: str
    service: str
    version: str
    baseline_transactions: int = Field(ge=0)


class BaselineResponse(StrictModel):
    status: str
    baseline_transactions: int = Field(ge=0)
    accounts_profiled: int = Field(ge=0)
    currencies_profiled: list[str]


class ContextualAnalysisRequest(StrictModel):
    transactions: list[Transaction] = Field(min_length=1, max_length=5000)
    baseline_transactions: list[Transaction] = Field(min_length=1, max_length=10000)


class VisualizationNodeData(StrictModel):
    id: str
    label: str
    suspicious: bool
    total_in: float = Field(ge=0)
    total_out: float = Field(ge=0)


class VisualizationEdgeData(StrictModel):
    id: str
    source: str
    target: str
    transaction_id: str
    amount: float = Field(gt=0)
    currency: str
    timestamp: datetime
    suspicious: bool


class VisualizationNode(StrictModel):
    data: VisualizationNodeData


class VisualizationEdge(StrictModel):
    data: VisualizationEdgeData


class VisualizationResponse(StrictModel):
    nodes: list[VisualizationNode]
    edges: list[VisualizationEdge]


class RiskBand(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class DetectorBreakdown(StrictModel):
    rules: float
    tgnn: float
    mule: float
    scam: float


class TransactionScoreInput(BaseModel):
    """Input payload for single transaction scoring.

    Accepts standard schema fields (source_account, destination_account) or
    convenient aliases (sender, receiver), with fallback defaults for metadata.
    """
    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    transaction_id: str
    timestamp: datetime
    sender: str | None = None
    receiver: str | None = None
    source_account: str | None = None
    destination_account: str | None = None
    amount: float = Field(gt=0)
    currency: str = "INR"
    device_id: str = "DEV-ONLINE"
    ip_address: str = "127.0.0.1"
    status: TransactionStatus = TransactionStatus.COMPLETED

    @field_validator("timestamp")
    @classmethod
    def ensure_utc_timestamp(cls, value: datetime) -> datetime:
        from datetime import timezone
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_accounts(self) -> "TransactionScoreInput":
        if not (self.source_account or self.sender):
            raise ValueError("Transaction must provide 'source_account' or 'sender'")
        if not (self.destination_account or self.receiver):
            raise ValueError("Transaction must provide 'destination_account' or 'receiver'")
        return self

    def get_source(self) -> str:
        src = self.source_account or self.sender
        if not src:
            raise ValueError("Transaction must provide 'source_account' or 'sender'")
        return src

    def get_destination(self) -> str:
        dst = self.destination_account or self.receiver
        if not dst:
            raise ValueError("Transaction must provide 'destination_account' or 'receiver'")
        return dst

    def to_transaction(self) -> Transaction:
        return Transaction(
            transaction_id=self.transaction_id,
            timestamp=self.timestamp,
            source_account=self.get_source(),
            destination_account=self.get_destination(),
            amount=self.amount,
            currency=self.currency,
            device_id=self.device_id,
            ip_address=self.ip_address,
            status=self.status,
        )


class TransactionScoreResponse(StrictModel):
    transaction_id: str
    sender: str
    receiver: str
    amount: float
    currency: str
    timestamp: datetime
    risk_score: float
    risk_band: RiskBand
    decision: Decision
    detectors: DetectorBreakdown
    top_factors: list[str]
    reasons: list[str]
    explanation: str

