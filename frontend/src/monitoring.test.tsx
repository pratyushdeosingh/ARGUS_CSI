import { describe, expect, it, vi, afterEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  applyEvent,
  emptyMonitor,
  neighborhood,
  score,
  detectionLabel,
  type StreamEvent,
} from "./monitoring";
import {
  DATA_SOURCES,
  generateRun,
  SCENARIOS,
  type RunConfig,
} from "./simulation";
import { connectStream } from "./stream";
import CanonicalDemo from "./CanonicalDemo";
import { IntelligenceLab } from "./IntelligenceLab";
const config: RunConfig = {
  session: "SYN-test",
  seed: 42,
  scenario: "mixed",
  start: "2026-10-25T00:00:00Z",
  count: 400,
  accounts: 100,
};
const event = (
  type: string,
  data: Record<string, unknown>,
  id = type,
): StreamEvent => ({
  event_id: id,
  event_type: type,
  timestamp: config.start,
  data,
});
afterEach(() => vi.useRealTimers());
describe("synthetic provider and scenario library", () => {
  it("keeps real data unavailable and synthetic mode operational", () => {
    expect(DATA_SOURCES.synthetic.available).toBe(true);
    expect(DATA_SOURCES.real.available).toBe(false);
    expect(DATA_SOURCES.real.label).toContain("Not Connected");
  });
  it("reproduces seeded transactions, timestamps and labels", () => {
    expect(generateRun(config)).toEqual(generateRun(config));
    expect(generateRun({ ...config, seed: 43 })).not.toEqual(
      generateRun(config),
    );
  });
  it("isolates every account and transaction between scenario sessions", () => {
    const a = generateRun(config);
    const b = generateRun({ ...config, session: "SYN-other" });
    expect(
      a.some(
        (r, i) =>
          r.transaction.transaction_id === b[i].transaction.transaction_id ||
          r.transaction.source_account === b[i].transaction.source_account,
      ),
    ).toBe(false);
  });
  it("produces bounded unique INR transactions, lifecycle statuses and mixed controls", () => {
    const records = generateRun(config);
    expect(records).toHaveLength(400);
    expect(new Set(records.map((r) => r.transaction.transaction_id)).size).toBe(
      400,
    );
    expect(new Set(records.map((r) => r.truth)).size).toBe(2);
    expect(new Set(records.map((r) => r.transaction.status)).size).toBe(3);
    expect(
      records.every(
        (r) =>
          r.transaction.amount > 0 &&
          r.transaction.currency === "INR" &&
          r.transaction.source_account !== r.transaction.destination_account,
      ),
    ).toBe(true);
    expect(generateRun({ ...config, count: 9999 })).toHaveLength(5000);
  });
  it("supports every scenario, clean controls and connected mule forwarding", () => {
    for (const scenario of SCENARIOS)
      expect(generateRun({ ...config, scenario: scenario.id })).toHaveLength(
        400,
      );
    expect(
      generateRun({ ...config, scenario: "normal" }).every(
        (r) => r.truth === "legitimate",
      ),
    ).toBe(true);
    const mule = generateRun({ ...config, scenario: "mule" });
    expect(mule[12].transaction.destination_account).toBe(
      mule[13].transaction.source_account,
    );
    expect(mule[12].transaction.amount).toBeGreaterThan(
      mule[13].transaction.amount,
    );
  });
});
describe("normalized monitoring state", () => {
  it("does not attribute an unrelated high-risk graph window to a clean payment", () => {
    let state = applyEvent(emptyMonitor(), event("transaction.scored", {transaction_id:"clean",risk_score:0.95,suspicious_transactions:["other"]}));
    state = applyEvent(state, event("transaction.scam_scored", {transaction_id:"clean",scam_score:0,risk_score:5}));
    expect(detectionLabel(state.detections.clean)).toBe("Cleared by analysis");
    expect(state.detections.clean.graph).toBe(95);
  });

  it("normalizes scales without treating missing scores as zero", () => {
    expect(score(0.78, 1)).toBe(78);
    expect(score(78, 100)).toBe(78);
    expect(score(undefined, 1)).toBeUndefined();
    expect(score(78, 1)).toBeUndefined();
    expect(score(NaN, 100)).toBeUndefined();
  });
  it("deduplicates events, accepts scoring before receipt and preserves payment status", () => {
    const tx = generateRun(config)[0].transaction;
    const scored = event("transaction.scored", {
      transaction_id: tx.transaction_id,
      risk_score: 0.8,
        suspicious_transactions: [tx.transaction_id],
      reasons: ["Rapid forwarding"],
    });
    let state = applyEvent(emptyMonitor(), scored);
    expect(applyEvent(state, scored)).toBe(state);
    state = applyEvent(state, event("transaction.received", { ...tx }));
    expect(state.transactions[tx.transaction_id].status).toBe("pending");
    expect(state.detections[tx.transaction_id].graph).toBe(80);
    expect(detectionLabel(state.detections[tx.transaction_id])).toBe("Flagged");
  });
  it("handles both detectors and late failures independently", () => {
    let state = applyEvent(
      emptyMonitor(),
      event("transaction.scam_scored", {
        transaction_id: "x",
        scam_score: 20,
        risk_score: 31,
      }),
    );
    state = applyEvent(
      state,
      event("transaction.scored", { transaction_id: "x", risk_score: 0.1 }),
    );
    state = applyEvent(
      state,
      event("transaction.analysis_failed", {
        transaction_id: "x",
        error: "offline",
      }),
    );
    expect(detectionLabel(state.detections.x)).toBe("Cleared by analysis");
    expect(state.detections.x.scam).toBe(20);
    expect(state.detections.x.combined).toBe(31);
  });
  it("deduplicates alert identifiers and retains navigation references and evidence", () => {
    let state = emptyMonitor();
    for (let i = 0; i < 3; i++)
      state = applyEvent(
        state,
        event(
          "scam_alert.created",
          {
            transaction_id: "x",
            alert_id: "a",
            severity: "high",
            supporting_evidence: ["Fan-out"],
          },
          String(i),
        ),
      );
    expect(Object.values(state.alerts)).toHaveLength(1);
    expect(state.alerts.a.transactionId).toBe("x");
    expect(state.alerts.a.evidence).toEqual(["Fan-out"]);
  });
  it("retains failure alerts and independently reports detector failure", () => {
    let state = applyEvent(
      emptyMonitor(),
      event("transaction.scam_scoring_failed", {
        transaction_id: "x",
        error: "Service offline",
      }),
    );
    expect(detectionLabel(state.detections.x)).toBe("Analysis failed");
    expect(Object.values(state.alerts)[0].type).toBe("Analysis unavailable");
  });
  it("bounds history, detector state and neighborhood; changing selection changes graph", () => {
    const txs = generateRun({ ...config, count: 1300 }).map(
      (r) => r.transaction,
    );
    let state = emptyMonitor();
    for (const tx of txs)
      state = applyEvent(
        state,
        event("transaction.received", { ...tx }, tx.transaction_id),
      );
    expect(Object.keys(state.transactions)).toHaveLength(1000);
    const a = neighborhood(txs, txs[12]);
    const b = neighborhood(txs, txs[26]);
    expect(a[0]).toBe(txs[12]);
    expect(b[0]).toBe(txs[26]);
    expect(a).not.toEqual(b);
    expect(a.length).toBeLessThanOrEqual(28);
    expect(neighborhood(txs)).toEqual([]);
  });
});
describe("stream lifecycle", () => {
  it("delivers valid messages, reconnects with recovery and cleans up timers", async () => {
    vi.useFakeTimers();
    const sockets: WebSocket[] = [];
    const create = () => {
      const s = {
        close: vi.fn(),
        onopen: null,
        onclose: null,
        onmessage: null,
        onerror: null,
      } as unknown as WebSocket;
      sockets.push(s);
      return s;
    };
    const receive = vi.fn();
    const status = vi.fn();
    const recover = vi.fn().mockResolvedValue(undefined);
    const stop = connectStream("ws://test", receive, status, recover, create);
    sockets[0].onopen?.call(sockets[0], {} as Event);
    await Promise.resolve();
    expect(recover).toHaveBeenCalledOnce();
    const payload = event("connection.established", {});
    sockets[0].onmessage?.call(sockets[0], {
      data: JSON.stringify(payload),
    } as MessageEvent);
    expect(receive).toHaveBeenCalledWith(payload);
    sockets[0].onmessage?.call(sockets[0], { data: "broken" } as MessageEvent);
    expect(receive).toHaveBeenCalledOnce();
    sockets[0].onclose?.call(sockets[0], {} as CloseEvent);
    await vi.advanceTimersByTimeAsync(1000);
    expect(sockets).toHaveLength(2);
    sockets[1].onopen?.call(sockets[1], {} as Event);
    expect(recover).toHaveBeenCalledTimes(2);
    stop();
    await vi.advanceTimersByTimeAsync(30000);
    expect(sockets).toHaveLength(2);
    expect(sockets[1].close).toHaveBeenCalledOnce();
  });
});
describe("legacy compatibility", () => {
  it("retains the canonical demo controls", () => {
    expect(renderToStaticMarkup(<CanonicalDemo />)).toContain("CANONICAL DEMO");
  });
  it("retains the Intelligence Lab templates and analysis controls", () => {
    const html = renderToStaticMarkup(
      <IntelligenceLab
        open={true}
        incidents={[]}
        onClose={() => {}}
        onAnalyze={vi.fn()}
      />,
    );
    expect(html).toContain("ARGUS Intelligence Lab");
    expect(html).toContain("RUN CROSS-DOMAIN ANALYSIS");
  });
});
