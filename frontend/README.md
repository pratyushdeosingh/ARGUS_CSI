# ARGUS dashboard — Pratyush

Build a dark, professional React/Vite SOC interface here after the backend mock flow is verified.

Required views on one main screen:

- system health and threat level;
- live attack timeline;
- transaction/mule graph;
- graph-detector evidence;
- eBPF evidence;
- correlated incident explanation;
- response recommendations and approval control; and
- containment audit log.

The dashboard should call the ARGUS backend on port `8000`. It must not call detector services directly; orchestration belongs in the backend.
