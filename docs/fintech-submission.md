# Fintech integration — Problem Statement #9

## Integrated teammate work

- Yojit: synthetic normal/mule simulator, JSON replay and WebSocket watcher,
  durable single-payment ingestion with duplicate/conflict handling, recent
  transaction APIs, bounded rolling graph scoring, and live stream events.
- Pratham: temporal graph neural network (TGNN) and bundled checkpoint,
  stateful single-transaction risk engine, dedicated mule/scam heuristics,
  explainable detector breakdown, scenario API, and standalone graph demo.
- Existing infrastructure detector and cross-domain case/approval flow remain
  available. Infrastructure evidence is optional for financial scoring.

The current `yojit/live-dashboard` and `yojit/scam-detection` branches have no
changes beyond the reviewed main branch. The older infrastructure and
orchestration branches are already ancestors of main. Pratham's newer work had
no PR when inspected; it is included in this integration with its commit history.

## Integration repairs

The merge preserves runtime baseline replacement and request-scoped baseline
analysis. New modules use `graph_models` to avoid collisions with the
infrastructure service's `models` module. Startup requires the bundled TGNN
checkpoint instead of silently using random parameters or retraining fixtures.

Rolling scoring keeps the newest bounded window, including precise timestamps
from both batch and streaming storage formats. The specialist history store
deduplicates deliveries, removes evicted account/graph indices, serializes history
access, and filters account evidence relative to the payment timestamp. Mule
forwarding and scam amount comparisons separate currencies. Scenario runs use
isolated history so demonstrations do not reset live scoring history.

## Actual integration boundaries

| Entry point | Current behavior |
| --- | --- |
| Core `POST /api/transactions` | Persists payment, scores rolling window through graph `/analyze`, broadcasts received/scored/high-risk alert or analysis failure |
| Core `/ws/transactions` | Live event stream; watcher script is provided |
| Graph `POST /analyze` and `/analyze-context` | Rules plus TGNN; existing 0–1 `GraphSignal` contract |
| Graph `POST /score-transaction` | Rules, TGNN, mule and scam specialists; 0–100 score with ALLOW/REVIEW/BLOCK recommendation |
| Graph `/demo` | Standalone scoring demonstration; independent of the React SOC |
| Core `POST /api/analyze` | Existing batch workflow; durable incident still requires a system signal |

`BLOCK` is a recommendation. Response actions remain simulated and require
analyst approval in the existing core workflow. The graph specialist endpoint
uses in-memory history and is not a durable payment ledger. Stream alerts are
not yet durable financial-only investigation cases. Do not claim that the React
dashboard already displays the live stream or specialist detector breakdown.

## Remaining submission work

| Priority | Work | Owner |
| --- | --- | --- |
| Critical | Evaluate trained model on independent held-out data; report precision, recall, F1, PR-AUC and false positives | Pratyush |
| Critical | Durable financial-only incidents without requiring infrastructure telemetry | Pratyush |
| High | Connect specialist mule/scam breakdown to core scoring and React, preserving 0–1/0–100 scale boundaries | All three |
| High | Subscribe React to live stream; reconnect, show failures, load persisted history | Yojit |
| High | Compliance investigation workflow, draft suspicious activity reports and audit history | Pratyush |
| High | Cycles, suspicious communities, centrality and network evidence beyond existing temporal paths | Pratham |
| High | Validate scam scenarios and coordinate specialist integration with Pratham | Yojit |
| Medium | Transaction-level ML attribution and model/data provenance in the UI | Pratyush |

The bundled TGNN was trained on canonical synthetic normal/attack batches.
Scenario assertions demonstrate behavior, not generalization or production fraud
accuracy. Detector scores and node rankings are not SHAP explanations. Preserve
these limits in the submission and demo until independent evaluation exists.

## Local verification and demo

Install all three Python requirements files. On machines without a GPU, install
PyTorch from its CPU index first, as CI and the graph Dockerfile do. Run:

```powershell
python -m pytest -q
pnpm --dir frontend test
pnpm --dir frontend build
```

Start graph, infrastructure replay and core services using the README commands.
Run `python -m backend.app.integration_check` for the existing detector smoke test.
Use the commands and session guidance in `scripts/README.md` to watch and replay
synthetic payments. Open the graph `/demo` separately to inspect specialist
scoring. Use a single graph-service worker for the prototype's in-memory history.
