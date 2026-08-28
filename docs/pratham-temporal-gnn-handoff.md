# ARGUS_CSI Project Handoff for ChatGPT

## Paste-ready context

I am going to a hackathon tomorrow. The project repo is named `ARGUS_CSI`.
My teammate has already made progress across the whole project: eBPF telemetry,
financial graph detection, backend integration, and frontend dashboard.

My assigned responsibility is the **Temporal Graph Neural Networks / temporal
graph intelligence** part of ARGUS. I need ChatGPT to guide me on what to work
on next, how to improve my part quickly, and how to explain it during the
hackathon.

## What ARGUS_CSI is

ARGUS is a synthetic Financial SOC prototype for detecting coordinated financial
attacks. It does not only look at transactions or infrastructure events in
isolation. It correlates:

- suspicious money movement in a transaction graph
- suspicious infrastructure behavior from eBPF-style host telemetry
- shared evidence such as related IP addresses and close timestamps
- a policy layer that recommends simulated containment actions

The core story is:

1. A fraud-like transaction pattern appears, such as account takeover, unusual
   transfer size, new beneficiaries, velocity, fan-out, or multi-hop mule
   movement.
2. At the same time, the payment infrastructure shows suspicious process, file,
   or network behavior.
3. ARGUS correlates the graph signal and system signal into one incident.
4. The dashboard shows explainable evidence and asks for analyst approval before
   simulated high-impact containment actions.

All data is synthetic. Response actions are simulated.

## Repo structure

Important paths:

- `README.md`: main project explanation, architecture, quick start, APIs
- `docs/architecture.md`: high-level system design
- `docs/integration.md`: service contracts and integration sequence
- `docs/demo-script.md`: hackathon demo flow
- `contracts/`: JSON schemas for transactions, graph signals, system signals,
  and incidents
- `services/graph-detector/`: my main area, the temporal graph detector
- `services/ebpf-detector/`: teammate's infrastructure/eBPF detector
- `backend/`: FastAPI orchestration, correlation, persistence, approval policy
- `frontend/`: React dashboard and Data Lab

## My area: temporal graph intelligence

My service is `services/graph-detector`.

It exposes a FastAPI service on port `8001` with endpoints:

- `GET /health`
- `GET /baseline`
- `POST /baseline/train`
- `POST /analyze`
- `POST /analyze-context`
- `POST /visualize`

The graph detector accepts transaction JSON matching
`contracts/transaction.schema.json` and returns a `GraphSignal` matching
`contracts/graph-signal.schema.json`.

Current implementation files:

- `services/graph-detector/app.py`: FastAPI entry point
- `services/graph-detector/graph_models.py`: strict Pydantic models
- `services/graph-detector/graph_builder.py`: NetworkX transaction graph and
  temporal path search
- `services/graph-detector/features.py`: feature extraction and evidence
- `services/graph-detector/detector.py`: risk scoring and `GraphSignal`
  generation
- `services/graph-detector/visualization.py`: Cytoscape graph output for the UI
- `services/graph-detector/tests/`: unit, API, schema, integration, and
  detector tests

## Current graph detector behavior

The current production path is an explainable temporal graph/rules detector,
not a trained neural network yet. It uses NetworkX and deterministic feature
engineering.

It detects seven features:

- `identity_change`: established account uses a new device or IP
- `unusual_amount`: transfer amount is at least 5x the baseline median
- `new_beneficiary`: source account pays a destination absent from baseline
- `velocity`: account participates in linked transfers within two minutes
- `rapid_multi_hop`: funds move through 2-4 time-respecting transfers
- `funds_forwarded`: recipient quickly forwards 50%-125% of received funds
- `fan_in_out`: account has at least three incoming or outgoing batch transfers

Only non-cancelled transfers count. Temporal paths cannot move backward in
time, mix currencies, revisit accounts, or report shorter subpaths when a
longer flow explains the same movement.

Feature weights in `services/graph-detector/detector.py`:

- rapid multi-hop: `0.30`
- funds forwarded: `0.18`
- unusual amount: `0.17`
- identity change: `0.10`
- velocity: `0.10`
- new beneficiary: `0.08`
- fan-in/fan-out: `0.07`

The detector adds a small corroboration bonus when multiple independent
features fire. The result includes:

- `signal_id`
- `timestamp`
- `risk_score`
- `anomaly_type`
- `suspicious_accounts`
- `suspicious_transactions`
- `related_ips`
- human-readable `reasons`

For the canonical attack fixture, the graph detector should produce high risk
and identify accounts like `ACC-101`, `ACC-202`, `ACC-303`, `ACC-404` and
transactions like `TX-1001..TX-1003`.

## How it integrates with the rest of ARGUS

The ARGUS backend calls the graph detector and receives a `GraphSignal`.
The eBPF detector produces a `SystemSignal`.

The backend correlation formula is:

```text
confidence = 0.50 * graph_risk
           + 0.35 * infrastructure_risk
           + up to 0.15 shared-evidence bonus
```

The shared-evidence bonus comes from shared IPs and signal timestamps inside a
15-minute window. High and critical incidents can recommend simulated actions
such as account freeze, transfer cancellation, or service isolation, but they
require human approval.

## What I need help with next

Please guide me as the person responsible for the Temporal GNN / graph
intelligence part. I need a practical plan for tomorrow's hackathon.

Focus on:

1. How to evaluate the current graph detector quickly and confirm it works.
2. Whether I should implement an actual lightweight Temporal GNN, a TGNN-like
   embedding/risk module, or keep the deterministic temporal graph detector and
   present it as explainable temporal graph intelligence.
3. If implementing a lightweight TGNN is realistic, propose the fastest safe
   approach that fits this repo.
4. What files I should modify first.
5. What tests I should add or run.
6. How to explain my contribution in the demo.
7. What minimum improvements would have the highest hackathon impact.

Constraints:

- The hackathon is tomorrow, so prioritize working, demo-ready changes.
- Do not break the existing contracts in `contracts/`.
- The graph detector must still return the same `GraphSignal` shape.
- The frontend/backend integration should keep working.
- Explanations are important; the judges should understand why a transaction
  pattern is suspicious.
- The project is synthetic and safe; no real financial accounts or production
  infrastructure should be touched.

## Useful commands

Run graph detector tests:

```bash
python -m pytest services/graph-detector/tests -q
```

Run all backend and detector tests:

```bash
python -m pytest backend/tests services/graph-detector/tests services/ebpf-detector/tests -q
```

Start the graph detector locally:

```bash
python -m uvicorn app:app --app-dir services/graph-detector --host 127.0.0.1 --port 8001 --reload
```

Start the whole stack with Docker:

```bash
docker compose up --build
```

Then open:

- Dashboard: `http://127.0.0.1:5173`
- ARGUS backend docs: `http://127.0.0.1:8000/docs`
- Graph detector docs: `http://127.0.0.1:8001/docs`
- eBPF detector docs: `http://127.0.0.1:8002/docs`

## Suggested immediate priorities

If there is limited time, I should probably do these in order:

1. Run the graph detector test suite and fix any failures.
2. Verify the canonical attack and normal fixtures produce clearly separated
   risk scores.
3. Add one visible improvement to the graph detector, such as clearer evidence,
   better visualization metadata, or a small temporal embedding/risk module
   that does not break the API.
4. Update the README or graph detector README to honestly describe whether this
   is a true TGNN model or explainable temporal graph detection.
5. Prepare a 45-60 second explanation of my component for the demo.

## Demo explanation for my part

My contribution is the temporal graph intelligence service. It takes a batch of
transactions and builds a directed account graph where edges are money
movements over time. It compares current behavior to a baseline and extracts
temporal graph evidence: new devices, unusual amounts, new beneficiaries,
velocity, fan-out, forwarded funds, and rapid multi-hop paths. It then produces
a strict `GraphSignal` with a risk score, suspicious accounts, suspicious
transactions, related IPs, and natural-language reasons. ARGUS correlates that
signal with infrastructure telemetry to decide whether the case is just a
financial anomaly or a coordinated attack involving the payment system.

The important design choice is explainability. Even if I add a lightweight TGNN
or embedding layer, the service should still show the temporal paths and
features that caused the score so judges can understand the detection.
