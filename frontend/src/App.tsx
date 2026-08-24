import type { Core } from "cytoscape";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Ban,
  Check,
  ChevronRight,
  CircleDot,
  Clock3,
  Cpu,
  Database,
  FlaskConical,
  Fingerprint,
  LockKeyhole,
  Network,
  Play,
  Radar,
  RefreshCw,
  ServerCog,
  Shield,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
  Wifi,
  X,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeData,
  approveIncident,
  loadDetectorStatus,
  loadIncidents,
  loadNormalState,
  loadPlatformMetrics,
  simulateAttack,
} from "./api";
import { IntelligenceLab } from "./IntelligenceLab";
import type {
  AnalysisRequest,
  AnalysisResponse,
  AttackResponse,
  AuditEvent,
  DetectorComponentStatus,
  DetectorStatus,
  Incident,
  PlatformMetrics,
  Transaction,
} from "./types";

type DemoPhase = 0 | 1 | 2 | 3 | 4 | 5 | 6;

const PHASE_LABELS = [
  "Environment secure",
  "Account compromise",
  "Mule transfers",
  "Graph anomaly",
  "System anomaly",
  "Attack correlated",
  "Threat contained",
] as const;

const NORMAL_TRANSACTIONS: Transaction[] = [
  {
    transaction_id: "TX-0001",
    timestamp: "2026-08-17T15:20:00Z",
    source_account: "ACC-101",
    destination_account: "ACC-050",
    amount: 1250,
    currency: "INR",
    device_id: "DEV-01",
    ip_address: "203.0.113.10",
    status: "completed",
  },
];

function classNames(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatTime(timestamp: string) {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(timestamp));
}

export function detectorSourceLabel(status: DetectorComponentStatus | undefined) {
  if (!status) return "CHECKING";
  if (status.origin === "service" && status.mode !== "unknown") {
    return `${status.mode.toUpperCase()} SERVICE`;
  }
  if (status.origin === "service") return "SERVICE";
  if (status.origin === "last_known") return "LAST KNOWN";
  if (status.origin === "fixture") return "FIXTURE";
  return "UNAVAILABLE";
}

function TransactionGraph({
  transactions,
  suspiciousAccounts,
  suspiciousTransactions,
}: {
  transactions: Transaction[];
  suspiciousAccounts: string[];
  suspiciousTransactions: string[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    let graph: Core | undefined;
    let resizeObserver: ResizeObserver | undefined;
    let cancelled = false;

    const accountIds = Array.from(
      new Set(
        transactions.flatMap((transaction) => [
          transaction.source_account,
          transaction.destination_account,
        ]),
      ),
    );
    const suspicious = new Set(suspiciousAccounts);
    const suspiciousEdges = new Set(suspiciousTransactions);
    const elements = [
      ...accountIds.map((account) => ({
        data: { id: account, label: account },
        classes: suspicious.has(account) ? "suspicious" : "normal",
      })),
      ...transactions.map((transaction) => ({
        data: {
          id: transaction.transaction_id,
          source: transaction.source_account,
          target: transaction.destination_account,
          label: formatCurrency(transaction.amount),
        },
        classes: suspiciousEdges.has(transaction.transaction_id) ? "attack-edge" : "normal-edge",
      })),
    ];

    const renderGraph = async () => {
      const { default: cytoscape } = await import("cytoscape");
      if (cancelled || !containerRef.current) return;

      graph = cytoscape({
        container: containerRef.current,
        elements,
        userZoomingEnabled: true,
        minZoom: 0.65,
        maxZoom: 1.6,
        style: [
        {
          selector: "node",
          style: {
            width: 58,
            height: 58,
            label: "data(label)",
            color: "#d8e7e2",
            "font-size": 10,
            "font-family": "IBM Plex Mono, monospace",
            "font-weight": 600,
            "text-valign": "center",
            "text-halign": "center",
            "background-color": "#142b27",
            "border-color": "#2e7566",
            "border-width": 2,
          },
        },
        {
          selector: "node.suspicious",
          style: {
            "background-color": "#321716",
            "border-color": "#f06456",
            color: "#ffd7d0",
            "border-width": 3,
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.8,
            label: "data(label)",
            color: "#809b94",
            "font-size": 9,
            "font-family": "IBM Plex Mono, monospace",
            "text-background-color": "#0c1715",
            "text-background-opacity": 1,
            "text-background-padding": "3px",
          },
        },
        {
          selector: "edge.normal-edge",
          style: {
            "line-color": "#2e7566",
            "target-arrow-color": "#2e7566",
          },
        },
        {
          selector: "edge.attack-edge",
          style: {
            "line-color": "#e04f43",
            "target-arrow-color": "#e04f43",
            width: 3,
          },
        },
        ],
        layout: {
          name: "breadthfirst",
          directed: true,
          spacingFactor: 1.25,
          padding: 24,
        },
      });

      resizeObserver = new ResizeObserver(() => {
        graph?.resize();
        graph?.fit(undefined, 24);
      });
      resizeObserver.observe(containerRef.current);
    };

    void renderGraph();

    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      graph?.destroy();
    };
  }, [suspiciousAccounts, suspiciousTransactions, transactions]);

  return <div className="graph-canvas" ref={containerRef} aria-label="Transaction network graph" />;
}

function ScoreBar({ score, tone }: { score: number; tone: "mint" | "danger" }) {
  return (
    <div className="score-wrap">
      <div className="score-track" aria-label={`Risk score ${Math.round(score * 100)} percent`}>
        <span className={`score-fill ${tone}`} style={{ width: `${score * 100}%` }} />
      </div>
      <strong>{Math.round(score * 100)}</strong>
      <span>/100</span>
    </div>
  );
}

function SignalCard({
  icon,
  eyebrow,
  title,
  score,
  findings,
  visible,
  status,
}: {
  icon: React.ReactNode;
  eyebrow: string;
  title: string;
  score: number;
  findings: string[];
  visible: boolean;
  status?: DetectorComponentStatus;
}) {
  return (
    <article className={classNames("signal-card", visible && "visible")}>
      <div className="signal-heading">
        <span className="icon-box">{icon}</span>
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h3>{visible ? title : "Signal nominal"}</h3>
        </div>
        <span
          className={classNames("source-pill", status?.availability ?? "offline")}
          title={status?.detail}
        >
          {detectorSourceLabel(status)}
        </span>
      </div>
      {status && status.availability !== "online" && (
        <div className="detector-notice" role="status">
          <AlertTriangle size={13} />
          <span>{status.detail}</span>
        </div>
      )}
      <ScoreBar score={visible ? score : 0.08} tone={visible ? "danger" : "mint"} />
      <ul className="finding-list">
        {(visible ? findings : ["No anomalous behavior detected", "Baseline profile active"]).map(
          (finding) => (
            <li key={finding}>
              {visible ? <AlertTriangle size={14} /> : <Check size={14} />}
              <span>{finding}</span>
            </li>
          ),
        )}
      </ul>
    </article>
  );
}

function IncidentPanel({ incident, phase }: { incident: Incident | null; phase: DemoPhase }) {
  if (!incident || phase < 5) {
    return (
      <section className="panel incident-panel empty-incident">
        <div className="empty-radar">
          <Radar size={38} strokeWidth={1.4} />
          <span />
        </div>
        <span className="eyebrow">ARGUS CORRELATION ENGINE</span>
        <h2>No active incident</h2>
        <p>Financial and infrastructure signals are continuously evaluated for shared evidence.</p>
        <div className="correlation-idle">
          <CircleDot size={14} /> Waiting for correlated signals
        </div>
      </section>
    );
  }

  return (
    <section className={classNames("panel incident-panel", phase === 6 && "contained")}>
      <div className="incident-topline">
        <span className={classNames("severity-pill", phase === 6 && "safe")}>
          {phase === 6 ? <ShieldCheck size={14} /> : <ShieldAlert size={14} />}
          {phase === 6 ? "CONTAINED" : incident.severity.toUpperCase()}
        </span>
        <span className="mono muted">{incident.incident_id}</span>
      </div>
      <span className="eyebrow">ARGUS VERDICT</span>
      <h2>{phase === 6 ? "Coordinated attack contained" : "Coordinated attack detected"}</h2>
      <div className="confidence-row">
        <span>Correlation confidence</span>
        <strong>{Math.round(incident.confidence * 100)}%</strong>
      </div>
      <div className="confidence-track">
        <span style={{ width: `${incident.confidence * 100}%` }} />
      </div>
      <p className="incident-summary">{incident.summary}</p>
      <div className="evidence-block">
        <span className="eyebrow">SHARED EVIDENCE</span>
        {incident.evidence.slice(-2).map((evidence) => (
          <div className="evidence-row" key={evidence}>
            <Fingerprint size={15} />
            <span>{evidence}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function App() {
  const [phase, setPhase] = useState<DemoPhase>(0);
  const [normalTransactions, setNormalTransactions] = useState<Transaction[]>(NORMAL_TRANSACTIONS);
  const [attack, setAttack] = useState<AttackResponse | null>(null);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [detectorStatus, setDetectorStatus] = useState<DetectorStatus | null>(null);
  const [metrics, setMetrics] = useState<PlatformMetrics | null>(null);
  const [incidentHistory, setIncidentHistory] = useState<Incident[]>([]);
  const [labOpen, setLabOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [utcTime, setUtcTime] = useState(new Date());
  const timersRef = useRef<number[]>([]);

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((timer) => window.clearTimeout(timer));
    timersRef.current = [];
  }, []);

  const refreshPlatform = useCallback(async () => {
    const [nextMetrics, nextIncidents] = await Promise.all([
      loadPlatformMetrics(),
      loadIncidents(20),
    ]);
    setMetrics(nextMetrics);
    setIncidentHistory(nextIncidents);
  }, []);

  const resetDemo = useCallback(async () => {
    clearTimers();
    setLoading(true);
    setError(null);
    try {
      const [response, status, nextMetrics, nextIncidents] = await Promise.all([
        loadNormalState(),
        loadDetectorStatus(),
        loadPlatformMetrics(),
        loadIncidents(20),
      ]);
      setNormalTransactions(response.transactions);
      setDetectorStatus(status);
      setMetrics(nextMetrics);
      setIncidentHistory(nextIncidents);
      setAttack(null);
      setIncident(null);
      setAuditEvents([]);
      setPhase(0);
    } catch {
      setError("ARGUS backend is offline. Start the FastAPI service on port 8000.");
    } finally {
      setLoading(false);
    }
  }, [clearTimers]);

  const refreshDetectorStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDetectorStatus(await loadDetectorStatus());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Detector health check failed.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void resetDemo();
    const clock = window.setInterval(() => setUtcTime(new Date()), 1000);
    return () => {
      window.clearInterval(clock);
      clearTimers();
    };
  }, [clearTimers, resetDemo]);

  const startAttack = async () => {
    clearTimers();
    setLoading(true);
    setError(null);
    setAuditEvents([]);
    try {
      const response = await simulateAttack();
      setAttack(response);
      setDetectorStatus(response.detector_status);
      setIncident(response.incident);
      void refreshPlatform();
      setPhase(1);
      [2, 3, 4, 5].forEach((nextPhase, index) => {
        timersRef.current.push(
          window.setTimeout(() => setPhase(nextPhase as DemoPhase), 850 * (index + 1)),
        );
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Attack simulation failed.");
    } finally {
      setLoading(false);
    }
  };

  const runCustomAnalysis = async (request: AnalysisRequest): Promise<AnalysisResponse> => {
    clearTimers();
    const response = await analyzeData(request);
    setDetectorStatus(response.detector_status);
    setAuditEvents([]);
    if (response.system_signal && response.incident) {
      setAttack({
        mode: "attack",
        transactions: response.transactions,
        graph_signal: response.graph_signal,
        system_signal: response.system_signal,
        detector_status: response.detector_status,
        incident: response.incident,
      });
      setIncident(response.incident);
      setPhase(5);
    }
    await refreshPlatform();
    return response;
  };

  const approve = async () => {
    if (!incident) return;
    setLoading(true);
    setError(null);
    try {
      const response = await approveIncident(incident.incident_id);
      setIncident(response.incident);
      setAuditEvents(response.audit_events);
      setPhase(6);
      await refreshPlatform();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Containment approval failed.");
    } finally {
      setLoading(false);
    }
  };

  const visibleTransactions = phase >= 2 && attack ? attack.transactions : normalTransactions;
  const graphVisible = phase >= 3 && attack !== null;
  const systemVisible = phase >= 4 && attack !== null;
  const attackTotal = attack?.transactions.reduce((sum, transaction) => sum + transaction.amount, 0) ?? 0;
  const suspiciousAccounts = attack?.graph_signal.suspicious_accounts ?? [];
  const suspiciousTransactions = attack?.graph_signal.suspicious_transactions ?? [];
  const originAccount = attack?.transactions[0]?.source_account ?? "—";
  const deviceId = attack?.transactions[0]?.device_id ?? "—";

  const timeline = useMemo(
    () => [
      {
        phase: 1,
        time: attack ? formatTime(attack.transactions[0]?.timestamp ?? attack.graph_signal.timestamp) : "--:--:--",
        title: "New device session",
        detail: attack ? `${attack.transactions[0]?.device_id ?? "Unknown device"} · ${attack.transactions[0]?.ip_address ?? "Unknown IP"}` : "Awaiting data",
        icon: <Fingerprint size={15} />,
      },
      {
        phase: 2,
        time: attack ? formatTime(attack.transactions.at(-1)?.timestamp ?? attack.graph_signal.timestamp) : "--:--:--",
        title: humanize(attack?.graph_signal.anomaly_type ?? "Transaction sequence"),
        detail: suspiciousAccounts.slice(0, 4).join(" → ") || "Awaiting graph analysis",
        icon: <Zap size={15} />,
      },
      {
        phase: 3,
        time: attack ? formatTime(attack.graph_signal.timestamp) : "--:--:--",
        title: "Graph anomaly detected",
        detail: `Financial risk ${Math.round((attack?.graph_signal.risk_score ?? 0) * 100)}/100`,
        icon: <Network size={15} />,
      },
      {
        phase: 4,
        time: attack ? formatTime(attack.system_signal.timestamp) : "--:--:--",
        title: "System anomaly detected",
        detail: `Infrastructure risk ${Math.round((attack?.system_signal.risk_score ?? 0) * 100)}/100`,
        icon: <Cpu size={15} />,
      },
      {
        phase: 5,
        time: incident ? formatTime(incident.timestamp) : "--:--:--",
        title: "Signals correlated",
        detail: incident ? `${humanize(incident.severity)} incident ${incident.incident_id}` : "Awaiting correlation",
        icon: <ShieldAlert size={15} />,
      },
    ],
    [attack, incident, suspiciousAccounts],
  );

  const detectorsHealthy = detectorStatus?.graph.availability === "online"
    && detectorStatus.system.availability === "online";

  return (
    <div className={classNames("app-shell", phase >= 5 && phase < 6 && "critical-mode")}>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark"><Shield size={22} /></span>
          <div>
            <strong>ARGUS</strong>
            <span>FINANCIAL SOC</span>
          </div>
        </div>
        <div className="topbar-center">
          <span className={classNames("system-status", detectorStatus && !detectorsHealthy && "degraded")}>
            <i /> {detectorsHealthy ? "SYSTEM OPERATIONAL" : detectorStatus ? "DETECTORS DEGRADED" : "CHECKING SERVICES"}
          </span>
          <span className="environment">LIVE INTELLIGENCE · SAFE LAB</span>
        </div>
        <div className="topbar-actions">
          <span className="utc-clock"><Clock3 size={14} /> {utcTime.toISOString().slice(11, 19)} UTC</span>
          <button className="icon-button" onClick={() => void resetDemo()} aria-label="Reset demonstration" disabled={loading}>
            <RefreshCw size={16} className={loading ? "spin" : ""} />
          </button>
          <button className="icon-button" onClick={() => void refreshDetectorStatus()} aria-label="Retry detector health checks" disabled={loading} title="Retry detector health checks">
            <Activity size={16} />
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <AlertTriangle size={16} />
          <span>{error}</span>
          <button onClick={() => setError(null)} aria-label="Dismiss error"><X size={16} /></button>
        </div>
      )}

      <main>
        <section className="command-strip">
          <div className="command-copy">
            <span className={classNames("threat-orb", phase >= 1 && phase < 6 && "alert", phase === 6 && "safe")}>
              {phase === 6 ? <ShieldCheck size={24} /> : phase >= 1 ? <ShieldAlert size={24} /> : <Radar size={24} />}
            </span>
            <div>
              <span className="eyebrow">CURRENT OPERATING STATE</span>
              <h1>{PHASE_LABELS[phase]}</h1>
            </div>
          </div>
          <div className="command-stats">
            <div><span>Accounts observed</span><strong>{metrics?.accounts_observed.toLocaleString() ?? "—"}</strong></div>
            <div><span>Transactions ingested</span><strong>{metrics?.transactions_ingested.toLocaleString() ?? "—"}</strong></div>
            <div><span>Open incidents</span><strong className={(metrics?.incidents_open ?? 0) > 0 ? "danger-text" : ""}>{metrics?.incidents_open.toLocaleString() ?? "—"}</strong></div>
          </div>
          <div className="command-actions">
            <button className="lab-button" onClick={() => setLabOpen(true)}>
              <FlaskConical size={17} /> DATA LAB
            </button>
            <button className="simulate-button" onClick={() => void startAttack()} disabled={loading || (phase > 0 && phase < 6)}>
              {loading ? <RefreshCw size={17} className="spin" /> : <Play size={17} fill="currentColor" />}
              {phase === 0 || phase === 6 ? "CANONICAL DEMO" : "ANALYSIS ACTIVE"}
            </button>
          </div>
        </section>

        <section className="dashboard-grid">
          <aside className="left-column">
            <section className="panel timeline-panel">
              <div className="panel-heading">
                <div><span className="eyebrow">LIVE SEQUENCE</span><h2>Attack timeline</h2></div>
                <Activity size={18} />
              </div>
              <div className="timeline">
                <div className="timeline-event active normal-event">
                  <span className="timeline-dot"><Check size={13} /></span>
                  <div><time>15:29:42</time><strong>Baseline verified</strong><p>Behavior within expected range</p></div>
                </div>
                {timeline.map((event) => (
                  <div className={classNames("timeline-event", phase >= event.phase && "active", phase === 6 && event.phase < 5 && "resolved")} key={event.title}>
                    <span className="timeline-dot">{event.icon}</span>
                    <div><time>{event.time}</time><strong>{event.title}</strong><p>{event.detail}</p></div>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel asset-panel">
              <div className="panel-heading compact">
                <div><span className="eyebrow">AT-RISK VALUE</span><h2>{formatCurrency(phase >= 2 ? attackTotal : 0)}</h2></div>
                <Database size={18} />
              </div>
              <div className="asset-row"><span>Origin account</span><strong>{phase >= 1 ? originAccount : "—"}</strong></div>
              <div className="asset-row"><span>Suspicious transfers</span><strong>{phase >= 2 ? suspiciousTransactions.length : "0"}</strong></div>
              <div className="asset-row"><span>Affected accounts</span><strong>{phase >= 2 ? suspiciousAccounts.length : "0"}</strong></div>
            </section>
          </aside>

          <section className="center-column">
            <section className="panel graph-panel">
              <div className="panel-heading">
                <div><span className="eyebrow">FINANCIAL INTELLIGENCE</span><h2>Transaction network</h2></div>
                <div className="graph-legend"><span><i className="normal-node" /> Normal</span><span><i className="risk-node" /> Suspicious</span></div>
              </div>
              <TransactionGraph
                transactions={visibleTransactions}
                suspiciousAccounts={phase >= 2 && phase < 6 ? suspiciousAccounts : []}
                suspiciousTransactions={phase >= 2 && phase < 6 ? suspiciousTransactions : []}
              />
              <div className="graph-footnote">
                <span><Wifi size={14} /> {phase >= 1 ? `Observed device: ${deviceId}` : "Known devices only"}</span>
                <span><Network size={14} /> {phase >= 2 ? `${visibleTransactions.length} linked transfers` : "No unusual paths"}</span>
              </div>
            </section>

            <div className="signal-grid">
              <SignalCard
                icon={<Network size={19} />}
                eyebrow="PRATHAM · GRAPH ML"
                title="Mule network anomaly"
                score={attack?.graph_signal.risk_score ?? 0}
                findings={attack?.graph_signal.reasons ?? []}
                visible={graphVisible}
                status={detectorStatus?.graph}
              />
              <SignalCard
                icon={<ServerCog size={19} />}
                eyebrow="NITIN · eBPF"
                title="Payment service anomaly"
                score={attack?.system_signal.risk_score ?? 0}
                findings={attack?.system_signal.indicators ?? []}
                visible={systemVisible}
                status={detectorStatus?.system}
              />
            </div>
          </section>

          <aside className="right-column">
            <IncidentPanel incident={incident} phase={phase} />

            <section className="panel response-panel">
              <div className="panel-heading">
                <div><span className="eyebrow">RESPONSE POLICY</span><h2>Containment</h2></div>
                <LockKeyhole size={18} />
              </div>
              {incident && phase >= 5 ? (
                <>
                  <div className="action-list">
                    {incident.recommended_actions.map((action) => (
                      <div className="action-row" key={`${action.action}-${action.target}`}>
                        <span className={classNames("action-icon", phase === 6 && "done")}>
                          {phase === 6 ? <Check size={14} /> : action.action === "isolate_service" ? <Ban size={14} /> : <LockKeyhole size={14} />}
                        </span>
                        <div><strong>{humanize(action.action)}</strong><span>{action.target}</span></div>
                        <span className="action-state">{phase === 6 ? "DONE" : "PENDING"}</span>
                      </div>
                    ))}
                  </div>
                  {phase === 5 && incident.status === "awaiting_approval" && (
                    <button className="approve-button" onClick={() => void approve()} disabled={loading}>
                      <UserCheck size={17} /> APPROVE CONTAINMENT <ChevronRight size={16} />
                    </button>
                  )}
                  {phase === 5 && incident.status === "monitoring" && (
                    <div className="monitoring-banner"><Radar size={17} /> Monitoring policy active · no destructive action required</div>
                  )}
                  {phase === 6 && <div className="contained-banner"><ShieldCheck size={17} /> Containment executed successfully</div>}
                </>
              ) : (
                <div className="response-empty">
                  <ShieldCheck size={25} />
                  <p>No response actions required</p>
                  <span>Critical actions require analyst approval</span>
                </div>
              )}
            </section>

            <section className="panel audit-panel">
              <div className="panel-heading compact">
                <div><span className="eyebrow">AUDIT TRAIL</span><h2>Recent actions</h2></div>
                <ArrowRight size={17} />
              </div>
              {auditEvents.length ? auditEvents.map((event) => (
                <div className="audit-row" key={`${event.action}-${event.target}`}>
                  <Check size={13} />
                  <div><strong>{humanize(event.action)}</strong><span>{event.target} · {formatTime(event.timestamp)}</span></div>
                </div>
              )) : <p className="audit-empty">No containment actions recorded.</p>}
            </section>
          </aside>
        </section>
      </main>

      <footer>
        <span><i /> ARGUS CORE ONLINE</span>
        <span title={detectorStatus?.graph.detail}>GRAPH DETECTOR · {detectorSourceLabel(detectorStatus?.graph)}</span>
        <span title={detectorStatus?.system.detail}>eBPF SENSOR · {detectorSourceLabel(detectorStatus?.system)}</span>
        <span className="mono">BUILD 1.0.0 · DATA-DRIVEN</span>
      </footer>

      <IntelligenceLab
        open={labOpen}
        incidents={incidentHistory}
        onClose={() => setLabOpen(false)}
        onAnalyze={runCustomAnalysis}
      />
    </div>
  );
}

export default App;
