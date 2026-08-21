import type {
  ApprovalResponse,
  AttackResponse,
  DetectorStatus,
  NormalResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

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
