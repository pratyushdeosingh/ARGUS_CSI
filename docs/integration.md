# Integration contract

## Rules

1. The schemas in `contracts/` are authoritative.
2. Use JSON and UTF-8 over HTTP.
3. Use UTC ISO-8601 timestamps ending in `Z`.
4. Scores are floating-point values from `0.0` to `1.0`.
5. Detector explanations must cite observable evidence.
6. Unknown additional fields are rejected by the initial backend models.
7. Coordinate contract changes in a pull request before merging.

## Graph detector interface

Recommended service URL: `http://127.0.0.1:8001`.

```text
GET  /health
GET  /baseline
POST /baseline/train
POST /analyze
POST /analyze-context
```

`POST /analyze` accepts a JSON array of objects matching `transaction.schema.json` and returns one object matching `graph-signal.schema.json`.
`POST /baseline/train` atomically replaces the detector's behavioral reference window with caller-supplied transactions. The next analysis is evaluated against that new baseline.
`POST /analyze-context` evaluates transactions against a request-scoped baseline without changing shared detector state; ARGUS uses this atomic path for `/api/analyze` so concurrent analysts cannot contaminate one another's behavioral context.

## eBPF detector interface

Recommended service URL: `http://127.0.0.1:8002`.

```text
GET  /health
POST /analyze-events
POST /simulate
GET  /signals/latest
```

`GET /signals/latest` returns one object matching `system-signal.schema.json`. Replay mode must return the same shape as live mode.
`POST /analyze-events` accepts raw process, file, and network observations plus caller-selected host/service metadata. It normalizes and scores those events without substituting the canonical replay fixture.

## ARGUS interface

Recommended service URL: `http://127.0.0.1:8000`.

```text
GET  /api/demo/normal
POST /api/demo/simulate-attack
GET  /api/detectors/status
POST /api/analyze
POST /api/signals/correlate
GET  /api/platform/metrics
GET  /api/incidents
GET  /api/incidents/{incident_id}
POST /api/incidents/{incident_id}/approve
GET  /api/audit
```

`POST /api/analyze` is the primary non-demo path. It accepts arbitrary transactions and optional `baseline_transactions`, `telemetry_events`, a contract-valid `system_signal`, or a request to correlate with the latest system signal. A batch can complete as graph-only analysis when no infrastructure evidence is supplied. Caller data is never replaced by a fixture.

The correlation request contains `graph_signal` and `system_signal`, populated using the matching schemas.

`POST /api/demo/simulate-attack` calls both detector services concurrently and
returns `detector_status` alongside the signals. Status metadata is owned by
ARGUS and does not change either shared detector schema. It reports service
availability, whether the selected signal came from a service, last-known
cache, or fixture, and live/replay mode when the eBPF service supplies it.

## Runtime modes

Configure ARGUS with environment variables from `.env.example`:

- `ARGUS_DETECTOR_MODE=auto` prefers services, then last-known signals, then fixtures.
- `ARGUS_DETECTOR_MODE=fixture` provides the deterministic offline demo.
- `ARGUS_DETECTOR_MODE=required` returns `503` rather than hiding an integration failure.
- `GRAPH_DETECTOR_URL`, `EBPF_DETECTOR_URL`, and `DETECTOR_TIMEOUT_SECONDS` control connectivity.
- `ARGUS_DB_PATH` selects the SQLite case-history database. Docker uses a named persistent volume.

When both teammate services are running, validate the actual contracts with:

```powershell
python -m backend.app.integration_check
```

The command always uses required behavior and exits non-zero if either service is unavailable or returns an invalid contract. The canonical fixture remains useful as a deterministic integration probe; `/api/analyze` and the dashboard Data Lab prove arbitrary-data behavior.

## Integration sequence

1. The dashboard or API submits transactions, an optional baseline, and optional telemetry.
2. ARGUS retrains Pratham's graph reference window when a baseline is supplied, then requests a fresh `GraphSignal`.
3. Nitin's service analyzes caller telemetry or supplies its latest replay/live `SystemSignal`.
4. ARGUS correlates independent evidence, derives a content-addressed incident, and persists the complete case.
5. Low-risk cases remain monitored. High-impact response actions remain pending until explicit analyst approval.
6. Approval results are persisted in the audit trail and reflected in platform metrics and history.

## Failure handling

- If the graph service is unavailable, display `Graph detector unavailable` and retain the last known signal.
- If live eBPF is unavailable, visibly label the signal source as replay mode.
- Never fabricate a successful detector connection in the dashboard.
- Keep canonical fixtures available as a controlled fallback.
- A fixture or last-known signal may keep the demo running, but its origin must remain visible.
