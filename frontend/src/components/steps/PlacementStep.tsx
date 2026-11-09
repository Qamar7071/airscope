import { ListOrdered, MousePointerClick, RotateCcw, Trash2 } from "lucide-react";
import { useCity, useRecommendations, useSimulation } from "../../hooks/useAirScopeData";
import { useCityStatus } from "../../hooks/useCityStatus";
import { useAppState, useDispatch } from "../../state/store";
import type { Impact, Strategy } from "../../types";
import { fmtCompact, fmtPct, fmtSigned, fmtSignedCompact } from "../../utils/formatting";
import { SectionTitle, Slider, Toggle } from "../ui";

const STRATEGIES: { id: Strategy; label: string; hint: string }[] = [
  { id: "coverage", label: "Need-weighted coverage", hint: "Greedy maximisation of coverage weighted by exposure need and uncertainty (submodular, (1−1/e) guarantee)." },
  { id: "variance", label: "Kriging-variance reduction", hint: "Greedy reduction of the spatial prediction variance, weighted by exposure need." },
  { id: "population", label: "Population heuristic", hint: "Baseline: densest eligible cells, respecting spacing." },
  { id: "random", label: "Random (baseline)", hint: "Baseline: random eligible cells, respecting spacing." },
];

export function ImpactRows({ impact, radius }: { impact: Impact; radius: number }) {
  const b = impact.before;
  const a = impact.after;
  const rows = [
    { label: "Need-weighted coverage", before: fmtPct(b.need_weighted_coverage_pct, 0), after: fmtPct(a.need_weighted_coverage_pct, 0), delta: fmtSigned(impact.delta.need_weighted_coverage_pct, 1, " pp") },
    { label: `Residents within ${radius} km`, before: fmtPct(b.population_within_radius_pct, 0), after: fmtPct(a.population_within_radius_pct, 0), delta: fmtSigned(impact.delta.population_within_radius_pct, 1, " pp") },
    { label: "Spatial uncertainty", before: "100%", after: fmtPct(100 - (impact.delta.uncertainty_reduction_pct ?? 0), 0), delta: fmtSigned(-(impact.delta.uncertainty_reduction_pct ?? 0), 1, "%") },
    { label: "Residents in critical gaps", before: fmtCompact(b.population_in_critical_gaps), after: fmtCompact(a.population_in_critical_gaps), delta: fmtSignedCompact(impact.delta.population_in_critical_gaps ?? 0) },
  ];
  return (
    <table className="w-full text-[11.5px]">
      <thead>
        <tr className="text-[10.5px] text-txt-muted">
          <th className="pb-1 text-left font-medium">Metric</th>
          <th className="pb-1 text-right font-medium">Now</th>
          <th className="pb-1 text-right font-medium">After</th>
          <th className="pb-1 text-right font-medium">Change</th>
        </tr>
      </thead>
      <tbody className="kbd-num">
        {rows.map((r) => (
          <tr key={r.label} className="border-t border-white/[0.05]">
            <td className="py-1 text-txt-secondary">{r.label}</td>
            <td className="py-1 text-right text-txt-secondary">{r.before}</td>
            <td className="py-1 text-right font-medium text-txt-primary">{r.after}</td>
            <td className="py-1 text-right text-txt-primary">{r.delta}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function PlacementStep() {
  const s = useAppState();
  const dispatch = useDispatch();
  const { ready } = useCityStatus(s.cityId);
  const city = useCity(s.cityId);
  const recs = useRecommendations(s.cityId, s.weights, s.placement, ready);
  const sim = useSimulation(s.cityId, s.weights, s.simSites, ready);
  const p = s.placement;
  const set = (patch: Partial<typeof p>) => dispatch({ type: "setPlacement", placement: patch });
  const radius = city.data?.coverage_radius_km ?? 2;

  return (
    <div className="space-y-4">
      <p className="text-xs leading-relaxed text-txt-secondary">
        AirScope proposes coordinates for new monitors that close the most important blind spots, and estimates how much coverage and
        certainty each one would add. Planning uses the period-average field.
      </p>
      <div className="space-y-3 rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/[0.06]">
        <div className="flex items-center justify-between">
          <h3 className="panel-title">Placement settings</h3>
          <button className="inline-flex items-center gap-1 text-[11px] text-txt-muted hover:text-txt-primary" onClick={() => dispatch({ type: "resetPlacement" })}>
            <RotateCcw className="h-3 w-3" /> Reset
          </button>
        </div>
        <Slider label="New stations" value={p.k} min={1} max={15} step={1} onChange={(v) => set({ k: v })} />
        <div className="space-y-1.5">
          <label htmlFor="strategy" className="text-xs text-txt-secondary">Strategy</label>
          <select
            id="strategy"
            value={p.strategy}
            onChange={(e) => set({ strategy: e.target.value as Strategy })}
            className="w-full rounded-lg bg-ink-800 px-2 py-1.5 text-xs text-txt-primary ring-1 ring-white/10 focus:outline-none focus:ring-2 focus:ring-brand-400/70"
          >
            {STRATEGIES.map((st) => (
              <option key={st.id} value={st.id}>{st.label}</option>
            ))}
          </select>
          <p className="text-[10.5px] leading-snug text-txt-muted">{STRATEGIES.find((st) => st.id === p.strategy)?.hint}</p>
        </div>
        <Slider label="Min. spacing between new sites" value={p.min_spacing_km} min={0} max={5} step={0.25} onChange={(v) => set({ min_spacing_km: v })} format={(v) => `${v} km`} />
        <Slider label="Min. distance to existing stations" value={p.min_station_distance_km} min={0} max={5} step={0.25} onChange={(v) => set({ min_station_distance_km: v })} format={(v) => `${v} km`} />
        <Slider
          label="Min. population density"
          value={p.min_population_density}
          min={0}
          max={5000}
          step={100}
          onChange={(v) => set({ min_population_density: v })}
          format={(v) => `${fmtCompact(v)}/km²`}
          hint="Proxy for power, access and security at a site; excludes forests, lakes and empty land."
        />
      </div>
      {recs.data && (
        <div>
          <SectionTitle right={<span className="text-[10.5px] text-txt-muted">{recs.data.sites.length} sites · {recs.data.eligible_cells} eligible cells</span>}>
            Expected impact
          </SectionTitle>
          <ImpactRows impact={recs.data.impact} radius={radius} />
          {recs.data.message && <p className="mt-1.5 text-[11px] text-status-warning">{recs.data.message}</p>}
          <button className="btn-primary mt-2.5 w-full" onClick={() => dispatch({ type: "setDrawerOpen", open: true })}>
            <ListOrdered className="h-4 w-4" /> Review recommended sites
          </button>
        </div>
      )}
      <div className="space-y-2 rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/[0.06]">
        <h3 className="panel-title">What-if simulation</h3>
        <Toggle
          label="Click the map to add sensors"
          checked={s.simulate}
          onChange={(v) => dispatch({ type: "setSimulate", simulate: v })}
          swatch={<MousePointerClick className="h-3.5 w-3.5 text-brand-400" aria-hidden />}
        />
        <p className="text-[10.5px] leading-snug text-txt-muted">Place up to 10 hypothetical sensors (drag to move). Their impact is computed with the same metrics.</p>
        {s.simSites.length > 0 && (
          <>
            {sim.data && <ImpactRows impact={sim.data.impact} radius={radius} />}
            <div className="flex gap-2">
              <button className="btn-ghost flex-1" onClick={() => dispatch({ type: "setDrawerOpen", open: true })}>Details</button>
              <button className="btn-ghost" onClick={() => dispatch({ type: "clearSimSites" })}>
                <Trash2 className="h-3.5 w-3.5" /> Clear
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
