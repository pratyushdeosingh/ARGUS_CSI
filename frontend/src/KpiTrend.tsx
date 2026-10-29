import { memo } from "react";
import { percentageChange, type Trend } from "./kpiTrends";

// Empty slots are presentation placeholders, not additional time buckets.
export const ContributionChart = memo(function ContributionChart({
  points,
  label,
}: {
  points: number[];
  label: string;
}) {
  const values = points.filter(Number.isFinite).map(value => Math.max(0, value));
  const maximum = Math.max(1, ...values);
  const slots = Math.max(12, values.length);
  const padding = slots - values.length;
  const step = 96 / slots;
  return (
    <svg className="m-contribution-chart" viewBox="0 0 100 48" role="img" aria-label={label}>
      {Array.from({ length: slots }, (_, i) => {
        const value = values[i - padding];
        const placeholder = value === undefined;
        const active = !placeholder && value > 0;
        const relative = active ? value / maximum : 0;
        const height = active ? Math.max(8, relative * 40) : 4;
        return (
          <rect
            key={i}
            className={placeholder ? "m-contribution-placeholder" : "m-contribution-bucket"}
            data-count={placeholder ? undefined : value}
            x={2 + i * step}
            y={44 - height}
            width={step * 0.65}
            height={height}
            rx="1"
            fill="currentColor"
            fillOpacity={active ? 0.55 + 0.4 * Math.sqrt(relative) : 0.25}
          >
            <title>{placeholder ? "No bucket history" : `Bucket ${i - padding + 1}: ${value}`}</title>
          </rect>
        );
      })}
    </svg>
  );
});
export const KpiTrend = memo(function KpiTrend({ trend, tone }: { trend: Trend; tone: "volume" | "danger" | "warning" }) {
  const change = trend.enoughHistory ? percentageChange(trend.current, trend.previous) : null;
  const direction = change === null || change === 0 ? "neutral" : change > 0 ? "up" : "down";
  const text = !trend.enoughHistory ? "Not enough history" : change === null ? "— Prior window: 0" : `${change > 0 ? "↑" : change < 0 ? "↓" : "→"} ${Math.abs(change).toFixed(1)}%`;
  return <div className={`m-kpi-trend m-kpi-${tone}`} title={`${trend.detail} Current window: ${trend.current}; previous: ${trend.previous}.`}>
    <ContributionChart points={trend.points} label={`${trend.period}; bucket counts: ${trend.points.length ? trend.points.join(", ") : "no data"}`} />
    <small><span className={`m-kpi-change m-kpi-${direction}`}>{text}</span><br />{trend.period}</small>
  </div>;
});
