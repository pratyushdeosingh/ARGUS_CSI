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
