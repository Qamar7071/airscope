import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { Metrics } from "../../types";
import { C, ChartCard, ChartTooltip, EmptyChart, Legend, axisProps, gridProps } from "./common";

const shortModel = (m: string) =>
  m.replace("Baseline: ", "").replace("inverse distance weighting", "IDW").replace("Histogram gradient boosting", "Gradient boosting").replace("training mean", "Training mean").replace("network mean", "Network mean");

export function ModelComparisonChart({ m }: { m: Metrics }) {
  const rows = (m.loso?.models ?? []).map((r) => ({ model: shortModel(r.model), rmse: r.rmse, r2: r.r2, baseline: r.model.startsWith("Baseline"), ensemble: r.model === "AirScope ensemble" }));
  return (
    <ChartCard
      title="Error at held-out stations"
      subtitle="Leave-one-station-out RMSE (µg/m³). Lower is better."
      table={{ columns: ["Model", "RMSE", "R²"], rows: rows.map((r) => [r.model, r.rmse.toFixed(1), r.r2 == null ? null : r.r2.toFixed(3)]) }}
      height={250}
    >
      <Legend items={[{ label: "AirScope models", color: C.s1, shape: "rect" }, { label: "Simple baselines", color: C.muted, shape: "rect" }]} />
      <ResponsiveContainer width="100%" height="88%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 4 }} barCategoryGap={6}>
          <CartesianGrid stroke={C.grid} horizontal={false} />
          <XAxis type="number" {...axisProps} />
          <YAxis type="category" dataKey="model" {...axisProps} width={110} />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<ChartTooltip format={(v) => `${v.toFixed(1)} µg/m³`} />} />
          <Bar dataKey="rmse" name="RMSE" barSize={14} radius={[0, 4, 4, 0]}>
            {rows.map((r) => (
              <Cell key={r.model} fill={r.baseline ? C.muted : C.s1} fillOpacity={r.ensemble || r.baseline ? 1 : 0.7} />
            ))}
            <LabelList dataKey="rmse" position="right" fill={C.text} fontSize={11} formatter={(v: number) => v.toFixed(1)} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function PerStationChart({ m }: { m: Metrics }) {
  const rows = (m.loso?.per_station ?? []).map((s) => ({ name: s.name.replace("Demo site - ", ""), ensemble: s.rmse, idw: s.rmse_idw, dist: s.nearest_other_station_km }));
  return (
    <ChartCard
      title="Error by held-out station"
      subtitle="Isolated stations are hardest to predict - the blind-spot problem in miniature."
      table={{ columns: ["Station", "Ensemble RMSE", "IDW RMSE", "Nearest other station (km)"], rows: rows.map((r) => [r.name, r.ensemble.toFixed(1), r.idw.toFixed(1), r.dist]) }}
      height={250}
    >
      <Legend items={[{ label: "AirScope ensemble", color: C.s1, shape: "rect" }, { label: "IDW baseline", color: C.s2, shape: "rect" }]} />
      <ResponsiveContainer width="100%" height="88%">
        <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 4, left: 0 }} barGap={2}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" {...axisProps} interval={0} tick={{ fill: C.tick, fontSize: 10 }} height={42} angle={-20} textAnchor="end" />
          <YAxis {...axisProps} width={36} />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<ChartTooltip format={(v) => `${v.toFixed(1)} µg/m³`} />} />
          <Bar dataKey="ensemble" name="AirScope ensemble" fill={C.s1} barSize={12} radius={[4, 4, 0, 0]} />
          <Bar dataKey="idw" name="IDW baseline" fill={C.s2} barSize={12} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function CalibrationChart({ m }: { m: Metrics }) {
  const cal = m.calibration;
  if (!cal) return <ChartCard title="Interval calibration" subtitle=""><EmptyChart>Needs at least 3 stations.</EmptyChart></ChartCard>;
  const rows = cal.levels.map((lv, i) => ({ nominal: lv * 100, empirical: cal.empirical_coverage[i] == null ? null : cal.empirical_coverage[i]! * 100, ideal: lv * 100 }));
  const modelOnly = cal.model_only_coverage_90 == null ? [] : [{ nominal: 90, modelOnly: cal.model_only_coverage_90 * 100 }];
  return (
    <ChartCard
      title="Interval calibration"
      subtitle="Share of held-out readings inside each interval (nested LOSO). On the diagonal = honest."
      table={{ columns: ["Nominal", "Empirical (AirScope)", "Model spread only"], rows: rows.map((r) => [`${r.nominal}%`, r.empirical == null ? null : `${r.empirical.toFixed(1)}%`, r.nominal === 90 && modelOnly.length ? `${modelOnly[0].modelOnly.toFixed(1)}%` : null]) }}
      height={250}
    >
      <Legend items={[{ label: "AirScope calibrated", color: C.s1, shape: "line" }, { label: "Tree-model spread only", color: C.s2, shape: "dot" }, { label: "Ideal", color: C.muted, shape: "line" }]} />
      <ResponsiveContainer width="100%" height="88%">
        <ComposedChart margin={{ top: 6, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={C.grid} />
          <XAxis type="number" dataKey="nominal" domain={[40, 100]} ticks={[50, 60, 70, 80, 90, 100]} {...axisProps} unit="%" allowDuplicatedCategory={false} />
          <YAxis type="number" domain={[30, 100]} {...axisProps} unit="%" width={44} />
          <Tooltip content={<ChartTooltip format={(v) => `${v.toFixed(1)}%`} labelFormat={(l) => `Nominal ${l}%`} />} />
          <Line data={rows} dataKey="ideal" name="Ideal" stroke={C.muted} strokeWidth={1} dot={false} isAnimationActive={false} />
          <Line data={rows} dataKey="empirical" name="AirScope calibrated" stroke={C.s1} strokeWidth={2} dot={{ r: 4, fill: C.s1, stroke: C.surface, strokeWidth: 2 }} isAnimationActive={false} />
          <Scatter data={modelOnly} dataKey="modelOnly" name="Tree-model spread only" fill={C.s2} shape="circle" isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function VariogramChart({ m }: { m: Metrics }) {
  const v = m.variogram;
  if (!v) return <ChartCard title="Spatial structure" subtitle=""><EmptyChart>Needs at least 3 stations.</EmptyChart></ChartCard>;
  const pts = v.pairs.map((p) => ({ d: p.distance_km, gamma: p.semivariance, pair: `${p.a}–${p.b}` }));
  const curve = v.curve.map((c) => ({ d: c.distance_km, fit: c.semivariance }));
  return (
    <ChartCard
      title="Spatial structure of errors"
      subtitle={`Semivariance of held-out residuals vs station distance. Range ${v.range_km.toFixed(1)} km${v.method === "fallback" ? " (fit unstable - city default used)" : ""}.`}
      table={{ columns: ["Station pair", "Distance (km)", "Semivariance"], rows: pts.map((p) => [p.pair, p.d.toFixed(2), p.gamma.toFixed(4)]) }}
      height={250}
    >
      <Legend items={[{ label: "Station pairs", color: C.s1, shape: "dot" }, { label: "Exponential model", color: C.s2, shape: "line" }]} />
      <ResponsiveContainer width="100%" height="88%">
        <ComposedChart margin={{ top: 6, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={C.grid} />
          <XAxis type="number" dataKey="d" {...axisProps} unit=" km" domain={[0, (max: number) => Math.ceil(max / 5) * 5]} tickFormatter={(x: number) => x.toFixed(0)} />
          <YAxis type="number" {...axisProps} width={48} tickFormatter={(x: number) => x.toFixed(2)} />
          <Tooltip content={<ChartTooltip format={(x) => x.toFixed(4)} labelFormat={(l) => `${Number(l).toFixed(2)} km`} />} />
          <Line data={curve} dataKey="fit" name="Exponential model" stroke={C.s2} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Scatter data={pts} dataKey="gamma" name="Station pair" fill={C.s1} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function CoverageByDistanceChart({ m }: { m: Metrics }) {
  const bands = m.osse?.reconstruction.coverage_by_distance ?? [];
  if (!bands.length) return null;
  return (
    <ChartCard
      title="Error grows away from stations (OSSE)"
      subtitle="City-wide RMSE vs the synthetic truth, by distance to the nearest station."
      table={{ columns: ["Distance band", "Cells", "RMSE", "90% interval coverage"], rows: bands.map((b) => [b.band, b.cells, b.rmse.toFixed(1), `${(100 * b.interval_coverage_90).toFixed(0)}%`]) }}
      height={250}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={bands} margin={{ top: 16, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="band" {...axisProps} />
          <YAxis {...axisProps} width={36} />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<ChartTooltip format={(x) => `${x.toFixed(1)} µg/m³`} />} />
          <Bar dataKey="rmse" name="RMSE" fill={C.s1} barSize={22} radius={[4, 4, 0, 0]}>
            <LabelList dataKey="rmse" position="top" fill={C.text} fontSize={11} formatter={(x: number) => x.toFixed(1)} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function ImportanceChart({ m }: { m: Metrics }) {
  const fi = m.feature_importance;
  if (!fi) return <ChartCard title="What drives the estimates" subtitle=""><EmptyChart>Feature importance is computed in the full training profile.</EmptyChart></ChartCard>;
  const rows = fi.features.slice(0, 12).map((f) => ({ name: f.description ?? f.name, value: Math.max(0, f.rmse_increase) }));
  return (
    <ChartCard
      title="What drives the estimates"
      subtitle="Permutation importance at held-out stations: RMSE increase (µg/m³) when a feature is scrambled."
      table={{ columns: ["Feature", "Group", "RMSE increase", "Relative"], rows: fi.features.map((f) => [f.description ?? f.name, f.group ?? "", f.rmse_increase.toFixed(2), `${f.relative_pct.toFixed(1)}%`]) }}
      height={300}
      note="Static features (location, population, elevation) can only show importance across stations; with few stations their effect is hard to separate."
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 4 }} barCategoryGap={4}>
          <CartesianGrid stroke={C.grid} horizontal={false} />
          <XAxis type="number" {...axisProps} />
          <YAxis type="category" dataKey="name" {...axisProps} width={190} tick={{ fill: C.tick, fontSize: 10.5 }} />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<ChartTooltip format={(x) => `+${x.toFixed(2)} µg/m³`} />} />
          <Bar dataKey="value" name="RMSE increase" fill={C.s1} barSize={12} radius={[0, 4, 4, 0]}>
            <LabelList dataKey="value" position="right" fill={C.text} fontSize={10.5} formatter={(x: number) => x.toFixed(1)} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function GroupImportanceChart({ m }: { m: Metrics }) {
  const fi = m.feature_importance;
  if (!fi) return null;
  const label: Record<string, string> = { meteorological: "Meteorology", network_context: "Other stations (same hour)", spatial: "Location & geography", temporal: "Time of day / year" };
  const rows = fi.groups.map((g) => ({ name: label[g.name] ?? g.name, value: Math.max(0, g.rmse_increase) }));
  return (
    <ChartCard
      title="Importance by feature group"
      subtitle="Whole groups scrambled together (captures shared information)."
      table={{ columns: ["Group", "RMSE increase"], rows: rows.map((r) => [r.name, r.value.toFixed(2)]) }}
      height={180}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 4 }} barCategoryGap={6}>
          <CartesianGrid stroke={C.grid} horizontal={false} />
          <XAxis type="number" {...axisProps} />
          <YAxis type="category" dataKey="name" {...axisProps} width={170} />
          <ReferenceLine x={0} stroke={C.axis} />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<ChartTooltip format={(x) => `+${x.toFixed(2)} µg/m³`} />} />
          <Bar dataKey="value" name="RMSE increase" fill={C.s1} barSize={14} radius={[0, 4, 4, 0]}>
            <LabelList dataKey="value" position="right" fill={C.text} fontSize={11} formatter={(x: number) => x.toFixed(1)} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
