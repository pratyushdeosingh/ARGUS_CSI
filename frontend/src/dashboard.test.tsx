// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { useMonitoring } from "./useMonitoring";
import { syntheticSource } from "./api";
import type { RunConfig } from "./simulation";
import type { StreamEvent } from "./monitoring";
const mocks = vi.hoisted(() => ({
  receive: undefined as undefined | ((event: StreamEvent) => void),
  recover: undefined as undefined | (() => Promise<void>),
}));
vi.mock("./stream", () => ({
  connectStream: (
    _url: string,
    receive: (e: StreamEvent) => void,
    status: (s: string) => void,
    recover: () => Promise<void>,
  ) => {
    mocks.receive = receive;
    mocks.recover = recover;
    status("Connected");
    return vi.fn();
  },
}));
vi.mock("./MoneyGraph", () => ({
  MoneyGraph: ({ transactions, selected, onTransaction, onAccount }: any) => (
    <div data-testid="graph" data-selected={selected}>
      {transactions.map((t: any) => (
        <button
          key={t.transaction_id}
          onClick={() => onTransaction(t.transaction_id)}
        >
          Edge {t.transaction_id}
        </button>
      ))}
      <button onClick={() => onAccount(transactions[0]?.source_account)}>
        Inspect account
      </button>
    </div>
  ),
}));
vi.mock("./api", () => ({
  apiBase: "http://test",
  syntheticSource: {
    history: vi.fn().mockResolvedValue([]),
    events: vi.fn().mockResolvedValue([]),
    ingest: vi.fn(async (transaction) => ({ transaction })),
  },
  loadDetectorStatus: vi.fn().mockRejectedValue(new Error("offline")),
  loadIncidents: vi.fn().mockResolvedValue([]),
  loadAuditEvents: vi.fn().mockResolvedValue([]),
  approveIncident: vi.fn(),
  analyzeData: vi.fn(),
  loadNormalState: vi.fn(),
  loadPlatformMetrics: vi.fn(),
  simulateAttack: vi.fn(),
}));
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.useFakeTimers();
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  vi.mocked(syntheticSource.ingest).mockClear();
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
});
const click = async (text: string) => {
  const b = Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent === text,
  );
  expect(b, `Button ${text}`).toBeTruthy();
  await act(async () => b!.click());
};
const emit = async (e: StreamEvent) => act(async () => mocks.receive?.(e));
describe("simulation controls through React", () => {
  it("pauses, resumes, changes pace and resets without mixing scenario state", async () => {
    const cfg: RunConfig = {
      session: "SYN-a",
      seed: 9,
      scenario: "mixed",
      start: "2026-10-25T00:00:00Z",
      count: 40,
      accounts: 60,
    };
    let current: ReturnType<typeof useMonitoring>;
    function Harness({
      config,
      running,
      speed,
    }: {
      config: RunConfig;
      running: boolean;
      speed: number;
    }) {
      current = useMonitoring(config, running, speed, vi.fn());
      return <span>{current.cursor}</span>;
    }
    await act(async () =>
      root.render(<Harness config={cfg} running={true} speed={2} />),
    );
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTimeAsync(500));
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(2);
    await act(async () =>
      root.render(<Harness config={cfg} running={false} speed={2} />),
    );
    await act(async () => vi.advanceTimersByTimeAsync(5000));
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(2);
    await act(async () =>
      root.render(<Harness config={cfg} running={true} speed={4} />),
    );
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(3);
    await act(async () => vi.advanceTimersByTimeAsync(250));
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(4);
    const next = { ...cfg, session: "SYN-b" };
    await act(async () =>
      root.render(<Harness config={next} running={false} speed={4} />),
    );
    expect(current!.cursor).toBe(0);
    expect(Object.keys(current!.state.transactions)).toHaveLength(0);
    await emit({
      event_id: "old",
      session_id: "SYN-a",
      event_type: "transaction.scored",
      timestamp: cfg.start,
      data: { transaction_id: "old", risk_score: 0.9 },
    });
    expect(current!.state.detections.old).toBeUndefined();
  });
});
describe("dashboard selection and navigation", () => {
  it("selects clean and suspicious payments, follows graph edges and alerts, and disables real mode", async () => {
    await act(async () => root.render(<App />));
    await click(" Pause");
    const real = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Real Data"),
    );
    expect(real?.disabled).toBe(true);
    const call = vi.mocked(syntheticSource.ingest).mock.calls[0];
    const tx = call[0];
    const session = call[1];
    const other = {
      ...tx,
      transaction_id: `${session}-99999`,
      source_account: `${session}-A999`,
      destination_account: `${session}-A998`,
      status: "cancelled",
    };
    await emit({
      event_id: "other",
      session_id: session,
      event_type: "transaction.received",
      timestamp: tx.timestamp,
      data: other,
    });
    await emit({
      event_id: "score",
      session_id: session,
      event_type: "transaction.scored",
      timestamp: tx.timestamp,
      data: {
        transaction_id: other.transaction_id,
        risk_score: 0.92,
        reasons: ["Rapid forwarding"],
      },
    });
    await click(other.transaction_id);
    expect(
      container
        .querySelector('[data-testid="graph"]')
        ?.getAttribute("data-selected"),
    ).toBe(other.transaction_id);
    expect(container.querySelector(".m-details")?.textContent).toContain(
      "cancelled",
    );
    expect(container.querySelector(".m-details")?.textContent).toContain(
      "Rapid forwarding",
    );
    await click(`Edge ${other.transaction_id}`);
    await click("Inspect account");
    expect(container.querySelector(".m-account")?.textContent).toContain(
      "A999",
    );
    await click(tx.transaction_id);
    expect(
      container
        .querySelector('[data-testid="graph"]')
        ?.getAttribute("data-selected"),
    ).toBe(tx.transaction_id);
    expect(container.querySelector(".m-details")?.textContent).toContain(
      "legitimate",
    );
    await emit({
      event_id: "alert",
      session_id: session,
      event_type: "alert.created",
      timestamp: tx.timestamp,
      data: {
        transaction_id: other.transaction_id,
        alert_id: "a",
        severity: "high",
        message: "Forwarding signal",
        supporting_evidence: ["Rapid forwarding"],
      },
    });
    const alert = container.querySelector(".m-alert") as HTMLButtonElement;
    await act(async () => alert.click());
    expect(
      container
        .querySelector('[data-testid="graph"]')
        ?.getAttribute("data-selected"),
    ).toBe(other.transaction_id);
    await click("Transactions");
    expect(container.querySelector("h2")?.textContent).toContain(
      "Transaction history",
    );
    await click("Demo");
    expect(container.textContent).toContain("Canonical Demo");
    expect(container.querySelectorAll(".m-scenario")).toHaveLength(8);
  });
});
