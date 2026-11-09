import { BarChart3, Info, PanelLeftClose, PanelLeftOpen, Radar } from "lucide-react";
import { useCities, useHealth } from "../hooks/useAirScopeData";
import { useAppState, useDispatch } from "../state/store";
import type { CitySummary, Health } from "../types";
import { Segmented } from "./ui";

function DataBadge({ city, health }: { city?: CitySummary; health?: Health }) {
  if (!city) return null;
  const live = city.data_mode === "live";
  const stale = city.data_label.includes("stale");
  const fallback = city.data_label.includes("unavailable");
  const tone = live ? (stale ? "bg-status-serious/15 text-status-serious ring-status-serious/30" : "bg-status-good/15 text-status-good ring-status-good/30")
    : "bg-status-warning/15 text-status-warning ring-status-warning/30";
  const title = live
    ? "Measured PM2.5 from OpenAQ-listed stations and Open-Meteo weather."
    : fallback
      ? "Live mode was requested but live data could not be fetched, so the synthetic demo dataset is shown."
      : "Offline demo: station readings are SYNTHETIC samples of a documented simulated pollution field (OSSE). No real observations are shown.";
  return (
    <span className={`chip ${tone}`} title={title}>
      <span className={`h-1.5 w-1.5 rounded-full ${live ? (stale ? "bg-status-serious" : "bg-status-good") : "bg-status-warning"}`} aria-hidden />
      {live ? (stale ? "LIVE · cached" : "LIVE") : "DEMO"} · {live ? "OpenAQ + Open-Meteo" : fallback ? "synthetic (live unavailable)" : "synthetic data"}
      {health && !health.live_enabled && live === false && <span className="sr-only">Live mode is not configured.</span>}
    </span>
  );
}

export default function Header() {
  const s = useAppState();
  const dispatch = useDispatch();
  const cities = useCities();
  const health = useHealth();
  const city = cities.data?.find((c) => c.id === s.cityId);

  return (
    <header className="glass flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl px-3 py-2">
      <div className="flex items-center gap-2.5">
        <button
          className="btn-icon hidden lg:inline-flex"
          onClick={() => dispatch({ type: "setSidebarOpen", open: !s.sidebarOpen })}
          aria-label={s.sidebarOpen ? "Hide insight panel" : "Show insight panel"}
          title={s.sidebarOpen ? "Hide insight panel" : "Show insight panel"}
        >
          {s.sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
        </button>
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500/15 ring-1 ring-brand-400/40">
          <Radar className="h-4.5 w-4.5 text-brand-400" aria-hidden />
        </div>
        <div className="leading-tight">
          <h1 className="text-[15px] font-semibold tracking-tight text-txt-primary">AirScope</h1>
          <p className="hidden text-[11px] text-txt-muted sm:block">Monitoring-gap intelligence for Pakistani cities</p>
        </div>
      </div>
      {cities.data && s.cityId && (
        <Segmented
          ariaLabel="City"
          value={s.cityId}
          onChange={(id) => dispatch({ type: "setCity", cityId: id })}
          options={cities.data.map((c) => ({ value: c.id, label: c.name, title: c.domain_note }))}
        />
      )}
      <DataBadge city={city} health={health.data} />
      <div className="ml-auto flex items-center gap-1.5">
        <button className="btn-ghost" onClick={() => dispatch({ type: "openCharts" })} title="Charts and model validation">
          <BarChart3 className="h-4 w-4" /> <span className="hidden md:inline">Charts</span>
        </button>
        <button className="btn-ghost" onClick={() => dispatch({ type: "setAboutOpen", open: true })} title="Methodology, data sources and licences">
          <Info className="h-4 w-4" /> <span className="hidden md:inline">About</span>
        </button>
      </div>
    </header>
  );
}
