# Financial intelligence dashboard

The default React application is now a synthetic monitoring workspace. Use Overview, Transactions, Alerts, Investigations, Demo and Lab from the sidebar. The original four-account demo is available in Demo → Canonical Demo; Intelligence Lab keeps its existing JSON dataset and telemetry analysis workflow.

## Synthetic engine and source boundary

`simulation.ts` produces up to 5,000 deterministic INR payment records with a configurable seed, logical start time, account population and scenario. The default run has 400 payments and 100 accounts. It remains idle on application mount. Records are generated and submitted only after an explicit Start action. Browser refresh creates an idle session; it does not start or resume a run.

Normal controls use lower amounts and three-minute logical intervals. Other scenarios use twenty-payment blocks with clean controls followed by connected patterns: mule forwarding, device/IP changes, fan-out and velocity. Mixed mode rotates patterns; randomized mode selects whole blocks with a seeded generator. Salary and large legitimate transfers occur occasionally. Logical event time and wall-clock delivery speed are intentionally separate.

`TransactionSource` in `api.ts` defines normalized history, event replay and ingestion operations. Only the synthetic source is implemented. Real Data — Not Connected is disabled. Future real providers need explicit server-side integration, provenance and authorization; adding a switch alone does not enable them.

`useMonitoring.ts` submits one request at a time to POST `/api/transactions?session_id=...`. Pacing is capped at four requests per second and remains limited by detector latency. Pause stops scheduling new requests; a payment already accepted may finish. Reset changes the namespace and aborts the previous client request. The server may finish accepted work, but its old-session events cannot enter the new run. No reset endpoint deletes persisted records.

Each run receives a fresh synthetic session ID, account namespace and transaction namespace. Replay retains seed, start time and configuration; identifiers change to avoid collisions with persisted payments. Scoring history uses the existing backend session/batch filter. Core graph models, weights and fusion rules are unchanged.

## Status and evidence

- Payment lifecycle: pending, completed, cancelled, directly from the backend payment schema.
- Detection: not analyzed, scoring, cleared by analysis, flagged, analysis failed.
- Synthetic truth: legitimate or suspicious pattern, from the generator, independent of detector prediction.
- Stream alerts: graph, scam and detector failures; these are separate from persisted cases.
- Investigation response: only existing backend incident approval/audit operations. Response controls explicitly say Simulated.

Graph risk is the rolling session-window score on a 0–1 scale, normalized to 0–100 for display. It is not an individual-transaction probability. A graph flag requires the current transaction in `suspicious_transactions`. Specialist scam and combined scores already use 0–100. REVIEW/BLOCK are detector decisions, not payment cancellations. Clean synthetic truth can disagree with detector output; those false positives remain visible.

## Stream and recovery

The reusable transport connects to `/ws/transactions`, reports connection state, reconnects with exponential backoff capped at fifteen seconds, and cleans up sockets/timers. It consumes connection.established, transaction.received, transaction.scored, alert.created, transaction.analysis_failed, transaction.scam_scored, scam_alert.created and transaction.scam_scoring_failed.

Transaction, graph and scam state merge independently so scoring can arrive before receipt. Stable event IDs deduplicate deliveries; stable alert IDs deduplicate alerts. Successful scores survive a late failure event.

Compatible backend additions:

- Optional `session_id` on GET `/api/transactions`; omitted queries retain the original behavior.
- Additive `session_id` metadata on ingestion stream envelopes.
- SQLite `stream_events` table stores ingestion/scoring/alert envelopes without changing payment schemas.
- GET `/api/transaction-events?session_id=...&limit=2000` replays a bounded session history on connection/reconnection. Maximum query limit is 5,000.

History loading uses the existing GET transactions API and event replay. There is no deletion of existing data. The local SQLite replay table has no automatic disk-retention policy; production retention and access controls remain future work.

## Rendering limits

The client retains 1,000 transactions, 1,200 detector records, 500 alerts and 5,000 event IDs. The table paginates twelve rows. The Cytoscape neighborhood uses at most twenty-eight transfers with up to three account-expansion steps; actual rendered nodes are the endpoints of the bounded edges (at most fifty-six). The selected edge and source/destination accounts are highlighted. Accounts and edges are clickable; fit, zoom and pan are supported. Stable neighborhood references avoid rebuilding the graph on unrelated scoring/UI changes.

KPIs state their scope: retained current-run payments, actual flags, retained alerts, latest fifty persisted cases, and backend detector-health provenance. They are not production throughput statistics.

## Verification and limitations

Run `pnpm --dir frontend test`, `pnpm --dir frontend build`, and `./.venv/bin/pytest -q`. `dashboard.test.tsx` covers React controls and coordinated selection with a mocked graph boundary; browser verification is needed to inspect the actual Cytoscape rendering. `monitoring.test.tsx` covers transport/reconnect, reducer, generator, isolation, graph filtering and legacy rendering. Backend session tests exercise real ingestion/WebSocket delivery with isolated temporary databases.

Satoshi is preferred when installed locally; Inter/system fallbacks are used without bundling a proprietary font. Google-hosted Inter/IBM Plex Mono imports are inherited from the original stylesheet. No supplied screenshot or typography image was available, so layout follows the written specification.

The browser must reach the API URL (default `http://127.0.0.1:8000`; override `VITE_API_BASE_URL` at build time). Docker uses actual graph and replay-mode eBPF services. If detectors are unavailable, errors and missing scores remain visible. No real banking integration, production-scale throughput certification, payment freezing, assignments or notes were added. Financial case creation is described below.


## Financial-only investigations and alert repair

`financial_cases.py` defines `financial-connected-v1`, independently of the existing cross-domain correlation/fusion rules. A financial investigation needs at least two connected, completed payments in one session in a fifteen-minute admission window. Each must have nonempty detector evidence and meet the configured graph or scam alert threshold. Graph admission additionally requires that payment in the detector's suspicious-transaction list. REVIEW alone, payment volume, scenario labels and synthetic truth never trigger a case. Severity is critical if the admitted detector score reaches 85/100, otherwise high. These are investigation candidates, not confirmed fraud.

SQLite tables `financial_findings` and `financial_investigations` are additive; old incidents and audits are preserved. Findings use a `(session_id, transaction_id)` primary key. Admission and case merging run under `BEGIN IMMEDIATE`; related findings form a connected component of accounts. Overlapping existing cases are updated, retaining the oldest case ID; later bridge evidence merges components and retains addressable merge aliases. Unrelated components and sessions remain separate. Candidates are bounded to 500 findings per admission query; case transaction references accumulate as related evidence arrives. Cases have open/merged status and no containment workflow. Policy changes or backfilling old alerts are not performed automatically.

Endpoints: GET `/api/financial-investigations` (optional session filter, latest 50 by default), GET `/api/financial-investigations/{case_id}`, and GET `/api/financial-investigations/{case_id}/context` (latest 200 referenced payments plus stored scoring events). GET `/api/transactions/{transaction_id}/context` retrieves an older alert payment directly by ID with up to 80 relevant same-session payments, rather than depending on the global history limit. GET `/api/incidents/{incident_id}/context` opens available historical cross-domain transaction references and stored graph evidence.

Successful case writes broadcast `investigation.updated`. The dashboard refreshes persisted cases on these notifications and reconnect, with a fifteen-second fallback poll. Financial cases and historical cross-domain incidents share the existing Investigations presentation but keep separate APIs/models. Source, session/scenario, creation time, accounts, payments, scores and evidence are shown. Historical cases retain their existing simulated approval and audit controls.

Alerts retain their own selected alert ID, severity, timestamp, explanation, normalized scores and supporting evidence. Missing payments are fetched from the backend; a 404 keeps the alert evidence visible without inventing a transaction. Stored inspection context is isolated from active-run metrics and can be left with Return to live run. Back to alerts / Back to investigations preserve selection context. Reset changes the active run without deleting cases. Pausing an in-flight request does not double-submit it on rapid resume.
