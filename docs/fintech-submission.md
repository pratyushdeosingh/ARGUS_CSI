# Fintech submission guide

Release date: 29 October 2026 (Asia/Kolkata). ARGUS demonstrates the team's
Problem Statement #9 scope with synthetic payments. The original official
assignment rubric was not supplied; confirm any required report/video format
with the course instructions before submitting.

## What to submit

- Repository main branch after the final integration CI passes.
- This guide, the README and the verification report.
- `reports/financial-evaluation.json` as reproducible **synthetic engineering**
  evidence; it must not be presented as real-world fraud accuracy.
- A running local Docker demo or a reviewer-accessible deployment following
  [deployment.md](deployment.md). Hosting is optional unless the course asks.

## Presentation sequence

1. Explain the flow: payment → graph/model/specialists → durable score/case →
   live dashboard → analyst investigation and draft report.
2. Start Docker Compose as described in the README. Open port 5173 and verify
   both detectors are healthy. The infrastructure service uses replay mode.
3. In Lab, select **Clean control batch**, leave infrastructure unchecked and
   run financial analysis. Show that below-threshold scoring creates no
   high-risk financial case.
4. Select **Adaptive account takeover** or **Structuring fan-out**, run analysis,
   and inspect reasons, payment contributions, checkpoint provenance and case.
5. Open Investigations and select the **Financial analysis** case. Open its
   payment context/graph, then **Manage investigation / draft report**. Assign
   an analyst, set investigating, add a note and save. Download draft JSON.
6. For an eligible pending case, approve the simulated response and inspect
   its audit. A repeat approval is rejected; stored state survives reanalysis.
7. Run a synthetic stream from Overview or Demo. Inspect live rows and alerts,
   pause, and open a flagged payment. Combined is the selected payment's unified
   score; Graph is window risk; supplementary specialist scores use 0–100.
8. Show a connected **Financial-only** stream investigation group. These groups
   aggregate related evidence; full notes/reporting belong to analysis cases.
9. Reload or restart the core and reopen history. Demonstrate Canonical Demo
   separately if optional infrastructure correlation is relevant.

## Architecture and evidence

The FastAPI core persists immutable payment IDs, assessments, replay events,
analysis cases, stream groups, investigation revisions and simulated action
audits in SQLite. The graph service combines financial rules, a bundled TGNN,
mule forwarding and scam heuristics in the `financial.v1` contract. ML promotion
needs independent behavioral risk >= 0.40. React subscribes to WebSockets and
loads persisted session context on reconnect. Docker Nginx proxies API and
WebSocket traffic under the dashboard's origin.

Financial-only analysis cases require the configured unified risk threshold.
Connected stream groups have a separate policy: two connected completed
payments with qualifying detector evidence in one session within 15 minutes.
Neither policy constitutes a determination of fraud or regulatory compliance.

## Evaluation statement

The evaluation script separates synthetic validation and test namespaces/seeds,
compares rules, raw TGNN and fusion, and records precision/recall/F1/PR-AUC,
false-positive rate and source/model fingerprints. The final synthetic fused
result is useful for regression checks, not a claim of representative accuracy.
Feature ablation is a bounded diagnostic, not SHAP or causal attribution.

## Known boundaries for the viva/report

No real bank feed or payment controls; all accounts are synthetic and response
actions are simulated. No authenticated analyst roles, representative real-data
validation, automatic retry worker, cross-process event broker, or full advanced
graph/community investigation. Accepted payments remain stored on detector
failure, with a visible failure event; failed scoring needs explicit operational
recovery. Do not describe the prototype as a production fraud prevention system.

Team: Pratyush (backend/scoring/investigation), Pratham (graph/TGNN/specialists),
Yojit (live dashboard/scam integration/redesign); Nitin contributed optional
infrastructure detection. See [verification](verification.md) and
[release checklist](release-checklist.md) for the release gate.
