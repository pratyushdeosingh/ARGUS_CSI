# Final integration verification — 29 October 2026

This release combines Yojit's PR #6 redesign/live dashboard with the backend
work from PR #5. Yojit's PR was merged first at its verified head cc9f276.
The integration resolves App/style conflicts by retaining the redesigned
layout, adding the financial case tools and using the same semantic styling.

## Local release results

- Python: **156 passed, 1 skipped** (privileged live Linux eBPF).
- Frontend: **52 passed**; TypeScript and production Vite build passed.
- Actual graph/core/infrastructure replay processes: service integration passed.
- HTTP/WebSocket smoke passed: durable financial-only case, per-payment scoring,
  duplicate/conflicting/invalid input, all specialist scenarios, investigation
  revision conflict, draft report, simulated approval/audit and reanalysis.
- Independent synthetic evaluation reproduced the committed report: fused
  precision/recall/F1 1.0 on 32 held-out generated cases, rules/raw TGNN recall
  0.5 at 0.70. This small synthetic result is not real-world accuracy evidence.
- Browser: live synthetic ingestion and scoring; financial-only takeover Lab
  analysis with contributions; nested case workbench assignment/status/note
  saved at revision 1; Escape returned to the still-open Lab. Visual layout
  was inspected. Broad device/accessibility certification is not claimed.

The integration adds a Docker same-origin Nginx API/WebSocket proxy, configurable
frontend CORS origins and Vercel static frontend settings. CI verifies actual
container startup and the proxy boundary; Docker is unavailable locally.

Final remote CI, restart/outage results and the release revision are recorded
below when the release gate completes. Test databases/logs remain under ignored
`artifacts/submission-20261029/`; existing user runtime data was not overwritten.
The official rubric, real-data evaluation and production readiness remain outside
the verified scope. See the current README/TODO for the delivered workflow and
remaining work. The earlier audit below describes the historical pre-integration
baseline and is retained for traceability.

---
> Historical audit of c1f9a1d. For the current implementation, see [Pratyush delivery](pratyush-delivery.md).

# Fintech readiness verification

Audit date: 24 October 2026 (Asia/Kolkata). Scope: the team's supplied Problem
Statement #9 requirements and the integrated ARGUS repository. The official
competition document was not supplied, so eligibility/rubric compliance has not
been independently verified.

## Finding

The implemented batch, ingestion, specialist and cross-domain demo paths have
automated checks. The complete fintech product is not finished. Missing
capabilities are listed in the README coverage table and [TODO](../TODO.md),
with owners and acceptance criteria. A passing test suite does not close them.

## Checks

| Area | Verification |
| --- | --- |
| Local backend rerun | 28 targeted tests passed after isolating API test databases |
| Local frontend rerun | 4 tests passed; TypeScript and production build passed |
| Browser smoke | Production React build against an isolated fixture backend: graph rendering, staged demo, three simulated approval actions, audit display, Data Lab fields/history and visible fixture-mode error |
| Complete Python suite | Required in the audit PR's Linux CI, including graph/TGNN and simulator tests |
| Containers | CI builds the four services and waits for health checks |
| Batch boundary | Real HTTP batch calls, request baseline, service provenance, graph-only null incident and cross-domain case |
| Ingestion boundary | Real HTTP/WebSocket delivery, score events, identical duplicates, conflicting IDs and invalid amounts |
| Specialist path | Detector breakdown contract and all six synthetic scenario bands/recommendations |
| Approval/replay | Simulated approval, repeat approval rejection, reanalysis preserves containment and audit |
| Restart | Stored payment, contained case and audit survive actual backend container restart |
| Detector outage | Batch returns 503; streamed payment is stored and emits analysis failure |

The audit branch's [CI runs](https://github.com/pratyushdeosingh/ARGUS_CSI/actions?query=branch%3Acodex%2Ffintech-readiness-audit)
provide the tested revision, full results and logs. CI must pass on the review
head before merge. Main's CI also runs the same gate after merging. The previous
integration baseline passed 100 Python tests, with one privileged Linux eBPF
test skipped; this audit adds identity and containment replay regressions.

Local full Python/TGNN and Docker verification could not run: PyTorch was not
installed after its earlier download timed out, and the local Docker daemon was
unavailable. Full model/container checks therefore run in Linux CI. The local
backend/frontend results above are separate from those CI results.

## Repairs from this audit

- Graph signal identity now includes full transaction contents and baseline
  history. Reusing payment IDs with changed values no longer aliases the signal.
  Previously stored signal/case IDs are retained; new analyses use the new IDs.
- Reanalysis cannot overwrite a stored contained case with a pending case.
  API responses return the persisted state; approval reads the stored case.
- Reopening a contained case in the React demo restores the contained display
  and loads its stored action audit instead of showing pending actions.
- Backend API tests use isolated temporary databases and reset in-memory state,
  rather than depending on previously saved demo cases.
- Compose maps the documented fraud threshold/window settings to the backend.
- README, component docs, architecture, integration, demo and release checklist
  distinguish working paths from missing work and remove unsupported claims.

## What these checks do not establish

- End-to-end financial-only investigation or live React integration: missing.
- Compliance case workflow/reporting or jurisdictional compliance: missing.
- Representative fraud/scam accuracy, model calibration or ML attribution:
  no independent evaluation or appropriate attribution study is included.
- Full rendered browser interactions, accessibility and responsive layout:
  only the desktop fixture workflow above was manually inspected. Arbitrary
  analysis with real detectors is checked at HTTP boundaries in CI, rather than
  as a complete browser workflow. No mobile, keyboard or visual-regression suite
  was run. Frontend automated tests cover API/helper behaviour.
- Live privileged Linux eBPF: opt-in and skipped in standard CI; replay is tested.
- Production throughput, concurrent approval atomicity, complete specialist
  scoring concurrency, durable alert recovery, immutable transaction revisions,
  authentication and multi-worker consistency: not established; see TODO.
- Multi-currency value aggregation: raw aggregate totals are not FX-converted
  portfolio value. TGNN amount features also need currency-aware evaluation.

All bundled events/accounts and verification inputs are synthetic. Containment
remains simulated. No claim of production banking readiness is made.
