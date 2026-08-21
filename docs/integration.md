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
GET  /api/detectors/status
POST /api/signals/correlate
POST /api/incidents/{incident_id}/approve
GET  /api/audit
```

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

When both teammate services are running, validate the actual contracts with:

```powershell
python -m backend.app.integration_check
```

The command always uses required behavior, sends only the canonical synthetic
attack fixture, and exits non-zero if either service is unavailable or returns
an invalid contract.

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
- A fixture or last-known signal may keep the demo running, but its origin must remain visible.
