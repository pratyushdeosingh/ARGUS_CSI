# Team start here

## Before anyone codes

- Accept the GitHub collaborator invitation.
- Clone the repository.
- Read the root README and integration contract.
- Confirm the canonical attack IDs.
- Switch to the assigned branch.
- Merge the latest `origin/main` into that branch.
- Confirm Python 3.11 is installed.

## Pratyush: first milestone

1. Run the existing FastAPI backend and tests.
2. Verify the mock attack returns a critical incident.
3. Scaffold the React dashboard in `frontend/`.
4. Connect normal and simulated-attack endpoints.
5. Render the incident, evidence, actions, and approval flow.

Success: the complete story works using mock detector signals.

## Pratham: first milestone

1. Load the normal and attack transaction fixtures.
2. Build graph nodes and edges.
3. Implement baseline anomaly features and a score.
4. Return the exact `GraphSignal` contract.
5. Prove attack score > normal score with tests.

Success: `POST /analyze` returns contract-valid results.

## Nitin: first milestone

1. Confirm an Ubuntu/Linux environment and kernel permissions.
2. Run a minimal eBPF process trace.
3. Create a harmless `payment-worker` simulation.
4. Map one observed event into the exact `SystemSignal` contract.
5. Store a sanitized replay fixture.

Success: ARGUS can receive the same contract from live and replay modes.

## Daily integration check

Spend 20 minutes each day confirming:

- every service starts;
- schemas still match;
- shared IDs are unchanged;
- ARGUS consumes both latest outputs; and
- the demo fallback remains functional.

Do not postpone the first integration attempt until the last day.
