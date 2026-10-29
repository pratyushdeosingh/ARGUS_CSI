import { useLayoutEffect, useRef } from "react";
import { ChevronRight, Network, RefreshCw } from "lucide-react";
import type { AuditEvent, FinancialInvestigation, Incident } from "./types";

type Case = FinancialInvestigation | Incident;
const caseKey = (item: Case) => "case_id" in item ? `financial:${item.case_id}` : `historical:${item.incident_id}`;
const caseId = (item: Case) => "case_id" in item ? item.case_id : item.incident_id;

interface Props {
  financial: FinancialInvestigation[];
  historical: Incident[];
  selectedKey: string;
  onSelect: (key: string) => void;
  onOpen: (item: Case) => void;
  onRefresh: () => void;
  onApprove: (item: Incident) => void;
  onAudit: (item: Incident) => void;
  onInvestigate?: (item: Incident) => void;
  audit: Record<string, AuditEvent[]>;
  busy: boolean;
  formatRisk: (value?: number) => string;
}

// This view owns no case data, requests, timers, or monitoring state. Selection
// is an ID in App; the inspector always reads the latest authoritative props.
export function CaseBrowser({ financial, historical, selectedKey, onSelect, onOpen, onRefresh, onApprove, onAudit, onInvestigate, audit, busy, formatRisk }: Props) {
  const cases: Case[] = [...financial, ...historical];
  const selected = cases.find(item => caseKey(item) === selectedKey) ?? cases[0];
  const inspector = useRef<HTMLElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const selectedId = selected ? caseKey(selected) : "";
  useLayoutEffect(() => {
    if (inspector.current) inspector.current.scrollTop = 0;
    const row = list.current?.querySelector<HTMLButtonElement>('[aria-pressed="true"]');
    if (list.current && row) {
      const bounds = list.current.getBoundingClientRect();
      const selectedBounds = row.getBoundingClientRect();
      if (selectedBounds.top < bounds.top) list.current.scrollTop += selectedBounds.top - bounds.top;
      else if (selectedBounds.bottom > bounds.bottom) list.current.scrollTop += selectedBounds.bottom - bounds.bottom;
    }
  }, [selectedId]);
  const financialCase = selected && "case_id" in selected ? selected : null;
  const historicalCase = selected && "incident_id" in selected ? selected : null;
  return <div className="m-case-workspace">
    <section className="m-panel m-case-browser" aria-label="Persisted investigation cases">
      <div className="m-panel-title">
        <div><h2>Persisted investigation cases</h2><p>Loaded: {financial.length} stream groups · {historical.length} analysis cases</p></div>
        <button onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>
      </div>
      <p className="m-case-scope"><span>Latest 50 per source · loaded subset, not all-time totals.</span><a href="#case-inspector">Selected record ↓</a></p>
      <div className="m-case-list" ref={list}>
        {cases.map(item => {
          const isFinancial = "case_id" in item;
          return <article key={caseKey(item)}>
            <button className="m-case-row" aria-pressed={selected === item} aria-controls="case-inspector" onClick={() => onSelect(caseKey(item))}>
              <span className="m-case-row-top"><span className="m-mono">{caseId(item)}</span><span className={`m-alert-severity ${item.severity}`}>{item.severity}</span></span>
              <span className="m-case-row-meta"><span className={`m-case-source ${isFinancial || item.case_type === "financial" ? "financial" : "historical"}`}>{isFinancial ? "Financial-only" : item.case_type === "financial" ? "Financial analysis" : "Historical cross-domain"}</span><span className="m-case-status">{item.status.replaceAll("_", " ")}</span></span>
              <strong>{isFinancial ? `${item.source} · ${item.scenario_id ?? "Financial investigation"}` : item.verdict.replaceAll("_", " ")}</strong>
              <span className="m-case-preview">{item.summary}</span>
              <span className="m-case-row-foot"><time dateTime={isFinancial ? item.updated_at : item.timestamp}>{isFinancial ? item.updated_at : item.timestamp}</time><span>{isFinancial ? `${item.accounts.length} accounts · ${item.transaction_ids.length} payments` : `${item.affected_accounts.length} accounts · correlated signals`}</span><ChevronRight size={13} /></span>
            </button>
          </article>;
        })}
        {!cases.length && <div className="m-empty"><Network size={26} /><h3>No persisted cases available</h3><p>Financial cases require at least two connected completed payments with qualifying detector evidence in one session within 15 minutes. Historical Canonical Demo and Lab cases also appear here.</p></div>}
      </div>
    </section>
    <section className="m-panel m-case-inspector" id="case-inspector" ref={inspector} tabIndex={-1} aria-label="Selected investigation">
      <div className="m-panel-title"><div><h2>Investigation record</h2><p>{selected ? `${caseId(selected)} · stored evidence` : "Select a persisted case"}</p></div><Network size={18} /></div>
      {selected ? <div className="m-case-reading">
        <div className="m-case-identity"><span className={`m-case-source ${financialCase || historicalCase?.case_type === "financial" ? "financial" : "historical"}`}>{financialCase ? "Financial-only investigation" : historicalCase?.case_type === "financial" ? "Financial analysis investigation" : "Historical cross-domain investigation"}</span><span className={`m-alert-severity ${selected.severity}`}>{selected.severity}</span></div>
        <h3 className="m-mono">{caseId(selected)}</h3>
        <p className="m-case-summary">{selected.summary}</p>
        <dl className="m-case-metadata">
          <dt>Persisted status</dt><dd>{selected.status.replaceAll("_", " ")}</dd>
          <dt>Source</dt><dd>{financialCase?.source ?? (historicalCase?.case_type === "financial" ? "Financial analysis" : historicalCase?.incident_id === "INC-001" ? "Canonical Demo" : "Historical cross-domain / Data Lab")}</dd>
          {financialCase ? <>
            <dt>Session</dt><dd className="m-mono">{financialCase.session_id}</dd>
            <dt>Scenario</dt><dd>{financialCase.scenario_id ?? "Unspecified"}</dd>
            <dt>Created</dt><dd><time dateTime={financialCase.created_at}>{financialCase.created_at}</time></dd>
            <dt>Updated</dt><dd><time dateTime={financialCase.updated_at}>{financialCase.updated_at}</time></dd>
            <dt>Last activity</dt><dd><time dateTime={financialCase.last_activity_at}>{financialCase.last_activity_at}</time></dd>
            {financialCase.merged_into && <><dt>Merged into</dt><dd className="m-mono">{financialCase.merged_into}</dd></>}
          </> : historicalCase && <><dt>Created</dt><dd><time dateTime={historicalCase.timestamp}>{historicalCase.timestamp}</time></dd><dt>Financial signal</dt><dd className="m-mono">{historicalCase.financial_signal_id}</dd><dt>Infrastructure signal</dt><dd className="m-mono">{historicalCase.infrastructure_signal_id}</dd></>}
        </dl>
        {financialCase && <>
          <h4>Detector outputs</h4>
          <div className="m-case-scores">{Object.entries(financialCase.risk_scores).map(([name, value]) => <div key={name}><span>{name}</span><strong>{formatRisk(value)}</strong></div>)}</div>
          <p className="m-case-qualification">Persisted detector evidence describes suspicious patterns; it is not confirmation of fraud or an executed response.</p>
        </>}
        <div className="m-case-open"><button className="m-primary" onClick={() => onOpen(selected)}>{financialCase ? "Open financial investigation" : historicalCase?.case_type === "financial" ? "Open financial analysis" : "Open historical investigation"}<ChevronRight size={14} /></button><p>Inspect available stored payments, detector events, and the connected account network.</p>{historicalCase && onInvestigate && <button onClick={() => onInvestigate(historicalCase)}>Manage investigation / draft report</button>}</div>
        <h4>Related accounts <span className="m-count">{financialCase?.accounts.length ?? historicalCase?.affected_accounts.length}</span></h4>
        <div className="m-case-accounts">{(financialCase?.accounts ?? historicalCase?.affected_accounts ?? []).map(id => <span className="m-mono" key={id}>{id}</span>)}</div>
        {financialCase && <><h4>Payment references <span className="m-count">{financialCase.transaction_ids.length}</span></h4><p className="m-case-qualification">Latest {Math.min(20, financialCase.transaction_ids.length)} linked references shown. Open the investigation for its retrieved payment context.</p><div className="m-case-references">{financialCase.transaction_ids.slice(-20).map(id => <span className="m-mono" key={id}>{id}</span>)}</div></>}
        <h4>Stored evidence <span className="m-count">{selected.evidence.length}</span></h4>
        <ul className="m-case-evidence">{selected.evidence.map((entry, i) => <li key={`${i}:${entry}`}>{entry}</li>)}</ul>
        {financialCase && <details className="m-case-signals"><summary>Policy and signal references</summary><p>Policy: {financialCase.policy_version}</p>{financialCase.signal_ids.map(id => <p className="m-mono" key={id}>{id}</p>)}</details>}
        {historicalCase && <section className="m-case-responses" aria-label="Historical simulated responses">
          <h4>Simulated response workflow</h4><p>Containment and approval actions are simulated.</p>
          {historicalCase.recommended_actions.map(action => <p key={action.action + action.target}>Simulated response: {action.action} · {action.target} · {action.status}</p>)}
          <div className="m-case-response-actions">{historicalCase.status === "awaiting_approval" && <button disabled={busy} onClick={() => onApprove(historicalCase)}>Approve simulated containment</button>}<button onClick={() => onAudit(historicalCase)}>View audit trail</button></div>
          {audit[historicalCase.incident_id]?.map((event, i) => <p key={i}>{event.timestamp} · {event.action} · {event.result}</p>)}
        </section>}
      </div> : <div className="m-empty"><Network size={26} /><h3>No case selected</h3><p>Available persisted records will appear in the case list.</p></div>}
    </section>
  </div>;
}
