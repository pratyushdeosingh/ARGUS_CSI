# Graph detector — Pratham

## Mission

Detect suspicious changes in the synthetic financial network over time and return a contract-valid `GraphSignal` to ARGUS.

## Inputs and outputs

- Input: transactions matching `contracts/transaction.schema.json`.
- Output: object matching `contracts/graph-signal.schema.json`.
- Fixtures: `data/normal/transactions.json` and `data/attack/transactions.json`.

## Required baseline

Implement explainable graph/temporal features first:

- unseen device or IP;
- unusual transfer amount;
- new beneficiary relationship;
- short inter-transaction time;
- rapid multi-hop transfer path;
- high fan-in/fan-out; and
- percentage of funds forwarded quickly.

Normalize risk to `0.0..1.0`. Reasons must describe evidence rather than model jargon.

## Suggested structure

```text
services/graph-detector/
  app.py
  detector.py
  features.py
  graph_builder.py
  visualization.py
  requirements.txt
  tests/
  experiments/
```

## Required endpoints

```text
GET  /health
POST /analyze
```

## Testing target

- The normal fixture has a clearly lower score than the attack fixture.
- The attack identifies `ACC-101`, the mule chain, and `TX-1001..1003`.
- Output validates against the shared contract.

## Optional GNN enhancement

After the baseline works, create temporal snapshots and experiment with GraphSAGE, a graph autoencoder, or a small temporal model. Keep the baseline as fallback and report honestly which detector produced the displayed score.

## AI handoff

Use the Pratham prompt in the root README. Ask the AI to inspect the repository before generating code, work only on the assigned branch, and implement one testable milestone at a time.
