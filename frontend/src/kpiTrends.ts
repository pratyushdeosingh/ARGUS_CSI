import { detectionLabel, type MonitorState } from "./monitoring";
import type { FinancialInvestigation } from "./types";

export interface Trend {
  points: number[];
  current: number;
  previous: number;
  enoughHistory: boolean;
  period: string;
  detail: string;
}
export function percentageChange(current: number, previous: number): number | null {
  if (previous === 0) return current === 0 ? 0 : null;
  return ((current - previous) / previous) * 100;
}
// Half-open adjacent windows: (end - 2w, end - w], (end - w, end].
// Coverage comes from the source history, never the first positive finding.
export function timeTrend(times: number[], start: number, end: number, window: number,
  period: string, detail: string): Trend {
  const valid = times.filter(Number.isFinite);
  const enoughHistory = Number.isFinite(start) && Number.isFinite(end) && end - start >= window * 2;
  const lower = Math.max(start, end - window * 2);
  const points = Number.isFinite(lower) && Number.isFinite(end)
    ? Array.from({ length: Math.max(1, Math.min(12, Math.ceil((end - lower) / (window / 6)))) }, () => 0) : [];
  for (const t of valid) {
    if ((t > lower || (!enoughHistory && t === lower)) && t <= end && points.length) {
      const index = end === lower ? 0 : Math.max(0, Math.min(points.length - 1, Math.ceil((t - lower) / (end - lower) * points.length) - 1));
      points[index]++;
    }
  }
  return {
    points,
    current: valid.filter(t => t > end - window && t <= end).length,
    previous: valid.filter(t => t > end - window * 2 && t <= end - window).length,
    enoughHistory, period, detail,
  };
}
export function runTrends(state: MonitorState) {
  const transactions = Object.values(state.transactions);
  const times = transactions.map(t => Date.parse(t.timestamp)).filter(Number.isFinite);
  const start = times.length ? Math.min(...times) : NaN;
  const end = times.length ? Math.max(...times) : NaN;
  const make = (values: number[], detail: string) => timeTrend(values, start, end, 60_000,
    "60s vs prior 60s · run time", detail);
  const flagged = transactions.filter(t => detectionLabel(state.detections[t.transaction_id]) === "Flagged");
  const alerts = Object.values(state.alerts);
  const alertTimes = alerts.map(a => Date.parse(state.transactions[a.transactionId]?.timestamp ?? ""));
  const alertTrend = make(alertTimes, "Retained alerts by payment time; unmatched payments excluded. Latest 500 alerts.");
  if (alertTimes.some(t => !Number.isFinite(t))) alertTrend.enoughHistory = false;
  return [
    make(times, "Submitted payments, current run; retained history. Chart: up to 120 logical seconds, counts per bucket."),
    make(flagged.map(t => Date.parse(t.timestamp)), "Actual flagged detector results by payment time; current retained run. Pending scores may revise buckets."),
    alertTrend,
  ];
}
export function investigationTrend(financial: FinancialInvestigation[], now: number, failed = false) {
  const history = financial.map(c => Date.parse(c.created_at)).filter(Number.isFinite);
  const active = [
    ...financial.filter(c => c.status === "open").map(c => Date.parse(c.created_at)),
  ];
  const trend = timeTrend(active, history.length ? Math.min(...history) : NaN, now, 7 * 86400_000,
    "7d vs prior 7d · financial created", "Currently open financial cases grouped by creation date, wall-clock UTC. Loaded subset only: latest 50 financial cases; not historical open-case totals. Legacy incidents have signal timestamps, so are excluded from the trend. Chart: up to 14 days.");
  if (failed) { trend.enoughHistory = false; trend.points = []; }
  return trend;
}
