# ARGUS architecture

## Current runtime

| Component | Responsibility | Port |
| --- | --- | --- |
| FastAPI core | Batch/stream orchestration, SQLite persistence, cross-domain correlation, approval API and WebSocket broadcasts | 8000 |
| Graph service | Behavioural rules, NetworkX temporal paths, TGNN batch scoring, specialist mule/scam engine and standalone demo | 8001 |
| Infrastructure service | Optional process/file/network evidence, replay and guarded Linux collection | 8002 |
| React dashboard | Batch Data Lab, account graph, evidence, cross-domain case history and simulated approval | 5173 |

## Financial data paths

Batch input goes through core `/api/analyze` to graph `/analyze` or
`/analyze-context`; transactions and signals are stored in SQLite. Without
infrastructure evidence this completes with no incident. The baseline-context
API does not mutate shared reference history.

Payment ingestion goes through core `/api/transactions`, persists the payment,
loads a bounded recent window in the selected session, and calls graph
`/analyze`. The core stores the resulting signal and broadcasts a scored event
and, above threshold, an alert. Detector failure emits an analysis-failed event
without rolling back ingestion. There is no durable queue or retry worker.

The graph `/score-transaction` engine uses rules, TGNN, mule and scam specialists
and in-memory history. Its 0–100 score is separate from the core 0–1 graph
contract. It is available through a separate demo; core and React integration
remain TODO items. React currently has no WebSocket subscription.

## Optional infrastructure correlation

A supplied system signal, raw telemetry or latest-system request enables the
existing core correlation path. Confidence combines graph risk (0.50), system
risk (0.35) and up to 0.15 linkage bonus. The time window is 15 minutes, not five.
The case, recommended simulated actions and eventual action audit are stored in
SQLite. Approval is required for high/critical containment. Reanalysis cannot
reopen a stored contained case.

## State and limitations

SQLite is mounted in a named Compose volume. Core signal caches and demo state
are per process. Specialist history is in memory; individual accesses are
locked, but full scoring is not atomic across concurrent requests. WebSocket
connections/events are per process and transient. No multi-worker broker or
production concurrency guarantee exists.

The bundled model is trained on synthetic demo batches. Its outputs and fusion
weights are uncalibrated; no representative held-out evaluation is included.
Risk is not a fraud probability. Rule evidence and node scores do not constitute
ML feature attribution. Financial-only cases and compliance reporting remain
unimplemented.

Accounts and telemetry are synthetic; response actions are simulated. There is
no production banking integration or authenticated operator/RBAC boundary.
See [integration contracts](integration.md) and [TODO](../TODO.md).
