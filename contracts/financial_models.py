"""Versioned financial scoring contract shared by the graph service and core."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FinancialModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DetectorScores(FinancialModel):
    rules: float = Field(ge=0, le=1)
    ml: float = Field(ge=0, le=1)
    mule: float = Field(ge=0, le=1)
    scam: float = Field(ge=0, le=1)


class ModelProvenance(FinancialModel):
    name: str = "ARGUS TGNN"
    checkpoint_sha256: str
    policy_sha256: str | None = None
    feature_schema: str = "tgnn-log-volume-count-v1"
    training_data: str = "bundled synthetic normal/attack batches"
    validation_status: Literal["synthetic_only"] = "synthetic_only"
    explanation_method: str = "Rule evidence and detector contributions; no ML feature attribution"


class PaymentScore(FinancialModel):
    transaction_id: str
    timestamp: datetime
    risk_score: float = Field(ge=0, le=1)
    detectors: DetectorScores
    raw_ml_score: float = Field(ge=0, le=1)
    raw_scam_score: float = Field(default=0, ge=0, le=1)
    ml_used: bool
    reasons: list[str]
    suspicious_accounts: list[str]
    suspicious_transactions: list[str]


class FinancialEdge(FinancialModel):
    transaction_id: str
    source_account: str
    destination_account: str
    amount: float
    currency: str
    suspicious: bool


class FeatureSensitivity(FinancialModel):
    feature: str
    score_without_feature: float = Field(ge=0, le=1)
    score_difference: float = Field(ge=-1, le=1)


class ModelDiagnostic(FinancialModel):
    transaction_id: str
    method: str = "initial_node_feature_ablation"
    scope: str = "Diagnostic only: zero one initial node feature for every node, holding graph and GRU amount/time inputs fixed. Not SHAP, causal attribution or a complete feature explanation."
    raw_score: float = Field(ge=0, le=1)
    sensitivities: list[FeatureSensitivity]


class FinancialAssessment(FinancialModel):
    schema_version: Literal["financial.v1"] = "financial.v1"
    assessment_id: str
    timestamp: datetime
    risk_score: float = Field(ge=0, le=1)
    fusion_policy: str = "max-specialists; ML promotion requires independent risk >= 0.40"
    model: ModelProvenance
    transaction_scores: list[PaymentScore]
    suspicious_accounts: list[str]
    suspicious_transactions: list[str]
    reasons: list[str]
    edges: list[FinancialEdge]
    related_ips: list[str] = Field(default_factory=list)
    model_diagnostic: ModelDiagnostic | None = None
