import { AnimatePresence, motion } from "framer-motion";
import { Copy, Crosshair, Download, FlaskConical, Loader2, MapPin, Trash2, X } from "lucide-react";
import { useState } from "react";
import { useCity, useHealth, useOsse, useRecommendations, useSimulation } from "../hooks/useAirScopeData";
import { useCityStatus } from "../hooks/useCityStatus";
import { useAppState, useDispatch } from "../state/store";
import type { Site } from "../types";
import { aqiBand } from "../utils/aqi";
import { exportSites } from "../utils/export";
import { fmtCompact, fmtCoord, fmtInt, fmtKm, fmtNum, fmtPct, fmtPm } from "../utils/formatting";
import { ImpactRows } from "./steps/PlacementStep";
import { useToast } from "./Toast";
import { AqiBadge, Segmented } from "./ui";

function SiteCard({ site, onZoom, onCopy, tag }: { site: Site; onZoom: () => void; onCopy: () => void; tag: string }) {
  const band = aqiBand(site.pm25);
  return (
    <li className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/[0.06]">
      <div className="flex items-start gap-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-400 text-xs font-bold text-ink-950 shadow-glow">{tag}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold text-txt-primary">{site.location.label}</p>
          <p className="kbd-num text-[11px] text-txt-muted">{fmtCoord(site.lat, site.lon)}</p>
        </div>
        <div className="flex gap-1">
          <button className="btn-icon h-7 w-7" onClick={onZoom} aria-label={`Zoom to site ${tag}`} title="Zoom to site">
            <Crosshair className="h-3.5 w-3.5" />
          </button>
          <button className="btn-icon h-7 w-7" onClick={onCopy} aria-label={`Copy coordinates of site ${tag}`} title="Copy coordinates">
            <Copy className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11.5px]">
        {site.pm25 != null && <span className="font-semibold text-txt-primary">{fmtPm(site.pm25)}</span>}
        {band && <AqiBadge category={band.short} color={band.color} textColor={band.text} />}
        <span className="chip bg-white/[0.04] text-txt-secondary ring-white/10">Gap {site.gap_index.toFixed(2)}</span>
        <span className="chip bg-white/[0.04] text-txt-secondary ring-white/10">{fmtInt(site.population_density)}/km²</span>
        <span className="chip bg-white/[0.04] text-txt-secondary ring-white/10">{fmtKm(site.nearest_station_km)} to monitor</span>
      </div>
      <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[11.5px] leading-snug text-txt-secondary">
        {site.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </li>
  );
}

export default function RecommendationsDrawer() {
  const s = useAppState();
  const dispatch = useDispatch();
  const toast = useToast();
  const { ready } = useCityStatus(s.cityId);
  const health = useHealth();
  const city = useCity(s.cityId);
  const recs = useRecommendations(s.cityId, s.weights, s.placement, ready && s.drawerOpen);
  const sim = useSimulation(s.cityId, s.weights, s.simSites, ready);
  const osse = useOsse(s.cityId);
  const [tab, setTab] = useState<"recommended" | "simulated">("recommended");
  const radius = city.data?.coverage_radius_km ?? 2;
  const demo = health.data?.data_mode !== "live";
  const activeTab = s.simSites.length === 0 ? "recommended" : tab;

  const copy = (site: Site) =>
    navigator.clipboard?.writeText(fmtCoord(site.lat, site.lon)).then(
      () => toast.push({ kind: "success", title: "Coordinates copied", description: fmtCoord(site.lat, site.lon) }),
      () => toast.push({ kind: "error", title: "Clipboard unavailable", description: fmtCoord(site.lat, site.lon) }),
    );

  const runOsse = (sites: { lat: number; lon: number }[]) =>
    osse.mutate(sites, {
      onSuccess: (r) => toast.push({ kind: "success", title: `City-wide error ${r.improvement_pct >= 0 ? "reduced" : "increased"} by ${Math.abs(r.improvement_pct).toFixed(1)}%`, description: "Synthetic-truth experiment (OSSE)." }),
      onError: (e) => toast.push({ kind: "error", title: "OSSE validation failed", description: e.message }),
    });

  return (
    <AnimatePresence>
      {s.drawerOpen && (
        <motion.aside
          initial={{ x: 40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 40, opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="glass flex h-full min-h-0 w-full flex-col rounded-xl"
          aria-label="Recommended sites"
        >
          <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-txt-primary">Sensor placement</h2>
              <p className="text-[11px] text-txt-muted">{recs.data?.strategy_label ?? "Computing…"}</p>
            </div>
            <button className="btn-icon" onClick={() => dispatch({ type: "setDrawerOpen", open: false })} aria-label="Close placement drawer">
              <X className="h-4 w-4" />
            </button>
          </div>
          {s.simSites.length > 0 && (
            <div className="px-4 pt-3">
              <Segmented
                ariaLabel="Site list"
                size="sm"
                value={activeTab}
                onChange={setTab}
                options={[
                  { value: "recommended", label: `Recommended (${recs.data?.sites.length ?? 0})` },
                  { value: "simulated", label: `Your sensors (${s.simSites.length})` },
                ]}
              />
            </div>
          )}
          <div className="scroll-thin min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {activeTab === "recommended" ? (
              <>
                {recs.isLoading && <p className="flex items-center gap-2 text-xs text-txt-muted"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Optimising placements…</p>}
                {recs.data && (
                  <>
                    <div className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/[0.06]">
                      <ImpactRows impact={recs.data.impact} radius={radius} />
                    </div>
                    {recs.data.message && <p className="text-[11px] text-status-warning">{recs.data.message}</p>}
                    <ol className="space-y-2">
                      {recs.data.sites.map((site) => (
                        <SiteCard key={site.rank} site={site} tag={String(site.rank)} onCopy={() => copy(site)} onZoom={() => dispatch({ type: "focus", lat: site.lat, lon: site.lon, zoom: 15 })} />
                      ))}
                    </ol>
                    {recs.data.sites.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="btn-ghost flex-1"
                          onClick={() => {
                            exportSites(recs.data!.sites, "csv", s.cityId!, {});
                            toast.push({ kind: "success", title: "CSV downloaded" });
                          }}
                        >
                          <Download className="h-3.5 w-3.5" /> CSV
                        </button>
                        <button
                          className="btn-ghost flex-1"
                          onClick={() => {
                            exportSites(recs.data!.sites, "geojson", s.cityId!, {
                              city: s.cityId, strategy: recs.data!.strategy, constraints: recs.data!.constraints, weights: recs.data!.weights,
                              data: recs.data!.provenance.label, generated_by: "AirScope",
                            });
                            toast.push({ kind: "success", title: "GeoJSON downloaded" });
                          }}
                        >
                          <Download className="h-3.5 w-3.5" /> GeoJSON
                        </button>
                        {demo && (
                          <button className="btn-ghost w-full" disabled={osse.isPending} onClick={() => runOsse(recs.data!.sites.map(({ lat, lon }) => ({ lat, lon })))}>
                            {osse.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />} Test these sites against the synthetic truth
                          </button>
                        )}
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <>
                {sim.data && (
                  <div className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/[0.06]">
                    <ImpactRows impact={sim.data.impact} radius={radius} />
                  </div>
                )}
                <ol className="space-y-2">
                  {s.simSites.map((site, i) => {
                    const info = sim.data?.sites[i];
                    return info ? (
                      <div key={site.id} className="relative">
                        <SiteCard site={info} tag={`S${i + 1}`} onCopy={() => copy(info)} onZoom={() => dispatch({ type: "focus", lat: site.lat, lon: site.lon, zoom: 15 })} />
                        <button className="absolute bottom-3 right-3 text-[11px] text-txt-muted hover:text-status-critical" onClick={() => dispatch({ type: "removeSimSite", id: site.id })}>
                          <Trash2 className="inline h-3 w-3" /> Remove
                        </button>
                      </div>
                    ) : (
                      <li key={site.id} className="flex items-center gap-2 rounded-xl bg-white/[0.03] p-3 text-xs text-txt-muted ring-1 ring-white/[0.06]">
                        <MapPin className="h-3.5 w-3.5" /> S{i + 1} · {fmtCoord(site.lat, site.lon)} · evaluating…
                      </li>
                    );
                  })}
                </ol>
                <div className="flex gap-2">
                  {demo && (
                    <button className="btn-ghost flex-1" disabled={osse.isPending} onClick={() => runOsse(s.simSites.map(({ lat, lon }) => ({ lat, lon })))}>
                      {osse.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />} Test in OSSE
                    </button>
                  )}
                  <button className="btn-ghost" onClick={() => dispatch({ type: "clearSimSites" })}>
                    <Trash2 className="h-3.5 w-3.5" /> Clear all
                  </button>
                </div>
              </>
            )}
            {osse.data && (
              <div className="rounded-xl bg-brand-500/10 p-3 text-[11.5px] leading-snug ring-1 ring-brand-400/30">
                <div className="flex items-center gap-2 font-semibold text-brand-300">
                  <FlaskConical className="h-3.5 w-3.5" /> OSSE result ({osse.data.sites.length} sites)
                </div>
                <p className="mt-1 text-txt-secondary">
                  City-wide RMSE {fmtNum(osse.data.baseline.rmse, 1)} → {fmtNum(osse.data.with_sites.rmse, 1)} µg/m³ (
                  <span className="font-semibold text-txt-primary">{fmtPct(Math.abs(osse.data.improvement_pct), 1)} {osse.data.improvement_pct >= 0 ? "lower" : "higher"}</span>;
                  population-weighted {fmtPct(Math.abs(osse.data.pop_improvement_pct), 1)} {osse.data.pop_improvement_pct >= 0 ? "lower" : "higher"}).
                </p>
                <p className="mt-1 text-[10.5px] text-txt-muted">{osse.data.note}</p>
              </div>
            )}
            <p className="text-[10.5px] leading-snug text-txt-muted">
              Coverage and uncertainty changes are computed from the station geometry (kriging variance), so they need no new measurements. Treat
              sites as candidates for field survey: power, access, security and local permissions still decide the final location.
              {recs.data && ` Estimated residents brought within ${radius} km: ${fmtCompact(recs.data.sites.reduce((a, x) => a + x.newly_covered_population, 0))}.`}
            </p>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
