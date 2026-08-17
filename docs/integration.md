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
POST /analyze
```

`POST /analyze` accepts a JSON array of objects matching `transaction.schema.json` and returns one object matching `graph-signal.schema.json`.

## eBPF detector interface

Recommended service URL: `http://127.0.0.1:8002`.

```text
GET  /health
POST /simulate
GET  /signals/latest
```

`GET /signals/latest` returns one object matching `system-signal.schema.json`. Replay mode must return the same shape as live mode.

## ARGUS interface

Recommended service URL: `http://127.0.0.1:8000`.

```text
GET  /api/demo/normal
POST /api/demo/simulate-attack
POST /api/signals/correlate
POST /api/incidents/{incident_id}/approve
GET  /api/audit
```

The correlation request contains `graph_signal` and `system_signal`, populated using the matching schemas.

## Integration sequence

1. Pratyush demonstrates the complete flow using mock fixtures.
2. Pratham replaces only the mock `GraphSignal` producer.
3. Nitin replaces only the mock `SystemSignal` producer.
4. Run contract validation and correlation tests.
5. Verify shared IP and timestamp linkage appear in incident evidence.

## Failure handling

- If the graph service is unavailable, display `Graph detector unavailable` and retain the last known signal.
- If live eBPF is unavailable, visibly label the signal source as replay mode.
- Never fabricate a successful detector connection in the dashboard.
- Keep canonical fixtures available as a controlled fallback.
