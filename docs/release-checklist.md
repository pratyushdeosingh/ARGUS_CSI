# ARGUS release checklist

Use this checklist before a demo, release, or merge to `main`.

## Automated verification

- Run `python -m pytest -q` from the repository root.
- Run `pnpm --dir frontend test`.
- Run `pnpm --dir frontend build`.
- Confirm GitHub Actions passes on the target commit.

## Integrated runtime

- Start the four-component stack with `docker compose up --build`.
- Confirm the dashboard opens at `http://127.0.0.1:5173`.
- Confirm both detector cards show a service origin; replay mode is expected for eBPF under Compose.
- Run `python -m backend.app.integration_check` when starting services manually.
- Trigger the canonical attack and confirm incident `INC-001` is critical.
- Approve containment and confirm exactly three simulated actions enter the audit log.

## Demo integrity

- Use only the synthetic fixtures under `data/`.
- Keep the canonical account, device, host, process, and IP identifiers unchanged.
- Never describe fixture or replay results as live telemetry.
- Never connect containment actions to a real account, service, or network control.
- Keep critical actions behind explicit analyst approval.

## Presentation readiness

- Reset the dashboard to the healthy state before presenting.
- Explain the shared IP and eight-second time linkage between the two signals.
- State that the graph detector is deterministic and explainable.
- State that eBPF replay makes the demo portable while the same contract supports live Linux collection.
- Close by showing the containment audit trail.
