# ARGUS React dashboard

React, TypeScript, Vite and Cytoscape interface for batch financial analysis and
the existing cross-domain investigation demo. It calls the core backend on port
8000, rather than calling detector services directly.

## Implemented

- Editable Data Lab transaction, baseline and telemetry inputs.
- Transaction/account graph, risk panels, rule evidence and detector provenance.
- Staged canonical demo, correlated cases and persisted case history.
- Analyst approval for simulated containment and action audit display.

## Missing

There is no WebSocket subscriber, live payment feed or specialist mule/scam
breakdown in this React app. The staged demo timeline is a presentation, not a
live payment stream. Use the CLI watcher and standalone graph demo for those
current capabilities. Financial-only cases and compliance reporting are also
pending. See [TODO](../TODO.md).

## Run

Install/start services using the root [README](../README.md), then:

```powershell
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev --host 127.0.0.1
```

Open [localhost:5173](http://127.0.0.1:5173). Use **DATA LAB** for custom batch
analysis and **CANONICAL DEMO** for the staged cross-domain scenario. Override
`VITE_API_BASE_URL` in the frontend environment before dev/build when necessary.

```powershell
pnpm --dir frontend test
pnpm --dir frontend build
```

Current tests cover API/helper behaviour and source labels, rather than a full
rendered browser workflow. Keyboard, layout, graph rendering and complete user
interaction checks remain part of the [release checklist](../docs/release-checklist.md).
