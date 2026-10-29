import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  Bell,
  ChevronRight,
  CircleHelp,
  FlaskConical,
  Network,
  Pause,
  Play,
  RefreshCw,
  Search,
  Shield,
  Wallet,
} from "lucide-react";
import CanonicalDemo from "./CanonicalDemo";
import { IntelligenceLab } from "./IntelligenceLab";
import {
  analyzeData,
  approveIncident,
  loadAuditEvents,
  loadDetectorStatus,
  loadIncidents,
  loadFinancialInvestigations,
  loadTransactionContext,
  loadFinancialContext,
  loadIncidentContext,
} from "./api";
import {
  contextState,
  detectionLabel,
  neighborhood,
  type Alert,
  type MonitorState,
} from "./monitoring";
import {
  DATA_SOURCES,
  SCENARIOS,
  type RunConfig,
  type ScenarioId,
} from "./simulation";
import { useMonitoring } from "./useMonitoring";
import { MoneyGraph } from "./MoneyGraph";
import { CaseBrowser } from "./CaseBrowser";
import { NavigationShell, type Page } from "./NavigationShell";
import { KpiTrend } from "./KpiTrend";
import { runTrends, investigationTrend } from "./kpiTrends";
import type {
  AuditEvent,
  DetectorStatus,
  Incident,
  FinancialInvestigation,
} from "./types";
export { detectorSourceLabel } from "./CanonicalDemo";

const currency = (value: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
const time = (value: string) =>
  new Date(value).toLocaleTimeString("en-GB", {
    timeZone: "UTC",
    hour12: false,
  });
const risk = (value?: number) =>
  value === undefined ? "—" : `${Math.round(value)}/100`;
const tone = (value?: number) =>
  value === undefined
    ? ""
    : value >= 70
      ? "danger"
      : value >= 40
        ? "warning"
        : "healthy";
const newConfig = (
  scenario: ScenarioId = "mixed",
  seed = 42017,
  count = 400,
  accounts = 100,
): RunConfig => ({
  session: `SYN-${crypto.randomUUID().slice(0, 8)}`,
  scenario,
  seed,
  count,
  accounts,
  start: new Date().toISOString(),
});
const EMPTY: string[] = [];
export default function App() {
  const [page, setPage] = useState<Page>("Overview");
  const monitoringPage = page !== "Demo" && page !== "Lab";
  const [caseSelection, setCaseSelection] = useState("");
  const [config, setConfig] = useState<RunConfig>(() => newConfig());
  const [running, setRunning] = useState(false);
  const [speed, setSpeed] = useState(2);
  const [seed, setSeed] = useState(42017);
  const [count, setCount] = useState(400);
  const [accounts, setAccounts] = useState(100);
  const [selectedId, setSelectedId] = useState("");
  const [account, setAccount] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("newest");
  const [tablePage, setTablePage] = useState(0);
  const [status, setStatus] = useState<DetectorStatus | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [caseError, setCaseError] = useState("");
  const [financialCases, setFinancialCases] = useState<
    FinancialInvestigation[]
  >([]);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [openedCase, setOpenedCase] = useState<FinancialInvestigation | null>(
    null,
  );
  const [inspection, setInspection] = useState<MonitorState | null>(null);
  const [selectionError, setSelectionError] = useState("");
  const [selectionLoading, setSelectionLoading] = useState(false);
  const selectionRequest = useRef(0);
  const refreshingCases = useRef(false);
  const refreshCases = useCallback(() => {
    if (refreshingCases.current) return;
    refreshingCases.current = true;
    void Promise.all([loadIncidents(50), loadFinancialInvestigations()])
      .then(([historical, financial]) => {
        setIncidents(historical);
        setFinancialCases(financial);
        setCaseError("");
      })
      .catch(() => setCaseError("Persisted investigations unavailable."))
      .finally(() => {
        refreshingCases.current = false;
      });
  }, []);
  const [audit, setAudit] = useState<Record<string, AuditEvent[]>>({});
  const [canonical, setCanonical] = useState(false);
  const [labOpen, setLabOpen] = useState(false);
  const [caseBusy, setCaseBusy] = useState(false);
  const navigate = useCallback((destination: Page) => {
    setPage(destination);
    setCanonical(false);
    if (destination === "Lab") setLabOpen(true);
  }, []);
  const complete = useCallback(() => setRunning(false), []);
  const { state, connection, error, cursor, records } = useMonitoring(
    config,
    running,
    speed,
    complete,
    refreshCases,
  );
  const refresh = useCallback(() => {
    void loadDetectorStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
    refreshCases();
  }, [refreshCases]);
  useEffect(() => {
    refresh();
    const healthTimer = setInterval(refresh, 30000);
    const caseTimer = setInterval(refreshCases, 15000);
    return () => {
      clearInterval(healthTimer);
      clearInterval(caseTimer);
    };
  }, [refresh, refreshCases]);
  const runTransactions = useMemo(
    () => Object.values(state.transactions),
    [state.transactions],
  );
  const activityTrends = useMemo(() => runTrends(state), [state.transactions, state.detections, state.alerts]);
  const caseTrend = useMemo(() => investigationTrend(financialCases, Date.now(), Boolean(caseError)), [financialCases, caseError]);
  const displayedState = inspection ?? state;
  const transactions = useMemo(
    () =>
      Object.values(displayedState.transactions).sort((a, b) =>
        b.timestamp.localeCompare(a.timestamp),
      ),
    [displayedState.transactions],
  );
  const selected = selectedId
    ? displayedState.transactions[selectedId]
    : transactions[0];
  const detection = selected
    ? displayedState.detections[selected.transaction_id]
    : undefined;
  const truth = useMemo(
    () =>
      new Map(
        records.map((record) => [record.transaction.transaction_id, record]),
      ),
    [records],
  );
  const alerts = useMemo(
    () =>
      Object.values(state.alerts).sort(
        (a, b) =>
          (({ critical: 3, high: 2, warning: 1 })[b.severity] ?? 0) -
            ({ critical: 3, high: 2, warning: 1 }[a.severity] ?? 0) ||
          b.timestamp.localeCompare(a.timestamp),
      ),
    [state.alerts],
  );
  const previousNeighborhood = useRef<ReturnType<typeof neighborhood>>([]);
  const related = useMemo(() => {
    const next = neighborhood(transactions, selected);
    const previous = previousNeighborhood.current;
    if (
      next.length === previous.length &&
      next.every((t, i) => t === previous[i])
    )
      return previous;
    previousNeighborhood.current = next;
    return next;
  }, [transactions, selected]);
  const suspicious = detection?.suspiciousAccounts ?? EMPTY;
  const inspect = useCallback(
    async (id: string) => {
      const request = ++selectionRequest.current;
      setSelectedId(id);
      setAccount("");
      setSelectionError("");
      setSelectionLoading(false);
      setQuery("");
      setFilter("all");
      setSort("newest");
      setTablePage(0);
      if (displayedState.transactions[id]) return;
      if (state.transactions[id]) {
        setInspection(null);
        return;
      }
      setSelectionLoading(true);
      try {
        const context = await loadTransactionContext(id);
        if (selectionRequest.current === request)
          setInspection(contextState(context));
      } catch (reason) {
        if (selectionRequest.current === request)
          setSelectionError(
            `Transaction unavailable: ${reason instanceof Error ? reason.message : String(reason)}`,
          );
      } finally {
        if (selectionRequest.current === request) setSelectionLoading(false);
      }
    },
    [displayedState.transactions, state.transactions],
  );
  const choose = useCallback(
    (id: string) => {
      setSelectedAlert(null);
      void inspect(id);
    },
    [inspect],
  );
  async function openCase(financial: FinancialInvestigation | Incident) {
    const request = ++selectionRequest.current;
    setOpenedCase("case_id" in financial ? financial : null);
    setSelectedAlert(null);
    setSelectedId("loading-case");
    setInspection(null);
    setAccount("");
    setSelectionError("");
    setSelectionLoading(true);
    setPage("Transactions");
    setQuery("");
    setFilter("all");
    setSort("newest");
    setTablePage(0);
    try {
      const context =
        "case_id" in financial
          ? await loadFinancialContext(financial.case_id)
          : await loadIncidentContext(financial.incident_id);
      if (selectionRequest.current !== request) return;
      const loaded = contextState(context);
      setInspection(loaded);
      setSelectedId(context.transactions.at(-1)?.transaction_id ?? "");
      if (!context.transactions.length)
        setSelectionError(
          "This historical case has no available payment records. Its stored evidence remains in Investigations.",
        );
    } catch (reason) {
      if (selectionRequest.current === request)
        setSelectionError(
          `Investigation context unavailable: ${String(reason)}`,
        );
    } finally {
      if (selectionRequest.current === request) setSelectionLoading(false);
    }
  }
  function returnToRun() {
    selectionRequest.current++;
    setInspection(null);
    setOpenedCase(null);
    setSelectedAlert(null);
    setSelectedId("");
    setSelectionError("");
    setSelectionLoading(false);
    setAccount("");
  }
  const filtered = useMemo(
    () =>
      transactions
        .filter((t) => {
          const label = detectionLabel(
            displayedState.detections[t.transaction_id],
          );
          return (
            `${t.transaction_id} ${t.source_account} ${t.destination_account} ${truth.get(t.transaction_id)?.category}`
              .toLowerCase()
              .includes(query.toLowerCase()) &&
            (filter === "all" || filter === t.status || filter === label)
          );
        })
        .sort((a, b) =>
          sort === "amount"
            ? b.amount - a.amount
            : sort === "oldest"
              ? a.timestamp.localeCompare(b.timestamp)
              : b.timestamp.localeCompare(a.timestamp),
        ),
    [transactions, displayedState.detections, query, filter, sort, truth],
  );
  const shown = filtered.slice(tablePage * 12, tablePage * 12 + 12);
  useEffect(() => {
    if (!selectedId) return;
    const index = filtered.findIndex((t) => t.transaction_id === selectedId);
    if (index >= 0) setTablePage(Math.floor(index / 12));
  }, [selectedId, filtered]);
  useEffect(() => setTablePage(0), [query, filter, sort, config]);
  const flagged = runTransactions.filter(
    (t) => detectionLabel(state.detections[t.transaction_id]) === "Flagged",
  ).length;
  const scenario = SCENARIOS.find((s) => s.id === config.scenario)!;
  function reset(scenarioId = config.scenario, randomize = false) {
    setRunning(false);
    returnToRun();
    setSelectedId("");
    setAccount("");
    const nextSeed = randomize
      ? crypto.getRandomValues(new Uint32Array(1))[0]
      : seed;
    setSeed(nextSeed);
    setConfig({
      ...newConfig(scenarioId, nextSeed, count, accounts),
      start: config.start,
    });
  }
  function alertItem(item: Alert) {
    return (
      <button
        key={item.id}
        className={`m-alert ${selectedAlert?.id === item.id ? "active" : ""}`}
        aria-pressed={selectedAlert?.id === item.id}
        onClick={() => {
          setSelectedAlert(item);
          setOpenedCase(null);
          void inspect(item.transactionId);
          if (page !== "Alerts") setPage("Overview");
        }}
      >
        {monitoringPage ? (
          <span className={`m-alert-severity ${item.severity}`}>
            {item.severity}
          </span>
        ) : (
          <span className={`m-alert-dot ${item.severity}`} />
        )}
        <div>
          <strong>{item.type}</strong>
          <small className="m-mono">{item.transactionId}</small>
          <p>{item.message}</p>
          <small>{item.evidence.slice(0, 2).join(" · ")}</small>
          <time>{time(item.timestamp)} UTC</time>
        </div>
        <ChevronRight size={14} />
      </button>
    );
  }
  const table = (
    <section className="m-panel m-transactions">
      <div className="m-panel-title">
        <div>
          <h2>
            {page === "Transactions"
              ? "Transaction history"
              : "Live transactions"}{" "}
            <span className="m-count">{transactions.length}</span>
          </h2>
          <p>
            {inspection
              ? "Historical investigation context · bounded retrieved records"
              : "Current synthetic run · latest 1,000 records retained"}
          </p>
        </div>
        <span className="m-pill">
          <i className={running ? "m-dot" : ""} />
          {running ? "Streaming" : cursor >= config.count ? "Complete" : cursor ? "Paused" : "Ready"}
        </span>
      </div>
      <div className="m-filters">
        <label className="m-search">
          <Search size={14} />
          <input
            aria-label="Search transactions"
            placeholder="Search ID, account or payment type…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <select
          aria-label="Filter transactions"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All statuses</option>
          {[
            "pending",
            "completed",
            "cancelled",
            "Flagged",
            "Cleared by analysis",
            "Analysis failed",
            "Not analyzed",
          ].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
        <select
          aria-label="Sort transactions"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="amount">Highest amount</option>
        </select>
      </div>
      <div className="m-table-wrap">
        <table>
          <thead>
            <tr>
              {[
                "Transaction / type",
                "Time · UTC",
                "Source → destination",
                "Amount",
                "Payment / detection",
                "Graph risk",
                "Scam risk",
                "Alert",
              ].map((v) => (
                <th key={v}>{v}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((t) => {
              const d = displayedState.detections[t.transaction_id];
              const label = detectionLabel(d);
              const alert = alerts.find(
                (a) => a.transactionId === t.transaction_id,
              );
              return (
                <tr
                  key={t.transaction_id}
                  className={
                    selected?.transaction_id === t.transaction_id
                      ? "selected"
                      : ""
                  }
                  onClick={() => choose(t.transaction_id)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") choose(t.transaction_id);
                  }}
                  aria-selected={selected?.transaction_id === t.transaction_id}
                >
                  <td>
                    <button
                      className="m-row-link"
                      onClick={() => choose(t.transaction_id)}
                    >
                      {t.transaction_id}
                    </button>
                    <small>
                      {truth.get(t.transaction_id)?.category ??
                        "Synthetic payment"}
                    </small>
                  </td>
                  <td className="m-mono">{time(t.timestamp)}</td>
                  <td className="m-mono">
                    {t.source_account.split("-").at(-1)}{" "}
                    <span className="m-muted">→</span>{" "}
                    {t.destination_account.split("-").at(-1)}
                  </td>
                  <td className="m-amount">{currency(t.amount)}</td>
                  <td>
                    <span className={`m-status ${t.status}`}>{t.status}</span>
                    <small className={label === "Flagged" ? "danger" : ""}>
                      {label}
                    </small>
                  </td>
                  <td className={tone(d?.graph)}>
                    {monitoringPage ? (
                      <span className="m-risk-value">{risk(d?.graph)}</span>
                    ) : risk(d?.graph)}
                  </td>
                  <td className={tone(d?.scam)}>
                    {monitoringPage ? (
                      <span className="m-risk-value">{risk(d?.scam)}</span>
                    ) : risk(d?.scam)}
                  </td>
                  <td>
                    <span
                      className={
                        alert?.severity === "critical" ||
                        alert?.severity === "high"
                          ? "danger"
                          : "m-muted"
                      }
                    >
                      {alert?.severity ?? "—"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!shown.length && (
          <div className="m-empty">
            <Wallet size={25} />
            <h3>
              {transactions.length
                ? "No matching payments"
                : "Ready to monitor"}
            </h3>
            <p>
              {transactions.length
                ? "Adjust your search or status filter."
                : "Start the simulation. Payments will be ingested and scored by the backend."}
            </p>
            {!transactions.length && (
              <button onClick={() => setRunning(true)}>Start simulation</button>
            )}
          </div>
        )}
      </div>
      <div className="m-table-footer">
        <span>
          {filtered.length
            ? `${tablePage * 12 + 1}–${Math.min((tablePage + 1) * 12, filtered.length)}`
            : "0"}{" "}
          of {filtered.length} payments
        </span>
        <div>
          <button
            disabled={tablePage === 0}
            onClick={() => setTablePage((p) => p - 1)}
          >
            Previous
          </button>
          <button
            disabled={(tablePage + 1) * 12 >= filtered.length}
            onClick={() => setTablePage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
  const details = (
    <section className="m-panel m-details" key="details" id="transaction-inspector" tabIndex={-1}>
      <div className="m-panel-title">
        <div>
          <h2>Investigation details</h2>
          <p>Payment record & detector evidence</p>
        </div>
        <Shield size={17} />
      </div>
      {selectedAlert && (
        <div className="m-account" aria-label="Selected alert evidence">
          <h3>
            {selectedAlert.type} · {selectedAlert.severity}
          </h3>
          <p className="m-mono">
            {selectedAlert.id} · {selectedAlert.transactionId}
          </p>
          <p>
            {selectedAlert.timestamp} · Graph {risk(selectedAlert.graph)} · Scam{" "}
            {risk(selectedAlert.scam)} · Combined {risk(selectedAlert.combined)}
          </p>
          <p>{selectedAlert.message}</p>
          <ul className="m-evidence">
            {selectedAlert.evidence.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
          <button onClick={() => {
            setPage("Alerts");
            if (page === "Alerts") document.getElementById("alert-queue")?.focus();
          }}>Back to alerts</button>
        </div>
      )}
      {openedCase && (
        <div className="m-account">
          <h3>
            {openedCase.case_id} · {openedCase.severity}
          </h3>
          <p>
            {openedCase.source} · {openedCase.session_id} ·{" "}
            {openedCase.scenario_id ?? "Unspecified scenario"}
          </p>
          <p>{openedCase.summary}</p>
          <ul className="m-evidence">
            {openedCase.evidence.slice(-12).map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
          <button onClick={() => setPage("Investigations")}>
            Back to investigations
          </button>
        </div>
      )}
      {selectionLoading && (
        <p className="m-muted" role="status">
          Loading persisted transaction context…
        </p>
      )}
      {selectionError && (
        <p className="m-muted" role="alert">
          {selectionError}
        </p>
      )}
      {selected ? (
        <>
          <div className="m-detail-amount">
            {currency(selected.amount)}
            <span className={`m-status ${selected.status}`}>
              {selected.status}
            </span>
          </div>
          <div className="m-transfer">
            <span>
              <ArrowUpRight size={14} /> From
              <strong>{selected.source_account}</strong>
            </span>
            <span>
              <ArrowDownLeft size={14} /> To
              <strong>{selected.destination_account}</strong>
            </span>
          </div>
          <dl>
            <dt>Transaction</dt>
            <dd className="m-mono">{selected.transaction_id}</dd>
            <dt>Timestamp</dt>
            <dd>
              {new Date(selected.timestamp)
                .toISOString()
                .replace("T", " ")
                .slice(0, 19)}{" "}
              UTC
            </dd>
            <dt>Detection status</dt>
            <dd>{detectionLabel(detection)}</dd>
            <dt>Risk severity</dt>
            <dd>
              {alerts.find((a) => a.transactionId === selected.transaction_id)
                ?.severity ??
                (detection?.combined === undefined
                  ? "Unavailable"
                  : detection.combined >= 70
                    ? "High"
                    : detection.combined >= 40
                      ? "Moderate"
                      : "Low")}
            </dd>
            <dt>Detector decision</dt>
            <dd>{detection?.decision || "Unavailable"}</dd>
            <dt>Analyst action</dt>
            <dd>None recorded</dd>
            <dt>Synthetic truth</dt>
            <dd>
              {truth.get(selected.transaction_id)?.truth ?? "Unavailable"}
            </dd>
          </dl>
          <div className="m-scores">
            {[
              ["Graph", detection?.graph],
              ["Scam", detection?.scam],
              ["Combined", detection?.combined],
            ].map(([name, value]) => (
              <div key={String(name)}>
                <span>{name}</span>
                <strong className={tone(value as number | undefined)}>
                  {risk(value as number | undefined)}
                </strong>
                <i>
                  <b style={{ width: `${value ?? 0}%` }} />
                </i>
              </div>
            ))}
          </div>
          <p className="m-score-note">
            Scores are detector outputs, not calibrated probabilities. Graph
            risk describes the rolling session window (0–1 normalized to 100),
            not an individual payment. A graph flag requires this transaction in
            the detector’s suspicious transaction list. Specialist scores use
            0–100.
          </p>
          <h3>Evidence</h3>
          {[
            ...new Set([
              ...(detection?.reasons ?? []),
              ...(detection?.scamReasons ?? []),
            ]),
          ].length ? (
            <ul className="m-evidence">
              {[
                ...new Set([
                  ...(detection?.reasons ?? []),
                  ...(detection?.scamReasons ?? []),
                ]),
              ].map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : (
            <p className="m-muted">
              No detector evidence received. A missing score does not mean a
              payment is safe.
            </p>
          )}
          {suspicious.length > 0 && (
            <p className="m-muted">
              Detector-identified accounts:{" "}
              {suspicious.map((a) => a.split("-").at(-1)).join(", ")}. This is a
              suspicious pattern, not a confirmed mule classification.
            </p>
          )}
          {account && (
            <div className="m-account">
              <h3>Selected account · {account.split("-").at(-1)}</h3>
              <p className="m-mono">{account}</p>
              <p>
                {
                  transactions.filter(
                    (t) =>
                      t.source_account === account ||
                      t.destination_account === account,
                  ).length
                }{" "}
                payments in retained history.
              </p>
            </div>
          )}
          <h3>
            Connected payments <span className="m-count">{related.length}</span>
          </h3>
          <div className="m-related">
            {related.slice(0, 6).map((t) => (
              <button
                key={t.transaction_id}
                onClick={() => choose(t.transaction_id)}
              >
                <span>
                  {t.source_account.split("-").at(-1)} →{" "}
                  {t.destination_account.split("-").at(-1)}
                </span>
                <strong>{currency(t.amount)}</strong>
                <ChevronRight size={12} />
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="m-empty">
          <Search size={24} />
          <h3>Select a transaction</h3>
          <p>
            Inspect payment status, account relationships and actual detector
            evidence here.
          </p>
        </div>
      )}
    </section>
  );
  const network = (
    <section className="m-panel m-network" key="network">
      <div className="m-panel-title">
        <div>
          <h2>Money-flow investigation</h2>
          <p>
            {selected
              ? `${selected.transaction_id} · ${related.length} connected payments`
              : "Select a transaction to begin"}
          </p>
        </div>
        <span className="m-legend">
          <i /> Selected transfer
        </span>
      </div>
      <MoneyGraph
        transactions={related}
        selected={selected?.transaction_id}
        suspicious={suspicious}
        onTransaction={choose}
        onAccount={setAccount}
      />
      <div className="m-network-footer">
        <span>
          <i className="m-dot" /> Bounded account neighborhood · max
          28 transfers
        </span>
        <span>Click an account or transfer to inspect</span>
      </div>
    </section>
  );
  return (
    <div className={`m-app m-experience m-${page.toLowerCase()}-page${monitoringPage ? " m-monitoring" : ""}${page === "Overview" ? " m-overview" : ""}`}>
      <a className="m-skip-link" href="#main-content">Skip to main content</a>
      <div className="m-workspace">
        <NavigationShell
          page={page}
          alertCount={alerts.length}
          connection={connection}
          onNavigate={navigate}
          onRefresh={refresh}
        />
        <main className="m-main" id="main-content" tabIndex={-1}>
          <section className="m-heading">
            <div>
              <span className="m-eyebrow">ARGUS CSI / MONITORING</span>
              <h1>
                {page === "Overview"
                  ? "Financial activity overview"
                  : page === "Demo"
                    ? "Synthetic scenario library"
                    : page === "Lab"
                      ? "Intelligence Lab"
                      : page}
              </h1>
              <p>
                {page === "Overview"
                  ? "Follow the money. Surface the signals. Investigate with context."
                  : page === "Transactions"
                    ? `${inspection ? "Stored investigation context" : "Current synthetic run"} · ${transactions.length} retained payments`
                    : page === "Alerts"
                      ? `${alerts.length} retained alerts · current synthetic run · ${scenario.name}`
                      : page === "Investigations"
                        ? "Persistent financial and historical cross-domain records · independent of the current run"
                        : `Synthetic workspace · ${scenario.name}`}
              </p>
            </div>
            <div className="m-source">
              <button className="active">{DATA_SOURCES.synthetic.label}</button>
              <button disabled title="No real transaction provider configured">
                {DATA_SOURCES.real.label}
              </button>
            </div>
          </section>
          {(error || caseError) && (
            <div className="m-notice" role="alert">
              {error || caseError}
              <button onClick={refresh}>Retry health check</button>
            </div>
          )}
          {(inspection || openedCase || selectionError) && (
            <div className="m-notice">
              <span>
                {inspection
                  ? "Viewing stored investigation context. Live run controls remain separate."
                  : selectionError || "Loading investigation context"}
              </span>
              <button onClick={returnToRun}>Return to live run</button>
            </div>
          )}
          <section className="m-controls" aria-label="Simulation controls">
            <div className="m-run-summary">
              <span className={`m-status ${running ? "completed" : "pending"}`}>
                {running
                  ? "Running"
                  : cursor >= config.count
                    ? "Complete"
                    : cursor
                      ? "Paused"
                      : "Ready"}
              </span>
              <strong>{scenario.name}</strong>
              <span className="m-muted">
                Seed {config.seed} · {cursor}/{config.count} submitted
              </span>
            </div>
            <div className="m-run-actions">
              <select
                aria-label="Simulation speed"
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
              >
                <option value={0.5}>0.5 tx/s</option>
                <option value={1}>1 tx/s</option>
                <option value={2}>2 tx/s</option>
                <option value={4}>4 tx/s max</option>
              </select>
              <button onClick={() => reset()} aria-label="Reset simulation">
                <RefreshCw size={14} /> Reset
              </button>
              <button
                className="m-primary"
                disabled={cursor >= config.count}
                onClick={() => setRunning((v) => !v)}
              >
                {running ? <Pause size={14} /> : <Play size={14} />}{" "}
                {running ? "Pause" : cursor ? "Resume" : "Start simulation"}
              </button>
            </div>
          </section>
          {page === "Demo" ? (
            <>
              <section className="m-demo-guide m-panel" aria-label="Demo workflow">
                <span className="m-eyebrow">GUIDED DEMONSTRATION</span>
                <h2>Present the evidence, step by step.</h2>
                <p>Load a scenario, start monitoring explicitly, then follow its payments, detector signals, and account relationships.</p>
                <ol><li><span>01</span>Choose a scenario</li><li><span>02</span>Start the simulation</li><li><span>03</span>Inspect the evidence</li></ol>
              </section>
              <div className="m-demo-config m-panel">
                <span className="m-eyebrow">RUN CONFIGURATION</span>
                <h2>Configure a reproducible run</h2>
                <p>
                  Reset or replay creates a new isolated session. No existing
                  data is deleted. One request at a time; selected speed is a
                  maximum.
                </p>
                <div>
                  <label>
                    Random seed
                    <input
                      type="number"
                      value={seed}
                      onChange={(e) => setSeed(Number(e.target.value) || 0)}
                    />
                  </label>
                  <label>
                    Payments (20–5,000)
                    <input
                      type="number"
                      min="20"
                      max="5000"
                      value={count}
                      onChange={(e) =>
                        setCount(
                          Math.min(5000, Math.max(20, Number(e.target.value))),
                        )
                      }
                    />
                  </label>
                  <label>
                    Accounts (40–400)
                    <input
                      type="number"
                      min="40"
                      max="400"
                      value={accounts}
                      onChange={(e) =>
                        setAccounts(
                          Math.min(400, Math.max(40, Number(e.target.value))),
                        )
                      }
                    />
                  </label>
                  <button onClick={() => reset()}>Apply & replay seed</button>
                  <button onClick={() => reset("random", true)}>
                    Randomize seed
                  </button>
                </div>
                <small>
                  Logical start: {config.start} · {config.session}. Scenario
                  timestamps advance independently of network delivery speed.
                </small>
              </div>
              <div className="m-demo-section-heading"><h2>Scenario library</h2><p>Loading a scenario prepares an isolated run. Start it when you are ready.</p></div>
              <div className="m-scenario-grid">
                {SCENARIOS.map((s, i) => (
                  <article
                    className={`m-panel m-scenario ${config.scenario === s.id ? "active" : ""}`}
                    key={s.id}
                  >
                    <span className="m-eyebrow">
                      SCENARIO {String(i + 1).padStart(2, "0")}
                    </span>
                    <h2>{s.name}</h2>
                    {config.scenario === s.id && <span className="m-scenario-selection">Selected scenario</span>}
                    <p>{s.description}</p>
                    <small>Expected pattern</small>
                    <p>{s.expected}</p>
                    <button
                      onClick={() => {
                        reset(s.id);
                        setPage("Overview");
                      }}
                    >
                      Load scenario <ChevronRight size={14} />
                    </button>
                  </article>
                ))}
                <article className="m-panel m-scenario">
                  <span className="m-eyebrow">LEGACY DEMONSTRATION</span>
                  <h2>Canonical Demo</h2>
                  <p>
                    The original four-account financial and infrastructure
                    correlation workflow, with its existing backend response
                    controls.
                  </p>
                  <button onClick={() => setCanonical((v) => !v)}>
                    {canonical ? "Close" : "Open"} Canonical Demo
                  </button>
                </article>
              </div>
              {canonical && (
                <div className="m-legacy">
                  <CanonicalDemo />
                </div>
              )}
            </>
          ) : page === "Investigations" ? (
            <CaseBrowser
              financial={financialCases}
              historical={incidents}
              selectedKey={caseSelection}
              onSelect={setCaseSelection}
              onOpen={(item) => {
                setCaseSelection("case_id" in item ? `financial:${item.case_id}` : `historical:${item.incident_id}`);
                void openCase(item);
              }}
              onRefresh={refresh}
              audit={audit}
              busy={caseBusy}
              formatRisk={risk}
              onApprove={(incident) => {
                setCaseBusy(true);
                void approveIncident(incident.incident_id)
                  .then((r) => {
                    setAudit((v) => ({ ...v, [incident.incident_id]: r.audit_events }));
                    refresh();
                  })
                  .catch((e) => setCaseError(String(e)))
                  .finally(() => setCaseBusy(false));
              }}
              onAudit={(incident) => {
                void loadAuditEvents(incident.incident_id)
                  .then((events) => setAudit((v) => ({ ...v, [incident.incident_id]: events })))
                  .catch((e) => setCaseError(String(e)));
              }}
            />
          ) : page === "Lab" ? (
            <section className="m-panel m-lab-intro">
              <FlaskConical size={28} />
              <span className="m-eyebrow">ANALYST SANDBOX</span>
              <h2>Analyze a dataset</h2>
              <p>
                Use the existing Intelligence Lab for JSON transactions,
                baseline history and infrastructure correlation.
              </p>
              <button className="m-primary" data-lab-launcher onClick={() => setLabOpen(true)}>
                Open Intelligence Lab
              </button>
              <div className="m-lab-capabilities"><article><span>01</span><h3>Prepare inputs</h3><p>Edit transactions, behavioral history, and optional host telemetry as JSON.</p></article><article><span>02</span><h3>Run existing detectors</h3><p>Submit the dataset for financial analysis and available cross-domain correlation.</p></article><article><span>03</span><h3>Read the result</h3><p>Inspect returned scores, explanations, and persisted incident history.</p></article></div>
            </section>
          ) : (
            <>
              <section className="m-kpis">
                {[
                  [
                    "Transactions monitored",
                    runTransactions.length,
                    "Current run · retained history",
                    Wallet,
                  ],
                  [
                    "Flagged transactions",
                    flagged,
                    "Actual detector predictions",
                    Shield,
                  ],
                  [
                    "Active alerts",
                    alerts.length,
                    "Current run · latest 500 events",
                    Bell,
                  ],
                  [
                    "High-risk investigations",
                    caseError
                      ? "—"
                      : incidents.filter(
                          (i) =>
                            (i.severity === "high" ||
                              i.severity === "critical") &&
                            i.status !== "contained",
                        ).length +
                        financialCases.filter((c) => c.status === "open")
                          .length,
                    "Each case source · latest 50",
                    Network,
                  ],
                  [
                    "Detector health",
                    status
                      ? `${[status.graph, status.system].filter((s) => s.availability === "online").length}/2`
                      : "—",
                    status
                      ? `Graph: ${status.graph.origin} · System: ${status.system.origin}`
                      : "Health unavailable",
                    Activity,
                  ],
                ].map(([label, value, caption, Icon], index) => {
                  const Glyph = Icon as typeof Wallet;
                  return (
                    <article className={`m-panel${index < 4 ? " m-kpi-enhanced" : ""}`} data-health={index === 4 && value === "2/2" ? "healthy" : undefined} key={String(label)}>
                      <div>
                        <span>{String(label)}</span>
                        <Glyph size={16} />
                      </div>
                      <strong>{String(value)}</strong>
                      {index < 4 && <KpiTrend trend={index === 3 ? caseTrend : activityTrends[index]} tone={index === 0 ? "volume" : index === 1 ? "danger" : "warning"} />}
                      <small>{String(caption)}</small>
                    </article>
                  );
                })}
              </section>
              <div className="m-operational-workspace">
              {page === "Alerts" ? (
                <section className="m-panel m-alert-review" id="alert-queue" tabIndex={-1} aria-label="Current run alerts">
                  <div className="m-panel-title">
                    <div>
                      <h2>Alert evidence review <span className="m-count">{alerts.length}</span></h2>
                      <p>
                        Severity then recency · selecting an alert opens its
                        payment context
                      </p>
                      {selectedAlert && <a className="m-selected-evidence-link" href="#transaction-inspector">Selected evidence ↓</a>}
                    </div>
                    <Bell size={18} />
                  </div>
                  <div className="m-alert-review-list">
                  {alerts.length ? (
                    alerts.map(alertItem)
                  ) : (
                    <div className="m-empty">
                      <Bell size={25} />
                      <h3>No alerts received</h3>
                      <p>
                        Alerts appear when the backend detects a threshold
                        breach or an analysis failure.
                      </p>
                    </div>
                  )}
                  </div>
                </section>
              ) : (
                <div
                  className={
                    page === "Transactions" ? "m-full-table" : "m-monitor-grid"
                  }
                >
                  {table}
                  {page !== "Transactions" && (
                    <section className="m-panel m-alerts">
                      <div className="m-panel-title">
                        <div>
                          <h2>
                            Priority alert queue{" "}
                            <span className="m-count">{alerts.length}</span>
                          </h2>
                          <p>Detector signals · current run</p>
                        </div>
                        <Bell size={17} />
                      </div>
                      <div className="m-alert-list">
                        {alerts.length ? (
                          alerts.slice(0, 30).map(alertItem)
                        ) : (
                          <div className="m-empty">
                            <Shield size={25} />
                            <h3>No alerts received</h3>
                            <p>
                              New graph, scam and availability alerts appear
                              here.
                            </p>
                          </div>
                        )}
                      </div>
                      <button
                        className="m-all-alerts"
                        onClick={() => setPage("Alerts")}
                      >
                        View all alerts <ChevronRight size={13} />
                      </button>
                    </section>
                  )}
                </div>
              )}
              <div className="m-investigation-grid">
                {page === "Alerts" ? [details, network] : [network, details]}
              </div>
              </div>
            </>
          )}
          <footer className="m-footer">
            <span>
              <Shield size={12} /> Synthetic financial intelligence · ARGUS CSI
            </span>
            <span>
              <CircleHelp size={12} /> Detector scores describe observed
              patterns; synthetic truth is separate.
            </span>
          </footer>
        </main>
      </div>
      <IntelligenceLab
        open={labOpen}
        incidents={incidents}
        onClose={() => setLabOpen(false)}
        onAnalyze={async (request) => {
          const response = await analyzeData(request);
          refresh();
          return response;
        }}
      />
    </div>
  );
}
