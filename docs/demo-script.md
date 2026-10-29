# Fintech demo walkthrough

Follow [the submission guide](fintech-submission.md#presentation-sequence) for
the complete redesigned dashboard walkthrough, including financial-only Lab
analysis, live synthetic monitoring, graph inspection, stored cases and reports.

The financial.v1 batch/stream assessment, persisted analysis cases and React
workbench share one scoring contract. The standalone legacy specialist demo
uses a separate experimental 0–100 fusion and in-memory history; label it when
showing that interface. All bank response actions remain simulated.

## Optional CLI stream

With the graph and core services running, open a watcher terminal:

```powershell
python scripts/watch_transactions.py --url ws://127.0.0.1:8000/ws/transactions
```

Replay inputs with fresh run IDs in another terminal:

```powershell
python scripts/replay_transactions.py --input data/generated/normal.json --run-id normal-demo-01 --interval 0.2
python scripts/replay_transactions.py --input data/generated/mule.json --run-id mule-demo-01 --interval 0.2
```

The dashboard's synthetic run is session isolated. An independently replayed CLI
session does not appear as if it belonged to that active run. Persisted analysis
cases can be opened through Investigations; the watcher shows all stream events.

## Optional specialist and infrastructure demos

Open `http://127.0.0.1:8001/demo` and compare normal, mule, fan-out and burst
scenarios. Its graph library requires CDN access. Explain the detector breakdown
and the difference between a recommendation and a real payment control.

Use Canonical Demo to show infrastructure replay, correlated evidence and
analyst-approved simulated containment. Replaying a contained case preserves
its audit; resetting the display does not erase persisted history.

Close with the verification report and synthetic evaluation evidence. Remaining
research/production work is tracked in [TODO](../TODO.md); passing synthetic
checks does not establish representative fraud accuracy or regulatory compliance.
