# ARGUS Synthetic Transaction Simulator (Phase 1)

Modular, deterministic synthetic financial transaction generator for the ARGUS fraud and cyber-financial incident response platform.

## Overview

The simulator generates realistic financial transaction datasets conforming strictly to `contracts/transaction.schema.json` and the ARGUS graph detector Pydantic models. It is built using Python's standard library with zero external runtime dependencies.

### Supported Scenarios

1. **`normal` (Legitimate P2P & Retail Traffic)**:
   - Varied realistic transaction amounts (INR 300 to 2,400).
   - Distinct synthetic bank accounts (`ACC-1001` to `ACC-1120`).
   - Dispersed activity avoiding fan-in/fan-out and rapid velocity traps.
   - Strictly chronological ISO 8601 UTC timestamps with `Z` suffix.
   - Evaluates to zero/low risk (`risk_score <= 0.15`, `anomaly_type: "no_suspicious_activity"`) when analyzed by the ARGUS graph detector.

2. **`mule` (Mule Account Fraud & Rapid Multi-Hop Layering)**:
   - Normal transactions followed by a rapid money-movement sequence.
   - Multi-hop chain across dedicated mule accounts (`ACC-MULE-00` -> `ACC-MULE-01` -> ... -> `ACC-MULE-04`).
   - High initial amount (~80,000 to 95,000 INR) triggering unusual amount ratio against baseline median.
   - Rapid forwarding within 30–45 seconds per hop (violating velocity <= 2 min and graph hop <= 5 min).
   - 95%–98% forwarded funds ratio per hop.
   - Reliably triggers the ARGUS graph detector (`risk_score >= 0.70`, `anomaly_type: "rapid_mule_fund_movement"`).

---

## CLI Usage

The script is located at `scripts/transaction_simulator.py`.

```bash
python3 scripts/transaction_simulator.py --scenario {normal,mule} --count COUNT --output OUTPUT_PATH [--seed SEED]
```

### Options

| Flag | Type | Required | Description |
|---|---|---|---|
| `--scenario` | string | Yes | Scenario type: `normal` or `mule` |
| `--count` | int | Yes | Number of transactions (>= 1 for normal, >= 2 for mule) |
| `--output` | string | Yes | Destination JSON file path (directories auto-created) |
| `--seed` | int | No | Random seed for reproducible, deterministic output |

### Examples

Generate 20 normal transactions:
```bash
python3 scripts/transaction_simulator.py --scenario normal --count 20 --output data/generated/normal.json
```

Generate 20 mule transactions with a reproducible random seed:
```bash
python3 scripts/transaction_simulator.py --scenario mule --count 20 --output data/generated/mule.json --seed 42
```

---

## Integration with Dockerized Graph Detector

The generated JSON files are top-level arrays of transaction objects ready for immediate consumption by the ARGUS Graph Detector endpoint `POST /analyze`.

With the ARGUS Docker Compose stack running:

### 1. Verify Service Health
```bash
curl -s http://localhost:8001/health
```

### 2. Analyze Normal Transactions
```bash
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d @data/generated/normal.json
```
**Expected Response**:
```json
{
  "signal_id": "GRAPH-...",
  "source": "graph_detector",
  "timestamp": "2026-10-23T...",
  "risk_score": 0.0,
  "anomaly_type": "no_suspicious_activity",
  "suspicious_accounts": [],
  "suspicious_transactions": [],
  "related_ips": [],
  "reasons": [
    "No suspicious graph or temporal behavior was observed."
  ]
}
```

### 3. Analyze Mule Transactions
```bash
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d @data/generated/mule.json
```
**Expected Response**:
```json
{
  "signal_id": "GRAPH-...",
  "source": "graph_detector",
  "timestamp": "2026-10-23T...",
  "risk_score": 0.768,
  "anomaly_type": "rapid_mule_fund_movement",
  "suspicious_accounts": [
    "ACC-MULE-00",
    "ACC-MULE-01",
    "ACC-MULE-02",
    "ACC-MULE-03",
    "ACC-MULE-04"
  ],
  "suspicious_transactions": [
    "MULE-100017",
    "MULE-100018",
    "MULE-100019",
    "MULE-100020"
  ],
  "related_ips": [
    "185.220.101.10",
    "185.220.101.27",
    "185.220.101.44",
    "185.220.101.61"
  ],
  "reasons": [
    "MULE-100017 transferred 88,421 INR, 82.3x the normal median.",
    "3 account(s) sent or received linked transfers within two minutes.",
    "Funds crossed 4 transfers and 5 accounts in 123 seconds.",
    "Intermediate accounts forwarded an average of 97.0% of received funds."
  ]
}
```

---

## Running Automated Tests

Run the test suite using `pytest`:
```bash
pytest tests/test_transaction_simulator.py -v
```

Or using standard library `unittest`:
```bash
python3 -m unittest tests/test_transaction_simulator.py -v
```
