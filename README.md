# ARGUS — Autonomous Financial Threat Response

ARGUS is a hackathon prototype of a **Financial Security Operations Center (Financial SOC)**. It detects a coordinated attack by combining abnormal movement of money through a financial graph with suspicious behavior inside payment infrastructure.

ARGUS correlates both signals, explains the incident, recommends containment, and requires a human analyst to approve critical simulated actions.

> This project uses synthetic data and simulated response actions. It is not a real banking system and must not be connected to real financial accounts.

## The demo in one minute

1. The dashboard begins in a healthy state.
2. The operator clicks **Simulate Attack**.
3. `ACC-101` logs in using new device `DEV-99` and suspicious IP `185.220.101.10`.
4. Money moves rapidly through `ACC-202`, `ACC-303`, and `ACC-404`.
5. Pratham's graph detector reports suspicious multi-hop fund movement.
6. Nitin's eBPF detector reports suspicious payment-service behavior involving the same IP and time window.
7. Pratyush's ARGUS core correlates both signals into one critical incident.
8. A human analyst approves the simulated containment actions.

## Architecture

```text
Synthetic transaction stream
          |
          v
Pratham: graph detector -----------\
                                    \
                                     > Pratyush: ARGUS orchestration
                                    /    correlation + explanation
Nitin: eBPF detector --------------/     policy + human approval
                                              |
                                              v
                                      React SOC dashboard
```

The components are developed separately only after agreeing on their interfaces. They communicate with JSON over HTTP. The files in [`contracts/`](contracts/) are the source of truth.

## Team ownership

| Member | Branch | Owned paths | Deliverable |
|---|---|---|---|
| Pratyush (`pratyushdeosingh`) | `pratyush/orchestration-dashboard` | `backend/app/`, `frontend/`, `docs/` | Simulator, correlation, policy, dashboard, integration |
| Pratham (`Prathamw007`) | `pratham/graph-detector` | `services/graph-detector/` | Transactions in; financial risk and suspicious graph entities out |
| Nitin (`nitinXjoshi`) | `nitin/ebpf-telemetry` | `services/ebpf-detector/` | Linux activity in; infrastructure risk and indicators out |

Do not change a shared contract silently. Open a pull request and coordinate the change with all three members.

## Canonical identifiers

All components must use these identifiers in the main demo:

| Entity | Identifier |
|---|---|
| Compromised account | `ACC-101` |
| Mule accounts | `ACC-202`, `ACC-303`, `ACC-404` |
| New attacker device | `DEV-99` |
| Suspicious shared IP | `185.220.101.10` |
| Payment host | `payment-node-01` |
| Payment service | `payment-api` |
| Payment process | `payment-worker` |

## Repository layout

```text
backend/                    ARGUS FastAPI orchestration service
  app/                      Models, simulator, correlation, policy, API
  tests/                    Backend tests
contracts/                  Stable JSON interfaces between components
data/normal/                Canonical healthy demo data
data/attack/                Canonical attack data and mock detector signals
docs/                       Architecture, integration, and demo guidance
frontend/                   Pratyush's React SOC dashboard
services/graph-detector/    Pratham's financial graph detector
services/ebpf-detector/     Nitin's Linux/eBPF detector
```

## Start the existing backend

Python 3.11 is recommended.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload
```

### macOS/Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to test the API.

Important endpoints:

- `GET /health`
- `GET /api/demo/normal`
- `POST /api/demo/simulate-attack`
- `POST /api/signals/correlate`
- `POST /api/incidents/INC-001/approve`
- `GET /api/audit`

Run tests from the repository root:

```bash
python -m pytest backend/tests
```

## Git workflow

After accepting the collaborator invitation:

```bash
git clone https://github.com/pratyushdeosingh/ARGUS_CSI.git
cd ARGUS_CSI
git fetch origin
```

Switch to your assigned branch and merge the shared foundation:

```bash
git switch pratham/graph-detector
# Alternatives: pratyush/orchestration-dashboard or nitin/ebpf-telemetry
git merge origin/main
```

Use small commits, push only to your assigned branch, and open a pull request into `main` when a working milestone is ready.

## Instructions for Pratyush's AI

Copy this prompt into the AI used for the orchestration/dashboard work:

```text
You are helping me build ARGUS, a hackathon Financial SOC prototype. I am
Pratyush and own orchestration, correlation, policy, human approval, dashboard,
and final integration. Work only on branch pratyush/orchestration-dashboard.

Read README.md, every file in contracts/, docs/architecture.md,
docs/integration.md, and the existing backend/app code before changing files.
The shared demo identifiers and JSON field names must remain unchanged.

My goal is a dark professional React SOC dashboard connected to the FastAPI
backend. The flow is normal state -> Simulate Attack -> graph signal -> eBPF
signal -> correlated incident -> explanation -> analyst approval -> simulated
containment audit log. Build against mock signals first, then replace them with
real detector HTTP responses without changing the dashboard's incident model.
Do not require a paid AI API. Keep critical response actions behind human
approval. Add tests for correlation and policy behavior. Avoid editing detector
services unless integration requires a coordinated contract change.
```

## Instructions for Pratham's AI

Copy this prompt into the AI used for graph/ML work:

```text
You are helping me build the financial graph detector for ARGUS, a hackathon
Financial SOC prototype. I am Pratham. Work only on branch
pratham/graph-detector and primarily inside services/graph-detector/.

Read README.md, contracts/transaction.schema.json,
contracts/graph-signal.schema.json, data/normal/transactions.json,
data/attack/transactions.json, and docs/integration.md before coding. Do not
change shared identifiers or the output contract without team agreement.

Build a Python service whose core behavior is:
transactions -> temporal/graph analysis -> GraphSignal.
Start with a reliable NetworkX/pandas baseline using new device/IP, unusual
amount, new beneficiary, transaction velocity, rapid multi-hop movement,
fan-in/fan-out, and short time windows. Return a 0..1 risk score, suspicious
account IDs, suspicious transaction IDs, related IPs, and human-readable
reasons exactly matching contracts/graph-signal.schema.json. Expose GET /health
and POST /analyze using FastAPI. Add tests proving the normal fixture scores
lower than the attack fixture. After the baseline works, add a lightweight
temporal GNN or GraphSAGE experiment if time permits; keep the baseline as a
fallback. Provide graph nodes/edges for Cytoscape and document integration.
```

Full instructions: [`services/graph-detector/README.md`](services/graph-detector/README.md).

## Instructions for Nitin's AI

Copy this prompt into the AI used for eBPF/security work:

```text
You are helping me build the infrastructure detector for ARGUS, a hackathon
Financial SOC prototype. I am Nitin. Work only on branch nitin/ebpf-telemetry
and primarily inside services/ebpf-detector/.

Read README.md, contracts/system-signal.schema.json,
data/attack/mock-system-signal.json, and docs/integration.md before coding. eBPF
requires a Linux kernel; my Mac must use an Ubuntu VM, Linux cloud machine, or
another verified Linux environment. Confirm the environment first.

Use bpftrace, BCC, or libbpf to observe a harmless simulated payment service.
Capture process execution, sensitive-file access, and outbound network
connections. Convert raw telemetry into a 0..1 risk score and a SystemSignal
that exactly matches contracts/system-signal.schema.json. Use canonical host
payment-node-01, service payment-api, process payment-worker, and shared IP
185.220.101.10. Expose GET /health and either POST /simulate plus GET
/signals/latest, or push the signal to ARGUS. Save sanitized recorded real
telemetry and implement replay mode so the demo works if kernel permissions
fail. Include setup, commands, safety notes, and signal-conversion tests. Never
perform destructive actions or access real secrets.
```

Full instructions: [`services/ebpf-detector/README.md`](services/ebpf-detector/README.md).

## Definition of done

The prototype is complete when:

- normal activity does not generate a critical incident;
- the canonical attack creates a high graph risk score;
- real or replayed eBPF telemetry creates a high infrastructure risk score;
- both findings correlate into one critical ARGUS incident;
- the dashboard explains the shared evidence;
- containment requires human approval and records an audit trail; and
- the complete demo runs locally from documented setup.

See [`docs/team-start-here.md`](docs/team-start-here.md) for the immediate team checklist.

## Current implementation status

- Shared contracts and canonical fixtures: complete
- ARGUS FastAPI mock orchestration: complete
- Correlation and human-approval flow: complete
- Pratyush SOC dashboard milestone: complete on `pratyush/orchestration-dashboard`
- Pratham graph detector: assigned/in progress
- Nitin eBPF detector: assigned/in progress
