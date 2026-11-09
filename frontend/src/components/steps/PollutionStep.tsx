import { MapPin } from "lucide-react";
import { useMemo } from "react";
import { useCity, useGrid } from "../../hooks/useAirScopeData";
import { useCityStatus } from "../../hooks/useCityStatus";
import { useAppState, useDispatch, useTimeParam } from "../../state/store";
import type { GridResponse, Locality } from "../../types";
import { aqiBand, WHO_24H } from "../../utils/aqi";
import { fmtCompact, fmtPct, fmtPm } from "../../utils/formatting";
import { cellCenter, describeLocation, haversineKm } from "../../utils/geo";
import MetricsPanel from "../MetricsPanel";
import { SectionTitle, SegmentedBar } from "../ui";

function hotspots(grid: GridResponse, localities: Locality[] | undefined, n = 4) {
  const pm = grid.layers.pm25 ?? [];
  const order = pm.map((v, i) => [v ?? -1, i] as [number, number]).filter(([v]) => v >= 0).sort((a, b) => b[0] - a[0]);
  const picks: { idx: number; lat: number; lon: number; pm: number; label: string }[] = [];
  for (const [v, i] of order) {
    const c = cellCenter(grid.geometry, i);
    if (picks.some((p) => haversineKm(p.lat, p.lon, c.lat, c.lon) < 2.5)) continue;
    picks.push({ idx: i, ...c, pm: v, label: describeLocation(localities, c.lat, c.lon) });
    if (picks.length >= n) break;
  }
  return picks;
}

export default function PollutionStep() {
  const s = useAppState();
  const dispatch = useDispatch();
  const { ready } = useCityStatus(s.cityId);
  const grid = useGrid(s.cityId, useTimeParam(), ready);
  const city = useCity(s.cityId);
  const g = grid.data;
  const st = g?.stats;
  const spots = useMemo(() => (g && g.pm25_available ? hotspots(g, city.data?.localities) : []), [g, city.data]);

  if (g && !g.pm25_available) {
    return <p className="text-xs text-txt-secondary">No usable monitoring stations: PM2.5 cannot be estimated for this city yet. Coverage and placement analyses still work.</p>;
  }
  const meanBand = aqiBand(st?.pm25?.population_weighted_mean);
  const total = st?.population_total ?? 0;
  return (
    <div className="space-y-4">
      <p className="text-xs leading-relaxed text-txt-secondary">
        City-wide PM2.5 estimated by an ensemble of tree models from {city.data?.dataset.n_usable_stations ?? "the"} stations, weather and
        geography - including where no station exists. {g?.mode === "snapshot" ? "Showing the selected hour." : "Showing the period average; switch to Hourly below to explore individual hours."}
      </p>
      <MetricsPanel
        loading={!st?.pm25}
        tiles={[
          { label: "Population-weighted mean", value: fmtPm(st?.pm25?.population_weighted_mean), sub: meanBand?.category, hint: "Average estimate experienced by residents (cells weighted by population)." },
          { label: "Highest cell estimate", value: fmtPm(st?.pm25?.max), sub: `10th–90th pct: ${Math.round(st?.pm25?.p10 ?? 0)}–${Math.round(st?.pm25?.p90 ?? 0)}` },
          { label: "Residents in unhealthy air", value: fmtCompact(st?.population_unhealthy), sub: `${fmtPct((100 * (st?.population_unhealthy ?? 0)) / (total || 1), 0)} of the domain (≥ 55.5 µg/m³)`, tone: "bad" },
          { label: `Above WHO 24-h (${WHO_24H} µg/m³)`, value: fmtPct((100 * (st?.population_above_who_24h ?? 0)) / (total || 1), 0), sub: `${fmtCompact(st?.population_above_who_24h)} residents` },
        ]}
      />
      {st?.aqi_distribution && (
        <div>
          <SectionTitle>Residents by AQI category</SectionTitle>
          <SegmentedBar label="Share of residents by AQI category" parts={st.aqi_distribution.map((r) => ({ key: r.category, value: r.population, color: r.color, name: r.category }))} />
          <ul className="mt-2 space-y-1">
            {st.aqi_distribution.filter((r) => r.population > 0).map((r) => (
              <li key={r.category} className="flex items-center justify-between text-[11.5px]">
                <span className="flex items-center gap-2 text-txt-secondary">
                  <span className="h-2 w-2 rounded-sm" style={{ background: r.color }} aria-hidden /> {r.category}
                </span>
                <span className="kbd-num text-txt-primary">{fmtPct(r.population_pct, 1)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {spots.length > 0 && (
        <div>
          <SectionTitle>Estimated hotspots</SectionTitle>
          <ul className="space-y-1">
            {spots.map((p) => (
              <li key={p.idx}>
                <button
                  className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-xs text-txt-secondary hover:bg-white/[0.05] hover:text-txt-primary"
                  onClick={() => dispatch({ type: "focus", lat: p.lat, lon: p.lon, zoom: 14 })}
                >
                  <span className="flex items-center gap-2">
                    <MapPin className="h-3.5 w-3.5 text-txt-muted" aria-hidden />
                    {p.label}
                  </span>
                  <span className="kbd-num font-medium text-txt-primary">{fmtPm(p.pm)}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[10.5px] text-txt-muted">Model estimates; check the uncertainty step before acting on them.</p>
        </div>
      )}
    </div>
  );
}
