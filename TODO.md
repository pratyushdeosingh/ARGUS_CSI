# ARGUS work checklist

The 29 October 2026 release integrates Yojit's dashboard/redesign with unified
financial scoring and the investigation workflow. This checklist distinguishes
assignment prototype delivery from work requiring real data or production
infrastructure. Release evidence is in [docs/verification.md](docs/verification.md).

## Delivered submission workflow

- [x] Preserve Yojit's live monitoring layout, navigation, graphs and styling.
- [x] Financial rules/TGNN/mule/scam `financial.v1` assessment and provenance.
- [x] Financial-only batch/stream analysis cases with optional infrastructure.
- [x] Connected financial stream evidence groups and persisted payment context.
- [x] Live React ingestion, scored/alert/failure events and reconnect replay.
- [x] Preserve per-payment unified score across supplementary event delivery.
- [x] Investigation assignment/status/notes with optimistic revision checks.
- [x] Draft JSON report export with transaction and assessment references.
- [x] Immutable payment IDs and atomic simulated response approval/audit.
- [x] Currency-separated API totals; no mixed-currency portfolio sum.
- [x] Synthetic evaluation/training scripts, metrics and model/data fingerprints.
- [x] Container startup, service/restart/outage checks in CI.
- [x] Same-origin Docker API/WebSocket proxy and Vercel frontend configuration.
- [x] Submission walkthrough, deployment instructions and documented limitations.

## Remaining research and production work

- [ ] Approve a representative labelled dataset/licence and perform independent
  leakage-controlled real-data evaluation, calibration and segment analysis.
- [ ] Validate model attribution beyond the bounded node-feature ablation diagnostic.
- [ ] Add time/currency-aware cycles, suspicious communities and centrality-based
  investigation with positive/negative graph counterexamples.
- [ ] Add a persisted scoring job/retry worker. Stored event replay recovers
  missed delivered scores/alerts; it does not automatically retry detector failures.
- [ ] Introduce authenticated analyst roles and authorization for shared sensitive
  deployments; current actor names are supplied by callers.
- [ ] Add a broker/shared state for multiple core workers, bounded slow-client
  handling and measured load/latency/resource tests.
- [ ] Strengthen payroll/refund/merchant-vs-scam discrimination on real data.
- [ ] Define production payment revision/cancellation semantics and external feed
  integration; no real holds/freezes/cancellations exist in this prototype.
- [ ] Expand mobile/browser/assistive-technology regression coverage.
- [ ] Confirm the original course rubric and any video/report requirements.

These unchecked items are explicit limits, not features claimed by the submission.
