import { useCity, useGaps, useStations } from "../../hooks/useAirScopeData";
import { useCityStatus } from "../../hooks/useCityStatus";
import { useAppState, useDispatch, useTimeParam } from "../../state/store";
import { aqiColor } from "../../utils/aqi";
import { fmtInt, fmtKm, fmtPct, fmtPm } from "../../utils/formatting";
import MetricsPanel from "../MetricsPanel";
import { SectionTitle } from "../ui";

const QC_LABELS: Record<string, string> = {
  missing_or_non_numeric: "Missing / non-numeric",
  out_of_range: "Out of range (< 0 or > 1000)",
  stuck: "Stuck sensor (≥ 6 h identical)",
  spikes: "Isolated spikes (Hampel filter)",
  duplicates_merged: "Duplicates merged",
};

export default function CoverageStep() {
  const s = useAppState();
  const dispatch = useDispatch();
  const { ready } = useCityStatus(s.cityId);
  const city = useCity(s.cityId);
  const gaps = useGaps(s.cityId, s.weights, ready);
  const stations = useStations(s.cityId, useTimeParam());
  const net = gaps.data?.summary.network;
  const radius = city.data?.coverage_radius_km ?? 2;
  const qc = city.data?.dataset.qc.observations;

  return (
    <div className="space-y-4">
      <p className="text-xs leading-relaxed text-txt-secondary">
        A station represents air quality only in its surroundings. AirScope treats each station as covering its neighbourhood with
        a probability that decays with distance ({radius} km scale) and maps where nobody is watching.
      </p>
      <MetricsPanel
        loading={!net}
        tiles={[
          { label: "Monitoring stations", value: `${city.data?.dataset.n_usable_stations ?? "–"}`, sub: `${city.data?.dataset.n_stations ?? "–"} listed, ${city.data?.dataset.n_usable_stations ?? "–"} pass QC` },
          { label: `Residents within ${radius} km`, value: fmtPct(net?.population_within_radius_pct, 0), sub: "of a monitor", tone: (net?.population_within_radius_pct ?? 0) < 50 ? "bad" : "default" },
          { label: `Area within ${radius} km`, value: fmtPct(net?.area_within_radius_pct, 0), sub: `${fmtInt(city.data?.domain_area_km2)} km² analysis domain` },
          { label: "Median distance to a monitor", value: fmtKm(net?.median_distance_to_station_km), sub: `max ${fmtKm(net?.max_distance_to_station_km)}` },
        ]}
      />
      <div>
        <SectionTitle>Stations</SectionTitle>
        <ul className="space-y-1">
          {stations.data?.stations.map((st) => {
            const v = s.timeMode === "hourly" ? st.value_at_time : st.mean_pm25;
            return (
              <li key={st.id}>
                <button
                  onClick={() => {
                    dispatch({ type: "selectStation", stationId: st.id });
                    dispatch({ type: "focus", lat: st.lat, lon: st.lon, zoom: 14 });
                  }}
                  className={`w-full rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-white/[0.05] ${s.selectedStation === st.id ? "bg-white/[0.06] ring-1 ring-white/10" : ""}`}
                >
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="flex min-w-0 items-center gap-2 text-txt-primary">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-ink-950" style={{ background: v == null ? "#5b616b" : aqiColor(v) }} aria-hidden />
                      <span className="truncate">{st.name.replace("Demo site - ", "")}</span>
                    </span>
                    <span className="kbd-num shrink-0 text-txt-secondary">{fmtPm(v)}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2 pl-[18px] text-[10.5px] text-txt-muted">
                    <span className="capitalize">{st.kind}</span>·<span>{fmtPct(100 * st.completeness, 0)} complete</span>·<span>{fmtKm(st.nearest_other_station_km)} to next</span>
                    {st.qc_flags.length > 0 && <span className="text-status-serious">· {st.qc_flags[0].replace(/_/g, " ")}</span>}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      {qc && (
        <div>
          <SectionTitle>Data quality control</SectionTitle>
          <ul className="space-y-1 text-[11.5px]">
            {Object.entries(QC_LABELS).map(([k, label]) => (
              <li key={k} className="flex justify-between text-txt-secondary">
                <span>{label}</span>
                <span className="kbd-num text-txt-primary">{fmtInt(qc[k])}</span>
              </li>
            ))}
            <li className="flex justify-between border-t border-white/[0.06] pt-1 text-txt-secondary">
              <span>Valid hourly readings kept</span>
              <span className="kbd-num text-txt-primary">
                {fmtInt(qc.valid)} / {fmtInt(qc.raw)}
              </span>
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}
