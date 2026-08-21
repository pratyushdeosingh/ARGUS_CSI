"""Strict HTTP and detector models for the graph service."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator


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
