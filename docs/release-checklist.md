# Fintech release checklist

This is a repeatable verification checklist, not a claim that unchecked fintech
features exist. Implementation work and owners are in [TODO](../TODO.md).

## Automated checks

- [ ] Run the complete Python suite in a supported environment.
- [ ] Run frontend tests and production build.
- [ ] Confirm CI passes on the exact PR head being merged.
- [ ] Confirm all containers build and health checks pass.
- [ ] Run actual HTTP/WebSocket smoke checks, including invalid/conflicting
  payment rejection, all specialist scenarios and graph-only response shape.
- [ ] Verify payment, contained case and audit persistence after backend restart.
- [ ] Verify batch detector failure is visible and ingestion persists with a
  streamed analysis-failed event during a graph outage.

## Manual interface checks

- [ ] Open React, run clean and suspicious Data Lab inputs, and inspect graph,
  evidence, errors, provenance and history.
- [ ] Open the standalone graph demo and inspect each scenario and score scale.
- [ ] Run watcher and replay scripts using fresh run IDs.
- [ ] Demonstrate simulated approval once on a fresh case and verify repeat
  approval is rejected; reanalysis must preserve containment and its audit.
- [ ] Check keyboard use and narrow-screen layout. These interactions are not
  covered by the existing frontend helper tests or the HTTP smoke script.

## Submission accuracy

- [ ] Match the final competition rubric against the team's requirement list.
- [ ] Update README coverage only for demonstrated capabilities.
- [ ] Label synthetic data, replay telemetry, simulated actions and model limits.
- [ ] Keep 0–1 graph scores separate from 0–100 specialist scores.
- [ ] Distinguish delivered financial cases and prototype draft reporting
  from unfinished live React streaming, real-data accuracy, authenticated
  compliance operation and complete ML attribution. Initial-feature ablation
  diagnostics are not SHAP or causal explanations.
- [ ] Record tested commit, CI link, manual-check results and remaining gaps in
  the verification report.

## Runtime hygiene

- [ ] Use an isolated synthetic/demo database for smoke checks.
- [ ] Confirm `.env` is exported for manual processes or mapped by Compose.
- [ ] Keep runtime databases and local test artifacts out of image build context.
- [ ] Preserve the named database volume when stopping a demo. Use `down -v`
  only when intentionally deleting its stored history.
