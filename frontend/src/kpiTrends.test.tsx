import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ContributionChart, KpiTrend } from "./KpiTrend";
import { percentageChange, timeTrend, runTrends, investigationTrend } from "./kpiTrends";
import { emptyMonitor } from "./monitoring";
import type { Transaction } from "./types";

describe("KPI calculations", () => {
  it("calculates increases, decreases, unchanged and zero baselines safely", () => {
    expect(percentageChange(15, 10)).toBe(50);
    expect(percentageChange(5, 10)).toBe(-50);
    expect(percentageChange(10, 10)).toBe(0);
    expect(percentageChange(0, 0)).toBe(0);
    expect(percentageChange(5, 0)).toBeNull();
  });
  it("compares equal adjacent windows with exact boundaries and requires full coverage", () => {
    const t = timeTrend([0, 60, 61, 120], 0, 120, 60, "period", "detail");
    expect(t).toMatchObject({ current: 2, previous: 1, enoughHistory: true });
    expect(t.points.reduce((sum, n) => sum + n, 0)).toBe(t.current + t.previous);
    expect(timeTrend([60, 120], 60, 120, 60, "", "").enoughHistory).toBe(false);
    expect(runTrends(emptyMonitor()).every(t => !t.enoughHistory && !t.points.length)).toBe(true);
  });
  it("uses payment logical time for actual normal/flagged records and alerts, ignoring delivery time", () => {
    const state = emptyMonitor();
    for (const [id, seconds] of [["a", 0], ["b", 60], ["c", 120]] as const) {
      state.transactions[id] = { transaction_id: id, timestamp: new Date(seconds * 1000).toISOString() } as Transaction;
    }
    state.detections.a = { scam: 2, scamState: "scored", graph: 1, graphState: "scored" };
    state.detections.b = { scam: 90, scamState: "scored" };
    state.detections.c = { scam: 95, scamState: "scored" };
    state.alerts.x = { id: "x", transactionId: "b", timestamp: "2026-10-25T00:00:00Z", type: "scam", severity: "high", message: "actual", evidence: [] };
    const [payments, flagged, alerts] = runTrends(state);
    expect(payments.current).toBe(1);
    expect(flagged).toMatchObject({ current: 1, previous: 1, enoughHistory: true });
    expect(alerts).toMatchObject({ current: 0, previous: 1, enoughHistory: true });
    state.alerts.x.transactionId = "evicted";
    expect(runTrends(state)[2].enoughHistory).toBe(false);
  });
  it("labels loaded open cases by creation date rather than historical open totals", () => {
    const day = 86400_000, now = Date.parse("2026-10-25T00:00:00Z");
    const cases = [15, 10, 2, 1].map((days, i) => ({ created_at: new Date(now - days * day).toISOString(), status: i === 3 ? "merged" : "open" })) as any;
    expect(investigationTrend(cases, now)).toMatchObject({ current: 1, previous: 1, enoughHistory: true, period: "7d vs prior 7d · financial created" });
    expect(investigationTrend(cases.slice(1), now).enoughHistory).toBe(false);
    expect(investigationTrend(cases, now, true).points).toEqual([]);
  });
});
describe("contribution micro charts", () => {
  const chart = (points: number[]) => renderToStaticMarkup(<ContributionChart points={points} label="Actual counts" />);
  it("renders actual bucket counts and no line chart geometry", () => {
    const html = chart([1, 4, 2]);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="Actual counts"');
    expect((html.match(/class="m-contribution-bucket"/g) ?? []).length).toBe(3);
    expect((html.match(/class="m-contribution-placeholder"/g) ?? []).length).toBe(9);
    for (const value of [1, 4, 2]) expect(html).toContain(`data-count="${value}"`);
    expect(html).not.toMatch(/<polyline|<path|<circle|NaN|Infinity/);
  });
  it("keeps no-history placeholders distinct from real zero buckets", () => {
    expect((chart([]).match(/class="m-contribution-placeholder"/g) ?? []).length).toBe(12);
    expect(chart([])).not.toContain('data-count=');
    const zero = chart([0, 0]);
    expect((zero.match(/data-count="0"/g) ?? []).length).toBe(2);
    expect(zero).toContain('height="4"');
    expect(zero).not.toMatch(/NaN|Infinity/);
  });
  it("renders constant positive activity as visible equal bars", () => {
    const html = chart([3, 3, 3]);
    expect((html.match(/height="40"/g) ?? []).length).toBe(3);
    expect(chart([1])).toContain('height="40"');
  });
  it("gives even a small nonzero value a visible minimum height", () => {
    const html = chart([1, 1000]);
    expect(html).toMatch(/data-count="1"[^>]*height="8"/);
    expect(html).toMatch(/data-count="1000"[^>]*height="40"/);
  });
  it("shows honest insufficient and zero-baseline states, and fraud increases use danger tone", () => {
    const trend = timeTrend([70, 80], 0, 120, 60, "60s vs prior 60s", "Actual events");
    const html = renderToStaticMarkup(<KpiTrend trend={trend} tone="danger" />);
    expect(html).toContain("Prior window: 0");
    expect(html).not.toContain("Infinity");
    expect(renderToStaticMarkup(<KpiTrend trend={{ ...trend, enoughHistory: false }} tone="warning" />)).toContain("Not enough history");
    expect(renderToStaticMarkup(<KpiTrend trend={{ ...trend, previous: 1 }} tone="danger" />)).toContain("↑ 100.0%");
  });
});
