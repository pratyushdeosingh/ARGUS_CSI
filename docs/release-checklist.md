# Fintech release checklist — 29 October 2026

Release scope: synthetic assignment workflow, preserving Yojit's redesigned UI.
See [submission guide](fintech-submission.md) and [verification](verification.md).

## Local gate

- [x] Full Python suite: 156 passed, 1 privileged Linux eBPF test skipped.
- [x] Frontend interaction/helper tests: 52 passed; TypeScript/Vite build passed.
- [x] Real graph/core/replay service integration and all specialist scenarios.
- [x] HTTP/WebSocket smoke: ingestion, duplicate/conflict/invalid data, financial
  case, investigation revision, draft export, simulated approval and audit.
- [x] Reproducible independent synthetic evaluation; no real-data accuracy claim.
- [x] Browser financial-only Lab analysis and saved assignment/status/note.
- [x] Nested investigation Escape returns to the still-open accessible Lab.
- [x] Saved analysis contexts retain payment contributions and complete labels.
- [x] Deployment configuration and same-origin proxy smoke added to CI.

## Final remote gate

- [ ] Integrated PR has no unresolved Git conflicts and exact-head CI passes.
- [x] CI container build/startup and dashboard HTTP/WebSocket proxy pass.
- [x] Restart persistence and detector outage checks pass.
- [ ] Merge release and confirm main CI passes.

## Submission and runtime boundaries

- [x] Synthetic data, replay infrastructure, simulated actions and model limits
  are stated in the README and submission guide.
- [x] Financial analysis cases are distinguished from connected stream groups.
- [x] Scores retain their documented 0–1 and 0–100 boundaries.
- [x] Local smoke databases and test artifacts are ignored by Git.
- [x] Docker preserves SQLite in a named volume; separate Vercel frontend
  requires a reachable HTTPS backend and configured allowed origins.
- [ ] Confirm the original official rubric and any required report/video format.
- [ ] Provision and verify a hosted deployment, if selected by the user.
