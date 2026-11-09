import { useMemo } from "react";
import { useGaps, useGrid } from "../hooks/useAirScopeData";
import { useCityStatus } from "../hooks/useCityStatus";
import { useAppState, useDispatch, useTimeParam } from "../state/store";
import { AQI_BANDS } from "../utils/aqi";
import { GAP_COLORS, RAMPS, cssGradient } from "../utils/colors";
import { fmtCompact } from "../utils/formatting";
import { osseDomain, populationDomain } from "./ContextLayers";
import { pmDomain } from "./PollutionGrid";
import { Segmented } from "./ui";
import { uncertaintyDomain } from "./UncertaintyLayer";

function Gradient({ stops, left, right, caption }: { stops: string[]; left: string; right: string; caption: string }) {
  return (
    <div>
      <div className="h-2 rounded-full" style={{ background: cssGradient(stops) }} aria-hidden />
      <div className="mt-1 flex justify-between text-[10.5px] text-txt-secondary kbd-num">
        <span>{left}</span>
        <span>{right}</span>
      </div>
      <p className="mt-1 text-[10.5px] leading-snug text-txt-muted">{caption}</p>
    </div>
  );
}

/** Legend for the active map layer plus keys for the visible overlays. */
export default function AQILegend() {
  const s = useAppState();
  const dispatch = useDispatch();
  const timeParam = useTimeParam();
  const { ready } = useCityStatus(s.cityId);
  const grid = useGrid(s.cityId, timeParam, ready);
  const gaps = useGaps(s.cityId, s.weights, ready);
  const g = grid.data;

  const body = useMemo(() => {
    if (!g) return null;
    switch (s.layer) {
      case "pm25":
        if (s.pmScale === "relative") {
          const [lo, hi] = pmDomain(g);
          return (
            <Gradient
              stops={RAMPS.orange}
              left={`${lo.toFixed(0)} µg/m³`}
              right={`${hi.toFixed(0)} µg/m³`}
              caption="Relative scale: the city's own 2nd–98th percentile range, to show within-city contrast. Not a health category."
            />
          );
        }
        return (
          <div>
            <ul className="space-y-1">
              {AQI_BANDS.map((b) => (
                <li key={b.category} className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="flex items-center gap-2 text-txt-secondary">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: b.color }} aria-hidden />
                    {b.short}
                  </span>
                  <span className="kbd-num text-txt-muted">{b.lo === 225.5 ? "≥ 225.5" : `${b.lo}–${b.hi}`}</span>
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-[10.5px] leading-snug text-txt-muted">
              PM2.5 µg/m³, US EPA AQI categories (2024). Defined for 24-h means; shown on hourly estimates for orientation.
            </p>
          </div>
        );
      case "uncertainty": {
        const [lo, hi] = uncertaintyDomain(g);
        return <Gradient stops={RAMPS.violet} left={`±${lo.toFixed(0)}%`} right={`±${hi.toFixed(0)}%`} caption="Half-width of the calibrated 90% interval, relative to the estimate. Brighter = less certain." />;
      }
      case "gaps":
        return (
          <div>
            <ul className="space-y-1">
              {(gaps.data?.classes ?? []).map((c) => (
                <li key={c.name} className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="flex items-center gap-2 capitalize text-txt-secondary">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: GAP_COLORS[c.name] }} aria-hidden />
                    {c.name}
                  </span>
                  <span className="kbd-num text-txt-muted">{c.name === "low" ? "< 0.45" : `≥ ${c.threshold.toFixed(2)}`}</span>
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-[10.5px] leading-snug text-txt-muted">Monitoring Gap Index: poorly observed AND important. Planning view (period average).</p>
          </div>
        );
      case "population": {
        const [lo, hi] = populationDomain(g.layers.population);
        return <Gradient stops={RAMPS.blue} left={fmtCompact(10 ** lo)} right={fmtCompact(10 ** hi)} caption="Population density, people per km² (log scale). Approximate bundled surface." />;
      }
      case "coverage":
        return <Gradient stops={RAMPS.teal} left="0%" right="100%" caption={`Probability that a station represents the cell (radius ${g.coverage_radius_km} km decay).`} />;
      case "osse_error": {
        const [, hi] = osseDomain(g);
        return <Gradient stops={RAMPS.orange} left="0" right={`${hi.toFixed(0)} µg/m³`} caption="Demo only: actual mean error vs the synthetic truth. Compare with the uncertainty layer." />;
      }
      default:
        return <p className="text-[11px] text-txt-muted">No data layer selected.</p>;
    }
  }, [g, s.layer, s.pmScale, gaps.data]);

  const titles: Record<string, string> = {
    pm25: "Estimated PM2.5",
    uncertainty: "Model uncertainty",
    gaps: "Monitoring gap index",
    population: "Population density",
    coverage: "Monitoring coverage",
    osse_error: "OSSE: actual error",
    none: "Map",
  };

  return (
    <div className="glass w-[252px] rounded-xl p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="panel-title">{titles[s.layer]}</h2>
        {s.layer === "pm25" && (
          <Segmented
            ariaLabel="PM2.5 colour scale"
            size="sm"
            value={s.pmScale}
            onChange={(v) => dispatch({ type: "setPmScale", scale: v })}
            options={[
              { value: "aqi", label: "AQI", title: "US EPA AQI category colours" },
              { value: "relative", label: "Relative", title: "City's own range (within-city contrast)" },
            ]}
          />
        )}
      </div>
      {body ?? <p className="text-[11px] text-txt-muted">Loading layer…</p>}
      <div className="mt-2.5 space-y-1 border-t border-white/[0.06] pt-2 text-[10.5px] text-txt-secondary">
        {s.overlays.stations && (
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ffff00] ring-2 ring-ink-950" aria-hidden /> Monitoring station (colour = PM2.5)
          </div>
        )}
        {s.overlays.recommendations && (
          <div className="flex items-center gap-2">
            <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-brand-400 text-[8px] font-bold text-ink-950" aria-hidden>1</span> Recommended new site
          </div>
        )}
        {s.simSites.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-txt-primary text-[7px] font-bold text-ink-950" aria-hidden>S</span> Hypothetical sensor
          </div>
        )}
        {s.overlays.clusters && (
          <div className="flex items-center gap-2">
            <span className="flex h-3.5 w-3.5 items-center justify-center rounded bg-status-critical text-[8px] font-bold text-white" aria-hidden>A</span> Critical blind-spot cluster
          </div>
        )}
        {s.overlays.coverageRings && (
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full border border-dashed border-brand-300" aria-hidden /> Station representativeness radius
          </div>
        )}
      </div>
    </div>
  );
}
