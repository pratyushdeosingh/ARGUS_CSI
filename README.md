# ARGUS — Financial Fraud Intelligence

ARGUS is a fintech assignment prototype for Problem Statement #9. It ingests
payments, detects suspicious money movement, streams explainable scores into an
analyst dashboard, and preserves investigation evidence and draft reports.
Yojit's live dashboard and matte-glass redesign are the submission interface.

All bundled data is synthetic. Payment holds and containment are simulated.
Scores describe detector risk, not calibrated fraud probabilities. Real-data
accuracy and regulatory compliance have not been established.

- [Submission guide and demo](docs/fintech-submission.md)
- [Deployment: Docker or Vercel frontend](docs/deployment.md)
- [Release verification](docs/verification.md)
- [API contracts](docs/integration.md)
- [Remaining work](TODO.md)

## Run the complete project

Install Git and Docker Desktop/Engine with Compose v2, then run:

```bash
git clone https://github.com/pratyushdeosingh/ARGUS_CSI.git
cd ARGUS_CSI
docker compose up --build -d --wait --wait-timeout 120
```

Open [the dashboard](http://127.0.0.1:5173). The frontend proxies API requests
and WebSockets to the backend, including when viewed from another machine.
Leave `VITE_API_BASE_URL` empty for this Docker setup.

| Service | Local interface |
| --- | --- |
| Dashboard | http://127.0.0.1:5173 |
| Core API documentation | http://127.0.0.1:8000/docs |
| Graph/model API documentation | http://127.0.0.1:8001/docs |
| Specialist scoring demo | http://127.0.0.1:8001/demo |
| Infrastructure replay API | http://127.0.0.1:8002/docs |

SQLite is stored in the `argus-runtime` Docker volume. `docker compose down`
preserves history; `down -v` deletes it. No separate database account is needed.
See [deployment instructions](docs/deployment.md) before hosting publicly.
Vercel can host `frontend/`; the Python services still need suitable compute
and persistent storage.

## Submission capabilities

| Requirement | Delivered behavior | Boundary |
| --- | --- | --- |
| Suspicious payment/customer behavior | Amount, velocity, device/IP, beneficiary and temporal flow evidence | Supplied payment history; no customer/KYC integration |
| Graph investigation | Account network, bounded selected-payment neighborhood, fan-in/out and forwarding evidence | Advanced communities/centrality/cycle investigation remains future work |
| Mule and scam detection | Unified `financial.v1` rules/TGNN/mule/scam contributions | Heuristics can flag legitimate activity; synthetic validation only |
| AI/ML | Bundled TGNN checkpoint, model/policy hashes, reproducible evaluation scripts | No independent representative real-data evaluation |
| Explainability | Rule reasons, detector contributions, references and bounded feature-ablation diagnostic | Diagnostic is not SHAP or validated causal attribution |
| Live dashboard | Ingestion, WebSocket updates, reconnect/history replay, filters, alerts and money-flow graph | Single core process; bounded retained UI/replay history |
| Durable cases | Financial-only analysis cases and connected stream investigation groups | Different admission policies, clearly identified in the interface |
| Investigation/reporting | Assignment, status, notes, revision history and draft JSON export on analysis cases | Caller-supplied analyst identity; no regulatory filing |
| Integrity | Duplicate/conflicting-ID handling, immutable batch writes, atomic simulated approval/audit | No real bank/payment controls |
| Evaluation | Independent synthetic validation/test namespaces, rules/model/fusion metrics | Does not establish real-world fraud accuracy |

## Five-minute demo

1. Start the stack and confirm detector health is 2/2.
2. Start a synthetic run. Observe received payments, detector results and alerts
   updating without refresh. Pause when enough evidence is present.
3. Inspect a flagged payment and its account graph. Read the rolling graph risk,
   supplementary scam score and the individual payment's unified contributions.
4. Open Investigations. Connected stream groups retain session/scenario context;
   financial analysis cases offer **Manage investigation / draft report**.
5. In Lab, run the clean control, then an account-takeover or fan-out starter.
   Infrastructure evidence is optional and off by default. Inspect the unified
   financial breakdown and resulting persisted case.
6. Assign the analysis case, save a note/status and download its draft JSON.
   Demonstrate a simulated approval and audit once on a fresh eligible case.
7. Refresh/reconnect or restart the core and reopen stored evidence. The
   Canonical Demo remains available for the optional infrastructure correlation.

## Run without Docker

Use Python 3.11/3.12, Node.js 22 and pnpm 11.22.0. From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r backend/requirements.txt -r services/graph-detector/requirements.txt -r services/ebpf-detector/requirements.txt
npm install --global pnpm@11.22.0
pnpm --dir frontend install --frozen-lockfile
```

Run each service in its own terminal with the environment activated:

```powershell
python -m uvicorn app:app --app-dir services/graph-detector --host 127.0.0.1 --port 8001
```

```powershell
$env:ARGUS_EBPF_MODE = "replay"
python -m uvicorn api:app --app-dir services/ebpf-detector --host 127.0.0.1 --port 8002
```

```powershell
$env:ARGUS_DETECTOR_MODE = "required"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
pnpm --dir frontend dev --host 127.0.0.1
```

On macOS/Linux use `python3`, `source .venv/bin/activate`, and `export NAME=value`.
Manual Python processes read exported environment variables, not a root `.env`
automatically. Vite reads `frontend/.env.local`. Keep the bundled checkpoint at
`services/graph-detector/tgnn_weights.pt`; startup never silently retrains it.

## API and scoring contracts

`POST /api/analyze` accepts 1–5,000 payments with optional earlier baseline
history and infrastructure evidence. It stores a versioned unified assessment,
graph signal and qualifying case. A financial case needs no host signal.

`POST /api/transactions?session_id=YOUR_RUN` stores one payment and scores a
bounded recent session window. New IDs return 201; identical duplicate delivery
returns 200; conflicting data returns 409; invalid data returns 422. Use explicit
session IDs. ID-prefix grouping is a legacy demo fallback.

WebSocket `/ws/transactions` emits received, scored, fraud/scam alert, failure
and investigation events. GET `/api/transaction-events?session_id=YOUR_RUN`
retrieves bounded persisted events after disconnection. Detector failure leaves
the accepted payment stored and displays analysis failure. Automatic background
retry after a detector outage is not implemented.

Unified assessment scores use 0–1, displayed out of 100. Supplementary specialist
scores use 0–100. The UI preserves the individual payment's unified combined
score when supplementary events arrive. The rolling graph column is window
risk. ML promotion requires independent behavioral risk of at least 0.40.
These policies are experimental, not calibrated fraud probabilities.

GET `/api/incidents` returns stored analysis cases; their `/investigation`
endpoint supports revision-checked PATCH updates, and `/report` returns a draft.
GET `/api/financial-investigations` returns connected stream evidence groups.
These groups require two connected completed payments with qualifying evidence
within 15 minutes and have no separate note/approval workflow. Stream analysis
also stores qualifying unified cases, which support the full case workbench.

## Verify

```powershell
python -m pytest -q
pnpm --dir frontend test
pnpm --dir frontend build
python scripts/evaluate_financial.py --output reports/financial-evaluation.json
```

Against an isolated running demo stack:

```powershell
python -m backend.app.integration_check
python scripts/check_integrated_stack.py --state-file smoke-state.json
# Docker dashboard: verifies the actual Nginx API and WebSocket proxy
python scripts/check_dashboard_proxy.py
```

CI also builds all containers, checks health, runs HTTP/WebSocket smoke checks,
restarts the core to verify persistence, and checks detector outage handling.
The smoke script writes synthetic data. See [verification](docs/verification.md)
for exact release evidence and [release checklist](docs/release-checklist.md).

## Configuration and layout

[.env.example](.env.example) documents defaults. Key settings are detector URLs,
`ARGUS_DETECTOR_MODE`, `ARGUS_DB_PATH`, `ARGUS_ALLOWED_ORIGINS`, fraud/scam
thresholds, analysis window size and `VITE_API_BASE_URL`. `required` mode exposes
detector outages; fixture modes never invent scores for arbitrary caller data.

```text
backend/                    FastAPI, SQLite, events, case policy and investigations
services/graph-detector/     Graph rules, TGNN, mule/scam engines and specialist demo
services/ebpf-detector/      Optional infrastructure replay / guarded Linux collector
frontend/                   Yojit's live React dashboard, graphs and analyst tools
contracts/                  Versioned data/financial response schemas
evaluation/                 Synthetic datasets and metric helpers
scripts/                    Replay, watcher, training, evaluation and smoke checks
reports/                    Synthetic evaluation evidence
docs/                       Submission, deployment, architecture and verification
```

Team: Pratyush (orchestration, unified scoring and investigations), Pratham
(graph/TGNN and specialist analytics), Yojit (live dashboard, stream/scam
integration and redesign). Nitin contributed infrastructure detection.

This submission demonstrates a synthetic fintech workflow. Authenticated roles,
production payment integration, automatic scoring retries, multi-process event
distribution, advanced graph analytics and representative real-data evaluation
remain outside its verified scope. The original official rubric was not supplied;
[the submission guide](docs/fintech-submission.md) maps the team's supplied scope.
