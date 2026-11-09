import { RotateCcw } from "lucide-react";
import { useGaps } from "../../hooks/useAirScopeData";
import { useCityStatus } from "../../hooks/useCityStatus";
import { useAppState, useDispatch } from "../../state/store";
import { GAP_COLORS } from "../../utils/colors";
import { fmtCompact, fmtKm, fmtPct, fmtPm } from "../../utils/formatting";
import MetricsPanel from "../MetricsPanel";
import { SectionTitle, SegmentedBar, Slider } from "../ui";

const ORDER = ["critical", "high", "moderate", "low"];

export default function GapsStep() {
  const s = useAppState();
  const dispatch = useDispatch();
  const { ready } = useCityStatus(s.cityId);
  const gaps = useGaps(s.cityId, s.weights, ready);
  const d = gaps.data;
  const w = s.weights;
  const set = (patch: Partial<typeof w>) => dispatch({ type: "setWeights", weights: patch });
  const fmtW = (v: number) => v.toFixed(2);

  return (
    <div className="space-y-4">
      <p className="text-xs leading-relaxed text-txt-secondary">
        The <span className="text-txt-primary">Monitoring Gap Index</span> flags places that are both <em>poorly observed</em> (far from
        stations, uncertain) and <em>important</em> (polluted, populated). It is a geometric mean, so a well-monitored district or an empty
        hillside never scores as a blind spot.
      </p>
      <MetricsPanel
        loading={!d}
        tiles={[
          { label: "Residents in critical gaps", value: fmtCompact(d?.summary.by_class.critical.population), sub: `${fmtPct(d?.summary.by_class.critical.population_pct, 0)} of the domain`, tone: "bad" },
          { label: "Critical area", value: `${Math.round(d?.summary.by_class.critical.area_km2 ?? 0)} km²`, sub: `${d?.summary.by_class.critical.cells ?? "–"} grid cells` },
          { label: "Blind-spot clusters", value: `${d?.clusters.length ?? "–"}`, sub: "connected critical areas" },
          { label: "Population-weighted index", value: d ? d.summary.network.population_weighted_gap_index.toFixed(2) : "–", sub: "0 = fully observed" },
        ]}
      />
      <div className="space-y-3 rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/[0.06]">
        <div className="flex items-center justify-between">
          <h3 className="panel-title">Index weights</h3>
          <button className="inline-flex items-center gap-1 text-[11px] text-txt-muted hover:text-txt-primary" onClick={() => dispatch({ type: "resetWeights" })}>
            <RotateCcw className="h-3 w-3" /> Reset
          </button>
        </div>
        <p className="text-[10.5px] font-medium uppercase tracking-wider text-txt-muted">Observation deficit</p>
        <Slider label="Coverage gap" value={w.coverage} min={0} max={1} step={0.05} onChange={(v) => set({ coverage: v })} format={fmtW} hint="Distance-based: how unlikely it is that any station represents the cell." />
        <Slider label="Model uncertainty" value={w.uncertainty} min={0} max={1} step={0.05} onChange={(v) => set({ uncertainty: v })} format={fmtW} hint="Calibrated predictive uncertainty (relative)." />
        <p className="text-[10.5px] font-medium uppercase tracking-wider text-txt-muted">Exposure need</p>
        <Slider label="Pollution level" value={w.pollution} min={0} max={1} step={0.05} onChange={(v) => set({ pollution: v })} format={fmtW} hint="Estimated PM2.5, scaled within the city." />
        <Slider label="Population density" value={w.population} min={0} max={1} step={0.05} onChange={(v) => set({ population: v })} format={fmtW} hint="Log population density, scaled within the city." />
        <Slider
          label="Balance: deficit ↔ need"
          value={w.balance}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => set({ balance: v })}
          format={(v) => `${Math.round(v * 100)} / ${Math.round((1 - v) * 100)}`}
          hint="Exponent α in MGI = deficit^α × need^(1-α). 1 = only observation deficit, 0 = only exposure need."
        />
      </div>
      {d && (
        <div>
          <SectionTitle>Residents by gap class</SectionTitle>
          <SegmentedBar label="Share of residents by monitoring gap class" parts={ORDER.map((k) => ({ key: k, value: d.summary.by_class[k].population, color: GAP_COLORS[k], name: k }))} />
          <ul className="mt-2 space-y-1 text-[11.5px]">
            {ORDER.map((k) => (
              <li key={k} className="flex items-center justify-between text-txt-secondary">
                <span className="flex items-center gap-2 capitalize">
                  <span className="h-2 w-2 rounded-sm" style={{ background: GAP_COLORS[k] }} aria-hidden /> {k}
                </span>
                <span className="kbd-num text-txt-primary">
                  {fmtPct(d.summary.by_class[k].population_pct, 0)} · {Math.round(d.summary.by_class[k].area_km2)} km²
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {d && d.clusters.length > 0 && (
        <div>
          <SectionTitle>Critical blind spots</SectionTitle>
          <ul className="space-y-1">
            {d.clusters.map((c) => (
              <li key={c.id}>
                <button
                  className="w-full rounded-lg px-2 py-1.5 text-left hover:bg-white/[0.05]"
                  onClick={() => dispatch({ type: "focus", lat: c.centroid.lat, lon: c.centroid.lon, zoom: 14 })}
                >
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="flex min-w-0 items-center gap-2 text-txt-primary">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-status-critical text-[10px] font-bold text-white">{c.id}</span>
                      <span className="truncate">{c.location.label}</span>
                    </span>
                    <span className="kbd-num shrink-0 text-txt-secondary">~{fmtCompact(c.population)}</span>
                  </div>
                  <div className="mt-0.5 pl-7 text-[10.5px] text-txt-muted">
                    {c.area_km2} km² · {c.mean_pm25 != null ? `${fmtPm(c.mean_pm25)} · ` : ""}
                    {fmtKm(c.distance_to_nearest_station_km)} to nearest monitor
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
