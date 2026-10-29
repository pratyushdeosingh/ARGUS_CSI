# ARGUS React dashboard

Yojit's React/TypeScript/Vite and Cytoscape dashboard provides live synthetic
monitoring, alerts, graph investigation, persisted financial cases and the
optional canonical cross-domain demonstration.

- Overview, Transactions, Alerts, Investigations, Demo and Lab navigation.
- Seeded synthetic scenario controls, pause/resume and explicit session isolation.
- WebSocket scores/failures, bounded persisted event replay on reconnect.
- Financial.v1 payment contributions; rolling graph and supplementary scam scores.
- Financial-only Lab inputs with optional infrastructure, model provenance and
  rule evidence. Investigation assignment/status/notes and draft JSON exports.
- Simulated approval and stored action audit; no bank controls.

The real-data provider is disabled. Analyst identities are caller supplied;
authenticated roles and real-data evaluation remain pending.

## Run and verify

Start services using the root [README](../README.md), then:

```powershell
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev --host 127.0.0.1
pnpm --dir frontend test
pnpm --dir frontend build
```

Manual development defaults to `http://127.0.0.1:8000`. Override
`VITE_API_BASE_URL` in `frontend/.env.local` before dev/build. Docker uses its
same-origin Nginx HTTP/WebSocket proxy. For Vercel, use `frontend` as the project
root and configure the public HTTPS backend URL; see
[deployment](../docs/deployment.md).

Tests cover rendered dashboard interactions, selection, graph boundaries,
modal focus/keyboard, stream reconnect/reducers, seeded scenarios and API helpers.
Browser verification is still needed for actual Cytoscape rendering and layout.
