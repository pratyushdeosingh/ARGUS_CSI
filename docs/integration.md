# Integration contract

## Shared data

`contracts/` defines transaction, graph-signal and system-signal JSON schemas.
Use UTF-8 JSON and UTC ISO-8601 timestamps (`Z` or `+00:00`). Core and batch
transaction models reject naive/non-UTC timestamps and unknown fields. The
specialist input also accepts `sender`/`receiver` aliases and normalizes its
timestamp; it is a distinct convenience contract.

A transaction contains `transaction_id`, `timestamp`, `source_account`,
`destination_account`, `amount`, `currency`, `device_id`, `ip_address`, and
`status` (`pending`, `completed`, `cancelled`). Amount must be positive.

Core graph/system risk is **0–1**. Specialist risk and its detector breakdown are
**0–100**. Neither is a calibrated probability. Do not pass specialist values
directly into the core correlation formula.

## Core API — port 8000

| Method | Path | Behaviour |
| --- | --- | --- |
| GET | `/health` | Process health; detector availability is separate |
| POST | `/api/analyze` | Batch graph analysis with optional baseline/telemetry/system signal |
| POST | `/api/transactions` | Persist one payment and attempt rolling graph scoring |
| GET | `/api/transactions` | Stored payments; `limit` 1–200, `offset` >= 0 |
| GET | `/api/transactions/{transaction_id}` | Stored payment or 404 |
| WS | `/ws/transactions` | Transient transaction and alert event stream |
| GET | `/api/detectors/status` | Availability, origin and infrastructure collection mode |
| GET | `/api/platform/metrics` | Stored transaction/signal/case aggregates |
| GET | `/api/incidents` | Persisted cases |
| GET | `/api/incidents/{incident_id}` | One case or 404 |
| POST | `/api/incidents/{incident_id}/approve` | Approve pending simulated containment; repeat returns 409 |
| GET | `/api/audit?incident_id=...` | Stored simulated action audit |
| POST | `/api/signals/correlate` | Cross-domain case from supplied graph and system signals |
| GET | `/api/demo/normal` | Reset in-memory demo state; does not erase SQLite history |
| POST | `/api/demo/simulate-attack` | Canonical two-detector demo; fixed demo case ID `INC-001` |

### Batch behaviour

`/api/analyze` accepts 1–5,000 transactions; optional baseline history, raw
telemetry, a system signal or `correlate_with_latest_system` are supported.
A supplied baseline uses graph `/analyze-context` without mutating the shared
baseline. Graph-only success returns no system signal and no incident. With
infrastructure evidence, correlation creates a case. Reanalysis preserves a
contained case's stored state; it does not authorize another containment run.

The core stores input transactions and signals. Current transaction persistence
is an upsert keyed by transaction ID, rather than an immutable revision ledger.
See TODO P1-5 for the remaining consistency work.

### Stream behaviour

Session precedence: `session_id` query parameter, `X-Session-ID` header, then
transaction ID prefix before the final hyphen (or `INGESTED`). Use an explicit
session for controlled demos. Windows include recent payments from that group,
ordered by event timestamp and bounded by configured count/time limits.

Ingestion returns 201 for new data, 200 for an identical duplicate, 409 for a
conflicting ID and 422 for invalid input. Successful ingestion is not proof of
successful scoring. Detector errors leave the transaction stored and emit
`transaction.analysis_failed`; duplicate delivery does not retry analysis.

Event envelopes contain `event_id`, `event_type`, `timestamp` and `data`.
Supported types: `connection.established`, `transaction.received`,
`transaction.scored`, `alert.created`, `transaction.analysis_failed`.
The scored risk describes the rolling batch, not an independently calibrated
probability for just the payment named by the event. Events are transient and
broadcast to connected clients; missed events cannot be replayed. Scores are
stored as signals, but financial-only alerts are not yet durable cases. React
has no stream subscriber yet. No cross-request ordering guarantee is provided.

## Graph API — port 8001

- `GET /health`, `GET /baseline`: readiness/reference-window information.
- `POST /baseline/train`: replace shared behavioural reference history; refresh
  specialist baseline and history. This does not train the TGNN.
- `POST /analyze`: transaction array to strict 0–1 `GraphSignal`.
- `POST /analyze-context`: transactions plus request-scoped baseline.
- `POST /visualize`: graph nodes and edges with suspicious markers.
- `POST /score-transaction`: specialist 0–100 scoring response.
- `GET /api/scenarios`, `POST /api/scenarios/{id}/run`: synthetic scenario demo;
  each run uses separate history.
- `POST /api/history/reset`: reset shared specialist history to its baseline.
- `GET /demo` or `/`: standalone specialist demonstration.

Batch risk uses seven weighted rules; TGNN can promote the result only when
rule risk >= 0.40. The bundled checkpoint is required at startup. The specialist
engine separately fuses rules, TGNN, mule and scam scores using experimental
weights. ALLOW/REVIEW/BLOCK are recommendations, with no payment enforcement.

Specialist history is per process and in memory. Individual history accesses
are locked, but the entire score operation is not a database transaction. Use a
single worker for demos; do not claim multi-worker consistency or restart
persistence. Graph demo HTML loads Cytoscape from a CDN and needs network access.

## Optional infrastructure API — port 8002

`GET /health`, `POST /analyze-events`, `POST /simulate` and
`GET /signals/latest` provide raw telemetry analysis and latest replay/live
system signals. Compose configures replay. Live collection requires the guarded
Linux setup in `services/ebpf-detector/SETUP_LINUX.md`.

Cross-domain confidence = 0.50 × graph risk + 0.35 × infrastructure risk + a
linkage bonus capped at 0.15. Shared IPs contribute 0.10; temporal proximity
within 15 minutes contributes up to 0.05. High/critical cases await approval.

## Configuration and failures

`ARGUS_DETECTOR_MODE=auto` enables service, last-known and fixture fallback for
the canonical demo; `fixture` forces that demo's fixtures; `required` rejects
unavailable detector services. Arbitrary batch and stream scoring never replace
caller transactions with demo fixture output. Batch detector failure returns
503; stream scoring failure is reported separately from ingestion success.
The UI displays detector origin instead of presenting fallbacks as live output.

The backend reads process environment variables, not `.env` files. Compose maps
its supported settings from the root `.env`; graph baseline and frontend build
settings must be configured on their respective processes/images.

## Verification

Run `python -m pytest -q`, frontend tests/build, then the service smoke commands
in the README. The full CI starts containers and tests real HTTP/WebSocket
boundaries. The verification report documents coverage and unverified behaviour;
[TODO.md](../TODO.md) tracks implementation work.

## Supplementary scam stream (Yojit PR #4)

Ingestion calls graph `/score-transaction-context` with the current payment and
its selected session window. The route creates isolated specialist history,
excludes future/other-currency context and returns zero risk for cancelled
payments. The legacy shared-memory demo route is retained separately.

Events are `transaction.scam_scored`, `scam_alert.created` and
`transaction.scam_scoring_failed`. Raw scores are 0–100; normalized fields are
0–1. `SCAM_ALERT_THRESHOLD` is 70/100 by default. Responses are checked against
the submitted payment and finite score bounds. Fixture mode cannot fabricate
specialist results. These events do not establish scam intent or execute bank
controls; broad false-positive limitations remain documented in tests.
