// @vitest-environment jsdom
import { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { useMonitoring } from "./useMonitoring";
import {
  syntheticSource,
  loadFinancialInvestigations,
  loadTransactionContext,
  loadFinancialContext,
} from "./api";
import type { RunConfig } from "./simulation";
import type { StreamEvent } from "./monitoring";
const mocks = vi.hoisted(() => ({
  subscriptions: vi.fn(),
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
    mocks.subscriptions();
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
  loadFinancialInvestigations: vi.fn().mockResolvedValue([]),
  loadTransactionContext: vi.fn().mockRejectedValue(new Error("Not found")),
  loadFinancialContext: vi.fn(),
  loadIncidentContext: vi.fn(),
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
  mocks.subscriptions.mockClear();
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  vi.mocked(syntheticSource.ingest).mockClear();
  vi.mocked(syntheticSource.ingest).mockImplementation(async (transaction) => ({
    transaction,
  }));
  vi.mocked(loadFinancialInvestigations).mockResolvedValue([]);
  vi.mocked(loadTransactionContext).mockRejectedValue(new Error("Not found"));
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
    await click(" Start simulation");
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

const nav = async (name: string) => {
  const button = Array.from(container.querySelectorAll("nav button")).find(
    (b) => b.textContent?.startsWith(name),
  );
  await act(async () => (button as HTMLButtonElement).click());
};

describe("explicit simulator lifecycle", () => {
  it("stays idle on initial load, navigation and remount; only explicit Start/Resume submit", async () => {
    await act(async () =>
      root.render(
        <StrictMode>
          <App />
        </StrictMode>,
      ),
    );
    await act(async () => vi.advanceTimersByTimeAsync(5000));
    expect(syntheticSource.ingest).not.toHaveBeenCalled();
    expect(container.querySelector(".m-controls")?.textContent).toContain(
      "Ready",
    );
    expect(container.textContent).toContain("Mixed activity");
    for (const page of [
      "Transactions",
      "Alerts",
      "Investigations",
      "Demo",
      "Overview",
    ])
      await nav(page);
    expect(syntheticSource.ingest).not.toHaveBeenCalled();
    await click(" Start simulation");
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(1);
    const firstSession = vi.mocked(syntheticSource.ingest).mock.calls[0][1];
    await nav("Transactions");
    await nav("Investigations");
    await nav("Demo");
    await act(async () => vi.advanceTimersByTimeAsync(500));
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(2);
    await click(" Pause");
    for (const page of ["Overview", "Alerts", "Demo"]) await nav(page);
    await act(async () => vi.advanceTimersByTimeAsync(5000));
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(2);
    await click(" Resume");
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(3);
    await click(" Reset");
    await nav("Overview");
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(3);
    await click(" Start simulation");
    expect(vi.mocked(syntheticSource.ingest).mock.calls[3][1]).not.toBe(
      firstSession,
    );
    await act(async () => root.unmount());
    root = createRoot(container);
    await act(async () => root.render(<App />));
    await act(async () => vi.advanceTimersByTimeAsync(5000));
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(4);
  });
  it("does not submit the same in-flight payment twice when rapidly pausing and resuming", async () => {
    let resolve!: (value: any) => void;
    vi.mocked(syntheticSource.ingest).mockImplementationOnce(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    await act(async () => root.render(<App />));
    await click(" Start simulation");
    const tx = vi.mocked(syntheticSource.ingest).mock.calls[0][0];
    await click(" Pause");
    await click(" Start simulation");
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(1);
    await act(async () => resolve({ transaction: tx }));
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(2);
    expect(
      vi.mocked(syntheticSource.ingest).mock.calls[1][0].transaction_id,
    ).not.toBe(tx.transaction_id);
  });
});

describe("alert recovery and financial investigations", () => {
  async function startPaused() {
    await act(async () => root.render(<App />));
    await click(" Start simulation");
    await click(" Pause");
    const [tx, session] = vi.mocked(syntheticSource.ingest).mock.calls[0];
    return { tx, session };
  }
  it("opens an evicted graph alert from Overview, recovers its payment and retains exact alert evidence", async () => {
    const { tx, session } = await startPaused();
    const older = {
      ...tx,
      transaction_id: "SYN-older",
      source_account: "old-a",
      destination_account: "old-b",
    };
    vi.mocked(loadTransactionContext).mockResolvedValue({
      session_id: session,
      transactions: [older],
      events: [],
    });
    const e: StreamEvent = {
      event_id: "graph-alert",
      session_id: session,
      event_type: "alert.created",
      timestamp: tx.timestamp,
      data: {
        alert_id: "graph-a",
        transaction_id: older.transaction_id,
        risk_score: 0.91,
        severity: "critical",
        message: "Graph explanation",
        supporting_evidence: ["Connected forwarding evidence"],
      },
    };
    await emit(e);
    await emit(e);
    expect(container.querySelectorAll(".m-alert")).toHaveLength(1);
    const button = container.querySelector(".m-alert") as HTMLButtonElement;
    expect(button.tagName).toBe("BUTTON");
    await act(async () => button.click());
    expect(loadTransactionContext).toHaveBeenCalledWith(older.transaction_id);
    expect(
      container
        .querySelector('[data-testid="graph"]')
        ?.getAttribute("data-selected"),
    ).toBe(older.transaction_id);
    const details = container.querySelector(".m-details")?.textContent;
    expect(details).toContain("Graph explanation");
    expect(details).toContain("Connected forwarding evidence");
    expect(details).toContain("91/100");
    expect(
      container.querySelector(".m-alert")?.getAttribute("aria-pressed"),
    ).toBe("true");
    await click("Back to alerts");
    expect(container.querySelector("h1")?.textContent).toBe("Alerts");
    await nav("Transactions");
    expect(
      container
        .querySelector('[data-testid="graph"]')
        ?.getAttribute("data-selected"),
    ).toBe(older.transaction_id);
  });
  it("opens specialist alerts from Alerts and handles a missing payment without fabricating context", async () => {
    const { tx, session } = await startPaused();
    await emit({
      event_id: "scam-alert",
      session_id: session,
      event_type: "scam_alert.created",
      timestamp: tx.timestamp,
      data: {
        alert_id: "scam-a",
        transaction_id: "missing-payment",
        scam_score: 88,
        risk_score: 92,
        severity: "high",
        message: "Scam explanation",
        supporting_evidence: ["Fan-out evidence"],
      },
    });
    await nav("Alerts");
    await act(async () =>
      (container.querySelector(".m-alert") as HTMLButtonElement).click(),
    );
    expect(container.querySelector("h1")?.textContent).toContain(
      "Financial activity overview",
    );
    expect(container.querySelector(".m-details")?.textContent).toContain(
      "Scam explanation",
    );
    expect(container.querySelector(".m-details")?.textContent).toContain(
      "88/100",
    );
    expect(container.querySelector(".m-details")?.textContent).toContain(
      "Transaction unavailable",
    );
    expect(
      container
        .querySelector('[data-testid="graph"]')
        ?.getAttribute("data-selected"),
    ).toBeNull();
    await click("Back to alerts");
    expect(
      container.querySelector(".m-alert")?.getAttribute("aria-pressed"),
    ).toBe("true");
  });
  it("refreshes persisted cases on a stream notification, opens their stored context, and keeps live run state separate", async () => {
    const { tx } = await startPaused();
    const saved = {
      case_id: "FIN-test",
      source: "Synthetic Stream" as const,
      session_id: "saved-session",
      scenario_id: "mule",
      created_at: tx.timestamp,
      updated_at: tx.timestamp,
      last_activity_at: tx.timestamp,
      severity: "high" as const,
      status: "open" as const,
      summary: "Related mule payments",
      transaction_ids: ["old-1", "old-2"],
      accounts: ["a", "b", "c"],
      risk_scores: { graph: 90 },
      evidence: ["Persisted case evidence"],
      signal_ids: ["g"],
      policy_version: "financial-connected-v1",
      merged_into: null,
    };
    vi.mocked(loadFinancialInvestigations).mockResolvedValue([saved]);
    const older = {
      ...tx,
      transaction_id: "old-1",
      source_account: "a",
      destination_account: "b",
    };
    vi.mocked(loadFinancialContext).mockResolvedValue({
      session_id: "saved-session",
      transactions: [older],
      events: [],
    });
    await nav("Investigations");
    expect(container.textContent).not.toContain("FIN-test");
    await emit({
      event_id: "case-change",
      event_type: "investigation.updated",
      session_id: "saved-session",
      timestamp: tx.timestamp,
      data: { case_id: saved.case_id },
    });
    expect(container.textContent).toContain("FIN-test");
    expect(container.textContent).toContain("Persisted case evidence");
    await click("Open financial investigation");
    expect(
      container
        .querySelector('[data-testid="graph"]')
        ?.getAttribute("data-selected"),
    ).toBe("old-1");
    expect(container.querySelector(".m-details")?.textContent).toContain(
      "FIN-test",
    );
    await click("Back to investigations");
    expect(container.textContent).toContain("FIN-test");
    await nav("Overview");
    await click("Return to live run");
    expect(
      container
        .querySelector('[data-testid="graph"]')
        ?.getAttribute("data-selected"),
    ).toBe(tx.transaction_id);
    expect(syntheticSource.ingest).toHaveBeenCalledTimes(1);
  });
});

describe("live KPI trends", () => {
  it("keeps Ready empty, updates on accepted payments/results, freezes on pause and clears run trends on reset", async () => {
    await act(async () => root.render(<App />));
    const cards = () => container.querySelectorAll(".m-kpis article");
    expect(cards()).toHaveLength(5);
    for (const card of Array.from(cards()).slice(0, 4)) {
      expect(card.querySelectorAll(".m-contribution-chart rect")).toHaveLength(12);
    }
    expect(container.querySelector(".m-activity-control, .m-activity-dialog")).toBeNull();
    expect(cards()[0].textContent).toContain("Not enough history");
    expect(cards()[0].querySelector(".m-contribution-bucket")).toBeNull();
    expect(cards()[4].querySelector(".m-contribution-chart")).toBeNull();
    expect(syntheticSource.ingest).not.toHaveBeenCalled();
    await click(" Start simulation");
    await click(" Pause");
    const [tx, session] = vi.mocked(syntheticSource.ingest).mock.calls[0];
    for (const [id, offset] of [["prior", 60000], ["latest", 120000]] as const) {
      const timestamp = new Date(Date.parse(tx.timestamp) + offset).toISOString();
      await emit({ event_id: id, event_type: "transaction.received", timestamp, session_id: session, data: { ...tx, transaction_id: id, timestamp } });
      await emit({ event_id: `${id}-score`, event_type: "transaction.scam_scored", timestamp, session_id: session, data: { transaction_id: id, scam_score: 90 } });
      await emit({ event_id: `${id}-alert`, event_type: "alert.created", timestamp: "2030-01-01T00:00:00Z", session_id: session, data: { transaction_id: id, alert_id: id, severity: "high" } });
    }
    expect(cards()[0].querySelector("strong")?.textContent).toBe("3");
    expect(cards()[0].querySelectorAll(".m-contribution-bucket")).toHaveLength(12);
    expect(cards()[0].textContent).toContain("→ 0.0%");
    expect(cards()[1].querySelector("strong")?.textContent).toBe("2");
    expect(cards()[1].textContent).toContain("→ 0.0%");
    expect(cards()[2].querySelector("strong")?.textContent).toBe("2");
    expect(cards()[2].textContent).toContain("→ 0.0%");
    const snapshot = container.querySelector(".m-kpis")?.innerHTML;
    await act(async () => vi.advanceTimersByTimeAsync(5000));
    expect(container.querySelector(".m-kpis")?.innerHTML).toBe(snapshot);
    await click(" Reset");
    expect(cards()[0].querySelector("strong")?.textContent).toBe("0");
    expect(cards()[0].textContent).toContain("Not enough history");
    expect(cards()[0].querySelector(".m-contribution-bucket")).toBeNull();
    expect(container.querySelector(".m-controls")?.textContent).toContain("Ready");
  });
});


describe("contribution chart scenario isolation", () => {
  it("clears run buckets on a scenario switch and ignores the previous session", async () => {
    await act(async () => root.render(<App />));
    await click(" Start simulation");
    await click(" Pause");
    const [previousTx, previousSession] = vi.mocked(syntheticSource.ingest).mock.calls[0];
    await nav("Demo");
    const scenario = Array.from(container.querySelectorAll(".m-scenario")).find(article => article.textContent?.includes("Normal financial activity"));
    const load = Array.from(scenario!.querySelectorAll("button")).find(button => button.textContent?.trim() === "Load scenario");
    await act(async () => load!.click());
    await nav("Overview");
    const firstCard = () => container.querySelector(".m-kpis article")!;
    expect(firstCard().querySelector("strong")?.textContent).toBe("0");
    expect(firstCard().querySelectorAll(".m-contribution-bucket")).toHaveLength(0);
    expect(firstCard().querySelectorAll(".m-contribution-placeholder")).toHaveLength(12);
    expect(container.querySelector(".m-controls")?.textContent).toContain("Ready");
    await click(" Start simulation");
    await click(" Pause");
    const nextCall = vi.mocked(syntheticSource.ingest).mock.calls.at(-1)!;
    expect(nextCall[1]).not.toBe(previousSession);
    await emit({ event_id: "stale-chart-event", session_id: previousSession, event_type: "transaction.received", timestamp: previousTx.timestamp, data: { ...previousTx } });
    expect(firstCard().querySelector("strong")?.textContent).toBe("1");
    expect(firstCard().querySelectorAll(".m-contribution-bucket")).toHaveLength(1);
    expect(firstCard().textContent).toContain("Not enough history");
  });
});

describe("shell ownership", () => {
  it("keeps one monitoring owner across all destinations and cosmetic menu interactions", async () => {
    await act(async () => root.render(<StrictMode><App /></StrictMode>));
    // StrictMode may probe initial effects; navigation must add no subscriptions.
    const subscriptions = mocks.subscriptions.mock.calls.length;
    const recoveries = vi.mocked(syntheticSource.history).mock.calls.length;
    for (const page of ["Transactions", "Alerts", "Investigations", "Demo", "Lab", "Overview"]) {
      await nav(page);
      if (page === "Lab") await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Close intelligence lab"]')!.click());
    }
    expect(syntheticSource.ingest).not.toHaveBeenCalled();
    expect(mocks.subscriptions).toHaveBeenCalledTimes(subscriptions);
    expect(syntheticSource.history).toHaveBeenCalledTimes(recoveries);
    await click(" Start simulation");
    await click(" Pause");
    const graph = container.querySelector('[data-testid="graph"]');
    const selected = graph?.getAttribute("data-selected");
    const toggle = container.querySelector<HTMLButtonElement>('[aria-expanded]')!;
    await act(async () => toggle.click());
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Reduce transparency"]')!.click());
    await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(container.querySelector('[data-testid="graph"]')).toBe(graph);
    expect(graph?.getAttribute("data-selected")).toBe(selected);
    const session = vi.mocked(syntheticSource.ingest).mock.calls[0][1];
    await nav("Demo"); await nav("Overview");
    await click(" Resume");
    expect(vi.mocked(syntheticSource.ingest).mock.calls[1][1]).toBe(session);
    expect(mocks.subscriptions).toHaveBeenCalledTimes(subscriptions);
    expect(syntheticSource.history).toHaveBeenCalledTimes(recoveries);
  });
});
