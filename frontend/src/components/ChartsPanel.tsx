import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useMetrics, useRecommendations, useStationSeries, useStations, useWeather } from "../hooks/useAirScopeData";
import { useCityStatus } from "../hooks/useCityStatus";
import { useAppState, useDispatch, useTimeParam } from "../state/store";
import type { ChartTab } from "../types";
import { EmptyChart } from "./charts/common";
import { CoverageCurveChart, OsseBenchmarkChart } from "./charts/PlanningCharts";
import { StationSeriesChart, WeatherCharts } from "./charts/TimeSeriesCharts";
import {
  CalibrationChart,
  CoverageByDistanceChart,
  GroupImportanceChart,
  ImportanceChart,
  ModelComparisonChart,
  PerStationChart,
  VariogramChart,
} from "./charts/ValidationCharts";

const TABS: { id: ChartTab; label: string }[] = [
  { id: "station", label: "Station series" },
  { id: "validation", label: "Validation" },
  { id: "uncertainty", label: "Uncertainty" },
  { id: "drivers", label: "Drivers" },
  { id: "curve", label: "Coverage curve" },
  { id: "osse", label: "OSSE benchmark" },
  { id: "weather", label: "Weather" },
];

export default function ChartsPanel() {
  const s = useAppState();
  const dispatch = useDispatch();
  const { ready } = useCityStatus(s.cityId);
  const metrics = useMetrics(s.cityId, ready && s.chartsOpen);
  const stations = useStations(s.cityId, useTimeParam());
  const stationId = s.selectedStation ?? stations.data?.stations[0]?.id ?? null;
  const series = useStationSeries(s.cityId, s.chartsOpen && s.chartTab === "station" ? stationId : null);
  const weather = useWeather(s.chartsOpen && s.chartTab === "weather" ? s.cityId : null);
  const recs = useRecommendations(s.cityId, s.weights, s.placement, ready && s.chartsOpen && s.chartTab === "curve");
  const m = metrics.data;
  const synthetic = m?.provenance?.synthetic;

  return (
    <AnimatePresence>
      {s.chartsOpen && (
        <motion.section
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 40, opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="glass pointer-events-auto flex max-h-[62vh] min-h-[320px] w-full flex-col rounded-t-2xl"
          aria-label="Charts"
        >
          <div className="flex flex-wrap items-center gap-2 border-b border-white/[0.06] px-4 py-2.5">
            <div role="tablist" aria-label="Chart topics" className="scroll-thin flex min-w-0 flex-1 gap-1 overflow-x-auto">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={s.chartTab === t.id}
                  onClick={() => dispatch({ type: "setChartTab", tab: t.id })}
                  className={`whitespace-nowrap rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                    s.chartTab === t.id ? "bg-brand-500/15 text-brand-300 ring-1 ring-brand-400/40" : "text-txt-secondary hover:bg-white/[0.05] hover:text-txt-primary"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            {synthetic && <span className="chip bg-status-warning/10 text-status-warning ring-status-warning/30">Synthetic demo data</span>}
            <button className="btn-icon" onClick={() => dispatch({ type: "setChartsOpen", open: false })} aria-label="Close charts">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-4">
            {s.chartTab === "station" && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <label htmlFor="station-pick" className="text-xs text-txt-secondary">Station</label>
                  <select
                    id="station-pick"
                    value={stationId ?? ""}
                    onChange={(e) => dispatch({ type: "selectStation", stationId: e.target.value })}
                    className="rounded-lg bg-ink-800 px-2 py-1 text-xs text-txt-primary ring-1 ring-white/10 focus:outline-none focus:ring-2 focus:ring-brand-400/70"
                  >
                    {stations.data?.stations.map((st) => (
                      <option key={st.id} value={st.id}>{st.name}</option>
                    ))}
                  </select>
                </div>
                <StationSeriesChart series={series.data} stationName={stations.data?.stations.find((x) => x.id === stationId)?.name.replace("Demo site - ", "")} />
              </div>
            )}
            {s.chartTab !== "station" && s.chartTab !== "weather" && s.chartTab !== "curve" && !m && (
              <div className="h-40"><EmptyChart>{metrics.isError ? "Metrics unavailable." : "Loading model evaluation…"}</EmptyChart></div>
            )}
            {m && !m.evaluation_available && s.chartTab !== "station" && s.chartTab !== "weather" && s.chartTab !== "curve" && (
              <div className="h-40"><EmptyChart>{m.message ?? "Spatial validation needs at least 3 usable stations."}</EmptyChart></div>
            )}
            {m?.evaluation_available && s.chartTab === "validation" && (
              <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                <ModelComparisonChart m={m} />
                <PerStationChart m={m} />
              </div>
            )}
            {m?.evaluation_available && s.chartTab === "uncertainty" && (
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
                <CalibrationChart m={m} />
                <VariogramChart m={m} />
                <CoverageByDistanceChart m={m} />
              </div>
            )}
            {m?.evaluation_available && s.chartTab === "drivers" && (
              <div className="grid grid-cols-1 gap-3 xl:grid-cols-[3fr_2fr]">
                <ImportanceChart m={m} />
                <GroupImportanceChart m={m} />
              </div>
            )}
            {s.chartTab === "curve" && <CoverageCurveChart recs={recs.data} k={s.placement.k} />}
            {m?.evaluation_available && s.chartTab === "osse" && <OsseBenchmarkChart m={m} />}
            {s.chartTab === "weather" && <WeatherCharts w={weather.data} />}
          </div>
        </motion.section>
      )}
    </AnimatePresence>
  );
}
