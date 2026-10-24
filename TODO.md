# ARGUS fintech TODO

Working checklist for the team's Problem Statement #9 requirements. Check an
item only after its acceptance criteria pass. Owners coordinate changes through
reviewed PRs; do not independently change shared score contracts.

## Working foundation

- [x] Batch graph analysis with supplied behavioural baseline and rule evidence.
- [x] TGNN checkpoint loading and corroboration guard for batch risk promotion.
- [x] Specialist mule/scam scoring API and synthetic scenario demo.
- [x] Durable single-payment ingestion with duplicate/conflict handling.
- [x] Rolling graph scoring and transaction/score/alert/failure WebSocket events.
- [x] React batch Data Lab, account graph and cross-domain case history.
- [x] Simulated analyst approval and stored action audit trail.
- [x] Automated unit/build/container/service checks in CI.

## Pratyush delivery notes

The current backend delivery implements unified financial.v1 scoring, durable
financial-only cases, Data Lab breakdowns, investigation/revision history and
draft reports, immutable payment ingestion, atomic approval/audit, and separate
currency totals. See [delivery evidence](docs/pratyush-delivery.md).

Synthetic evaluation/training tooling and checkpoint provenance are implemented.
P0-4 remains open for approved representative real data, as requested by the
user. P1-4 has checkpoint/policy provenance and a tested initial-feature ablation
diagnostic; complete validated ML attribution remains pending. P0-3 is still Yojit's live
React work; P0-5 still needs durable event replay and failed-analysis recovery.
New request-scoped assessment history avoids the legacy engine's shared-state
problem, but P1-6 remains open for the legacy endpoint and production concurrency.
Completed checkboxes refer to the documented synthetic prototype scope.

## P0 — complete the financial fraud workflow

- [x] **P0-1: Unify core and specialist scoring — all three; Pratyush coordinates.**
  Define one versioned response containing transaction ID, 0–1 combined risk,
  detector contributions, reasons, suspicious nodes/edges and model provenance.
  Convert specialist 0–100 values once at the boundary. Batch and stream paths
  must use the agreed fusion, including a documented policy for unsupported ML
  predictions. Accept when the same controlled scenario reaches API, stored
  result and UI with consistent scores and no hidden fixture substitution.

- [x] **P0-2: Create financial-only cases — Pratyush.**
  Persist a qualifying fraud case from batch or streamed payments without a
  system signal. Keep infrastructure evidence optional. Accept when a mule
  stream creates a case visible in history after restart, a clean control does
  not create a high-risk case, repeat delivery does not duplicate cases/actions,
  and approval preserves its audit trail.

- [ ] **P0-3: Connect the live React workflow — Yojit.**
  Subscribe to WebSocket received/scored/alert/failure events, display scores and
  evidence, highlight affected accounts, and show disconnected/reconnecting
  state. Accept when replay updates the screen without refresh, reconnect loads
  persisted history, duplicate events do not duplicate rows and failures are
  visible. Add browser-level tests; current frontend tests cover helpers/API
  behaviour rather than complete rendered interaction.

- [ ] **P0-4: Evaluate ML independently — Pratyush.**
  Choose a dataset with documented provenance, licence and labels; separate
  training, validation and held-out evaluation without customer/time leakage.
  Publish precision, recall, F1, PR-AUC, false positives, thresholds and a rules
  baseline, including performance by relevant payment segment. Accept when
  results are reproducible from committed scripts and a model/data manifest.
  Fixture training and scenario assertions do not satisfy this item.

- [ ] **P0-5: Make scoring and alert delivery recoverable — Yojit + Pratyush.**
  Store pending/scored/failed analysis status, durable alert IDs and retry state;
  separate ingestion acknowledgement from scoring outcome. Define event/session
  grouping explicitly rather than deriving production context from ID prefixes.
  Accept when a detector outage followed by recovery scores each accepted
  payment, missed alerts can be retrieved, and retries preserve idempotency.

## P1 — complete the problem-statement capabilities

- [ ] **P1-1: Advanced graph investigation — Pratham.**
  Add time/currency-aware cycle detection, suspicious communities, centrality
  features and coordinated mule-group output. Return nodes, edges, transaction
  IDs and observable evidence. Validate positive and clean counterexamples,
  including cancelled transfers and mixed currencies. Bound expensive graph
  searches and document limits.

- [ ] **P1-2: Validate dedicated scam detection — Yojit + Pratham.**
  Define supported scam hypotheses and the data needed to distinguish them from
  legitimate fan-out, payroll, refunds and merchant settlement. Add positive and
  negative labelled scenarios. Accept when integrated scam evidence reaches a
  financial case and false-positive examples are documented.

- [x] **P1-3: Investigation and draft reporting — Pratyush.**
  Add assignment, investigation status, notes, evidence references and draft
  suspicious activity report export. Retain reviewer identity and revision
  history. Accept when a case can be investigated and exported with source
  transaction references. Label output as a draft; do not claim regulatory
  filing, jurisdictional compliance or automatic submission.

- [ ] **P1-4: ML explanation and provenance — Pratyush + Pratham.**
  Record model version, training-data reference, feature schema and explanation
  method. Separate rule evidence from model attribution. Accept when a saved
  score can be reproduced and its top model factors explained using an
  appropriate tested attribution method. Node rankings alone are insufficient.

- [x] **P1-5: Preserve ledger and approval integrity — Pratyush.**
  Define transaction revision rules across batch and stream ingestion. Both batch and stream now reject conflicting IDs and preserve original
  grouping for identical data. Corrections require a new ID; an immutable
  revision-ledger feature is not implemented. Add atomic approval/audit writes and
  concurrent-approval tests. Accept when conflicting inputs cannot silently
  rewrite investigation history or execute duplicate simulated actions.

- [ ] **P1-6: Bound and isolate scoring state — Pratham + Pratyush.**
  Serialize the complete specialist scoring operation, define duplicate score
  semantics and cancellation handling, persist or reconstruct history, and test
  out-of-order and simultaneous payments. Individual history-method locks do
  not make scoring atomic. Accept when restart/concurrent evaluation produces
  documented, reproducible results within bounded memory.

- [x] **P1-7: Payment-value metrics — Pratyush + Yojit.**
  Group totals by currency and distinguish payment counts from sums of money.
  The API now returns `value_by_currency`; the legacy scalar total is null
  for mixed currencies. The graph labels and observed-value display retain
  each currency. No FX conversion is performed. Accept when INR
  and USD controls remain separate in API and UI.

Additional remaining work: define case grouping across overlapping windows;
review prototype fan-out/known-beneficiary suppression against representative
legitimate and fraudulent data; authenticate analyst identities before shared
use. Synthetic acceptance checks are not a green flag for production use.

## P2 — submission hardening

- [ ] **P2-1: Runtime reliability — all three.** Add slow/disconnected WebSocket
  client limits, request/window bounds, dependency pinning, load/latency tests,
  and detector timeout/recovery coverage. Report measured results, not a claim
  of production throughput.
- [ ] **P2-2: Operator access — Pratyush + Yojit.** Add authentication,
  investigation/approval roles and access-scoped APIs/events before any shared
  deployment with sensitive data. Test denied actions and audit actor identity.
- [ ] **P2-3: Fintech presentation — all three.** Verify the official rubric
  against the team's supplied requirement list. Rehearse one clean payment,
  one mule network and one scam investigation through the completed flow.
  Show model evaluation and distinguish synthetic replay from live telemetry.
- [ ] **P2-4: Final release evidence — all three.** Run the release checklist,
  record CI revision and demo limitations, and update the README coverage table
  only after the corresponding acceptance criteria pass.

Recommended order: agree on P0-1's contract first; start P0-4's data/evaluation
work in parallel; complete P0-2, P0-3 and P0-5 around the shared contract; then
finish the P1 capabilities. Keep the optional infrastructure demo working while
building the financial-only path.
