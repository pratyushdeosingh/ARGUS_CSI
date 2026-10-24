"""FastAPI entry point for the ARGUS financial graph detector and transaction risk engine."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from detector import GraphDetector
from engine import TransactionRiskEngine
from graph_models import (
    BaselineResponse,
    ContextualAnalysisRequest,
    GraphSignal,
    HealthResponse,
    Transaction,
    TransactionBatch,
    TransactionScoreInput,
    TransactionScoreResponse,
    VisualizationResponse,
)
from scenarios import get_all_scenarios
from scam_detector import ScamDetector
from contextual_scoring import ContextScoreRequest, score_context
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
risk_engine = TransactionRiskEngine(detector)

app = FastAPI(
    title="ARGUS Financial Graph Detector & Transaction Risk Engine",
    description="Explainable real-time transaction scoring, TGNN anomaly detection, mule detection, and scam analytics.",
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
    risk_engine.scam_detector = ScamDetector(risk_engine.history_store, batch.root)
    risk_engine.reset()
    return _baseline_response()


@app.post("/analyze", response_model=GraphSignal)
def analyze(batch: TransactionBatch) -> GraphSignal:
    """Contract-compliant batch analysis endpoint."""
    return detector.analyze(batch.root)


@app.post("/analyze-context", response_model=GraphSignal)
def analyze_context(request: ContextualAnalysisRequest) -> GraphSignal:
    """Analyze against a request-scoped baseline without mutating global state."""

    return detector.analyze(request.transactions, request.baseline_transactions)


@app.post("/visualize", response_model=VisualizationResponse)
def visualize(batch: TransactionBatch) -> VisualizationResponse:
    """Generate Cytoscape visualization elements for transaction graph."""
    transactions = batch.root
    signal = detector.analyze(transactions)
    return to_cytoscape(
        transactions,
        suspicious_accounts=set(signal.suspicious_accounts),
        suspicious_transactions=set(signal.suspicious_transactions),
    )


@app.post("/score-transaction", response_model=TransactionScoreResponse)
def score_transaction(payload: TransactionScoreInput) -> TransactionScoreResponse:
    """Real-time transaction scoring combining Rules, TGNN, Mule, and Scam detectors."""
    return risk_engine.score_transaction(payload)


@app.post("/score-transaction-context", response_model=TransactionScoreResponse)
def score_transaction_context(payload: ContextScoreRequest) -> TransactionScoreResponse:
    try:
        return score_context(detector, payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/history/reset")
def reset_history() -> dict[str, str]:
    """Reset the stateful history store back to initial baseline."""
    risk_engine.reset()
    return {"status": "reset_successful"}


@app.get("/api/scenarios")
def list_scenarios() -> list[dict]:
    """Return catalog of synthetic demonstration scenarios."""
    scenarios = get_all_scenarios()
    return [
        {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "description": s.description,
            "expected_band": s.expected_band,
            "expected_decision": s.expected_decision,
            "eval_transaction": s.eval_transaction.model_dump(mode="json"),
        }
        for s in scenarios.values()
    ]


@app.post("/api/scenarios/{scenario_id}/run")
def run_scenario(scenario_id: str) -> dict:
    """Execute a deterministic demonstration scenario and return score and graph."""
    scenarios = get_all_scenarios()
    if scenario_id not in scenarios:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")

    scenario = scenarios[scenario_id]
    scenario_engine = TransactionRiskEngine(detector)

    # Pre-seed history with setup context
    for tx in scenario.setup_transactions:
        scenario_engine.history_store.add_transaction(tx)

    # Score target transaction
    score_result = scenario_engine.score_transaction(scenario.eval_transaction)

    # Generate graph visualization for the scenario
    all_scenario_txs = [*scenario.setup_transactions, scenario.eval_transaction.to_transaction()]
    suspicious_accounts = {score_result.sender, score_result.receiver} if score_result.risk_score >= 30 else set()
    suspicious_txs = {score_result.transaction_id} if score_result.risk_score >= 30 else set()
    graph_vis = to_cytoscape(
        all_scenario_txs,
        suspicious_accounts=suspicious_accounts,
        suspicious_transactions=suspicious_txs,
    )

    return {
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "category": scenario.category,
            "description": scenario.description,
            "expected_band": scenario.expected_band,
            "expected_decision": scenario.expected_decision,
        },
        "score_result": score_result.model_dump(mode="json"),
        "visualization": graph_vis.model_dump(mode="json"),
    }


@app.get("/", response_class=HTMLResponse)
@app.get("/demo", response_class=HTMLResponse)
def demo_ui() -> HTMLResponse:
    """Interactive demo interface displaying transaction scoring, explainability, and graph."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARGUS CSI — Transaction Fraud Detection & TGNN</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
    <style>
        :root {
            --bg-primary: #0a0e17;
            --bg-secondary: #121826;
            --bg-card: #182234;
            --border: #25334d;
            --text-main: #f0f4fc;
            --text-muted: #8ba0c2;
            --accent-blue: #3b82f6;
            --accent-cyan: #06b6d4;
            --severity-low: #10b981;
            --severity-mod: #f59e0b;
            --severity-high: #f97316;
            --severity-severe: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg-primary); color: var(--text-main); min-height: 100vh; padding: 20px; }
        header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
        .logo { font-size: 22px; font-weight: 800; letter-spacing: 1px; color: var(--text-main); display: flex; align-items: center; gap: 10px; }
        .badge-2026 { background: linear-gradient(135deg, #6366f1, #a855f7); font-size: 11px; padding: 4px 8px; border-radius: 6px; font-weight: 600; }
        .grid { display: grid; grid-template-columns: 360px 1fr 400px; gap: 20px; }
        .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 18px; }
        .card h2 { font-size: 15px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 14px; }
        .scenario-btn { width: 100%; text-align: left; padding: 12px 14px; margin-bottom: 10px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; color: var(--text-main); cursor: pointer; transition: all 0.2s; }
        .scenario-btn:hover { border-color: var(--accent-blue); transform: translateX(3px); }
        .scenario-btn.active { border-color: var(--accent-cyan); background: #1e293b; box-shadow: 0 0 10px rgba(6, 182, 212, 0.2); }
        .scenario-title { font-weight: 600; font-size: 14px; margin-bottom: 3px; display: flex; justify-content: space-between; }
        .scenario-desc { font-size: 12px; color: var(--text-muted); line-height: 1.4; }
        .score-box { text-align: center; padding: 20px; background: var(--bg-secondary); border-radius: 10px; margin-bottom: 16px; border: 1px solid var(--border); }
        .score-val { font-size: 52px; font-weight: 900; line-height: 1; margin: 10px 0; }
        .badges-row { display: flex; justify-content: center; gap: 10px; margin-top: 8px; }
        .tag { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; text-transform: uppercase; }
        .tag-allow { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }
        .tag-review { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }
        .tag-block { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
        .detector-bars { margin-bottom: 18px; }
        .bar-row { margin-bottom: 10px; }
        .bar-label { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; font-weight: 500; }
        .bar-track { height: 7px; background: #0f172a; border-radius: 4px; overflow: hidden; }
        .bar-fill { height: 100%; border-radius: 4px; transition: width 0.4s ease; }
        .reasons-list { list-style: none; }
        .reasons-list li { background: var(--bg-secondary); border-left: 3px solid var(--accent-cyan); padding: 8px 12px; margin-bottom: 8px; border-radius: 0 6px 6px 0; font-size: 12px; line-height: 1.4; }
        #cy { width: 100%; height: 500px; background: var(--bg-secondary); border-radius: 10px; border: 1px solid var(--border); }
        .field-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #1e293b; font-size: 13px; }
        .field-name { color: var(--text-muted); }
        .field-val { font-weight: 600; }
        .form-input { width: 100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 6px; color: var(--text-main); margin-bottom: 8px; font-size: 13px; }
        .submit-btn { width: 100%; padding: 10px; background: var(--accent-blue); border: none; border-radius: 6px; color: white; font-weight: 700; cursor: pointer; margin-top: 6px; }
        .submit-btn:hover { background: #2563eb; }
    </style>
</head>
<body>
    <header>
        <div class="logo">
            <span>🛡️ ARGUS CSI</span>
            <span class="badge-2026">2026 FRAUD DETECTION & TGNN</span>
        </div>
        <div style="font-size: 13px; color: var(--text-muted);">
            Real-Time Scoring • Mule Detector • Scam Analytics • Explainable AI
        </div>
    </header>

    <div class="grid">
        <!-- Scenarios Column -->
        <div class="card">
            <h2>Select Fraud Scenario</h2>
            <div id="scenarios-list">Loading scenarios...</div>

            <h2 style="margin-top: 20px;">Or Custom Transaction</h2>
            <input class="form-input" id="inp-id" value="TX-CUSTOM-101" placeholder="Transaction ID" />
            <input class="form-input" id="inp-sender" value="ACC-101" placeholder="Sender Account" />
            <input class="form-input" id="inp-receiver" value="ACC-202" placeholder="Receiver Account" />
            <input class="form-input" id="inp-amount" type="number" value="85000" placeholder="Amount (INR)" />
            <button class="submit-btn" onclick="submitCustom()">Score Transaction</button>
        </div>

        <!-- Graph & Details Column -->
        <div class="card" style="display: flex; flex-direction: column;">
            <h2>Transaction Subgraph Visualization</h2>
            <div id="cy"></div>
            <div style="margin-top: 16px;">
                <h2>Transaction Details</h2>
                <div class="field-row"><span class="field-name">Transaction ID</span><span class="field-val" id="tx-id">-</span></div>
                <div class="field-row"><span class="field-name">Sender</span><span class="field-val" id="tx-sender">-</span></div>
                <div class="field-row"><span class="field-name">Receiver</span><span class="field-val" id="tx-receiver">-</span></div>
                <div class="field-row"><span class="field-name">Amount</span><span class="field-val" id="tx-amount">-</span></div>
                <div class="field-row"><span class="field-name">Timestamp</span><span class="field-val" id="tx-timestamp">-</span></div>
            </div>
        </div>

        <!-- Detection Results & Explainability Column -->
        <div class="card">
            <h2>Risk Assessment</h2>
            <div class="score-box">
                <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; font-weight: 700;">Unified Risk Score</div>
                <div class="score-val" id="res-score">--</div>
                <div class="badges-row">
                    <span class="tag" id="res-band">--</span>
                    <span class="tag" id="res-decision">--</span>
                </div>
            </div>

            <h2>Detector Breakdown</h2>
            <div class="detector-bars">
                <div class="bar-row">
                    <div class="bar-label"><span>Rule Detector</span><span id="score-rules">0/100</span></div>
                    <div class="bar-track"><div class="bar-fill" id="bar-rules" style="width: 0%; background: #3b82f6;"></div></div>
                </div>
                <div class="bar-row">
                    <div class="bar-label"><span>Temporal GNN (TGNN)</span><span id="score-tgnn">0/100</span></div>
                    <div class="bar-track"><div class="bar-fill" id="bar-tgnn" style="width: 0%; background: #a855f7;"></div></div>
                </div>
                <div class="bar-row">
                    <div class="bar-label"><span>Mule Detector</span><span id="score-mule">0/100</span></div>
                    <div class="bar-track"><div class="bar-fill" id="bar-mule" style="width: 0%; background: #f59e0b;"></div></div>
                </div>
                <div class="bar-row">
                    <div class="bar-label"><span>Scam Detector</span><span id="score-scam">0/100</span></div>
                    <div class="bar-track"><div class="bar-fill" id="bar-scam" style="width: 0%; background: #ef4444;"></div></div>
                </div>
            </div>

            <h2>Explainable AI Evidence</h2>
            <ul class="reasons-list" id="res-reasons">
                <li>Select a scenario to inspect explainable evidence.</li>
            </ul>
        </div>
    </div>

    <script>
        let cy = null;

        function initCy(elements = []) {
            cy = cytoscape({
                container: document.getElementById('cy'),
                elements: elements,
                style: [
                    {
                        selector: 'node',
                        style: {
                            'background-color': '#334155',
                            'label': 'data(label)',
                            'color': '#f8fafc',
                            'font-size': '11px',
                            'text-valign': 'center',
                            'width': '38px',
                            'height': '38px',
                            'border-width': 2,
                            'border-color': '#64748b'
                        }
                    },
                    {
                        selector: 'node[?suspicious]',
                        style: {
                            'background-color': '#ef4444',
                            'border-color': '#fca5a5',
                            'border-width': 3
                        }
                    },
                    {
                        selector: 'edge',
                        style: {
                            'width': 2,
                            'line-color': '#475569',
                            'target-arrow-color': '#475569',
                            'target-arrow-shape': 'triangle',
                            'curve-style': 'bezier',
                            'label': 'data(amount)',
                            'font-size': '9px',
                            'color': '#94a3b8'
                        }
                    },
                    {
                        selector: 'edge[?suspicious]',
                        style: {
                            'line-color': '#f97316',
                            'target-arrow-color': '#f97316',
                            'width': 3
                        }
                    }
                ],
                layout: { name: 'breadthfirst', directed: true, padding: 25 }
            });
        }

        async function loadScenarios() {
            const res = await fetch('/api/scenarios');
            const data = await res.json();
            const container = document.getElementById('scenarios-list');
            container.innerHTML = '';

            data.forEach((s, idx) => {
                const btn = document.createElement('button');
                btn.className = `scenario-btn ${idx === 0 ? 'active' : ''}`;
                btn.id = `btn-${s.id}`;
                btn.innerHTML = `
                    <div class="scenario-title">
                        <span>${s.name}</span>
                        <span style="font-size: 10px; color: ${s.expected_decision === 'BLOCK' ? '#ef4444' : (s.expected_decision === 'REVIEW' ? '#f59e0b' : '#10b981')}">${s.expected_decision}</span>
                    </div>
                    <div class="scenario-desc">${s.description}</div>
                `;
                btn.onclick = () => runScenario(s.id);
                container.appendChild(btn);
            });

            if (data.length > 0) {
                runScenario(data[0].id);
            }
        }

        async function runScenario(scenarioId) {
            document.querySelectorAll('.scenario-btn').forEach(b => b.classList.remove('active'));
            const activeBtn = document.getElementById(`btn-${scenarioId}`);
            if (activeBtn) activeBtn.classList.add('active');

            const res = await fetch(`/api/scenarios/${scenarioId}/run`, { method: 'POST' });
            const data = await res.json();
            updateUI(data.score_result, data.visualization);
        }

        async function submitCustom() {
            const payload = {
                transaction_id: document.getElementById('inp-id').value,
                sender: document.getElementById('inp-sender').value,
                receiver: document.getElementById('inp-receiver').value,
                amount: parseFloat(document.getElementById('inp-amount').value),
                timestamp: new Date().toISOString()
            };
            const res = await fetch('/score-transaction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            updateUI(data, null);
        }

        function updateUI(score, vis) {
            document.getElementById('tx-id').innerText = score.transaction_id;
            document.getElementById('tx-sender').innerText = score.sender;
            document.getElementById('tx-receiver').innerText = score.receiver;
            document.getElementById('tx-amount').innerText = `${score.amount.toLocaleString()} ${score.currency || 'INR'}`;
            document.getElementById('tx-timestamp').innerText = score.timestamp;

            const scoreEl = document.getElementById('res-score');
            scoreEl.innerText = score.risk_score;
            scoreEl.style.color = score.risk_score >= 80 ? '#ef4444' : (score.risk_score >= 60 ? '#f97316' : (score.risk_score >= 30 ? '#f59e0b' : '#10b981'));

            const bandEl = document.getElementById('res-band');
            bandEl.innerText = score.risk_band;
            bandEl.className = `tag ${score.risk_band === 'SEVERE' || score.risk_band === 'HIGH' ? 'tag-block' : (score.risk_band === 'MODERATE' ? 'tag-review' : 'tag-allow')}`;

            const decEl = document.getElementById('res-decision');
            decEl.innerText = score.decision;
            decEl.className = `tag ${score.decision === 'BLOCK' ? 'tag-block' : (score.decision === 'REVIEW' ? 'tag-review' : 'tag-allow')}`;

            // Bars
            setBar('rules', score.detectors.rules);
            setBar('tgnn', score.detectors.tgnn);
            setBar('mule', score.detectors.mule);
            setBar('scam', score.detectors.scam);

            // Reasons
            const reasonsEl = document.getElementById('res-reasons');
            reasonsEl.innerHTML = '';
            score.reasons.forEach(r => {
                const li = document.createElement('li');
                li.innerText = r;
                reasonsEl.appendChild(li);
            });

            // Graph
            if (vis) {
                const elements = [...vis.nodes, ...vis.edges];
                initCy(elements);
            }
        }

        function setBar(id, val) {
            document.getElementById(`score-${id}`).innerText = `${Math.round(val)}/100`;
            document.getElementById(`bar-${id}`).style.width = `${Math.min(100, Math.max(0, val))}%`;
        }

        window.onload = () => {
            initCy();
            loadScenarios();
        };
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html, status_code=200)
