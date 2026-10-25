// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CaseBrowser } from "./CaseBrowser";
import type { FinancialInvestigation, Incident } from "./types";

const financial: FinancialInvestigation = {
  case_id: "FIN-test", source: "Synthetic Stream", session_id: "SYN-saved",
  scenario_id: "mule", created_at: "2026-10-25T01:00:00Z", updated_at: "2026-10-25T02:00:00Z",
  last_activity_at: "2026-10-25T01:30:00Z", severity: "high", status: "open",
  summary: "Connected financial detector evidence", transaction_ids: ["tx-old-1", "tx-old-2"],
  accounts: ["a", "b", "c"], risk_scores: { graph: 91 }, evidence: ["Stored forwarding evidence"],
  signal_ids: ["graph-1"], policy_version: "financial-connected-v1", merged_into: null,
};
const historical: Incident = {
  incident_id: "INC-test", timestamp: "2026-10-24T01:00:00Z", verdict: "correlated_signals",
  severity: "critical", confidence: .95, financial_signal_id: "graph-old", infrastructure_signal_id: "system-old",
  affected_accounts: ["acc-old"], summary: "Financial and infrastructure evidence", evidence: ["Historical evidence"],
  recommended_actions: [{ action: "contain", target: "host-old", approval_required: true, status: "pending" }],
  status: "awaiting_approval",
};
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div"); document.body.append(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const props = () => ({
  financial: [financial], historical: [historical], selectedKey: "financial:FIN-test",
  onSelect: vi.fn(), onOpen: vi.fn(), onRefresh: vi.fn(), onApprove: vi.fn(), onAudit: vi.fn(),
  audit: {}, busy: false, formatRisk: (value?: number) => value === undefined ? "—" : `${Math.round(value)}/100`,
});
const button = (text: string) => Array.from(container.querySelectorAll("button")).find(e => e.textContent?.includes(text))!;

it("browses financial cases without fetching or starting a run and reads refreshed authoritative records", async () => {
  const p = props();
  await act(async () => root.render(<CaseBrowser {...p} />));
  expect(container.textContent).toContain("Latest 50 per source");
  const inspector = container.querySelector("#case-inspector")!;
  expect(inspector.textContent).toContain("Financial-only investigation");
  expect(inspector.textContent).toContain("91/100");
  expect(inspector.textContent).toContain("Stored forwarding evidence");
  expect(inspector.textContent).not.toContain("Approve simulated containment");
  expect(inspector.textContent).not.toContain("View audit trail");
  await act(async () => button("Open financial investigation").click());
  expect(p.onOpen).toHaveBeenCalledWith(financial);
  (inspector as HTMLElement).scrollTop = 123;
  const refreshed = { ...financial, status: "merged" as const, merged_into: "FIN-parent", evidence: ["Updated stored evidence"] };
  await act(async () => root.render(<CaseBrowser {...p} financial={[refreshed]} />));
  expect(inspector.scrollTop).toBe(123);
  expect(inspector.textContent).toContain("FIN-parent");
  expect(inspector.textContent).toContain("Updated stored evidence");
  expect(inspector.textContent).not.toContain("Stored forwarding evidence");
  await act(async () => button("Refresh").click());
  expect(p.onRefresh).toHaveBeenCalledOnce();
});

it("selects historical IDs and delegates only their existing simulated workflow and audit actions", async () => {
  const p = props();
  await act(async () => root.render(<CaseBrowser {...p} />));
  await act(async () => button("INC-test").click());
  expect(p.onSelect).toHaveBeenCalledWith("historical:INC-test");
  (container.querySelector("#case-inspector") as HTMLElement).scrollTop = 123;
  await act(async () => root.render(<CaseBrowser {...p} selectedKey="historical:INC-test" />));
  const inspector = container.querySelector("#case-inspector")!;
  expect(inspector.scrollTop).toBe(0);
  expect(inspector.textContent).toContain("Historical cross-domain investigation");
  expect(inspector.textContent).toContain("Historical evidence");
  expect(inspector.textContent).toContain("graph-old");
  expect(inspector.textContent).toContain("system-old");
  expect(inspector.textContent).toContain("Simulated response: contain");
  await act(async () => button("Approve simulated containment").click());
  await act(async () => button("View audit trail").click());
  await act(async () => button("Open historical investigation").click());
  expect(p.onApprove).toHaveBeenCalledWith(historical);
  expect(p.onAudit).toHaveBeenCalledWith(historical);
  expect(p.onOpen).toHaveBeenCalledWith(historical);
  await act(async () => root.render(<CaseBrowser {...p} selectedKey="historical:INC-test" busy audit={{ "INC-test": [{ timestamp: historical.timestamp, action: "contain", target: "host-old", actor: "analyst", result: "simulated" }] }} />));
  expect(button("Approve simulated containment").disabled).toBe(true);
  expect(inspector.textContent).toContain("contain · simulated");
});

it("explains the empty persisted-case state without inventing a record or action", async () => {
  await act(async () => root.render(<CaseBrowser {...props()} financial={[]} historical={[]} />));
  expect(container.textContent).toContain("No persisted cases available");
  expect(container.textContent).toContain("No case selected");
  expect(container.querySelectorAll(".m-case-row")).toHaveLength(0);
  expect(container.querySelector(".m-case-open")).toBeNull();
});
