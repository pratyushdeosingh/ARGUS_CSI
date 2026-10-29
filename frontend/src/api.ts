import type {
  ApprovalResponse,
  AuditEvent,
  AnalysisRequest,
  AnalysisResponse,
  AttackResponse,
  DetectorStatus,
  Incident,
  Investigation,
  NormalResponse,
  PlatformMetrics,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const message = await response.text();
    let detail = message;
    try {
      const payload = JSON.parse(message) as { detail?: string };
      detail = payload.detail ?? message;
    } catch {
      // Preserve a non-JSON error body.
    }
    throw new Error(detail || `ARGUS API returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function loadDetectorStatus(): Promise<DetectorStatus> {
  return request<DetectorStatus>("/api/detectors/status");
}

export function loadNormalState(): Promise<NormalResponse> {
  return request<NormalResponse>("/api/demo/normal");
}

export function simulateAttack(): Promise<AttackResponse> {
  return request<AttackResponse>("/api/demo/simulate-attack", {
    method: "POST",
  });
}

export function approveIncident(incidentId: string): Promise<ApprovalResponse> {
  return request<ApprovalResponse>(`/api/incidents/${incidentId}/approve`, {
    method: "POST",
  });
}

export function analyzeData(
  payload: AnalysisRequest,
): Promise<AnalysisResponse> {
  return request<AnalysisResponse>("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function loadPlatformMetrics(): Promise<PlatformMetrics> {
  return request<PlatformMetrics>("/api/platform/metrics");
}

export function loadIncidents(limit = 20): Promise<Incident[]> {
  return request<Incident[]>(`/api/incidents?limit=${limit}`);
}

export function loadAuditEvents(incidentId: string): Promise<AuditEvent[]> {
  return request<AuditEvent[]>(
    `/api/audit?incident_id=${encodeURIComponent(incidentId)}`,
  );
}

export const apiBase = API_BASE;
export interface TransactionSource {
  history(session: string): Promise<import("./types").Transaction[]>;
  events(session: string): Promise<import("./monitoring").StreamEvent[]>;
  ingest(
    transaction: import("./types").Transaction,
    session: string,
    signal?: AbortSignal,
    scenario?: string,
  ): Promise<{ transaction: import("./types").Transaction }>;
}
export const syntheticSource: TransactionSource = {
  async history(session: string) {
    return request<import("./types").Transaction[]>(
      `/api/transactions?limit=200&session_id=${encodeURIComponent(session)}`,
    );
  },
  async events(session: string) {
    return request<import("./monitoring").StreamEvent[]>(
      `/api/transaction-events?session_id=${encodeURIComponent(session)}`,
    );
  },
  async ingest(
    transaction: import("./types").Transaction,
    session: string,
    signal?: AbortSignal,
    scenario?: string,
  ) {
    return request<{ transaction: import("./types").Transaction }>(
      `/api/transactions?session_id=${encodeURIComponent(session)}${scenario ? `&scenario_id=${encodeURIComponent(scenario)}` : ""}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(transaction),
        signal,
      },
    );
  },
};

export function loadFinancialInvestigations(): Promise<
  import("./types").FinancialInvestigation[]
> {
  return request("/api/financial-investigations?limit=50");
}
export function loadTransactionContext(
  id: string,
): Promise<import("./types").InvestigationContext> {
  return request(`/api/transactions/${encodeURIComponent(id)}/context`);
}
export function loadFinancialContext(
  id: string,
): Promise<import("./types").InvestigationContext> {
  return request(
    `/api/financial-investigations/${encodeURIComponent(id)}/context`,
  );
}
export function loadIncidentContext(
  id: string,
): Promise<import("./types").InvestigationContext> {
  return request(`/api/incidents/${encodeURIComponent(id)}/context`);
}

export function loadInvestigation(incidentId: string): Promise<Investigation> {
  return request<Investigation>(`/api/incidents/${encodeURIComponent(incidentId)}/investigation`);
}

export function updateInvestigation(incidentId: string, update: {
  actor: string; expected_revision: number; assigned_to: string | null;
  status: Investigation["status"]; note?: string;
}): Promise<Investigation> {
  return request<Investigation>(`/api/incidents/${encodeURIComponent(incidentId)}/investigation`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(update),
  });
}

export function loadDraftReport(incidentId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/api/incidents/${encodeURIComponent(incidentId)}/report`);
}
