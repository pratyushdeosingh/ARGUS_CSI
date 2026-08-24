"""Strict data models for normalized telemetry and the shared ARGUS contract."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RawEvent(StrictModel):
    """Sanitized event emitted by replay or the live collector."""

    timestamp: datetime
    event_type: Literal["process_exec", "file_open", "network_connect"]
    process: str
    details: dict[str, Any] = Field(default_factory=dict)


class TelemetryAnalysisRequest(StrictModel):
    events: list[RawEvent] = Field(min_length=1, max_length=5000)
    host: str = "payment-node-01"
    service: str = "payment-api"


class NormalizedEvent(StrictModel):
    timestamp: datetime
    category: Literal["process", "file", "network"]
    process: str
    indicator: str | None = None
    related_ip: str | None = None
    suspicious: bool = False


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
