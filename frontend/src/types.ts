export type TransactionStatus = "pending" | "completed" | "cancelled";

export interface Transaction {
  transaction_id: string;
  timestamp: string;
  source_account: string;
  destination_account: string;
  amount: number;
  currency: string;
  device_id: string;
  ip_address: string;
  status: TransactionStatus;
}

export interface GraphSignal {
  signal_id: string;
  source: "graph_detector";
  timestamp: string;
  risk_score: number;
  anomaly_type: string;
  suspicious_accounts: string[];
  suspicious_transactions: string[];
  related_ips: string[];
  reasons: string[];
}

export interface SystemSignal {
  signal_id: string;
  source: "ebpf_detector";
  timestamp: string;
  risk_score: number;
  host: string;
  service: string;
  process: string;
  event_type: string;
  related_ips: string[];
  indicators: string[];
}

export interface RawTelemetryEvent {
  timestamp: string;
  event_type: "process_exec" | "file_open" | "network_connect";
  process: string;
  details: Record<string, unknown>;
}

export interface ResponseAction {
  action: string;
  target: string;
  approval_required: boolean;
  status: string;
}

export interface Incident {
  incident_id: string;
  timestamp: string;
  verdict: string;
  severity: "informational" | "suspicious" | "high" | "critical";
  confidence: number;
  financial_signal_id: string;
  infrastructure_signal_id: string | null;
  case_type?: "financial" | "cross_domain";
  financial_assessment_id?: string | null;
  transaction_ids?: string[];
  affected_accounts: string[];
  summary: string;
  evidence: string[];
  recommended_actions: ResponseAction[];
  status: "monitoring" | "awaiting_approval" | "contained";
}

export interface AuditEvent {
  timestamp: string;
  action: string;
  target: string;
  actor: string;
  result: string;
}

export type DetectorAvailability = "online" | "degraded" | "offline";
export type DetectorOrigin = "service" | "last_known" | "fixture" | "none";
export type DetectorMode = "live" | "replay" | "fixture" | "unknown";

export interface DetectorComponentStatus {
  availability: DetectorAvailability;
  origin: DetectorOrigin;
  mode: DetectorMode;
  detail: string;
}

export interface DetectorStatus {
  graph: DetectorComponentStatus;
  system: DetectorComponentStatus;
}

export interface NormalResponse {
  mode: "normal";
  transactions: Transaction[];
  incident: null;
}

export interface AttackResponse {
  mode: "attack";
  transactions: Transaction[];
  graph_signal: GraphSignal;
  system_signal: SystemSignal;
  detector_status: DetectorStatus;
  incident: Incident;
}

export interface ApprovalResponse {
  incident: Incident;
  audit_events: AuditEvent[];
}

export interface AnalysisRequest {
  transactions: Transaction[];
  baseline_transactions?: Transaction[];
  telemetry_events?: RawTelemetryEvent[];
  system_signal?: SystemSignal;
  correlate_with_latest_system?: boolean;
  telemetry_host?: string;
  telemetry_service?: string;
  source_label?: string;
}

export interface AnalysisResponse {
  analysis_id: string;
  mode: "analysis";
  source_label: string;
  transactions: Transaction[];
  graph_signal: GraphSignal;
  system_signal: SystemSignal | null;
  detector_status: DetectorStatus;
  incident: Incident | null;
  financial_assessment?: FinancialAssessment | null;
}

export interface FinancialAssessment {
  schema_version: "financial.v1";
  assessment_id: string;
  risk_score: number;
  fusion_policy: string;
  model: { name: string; checkpoint_sha256: string; validation_status: "synthetic_only"; explanation_method: string };
  transaction_scores: {
    transaction_id: string; risk_score: number; raw_ml_score: number; ml_used: boolean;
    detectors: { rules: number; ml: number; mule: number; scam: number };
    reasons: string[];
  }[];
  model_diagnostic?: { transaction_id: string; scope: string; sensitivities: {
    feature: string; score_without_feature: number; score_difference: number;
  }[] } | null;
}

export interface Investigation {
  incident_id: string;
  revision: number;
  assigned_to: string | null;
  status: "open" | "investigating" | "escalated" | "closed";
  history: { id: number; timestamp: string; actor: string; revision: number; changes: Record<string, unknown> }[];
}

export interface PlatformMetrics {
  transactions_ingested: number;
  signals_analyzed: number;
  incidents_total: number;
  incidents_open: number;
  critical_incidents: number;
  accounts_observed: number;
  total_value_observed: number | null;
  value_by_currency?: Record<string, number>;
  average_confidence: number;
  severity_counts: Record<string, number>;
}

export interface FinancialInvestigation {
  case_id: string;
  source: "Synthetic Stream" | "Transaction Stream";
  session_id: string;
  scenario_id: string | null;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
  severity: "high" | "critical";
  status: "open" | "merged";
  summary: string;
  transaction_ids: string[];
  accounts: string[];
  risk_scores: Record<string, number>;
  evidence: string[];
  signal_ids: string[];
  policy_version: string;
  merged_into: string | null;
}
export interface InvestigationContext {
  session_id: string;
  transactions: Transaction[];
  events: import("./monitoring").StreamEvent[];
}
