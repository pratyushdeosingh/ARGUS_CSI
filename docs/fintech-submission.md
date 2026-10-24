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

The core supports batch and per-payment graph scoring. The specialist mule/scam
engine has a separate demo/API; React does not yet consume its breakdown or live
WebSocket events. Graph-only results and streamed alerts do not create durable
financial-only cases. The existing audit trail covers simulated response
execution, rather than a complete compliance investigation/reporting workflow.

The TGNN checkpoint was trained on synthetic normal/attack batches. Batch model
promotion requires rule risk >= 0.40; specialist fusion remains experimental.
No independent held-out metrics, calibrated fraud probabilities or SHAP
explanations are included. All response actions are simulated.

Before submitting, verify the original official problem statement against the
working requirement list. This repository documents implementation status,
not a guarantee of competition eligibility or regulatory compliance.
