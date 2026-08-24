"""FastAPI entry point for the ARGUS financial graph detector."""

import json
import os
from pathlib import Path

from fastapi import FastAPI

from detector import GraphDetector
from graph_models import (
    BaselineResponse,
    ContextualAnalysisRequest,
    GraphSignal,
    HealthResponse,
    Transaction,
    TransactionBatch,
    VisualizationResponse,
)
from visualization import to_cytoscape


SERVICE_VERSION = "1.0.0"
SERVICE_DIR = Path(__file__).resolve().parent
DEFAULT_BASELINE_PATH = SERVICE_DIR.parent.parent / "data" / "normal" / "transactions.json"


def _load_baseline() -> list[Transaction]:
    configured = os.getenv("ARGUS_GRAPH_BASELINE")
    path = Path(configured).expanduser() if configured else DEFAULT_BASELINE_PATH
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Transaction.model_validate(item) for item in payload]


detector = GraphDetector(_load_baseline())
app = FastAPI(
    title="ARGUS Financial Graph Detector",
    description="Explainable temporal graph risk analysis for synthetic transactions.",
    version=SERVICE_VERSION,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="graph_detector",
        version=SERVICE_VERSION,
        baseline_transactions=len(detector.baseline_transactions),
    )


def _baseline_response() -> BaselineResponse:
    baseline = detector.baseline_transactions
    accounts = {
        account
        for item in baseline
        for account in (item.source_account, item.destination_account)
    }
    return BaselineResponse(
        status="ready",
        baseline_transactions=len(baseline),
        accounts_profiled=len(accounts),
        currencies_profiled=sorted({item.currency for item in baseline}),
    )


@app.get("/baseline", response_model=BaselineResponse)
def baseline_status() -> BaselineResponse:
    return _baseline_response()


@app.post("/baseline/train", response_model=BaselineResponse)
def train_baseline(batch: TransactionBatch) -> BaselineResponse:
    """Replace the behavioral reference window with caller-supplied history."""

    detector.replace_baseline(batch.root)
    return _baseline_response()


@app.post("/analyze", response_model=GraphSignal)
def analyze(batch: TransactionBatch) -> GraphSignal:
    return detector.analyze(batch.root)


@app.post("/analyze-context", response_model=GraphSignal)
def analyze_context(request: ContextualAnalysisRequest) -> GraphSignal:
    """Analyze against a request-scoped baseline without mutating global state."""

    return detector.analyze(request.transactions, request.baseline_transactions)


@app.post("/visualize", response_model=VisualizationResponse)
def visualize(batch: TransactionBatch) -> VisualizationResponse:
    transactions = batch.root
    signal = detector.analyze(transactions)
    return to_cytoscape(
        transactions,
        suspicious_accounts=set(signal.suspicious_accounts),
        suspicious_transactions=set(signal.suspicious_transactions),
    )
