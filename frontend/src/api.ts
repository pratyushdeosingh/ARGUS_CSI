import type {
  ApprovalResponse,
  AttackResponse,
  NormalResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `ARGUS API returned ${response.status}`);
  }
  return response.json() as Promise<T>;
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
