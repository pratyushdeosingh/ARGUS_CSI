# Pratyush: backend, ML tooling and investigation delivery

Branch: `codex/pratyush-ml-regtech`, based on verified main `c1f9a1d`.
The baseline main CI passed before building; 14 core tests were also rerun
locally before edits. Yojit's newer scam branch was inspected but not modified
or merged by this work.

## Delivered scope

- A shared `financial.v1` contract for core batch/stream scoring. The graph
  `/assess-financial` endpoint reuses rules, TGNN, mule and scam components with
  independent request history. Inputs are chronological, currency-specific and
  bounded to 100 context payments per decision. Future baseline evidence is
  rejected for explicitly supplied history; future startup-baseline entries are
  excluded. Cancelled payments do not contribute risk.
- Per-payment normalized contributions, raw ML/scam values, used/withheld ML,
  reasons, suspicious account/transaction/edge references and loaded checkpoint/policy-source checksums. A bounded initial-node
  feature-ablation diagnostic is included when ML promotes risk. It holds
  graph and temporal inputs fixed and is labelled as a diagnostic, not SHAP
  or complete/causal attribution. ML requires independent behavioural corroboration. Baseline-scale
  payments to known payees with unchanged identity do not receive an elevated
  scam contribution solely for fan-out. This is a prototype policy to validate.
- Durable assessments and financial-only cases above the configured threshold,
  for batch and stream input, without requiring infrastructure telemetry.
  SQLite persistence and content-derived IDs make exact reanalysis idempotent.
  Overlapping windows can produce separate cases; no network-wide case merging
  policy is claimed.
- Data Lab defaults to financial-only analysis, exposes detector contributions,
  and displays the resulting financial case/graph. Optional infrastructure
  analysis and the existing canonical demo remain available. Live React stream
  subscription remains Yojit's work.
- Investigation assignment/status, revisioned append-only notes/history and
  snapshot draft JSON report export, with source payments, assessment/model
  provenance and action audit. Reports are `DRAFT_NOT_FILED`; identity is caller
  supplied and unauthenticated. No jurisdictional compliance or filing claim.
- Consistent immutable transaction-ID policy for batch/stream: identical input
  is accepted without regrouping, conflicting contents return 409. Approval and
  action-audit writes use one SQLite transaction, preventing duplicate approval
  across concurrent connections.
- Currency-specific metrics and UI labels; mixed-currency scalar total is null.
- Reproducible offline training CLI (experimental output + manifest), synthetic
  evaluation CLI, validation/test split generator, tested binary metrics and
  saved evaluation report. No bundled model was replaced or retrained.

## Core API additions

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/financial-assessments/{assessment_id}` | Retrieve persisted financial.v1 output |
| GET | `/api/incidents/{incident_id}/investigation` | Assignment, status, revision and history |
| PATCH | `/api/incidents/{incident_id}/investigation` | Save with `actor` and `expected_revision`; stale edits return 409 |
| GET | `/api/incidents/{incident_id}/report` | Draft JSON evidence report; no external submission |

`POST /api/analyze`, ingestion responses and scored WebSocket events now include
`financial_assessment`; qualifying cases include `case_type: financial`, a null
infrastructure signal ID, assessment reference and source transaction IDs.
Legacy GraphSignal endpoints and the legacy 0â€“100 specialist API remain intact.
Deploy the graph/core changes together; there is no silent fallback to the old
graph scoring contract for arbitrary input.

## Evaluation evidence

Run `python scripts/evaluate_financial.py`. The saved report at
[`reports/financial-evaluation.json`](../reports/financial-evaluation.json)
contains raw model/rules/fusion precision, recall, F1, average-precision PR-AUC,
false positives, segment results, thresholds and data/model/source fingerprints.

Each validation/test split contains 32 generated cases: normal, mule, scam and
legitimate payroll controls. Accounts, seeds and timestamps are disjoint. The
bundled model was previously trained on separate canonical normal/attack
fixtures. An earlier synthetic test seed exposed payroll false positives and
was used during policy development; the final synthetic seed was changed after
that correction. Both that development history and the final seeds are recorded.

The raw TGNN is not sufficient alone: at 0.70 it recalls half of this small
synthetic test's positives. Fusion recovers the generated scam cases through
independent heuristics. The report's perfect fused result on this narrow set is
not real-world accuracy, calibration or proof against broader false positives.
Representative labelled data and validated model attribution remain pending,
as agreed with the user. Policy thresholds are not automatically changed by the
evaluation script.

Offline training example:

```powershell
python scripts/train_tgnn.py --output artifacts/models/experiment.pt --epochs 60
```

The output manifest records seed, hyperparameters, dataset hashes and checkpoint
hash, and marks the output unevaluated/not deployed. Training fit is not an
acceptance test. The script refuses to overwrite the bundled inference
checkpoint. No production deployment is implied by the word "checkpoint".

## Verification and green-flag boundary

The branch must pass the complete Python suite, frontend tests/build, container
build/startup, real HTTP/WebSocket smoke, financial-only cases, investigation
conflicts/reporting, approval idempotency, restart persistence and detector
outage checks before merge. CI also runs and uploads synthetic evaluation.

Local real-service and browser checks cover financial-only Data Lab analysis,
the detector table, financial case creation, investigation assignment/status/
note, revision history and draft export. An isolated synthetic SQLite database
is used; no bank or external regulator is contacted.

A green flag applies only to the verified synthetic prototype scope above.
The full fintech submission still needs live React streaming, broader graph
analytics, recoverable scoring/event replay, independent real-data evaluation,
ML attribution, authenticated roles and load/concurrency testing. See TODO.md.
