import type { Transaction, FinancialAssessment } from "./types";
export interface StreamEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  session_id?: string;
  data: Record<string, unknown>;
}
export interface Detection {
  financial?: FinancialAssessment["transaction_scores"][number];
  incidentId?: string;
  graph?: number;
  scam?: number;
  combined?: number;
  graphFlagged?: boolean;
  graphState?: "scored" | "failed";
  scamState?: "scored" | "failed";
  reasons?: string[];
  scamReasons?: string[];
  suspiciousAccounts?: string[];
  decision?: string;
}
export interface Alert {
  id: string;
  transactionId: string;
  type: string;
  severity: string;
  timestamp: string;
  message: string;
  evidence: string[];
  graph?: number;
  scam?: number;
  combined?: number;
}
export interface MonitorState {
  transactions: Record<string, Transaction>;
  detections: Record<string, Detection>;
  alerts: Record<string, Alert>;
  seen: string[];
}
export const emptyMonitor = (): MonitorState => ({
  transactions: {},
  detections: {},
  alerts: {},
  seen: [],
});
export function score(value: unknown, scale: 1 | 100): number | undefined {
  return typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= scale
    ? (value * 100) / scale
    : undefined;
}
const strings = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
export function applyEvent(
  state: MonitorState,
  event: StreamEvent,
): MonitorState {
  if (!event.event_id || state.seen.includes(event.event_id)) return state;
  const data = event.data;
  const id = String(data.transaction_id ?? "");
  const next = { ...state, seen: [...state.seen.slice(-4999), event.event_id] };
  if (
    event.event_type === "transaction.received" &&
    id &&
    data.source_account
  ) {
    next.transactions = {
      ...state.transactions,
      [id]: data as unknown as Transaction,
    };
    const ids = Object.keys(next.transactions);
    if (ids.length > 1000) {
      const oldest = ids
        .sort((a, b) =>
          next.transactions[a].timestamp.localeCompare(
            next.transactions[b].timestamp,
          ),
        )
        .slice(0, ids.length - 1000);
      for (const key of oldest) delete next.transactions[key];
    }
  }
  if (event.event_type === "transaction.scored") {
    const assessment = data.financial_assessment as FinancialAssessment | undefined;
    const payment = assessment?.transaction_scores?.find(item => item.transaction_id === id);
    next.detections = {
      ...state.detections,
      [id]: {
        ...state.detections[id],
        financial: payment,
        incidentId: typeof data.incident_id === "string" ? data.incident_id : undefined,
        ...(payment ? { combined: score(payment.risk_score, 1) } : {}),
        graph: score(data.risk_score, 1),
        graphState: "scored",
        graphFlagged: strings(data.suspicious_transactions).includes(id),
        reasons: strings(data.reasons),
        suspiciousAccounts: strings(data.suspicious_accounts),
      },
    };
  }
  if (event.event_type === "transaction.scam_scored")
    next.detections = {
      ...state.detections,
      [id]: {
        ...state.detections[id],
        scam: score(data.scam_score, 100),
        combined: state.detections[id]?.financial
          ? score(state.detections[id].financial!.risk_score, 1)
          : score(data.risk_score, 100),
        scamState: "scored",
        scamReasons: [...strings(data.top_factors), ...strings(data.reasons)],
        decision: String(data.decision ?? ""),
      },
    };
  const failed =
    event.event_type === "transaction.analysis_failed" ||
    event.event_type === "transaction.scam_scoring_failed";
  if (failed) {
    const field =
      event.event_type === "transaction.analysis_failed"
        ? "graphState"
        : "scamState";
    // A late failure cannot erase a successful detector result.
    if (state.detections[id]?.[field] !== "scored")
      next.detections = {
        ...state.detections,
        [id]: { ...state.detections[id], [field]: "failed" },
      };
  }
  if (
    failed ||
    event.event_type === "alert.created" ||
    event.event_type === "scam_alert.created"
  ) {
    const alertId = String(data.alert_id ?? `${event.event_type}:${id}`);
    next.alerts = {
      ...state.alerts,
      [alertId]: {
        id: alertId,
        transactionId: id,
        type: failed
          ? "Analysis unavailable"
          : event.event_type === "scam_alert.created"
            ? "Specialist scam alert"
            : "Graph fraud alert",
        severity: failed ? "warning" : String(data.severity ?? "high"),
        timestamp: event.timestamp,
        message: String(data.message ?? data.error ?? ""),
        evidence: strings(data.supporting_evidence),
        graph:
          event.event_type === "alert.created"
            ? score(data.risk_score, 1)
            : undefined,
        scam: score(data.scam_score, 100),
        combined:
          event.event_type === "scam_alert.created"
            ? score(data.risk_score, 100)
            : undefined,
      },
    };
    next.alerts = Object.fromEntries(Object.entries(next.alerts).slice(-500));
  }
  // Prune orphan detector records, retaining a small buffer for out-of-order deliveries.
  const detectionIds = Object.keys(next.detections);
  if (detectionIds.length > 1200)
    next.detections = Object.fromEntries(
      Object.entries(next.detections).slice(-1200),
    );
  return next;
}
export function detectionLabel(d?: Detection): string {
  if (!d) return "Not analyzed";
  if (
    ((d.graph ?? 0) >= 70 && d.graphFlagged === true) ||
    (d.scam ?? 0) >= 70 ||
    d.decision === "BLOCK" ||
    d.decision === "REVIEW"
  )
    return "Flagged";
  if (d.graphState === "failed" || d.scamState === "failed")
    return "Analysis failed";
  if (d.graphState === "scored" && d.scamState === "scored")
    return "Cleared by analysis";
  return "Scoring";
}
export function neighborhood(
  transactions: Transaction[],
  selected?: Transaction,
): Transaction[] {
  if (!selected) return [];
  const accounts = new Set([
    selected.source_account,
    selected.destination_account,
  ]);
  for (let depth = 0; depth < 3; depth++) {
    const nearby = transactions.filter(
      (t) =>
        accounts.has(t.source_account) || accounts.has(t.destination_account),
    );
    nearby.forEach((t) => {
      accounts.add(t.source_account);
      accounts.add(t.destination_account);
    });
    if (accounts.size >= 60) break;
  }
  const relevant = transactions.filter(
    (t) =>
      accounts.has(t.source_account) && accounts.has(t.destination_account),
  );
  return [
    selected,
    ...relevant
      .filter((t) => t.transaction_id !== selected.transaction_id)
      .sort(
        (a, b) =>
          Math.abs(Date.parse(a.timestamp) - Date.parse(selected.timestamp)) -
          Math.abs(Date.parse(b.timestamp) - Date.parse(selected.timestamp)),
      ),
  ].slice(0, 28);
}

export function contextState(
  context: import("./types").InvestigationContext,
): MonitorState {
  let state = emptyMonitor();
  for (const tx of context.transactions)
    state = applyEvent(state, {
      event_id: `context:${tx.transaction_id}`,
      event_type: "transaction.received",
      timestamp: tx.timestamp,
      data: { ...tx },
    });
  for (const event of context.events) state = applyEvent(state, event);
  return state;
}
