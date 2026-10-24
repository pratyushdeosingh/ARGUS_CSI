# Financial graph and specialist scoring service

FastAPI service on port 8001. It contains two scoring paths with different
contracts. The core backend currently calls the batch path; the specialist path
is available through its own API/demo and is not integrated into core/React.

## Batch graph analysis — 0–1 risk

`POST /analyze` accepts a transaction array and returns the shared `GraphSignal`.
`POST /analyze-context` accepts transactions and request-scoped baseline history.
`GET /baseline` reports shared reference history; `POST /baseline/train`
replaces it and resets specialist history. Baseline replacement is not ML training.

| Rule | Weight | Evidence |
| --- | --- | --- |
| Rapid multi-hop | 0.30 | Time-respecting linked payments |
| Funds forwarded | 0.18 | A recipient quickly sends funds onward |
| Unusual amount | 0.17 | Amount relative to baseline history |
| Device/IP change | 0.10 | Identity metadata differs from account history |
| Velocity | 0.10 | Payments cluster in time |
| New beneficiary | 0.08 | Destination absent from account history |
| Fan-in/fan-out | 0.07 | Account aggregates/distributes across multiple peers |

Corroborating rule evidence adds up to 0.08. Temporal path rules exclude cancelled
payments and cross-currency forwarding. Explicit cycles, suspicious communities
and centrality-based investigation are not yet implemented.

The TGNN runs alongside rules. Only when rule risk >= 0.40 can the model promote
batch risk to `max(rule_score, model_score)`. Otherwise the rule score is kept.
Signals include reasons, suspicious accounts/transactions and related IPs.
Identity hashes transaction contents and baseline history, not just payment IDs.
For the same inputs, checkpoint and code, scoring is deterministic.

## TGNN prototype

`tgnn.py` implements log-volume/count node features, linear projection, neighbour
aggregation, a GRU temporal update and sigmoid node scores. Batch model risk is
the maximum node score. Currency is an edge attribute but is not separately
encoded as a TGNN feature; the model can aggregate raw amounts across currencies.

`tgnn_weights.pt` is required at startup. Inference neither trains nor writes a
checkpoint and does not silently continue with random parameters. The bundled
checkpoint was trained on synthetic canonical normal/attack batches. There is no
independent held-out evaluation, calibrated fraud probability, SHAP explanation
or production accuracy claim. Node scores are not feature attribution.

## Specialist engine — 0–100 risk

`POST /score-transaction` combines rules, TGNN, mule and scam heuristics.
Inputs accept standard account fields or `sender`/`receiver` aliases. Output
contains risk band, ALLOW/REVIEW/BLOCK recommendation, detector breakdown, top
factors and reasons. All recommendations are simulated and do not control banks.

- Mule heuristics: fan-in, forwarding delay, turnover, counterparty diversity and
  temporal burst.
- Scam heuristics: fan-out, velocity, repeated amounts, amount surge and temporal
  clustering. They do not establish scam intent or classify message content.
- Fusion: experimental weighted/peak/corroboration rules in `engine.py`, separate
  from batch risk. The batch model-promotion guard does not apply to this engine.
- State: bounded in-memory transaction history with per-method locks. Scoring as
  a whole is not atomic; restart/multi-worker consistency is not implemented.

`GET /api/scenarios` lists six synthetic scenarios. `POST /api/scenarios/{id}/run`
uses isolated history and returns score/visualization. `POST /api/history/reset`
resets shared specialist history. `/demo` and `/` serve the standalone scenario
UI, loading Cytoscape from a CDN. It needs network access and is separate from the
React dashboard. `POST /visualize` produces graph elements from batch input.

## Run and verify

Follow the root [README](../../README.md) to install dependencies, including CPU
PyTorch, then run from the repository root:

```powershell
python -m uvicorn app:app --app-dir services/graph-detector --host 127.0.0.1 --port 8001
python -m pytest services/graph-detector/tests -q
```

Use one worker for the demo's shared specialist history. Configure the startup
baseline with `ARGUS_GRAPH_BASELINE`, or use the bundled normal transactions.
API details: [localhost:8001/docs](http://127.0.0.1:8001/docs).

Tests cover rules, model execution/order sensitivity, contracts, cancelled and
mixed-currency rules, input-derived identity, baseline isolation, specialist
scenarios and bounded history. They do not substitute for independent model
evaluation, browser interaction testing or load testing. Next work is in
[TODO.md](../../TODO.md).
