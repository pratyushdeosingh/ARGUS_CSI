# Fintech submission status

ARGUS partially implements the team's supplied requirements for Problem
Statement #9. The [README coverage table](../README.md#coverage-of-the-fintech-requirements)
is the product summary. [TODO.md](../TODO.md) is the single work checklist with
priorities, owners and acceptance criteria. [Verification](verification.md)
records tested behaviour and limits; [integration](integration.md) describes the
actual API boundaries.

## Current team

- Pratyush: model evaluation, core integration, financial-only cases and RegTech.
- Pratham: graph analytics, mule networks, specialist scoring and evidence.
- Yojit: streaming reliability, live React updates and scam integration.

Nitin's existing infrastructure detector remains available as optional evidence.
It is not a prerequisite for financial scoring, although the Compose demo starts
it and the existing durable case workflow requires a system signal.

## Submission boundaries

Core batch/stream input uses a shared financial.v1 assessment with rules, TGNN,
mule and scam components and creates durable financial-only cases. React Data
Lab shows contributions, cases and an investigation dialog with revisioned
notes/assignment/status and draft report export. It does not yet subscribe to
the live stream. The legacy standalone specialist demo is retained.

The [Pratyush delivery report](pratyush-delivery.md) records this scope and its
verification. Investigation/reporting is a synthetic prototype with caller-
supplied identities, not authenticated compliance operation or regulatory
filing. No model was newly deployed: the bundled TGNN remains demo-trained.
Independent synthetic evaluation and offline training tooling now exist; real
labelled data, calibrated performance and ML feature attribution remain pending.

Before submitting, verify the official rubric against the working requirement
list. Passing prototype checks is not proof of production banking readiness.
