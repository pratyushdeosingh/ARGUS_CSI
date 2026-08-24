import { AlertTriangle, Braces, CheckCircle2, FlaskConical, History, Play, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { LAB_TEMPLATES } from "./labTemplates";
import type { AnalysisRequest, AnalysisResponse, Incident, RawTelemetryEvent, Transaction } from "./types";

interface IntelligenceLabProps {
  open: boolean;
  incidents: Incident[];
  onClose: () => void;
  onAnalyze: (request: AnalysisRequest) => Promise<AnalysisResponse>;
}

function pretty(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function parseArray<T>(label: string, value: string): T[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${label} is not valid JSON.`);
  }
  if (!Array.isArray(parsed)) throw new Error(`${label} must be a JSON array.`);
  return parsed as T[];
}

export function IntelligenceLab({ open, incidents, onClose, onAnalyze }: IntelligenceLabProps) {
  const [templateKey, setTemplateKey] = useState("adaptive_ato");
  const [transactions, setTransactions] = useState("");
  const [baseline, setBaseline] = useState("");
  const [telemetry, setTelemetry] = useState("");
  const [sourceLabel, setSourceLabel] = useState("");
  const [host, setHost] = useState("");
  const [service, setService] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);

  const template = useMemo(() => LAB_TEMPLATES[templateKey], [templateKey]);

  useEffect(() => {
    const request = template.request;
    setTransactions(pretty(request.transactions));
    setBaseline(pretty(request.baseline_transactions ?? []));
    setTelemetry(pretty(request.telemetry_events ?? []));
    setSourceLabel(request.source_label ?? "analyst-lab");
    setHost(request.telemetry_host ?? "payments-node");
    setService(request.telemetry_service ?? "payments-api");
    setResult(null);
    setError(null);
  }, [template]);

  if (!open) return null;

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const request: AnalysisRequest = {
        source_label: sourceLabel.trim() || "analyst-lab",
        telemetry_host: host.trim() || "payments-node",
        telemetry_service: service.trim() || "payments-api",
        transactions: parseArray<Transaction>("Transactions", transactions),
        baseline_transactions: parseArray<Transaction>("Baseline", baseline),
        telemetry_events: parseArray<RawTelemetryEvent>("Telemetry", telemetry),
      };
      if (!request.transactions.length) throw new Error("Add at least one transaction to analyze.");
      setResult(await onAnalyze(request));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Analysis failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="lab-backdrop" role="presentation">
      <section className="lab-modal" role="dialog" aria-modal="true" aria-labelledby="lab-title">
        <header className="lab-header">
          <div className="lab-title">
            <span className="lab-icon"><FlaskConical size={21} /></span>
            <div><span className="eyebrow">DATA-DRIVEN ANALYSIS</span><h2 id="lab-title">ARGUS Intelligence Lab</h2></div>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close intelligence lab"><X size={17} /></button>
        </header>

        <div className="lab-content">
          <div className="lab-editor-column">
            <div className="lab-template-row">
              <label>
                Scenario starter
                <select value={templateKey} onChange={(event) => setTemplateKey(event.target.value)}>
                  {Object.entries(LAB_TEMPLATES).map(([key, entry]) => <option value={key} key={key}>{entry.label}</option>)}
                </select>
              </label>
              <p>{template.description} Every field remains editable.</p>
            </div>

            <div className="lab-meta-grid">
              <label>Source label<input value={sourceLabel} onChange={(event) => setSourceLabel(event.target.value)} /></label>
              <label>Telemetry host<input value={host} onChange={(event) => setHost(event.target.value)} /></label>
              <label>Service<input value={service} onChange={(event) => setService(event.target.value)} /></label>
            </div>

            <div className="json-grid">
              <label><span><Braces size={14} /> Transactions</span><textarea spellCheck={false} value={transactions} onChange={(event) => setTransactions(event.target.value)} /></label>
              <label><span><Braces size={14} /> Behavioral baseline</span><textarea spellCheck={false} value={baseline} onChange={(event) => setBaseline(event.target.value)} /></label>
              <label><span><Braces size={14} /> Raw host telemetry</span><textarea spellCheck={false} value={telemetry} onChange={(event) => setTelemetry(event.target.value)} /></label>
            </div>

            {error && <div className="lab-error"><AlertTriangle size={15} /> {error}</div>}
            <button className="lab-run-button" onClick={() => void run()} disabled={busy}>
              <Play size={16} fill="currentColor" /> {busy ? "ANALYZING ACROSS DETECTORS…" : "RUN CROSS-DOMAIN ANALYSIS"}
            </button>
          </div>

          <aside className="lab-results-column">
            <div className="lab-side-heading"><span><CheckCircle2 size={16} /> Analysis result</span><small>Content-derived · persisted</small></div>
            {result ? (
              <div className="analysis-result">
                <span className="analysis-id">{result.analysis_id}</span>
                <div className="result-score-grid">
                  <div><span>Financial risk</span><strong>{Math.round(result.graph_signal.risk_score * 100)}</strong></div>
                  <div><span>Host risk</span><strong>{result.system_signal ? Math.round(result.system_signal.risk_score * 100) : "—"}</strong></div>
                  <div><span>Confidence</span><strong>{result.incident ? Math.round(result.incident.confidence * 100) : "—"}</strong></div>
                </div>
                <div className={`result-verdict ${result.incident?.severity ?? "informational"}`}>
                  <span>{result.incident ? result.incident.severity.toUpperCase() : "GRAPH-ONLY"}</span>
                  <strong>{result.incident?.verdict.replaceAll("_", " ") ?? result.graph_signal.anomaly_type.replaceAll("_", " ")}</strong>
                  <p>{result.incident?.summary ?? "Financial analysis completed. Add host telemetry or a system signal for cross-domain correlation."}</p>
                </div>
                <ul>{result.graph_signal.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
              </div>
            ) : (
              <div className="result-empty"><FlaskConical size={30} /><p>Run any JSON dataset to generate a fresh graph signal, infrastructure signal, and correlated verdict.</p></div>
            )}

            <div className="lab-side-heading history-heading"><span><History size={16} /> Persistent incident history</span><small>{incidents.length} shown</small></div>
            <div className="incident-history">
              {incidents.length ? incidents.slice(0, 6).map((entry) => (
                <div className="history-row" key={entry.incident_id}>
                  <i className={entry.severity} />
                  <div><strong>{entry.incident_id}</strong><span>{entry.verdict.replaceAll("_", " ")}</span></div>
                  <small>{entry.status.replaceAll("_", " ")}</small>
                </div>
              )) : <p className="history-empty">No persisted incidents yet.</p>}
            </div>
          </aside>
        </div>
      </section>
    </div>
  );
}
