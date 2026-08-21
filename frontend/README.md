# ARGUS dashboard — Pratyush

This React/Vite interface is the analyst-facing layer of ARGUS. It visualizes
the healthy baseline, staged attack timeline, transaction graph, detector
provenance, correlated incident, approval gate, and containment audit trail.

Required views on one main screen:

- system health and threat level;
- live attack timeline;
- transaction/mule graph;
- graph-detector evidence;
- eBPF evidence;
- correlated incident explanation;
- response recommendations and approval control; and
- containment audit log.

The dashboard should call the ARGUS backend on port `8000`. It must not call detector services directly; orchestration belongs in the backend.

## Included capabilities

The first working dashboard includes:

- healthy-state monitoring;
- staged account compromise and mule-transfer simulation;
- Cytoscape transaction graph;
- financial graph and eBPF risk panels;
- ARGUS correlation explanation;
- human containment approval; and
- response audit trail.

## Run locally

Start the backend from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload
```

In a second terminal:

```powershell
cd frontend
pnpm install
pnpm dev
```

Open `http://127.0.0.1:5173` and click **Simulate Attack**. The default backend URL is `http://127.0.0.1:8000`; override it with `VITE_API_BASE_URL` only when necessary.
