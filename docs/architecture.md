# ARGUS architecture

## Product boundary

ARGUS is a synthetic, local Financial SOC prototype. The financial detector and infrastructure detector are sensors. The orchestration backend is the decision layer. The dashboard is the analyst interface. All containment actions are state changes inside the demo.

## Data flow

```text
Transaction fixtures / simulator
             |
             v
Graph detector (Pratham) --> GraphSignal -----\
                                                > Correlation engine
Linux telemetry (Nitin) --> SystemSignal ------/          |
                                                           v
                                                Incident + explanation
                                                           |
                                                           v
                                                  Policy evaluation
                                                           |
                                                           v
                                                   Human approval
                                                           |
                                                           v
                                              Simulated actions + audit
```

## Correlation model

The initial correlation formula is transparent:

```text
confidence = 0.50 * graph_risk
           + 0.35 * infrastructure_risk
           + up to 0.15 linkage bonus
```

The linkage bonus comes from shared evidence such as the same IP address and signals occurring within five minutes. This makes the demo explainable and allows each detector to be tested independently.

## Trust and safety boundary

- Synthetic accounts and transactions only.
- Harmless eBPF test process only.
- No real credentials or sensitive files.
- No real freeze, network block, or machine-isolation actions.
- Critical simulated actions require explicit human approval.

## Planned runtime

| Component | Runtime | Default port |
|---|---|---|
| ARGUS orchestration | Python 3.11 / FastAPI | `8000` |
| Graph detector | Python 3.11 / FastAPI | `8001` |
| eBPF adapter | Linux + Python FastAPI | `8002` |
| Dashboard | React / Vite | `5173` |
