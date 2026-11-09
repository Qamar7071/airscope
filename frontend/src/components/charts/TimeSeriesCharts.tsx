import { Area, CartesianGrid, ComposedChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { StationSeries, WeatherSeries } from "../../types";
import { WHO_24H } from "../../utils/aqi";
import { fmtLocalTime, fmtShortDate } from "../../utils/formatting";
import { C, ChartCard, ChartTooltip, EmptyChart, Legend, axisProps, gridProps } from "./common";

const dayTicks = (ts: string[]) => ts.filter((t) => new Date(t).getUTCHours() === 19); // 00:00 PKT

export function StationSeriesChart({ series, stationName }: { series?: StationSeries; stationName?: string }) {
  if (!series) return <ChartCard title="Station time series"><EmptyChart>Select a station on the map or in the Coverage step.</EmptyChart></ChartCard>;
  const rows = series.timestamps.map((t, i) => ({
    t,
    observed: series.observed[i],
    predicted: series.predicted[i],
    band: series.lower[i] != null && series.upper[i] != null ? [series.lower[i], series.upper[i]] : null,
  }));
  const l = series.loso;
  return (
    <ChartCard
      title={`${stationName ?? series.station_id}: observed vs held-out estimate`}
      subtitle="Estimates come from a model that never saw this station (leave-one-station-out), with the calibrated 90% interval."
      table={{
        columns: ["Time (PKT)", "Observed", "Held-out estimate", "90% low", "90% high"],
        rows: rows.map((r) => [fmtLocalTime(r.t), r.observed, r.predicted, r.band?.[0] ?? null, r.band?.[1] ?? null]),
      }}
      height={260}
      note={l ? `Held-out RMSE ${l.rmse.toFixed(1)} µg/m³ (IDW baseline ${l.rmse_idw.toFixed(1)}), bias ${l.bias >= 0 ? "+" : ""}${l.bias.toFixed(1)}. Dashed line: WHO 24-h guideline.` : undefined}
    >
      <Legend items={[{ label: "Observed", color: C.s1 }, { label: "Held-out estimate", color: C.s2 }, { label: "90% interval", color: "rgba(217,89,38,0.35)", shape: "rect" }]} />
      <ResponsiveContainer width="100%" height="88%">
        <ComposedChart data={rows} margin={{ top: 6, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="t" {...axisProps} ticks={dayTicks(series.timestamps)} tickFormatter={(t: string) => fmtShortDate(t)} />
          <YAxis {...axisProps} width={40} />
          <ReferenceLine y={WHO_24H} stroke={C.tick} strokeDasharray="4 4" />
          <Tooltip content={<ChartTooltip format={(v) => `${v.toFixed(0)} µg/m³`} labelFormat={(l) => `${fmtLocalTime(String(l))} PKT`} />} />
          <Area dataKey="band" name="90% interval" stroke="none" fill={C.s2} fillOpacity={0.12} isAnimationActive={false} connectNulls />
          <Line dataKey="observed" name="Observed" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line dataKey="predicted" name="Held-out estimate" stroke={C.s2} strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** Small multiples sharing the time axis (never a dual-axis chart). */
export function WeatherCharts({ w }: { w?: WeatherSeries }) {
  if (!w) return <ChartCard title="Meteorology and dispersion"><EmptyChart>Loading weather…</EmptyChart></ChartCard>;
  const rows = w.timestamps.map((t, i) => ({ t, pm: w.network_mean_pm25[i], vent: w.ventilation_index[i], blh: w.boundary_layer_height_m[i] }));
  const ticks = dayTicks(w.timestamps);
  const panels = [
    { key: "pm", title: "Network-mean PM2.5 (µg/m³)", color: C.s1, fmt: (v: number) => `${v.toFixed(0)} µg/m³` },
    { key: "vent", title: "Ventilation index = boundary-layer height × wind speed (m²/s)", color: C.s3, fmt: (v: number) => `${v.toFixed(0)} m²/s` },
  ] as const;
  return (
    <ChartCard
      title="Why pollution peaks at night"
      subtitle="When the ventilation index collapses after sunset, PM2.5 accumulates. Last 7 days of the dataset."
      table={{ columns: ["Time (PKT)", "Network-mean PM2.5", "Ventilation index", "Boundary-layer height"], rows: rows.map((r) => [fmtLocalTime(r.t), r.pm, r.vent, r.blh]) }}
      height={300}
      note={w.provenance.synthetic ? "Synthetic demo weather and readings." : "Weather: Open-Meteo (CC BY 4.0). PM2.5: OpenAQ stations."}
    >
      <div className="flex h-full flex-col gap-1">
        {panels.map((p) => (
          <div key={p.key} className="min-h-0 flex-1">
            <div className="text-[10.5px] text-txt-muted">{p.title}</div>
            <ResponsiveContainer width="100%" height="85%">
              <LineChart data={rows} syncId="weather" margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="t" {...axisProps} ticks={ticks} tickFormatter={(t: string) => fmtShortDate(t)} hide={p.key === "pm"} />
                <YAxis {...axisProps} width={48} tickFormatter={(v: number) => (v >= 1000 ? `${Math.round(v / 1000)}K` : `${v}`)} />
                <Tooltip content={<ChartTooltip format={p.fmt} labelFormat={(l) => `${fmtLocalTime(String(l))} PKT`} />} />
                <Line dataKey={p.key} name={p.title.split(" (")[0]} stroke={p.color} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}
