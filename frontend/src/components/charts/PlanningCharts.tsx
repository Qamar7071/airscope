import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, LabelList, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Metrics, RecommendationsResponse } from "../../types";
import { C, ChartCard, ChartTooltip, EmptyChart, Legend, axisProps, gridProps } from "./common";

export function CoverageCurveChart({ recs, k }: { recs?: RecommendationsResponse; k: number }) {
  if (!recs) return <ChartCard title="How many new stations are worth it?"><EmptyChart>Computing placements…</EmptyChart></ChartCard>;
  const rows = recs.curve;
  return (
    <ChartCard
      title="How many new stations are worth it?"
      subtitle={`Greedy sequence for "${recs.strategy_label}" - each added station gains less (diminishing returns).`}
      table={{
        columns: ["New stations", "Need-weighted coverage", "Residents within radius", "Spatial uncertainty reduction", "Residents in critical gaps"],
        rows: rows.map((r) => [r.k, `${r.need_weighted_coverage_pct.toFixed(1)}%`, `${r.population_within_radius_pct.toFixed(1)}%`, `${r.uncertainty_reduction_pct.toFixed(1)}%`, r.population_in_critical_gaps.toLocaleString()]),
      }}
      height={270}
    >
      <Legend
        items={[
          { label: "Need-weighted coverage", color: C.s1 },
          { label: "Residents within radius", color: C.s2 },
          { label: "Spatial uncertainty reduction", color: C.s3 },
        ]}
      />
      <ResponsiveContainer width="100%" height="88%">
        <LineChart data={rows} margin={{ top: 6, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="k" {...axisProps} allowDecimals={false} />
          <YAxis {...axisProps} unit="%" width={44} domain={[0, 100]} />
          <ReferenceLine x={k} stroke={C.tick} strokeWidth={1} label={{ value: `k = ${k}`, fill: C.tick, fontSize: 10, position: "insideTopRight" }} />
          <Tooltip content={<ChartTooltip format={(v) => `${v.toFixed(1)}%`} labelFormat={(l) => `${l} new station${l === 1 ? "" : "s"}`} />} />
          <Line type="monotone" dataKey="need_weighted_coverage_pct" name="Need-weighted coverage" stroke={C.s1} strokeWidth={2} dot={{ r: 3, fill: C.s1, stroke: C.surface, strokeWidth: 2 }} isAnimationActive={false} />
          <Line type="monotone" dataKey="population_within_radius_pct" name="Residents within radius" stroke={C.s2} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="uncertainty_reduction_pct" name="Spatial uncertainty reduction" stroke={C.s3} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function OsseBenchmarkChart({ m }: { m: Metrics }) {
  const bench = m.osse?.placement_benchmark;
  if (!bench) {
    return (
      <ChartCard title="Placement strategies vs synthetic truth">
        <EmptyChart>The OSSE benchmark runs only in demo mode (it needs a known truth) with the full training profile.</EmptyChart>
      </ChartCard>
    );
  }
  const rows = bench.scenarios
    .filter((s) => s.key !== "baseline")
    .map((s) => ({
      name: s.key === "coverage" ? "AirScope: coverage" : s.key === "variance" ? "AirScope: kriging variance" : s.key === "population" ? "Population heuristic" : "Random (mean)",
      value: s.improvement_pct,
      err: s.improvement_std ?? 0,
      pop: s.pop_improvement_pct,
      rmse: s.rmse,
      airscope: s.key === "coverage" || s.key === "variance",
    }));
  const base = bench.scenarios.find((s) => s.key === "baseline");
  return (
    <ChartCard
      title={`Error reduction from ${bench.k} new stations (OSSE)`}
      subtitle="Virtual stations sample the synthetic truth; the ensemble is retrained; city-wide RMSE is re-measured."
      table={{
        columns: ["Scenario", "City-wide RMSE", "Improvement", "Population-weighted improvement"],
        rows: [
          ["Current network", base?.rmse.toFixed(2) ?? null, "0%", "0%"],
          ...rows.map((r) => [r.name, r.rmse.toFixed(2), `${r.value.toFixed(1)}%${r.err ? ` ± ${r.err.toFixed(1)}` : ""}`, `${r.pop.toFixed(1)}%`]),
        ],
      }}
      height={250}
      note="Synthetic experiment. The random bar shows the mean ± standard deviation over independent random draws."
    >
      <Legend items={[{ label: "AirScope strategies", color: C.s1, shape: "rect" }, { label: "Baselines", color: C.muted, shape: "rect" }]} />
      <ResponsiveContainer width="100%" height="88%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 4 }} barCategoryGap={8}>
          <CartesianGrid stroke={C.grid} horizontal={false} />
          <XAxis type="number" {...axisProps} unit="%" />
          <YAxis type="category" dataKey="name" {...axisProps} width={150} />
          <ReferenceLine x={0} stroke={C.axis} />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<ChartTooltip format={(v) => `${v.toFixed(1)}%`} />} />
          <Bar dataKey="value" name="RMSE reduction" barSize={16} radius={[0, 4, 4, 0]}>
            {rows.map((r) => (
              <Cell key={r.name} fill={r.airscope ? C.s1 : C.muted} />
            ))}
            <ErrorBar dataKey="err" width={4} strokeWidth={1.5} stroke={C.text} direction="x" />
            <LabelList dataKey="value" position="right" fill={C.text} fontSize={11} formatter={(v: number) => `${v.toFixed(1)}%`} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
