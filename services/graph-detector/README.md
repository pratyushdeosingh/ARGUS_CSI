# ARGUS financial graph detector

Pratham's service converts a batch of synthetic transactions into the exact
`GraphSignal` consumed by ARGUS. It combines an immutable behavioral baseline,
temporal money-flow analysis, and directed graph features. Every finding is
deterministic and cites observable evidence; no paid model or external service
is required.

## What it detects

The baseline detector evaluates seven independent signals:

| Feature | Evidence |
|---|---|
| Device/IP change | An established account uses a device or IP absent from its baseline |
| Unusual amount | A transfer is at least 5x its currency's baseline median |
| New beneficiary | An established source pays a destination absent from its baseline |
| Velocity | One account participates in linked transfers within two minutes |
| Rapid multi-hop | Funds cross two to four time-respecting transfers within five minutes per hop |
| Funds forwarded | A receiving account quickly forwards 50%–125% of the amount it received |
| Fan-in/fan-out | An account has at least three incoming or outgoing batch transfers |

Only non-cancelled transfers contribute to risk. Temporal paths cannot mix
currencies, revisit an account, move backward in time, or report a shorter
subpath when a longer path explains the same flow. Feature contributions use
fixed documented weights in `detector.py`, with a small corroboration bonus for
three or more independent findings. The baseline remains the reliable fallback;
there is deliberately no untrained GNN in the production path.

The default behavioral baseline is `data/normal/transactions.json`. Set
`ARGUS_GRAPH_BASELINE` to an alternate JSON fixture when running a different
synthetic scenario. If it is missing, graph and temporal features continue to
work, while history-dependent identity and beneficiary features remain off.

## Run locally

From the repository root, using Python 3.11 or newer:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r services/graph-detector/requirements.txt
Set-Location services/graph-detector
python -m uvicorn app:app --host 127.0.0.1 --port 8001 --reload
```

On macOS/Linux, replace activation with `source .venv/bin/activate` and use
`python3` if necessary. Open `http://127.0.0.1:8001/docs` for the generated API
documentation.

## API

`GET /health` reports readiness, version, and how many baseline transactions
were loaded.

`POST /analyze` accepts a bare JSON array matching
`contracts/transaction.schema.json` and returns only fields from
`contracts/graph-signal.schema.json`:

```bash
curl -X POST http://127.0.0.1:8001/analyze \
  -H "Content-Type: application/json" \
  --data-binary @data/attack/transactions.json
```

For the canonical fixtures the normal score is `0.000`, while the attack score
is `0.898` and identifies `ACC-101`, `ACC-202`, `ACC-303`, `ACC-404`, and
`TX-1001..TX-1003`.

`POST /visualize` accepts the same array and returns Cytoscape-compatible
`nodes` and `edges`. This is intentionally separate from `/analyze`, so the
shared `GraphSignal` remains strict and unchanged. Each element contains a
`data` object; suspicious elements are marked with `suspicious: true`.

## Test

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest services/graph-detector/tests -q
```

The suite covers fixture separation, the shared JSON Schema, API validation,
determinism, input ordering, cancelled transfers, currency boundaries,
temporal path construction, and Cytoscape output.

## Integration

ARGUS should call `POST http://127.0.0.1:8001/analyze` with its transaction
array and pass the response unchanged as `graph_signal` to
`POST http://127.0.0.1:8000/api/signals/correlate`. Timestamps are required to
be UTC. The canonical response includes `185.220.101.10`, allowing the
orchestrator to correlate the graph finding with the infrastructure signal.

The analyzer is stateless: identical batches and the same baseline always
produce the same signal ID and score. This avoids demo drift and makes retries
safe.

## Temporal Graph Neural Network (TGNN)

To complement the hand-crafted rule-based detector, this service integrates a lightweight Temporal Graph Neural Network (TGNN) built in PyTorch (CPU-compatible).

### How it works:
- **Node Representation**: A node represents a unique bank account involved in the transaction batch. Initial node features are constructed from the batch context: log of total amount sent/received and counts of outgoing/incoming transfers.
- **Edge Representation**: An edge represents an active, non-cancelled transaction between two accounts, carrying transaction amount, currency, and timestamp attributes.
- **Linear Projection**: Initial node features are projected to a hidden representation (8-dimensional space) using a learnable linear layer.
- **Message Passing**: Each node aggregates representations from its connected neighboring nodes (predecessors and successors in the transaction graph) via average aggregation, propagating structural flow information.
- **Combine & Non-linear Transformation**: The node's own representation and the aggregated neighbor message are concatenated and passed through a linear layer with a ReLU activation.
- **Temporal Update**: Transactions in the batch are processed in chronological order. A GRUCell updates the recurrent state of the source and destination nodes at each transaction, incorporating the time-delta between consecutive events, transaction amount, and the counterpart's hidden state.
- **Anomaly Output**: Node embeddings are projected via a linear layer with a Sigmoid activation to individual account risk scores. The overall batch TGNN score is the maximum of these individual node risk scores.

### Integration in the Pipeline:
The TGNN is evaluated inside [GraphDetector.analyze](file:///Users/pratham/Desktop/ARGUS_CSI/services/graph-detector/detector.py#L52-L109) alongside the rule-based features. The final `risk_score` is the maximum of the hand-crafted rule score and the TGNN score:
$$\text{risk\_score} = \max(\text{rule\_score}, \text{tgnn\_score})$$
If the TGNN score is elevated ($\ge 0.25$), it adds an explanatory message to the `reasons` list and flags the highest-risk node in `suspicious_accounts`, preserving the strict contract schema of the `GraphSignal`.

---

## 2026 Update: Real-Time Transaction Scoring & Unified Risk Engine

ARGUS CSI now includes a modular, real-time transaction detection system that evaluates transactions individually against rolling customer state, dedicated mule behavioral analysis, scam heuristics, and the underlying TGNN.

### Architecture Pipeline:

```text
TRANSACTION INPUT (POST /score-transaction)
                   │
                   ▼
       FEATURE EXTRACTION & STATE
       (AccountHistoryStore Sliding Window)
                   │
      ┌────────────┼────────────┬────────────┐
      ▼            ▼            ▼            ▼
RULE DETECTOR     TGNN     MULE DETECTOR  SCAM DETECTOR
  (0-100)        (0-100)      (0-100)        (0-100)
      │            │            │            │
      └────────────┼────────────┴────────────┘
                   │
                   ▼
         UNIFIED RISK AGGREGATOR
     (Peak + Balanced + Corroboration)
                   │
                   ▼
           FINAL RISK SCORE (0-100)
                   │
                   ▼
       RISK BAND & DECISION
       • LOW      (0-29)   --> ALLOW
       • MODERATE (30-59)  --> REVIEW
       • HIGH     (60-79)  --> REVIEW / BLOCK
       • SEVERE   (80-100) --> BLOCK
                   │
                   ▼
         GROUNDED EXPLAINABLE AI
```

### Components:

1. **Stateful History Layer (`history.py`)**:
   - `BaseHistoryStore` abstract protocol with in-memory thread-safe `InMemoryHistoryStore`.
   - Maintains circular buffer of recent transactions, subgraphs, distinct counterparties, velocity, and volume turnover.
   - Modular design allows drop-in replacement with Redis or PostgreSQL.

2. **Dedicated Mule Detector (`mule_detector.py`)**:
   - Evaluates:
     - Fan-in score (weight 0.25): distinct senders to one recipient
     - Forwarding speed score (weight 0.25): duration between fund arrival and onward transfer
     - Turnover score (weight 0.20): ratio of forwarded vs received funds
     - Counterparty diversity score (weight 0.15): unique vs repeat counterparty ratio
     - Temporal burst score (weight 0.15): clustering of inflows and outflows
   - Produces 0-100 score and grounded explanations (e.g., `"Account ACC-MULE-501 received funds from 4 distinct senders and forwarded 95% within 2 minutes."`).

3. **Dedicated Scam Detector (`scam_detector.py`)**:
   - Evaluates:
     - Fan-out score (weight 0.30): burst of outgoing transfers to new counterparties
     - Velocity burst score (weight 0.25): high frequency in short window
     - Repeated amounts score (weight 0.20): structured transfers of identical amount
     - Volume surge score (weight 0.15): ratio vs account baseline median
     - Temporal cluster score (weight 0.10): seconds between successive payments
   - Produces 0-100 score and grounded explanations.

4. **Unified Risk Engine (`engine.py`)**:
   - Synthesizes all 4 detector outputs: Rules, TGNN, Mule, and Scam.
   - Applies peak-signal preservation (so critical fraud alerts aren't diluted) and multi-detector corroboration bonus.
   - Maps scores deterministically to `ALLOW`, `REVIEW`, or `BLOCK`.

5. **Deterministic Scenarios (`scenarios.py`)**:
   - `normal`: Low-frequency baseline transaction (`ALLOW`)
   - `high_value_fraud`: Extreme volume surge >80x normal (`BLOCK`)
   - `rapid_forwarding`: A -> B -> C within 45s (`BLOCK`)
   - `mule_account`: Multi-inflow fan-in + pass-through (`BLOCK`)
   - `scam_fan_out`: Rapid outgoing dispersal to 5 new payees (`BLOCK`)
   - `suspicious_burst`: 4 identical transfers in 60s (`BLOCK`)

6. **Interactive Demo UI**:
   - Available directly at `http://127.0.0.1:8001/` or `http://127.0.0.1:8001/demo`.
   - Allows instant one-click scenario testing, custom transaction scoring, real-time Cytoscape graph rendering, risk gauge display, detector breakdown bars, and explainable AI reasons.

