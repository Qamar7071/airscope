import { Activity, Gauge, Layers, ScanSearch, ShieldAlert, Signal, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useGrid } from "../hooks/useAirScopeData";
import { useCityStatus } from "../hooks/useCityStatus";
import { useAppState, useDispatch, useTimeParam } from "../state/store";
import type { LayerId } from "../types";
import { Slider, Toggle } from "./ui";

const LAYERS: { id: LayerId; label: string; icon: typeof Layers; hint: string }[] = [
  { id: "pm25", label: "PM2.5 estimate", icon: Activity, hint: "City-wide PM2.5 estimated by the ML ensemble." },
  { id: "uncertainty", label: "Uncertainty", icon: Gauge, hint: "Calibrated 90% interval width, relative to the estimate." },
  { id: "gaps", label: "Monitoring gaps", icon: ShieldAlert, hint: "Monitoring Gap Index - poorly observed and important areas." },
  { id: "coverage", label: "Station coverage", icon: Signal, hint: "Probability that the existing network represents each cell." },
  { id: "population", label: "Population", icon: Users, hint: "Approximate population density (bundled surface)." },
  { id: "osse_error", label: "OSSE actual error", icon: ScanSearch, hint: "Demo only: true error against the synthetic truth." },
];

export default function LayerControls() {
  const s = useAppState();
  const dispatch = useDispatch();
  const [open, setOpen] = useState(true);
  const wasDrawerOpen = useRef(s.drawerOpen);
  useEffect(() => {
    // collapse while the placement drawer needs the space; restore when it closes
    if (s.drawerOpen && !wasDrawerOpen.current) setOpen(false);
    if (!s.drawerOpen && wasDrawerOpen.current) setOpen(true);
    wasDrawerOpen.current = s.drawerOpen;
  }, [s.drawerOpen]);
  const { ready } = useCityStatus(s.cityId);
  const grid = useGrid(s.cityId, useTimeParam(), ready);
  const hasOsse = !!grid.data?.layers.osse_error;
  const pmAvailable = grid.data?.pm25_available ?? true;

  return (
    <div className="glass w-[230px] rounded-xl">
      <button
        className="flex w-full items-center justify-between px-3 py-2.5 text-left"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-xs font-semibold text-txt-primary">
          <Layers className="h-4 w-4 text-brand-400" aria-hidden /> Map layers
        </span>
        <span className="text-[11px] text-txt-muted">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-white/[0.06] px-3 pb-3 pt-2">
          <div role="radiogroup" aria-label="Data layer" className="space-y-0.5">
            {LAYERS.map((l) => {
              const disabled = (l.id === "osse_error" && !hasOsse) || ((l.id === "pm25" || l.id === "uncertainty") && !pmAvailable);
              if (l.id === "osse_error" && !hasOsse) return null;
              const active = s.layer === l.id;
              const Icon = l.icon;
              return (
                <button
                  key={l.id}
                  role="radio"
                  aria-checked={active}
                  disabled={disabled}
                  title={l.hint}
                  onClick={() => dispatch({ type: "setLayer", layer: active ? "none" : l.id })}
                  className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors disabled:opacity-40 ${
                    active ? "bg-brand-500/15 text-brand-300 ring-1 ring-brand-400/40" : "text-txt-secondary hover:bg-white/[0.05] hover:text-txt-primary"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" aria-hidden />
                  {l.label}
                </button>
              );
            })}
          </div>
          <div className="border-t border-white/[0.06] pt-2">
            <Toggle label="Stations" checked={s.overlays.stations} onChange={() => dispatch({ type: "toggleOverlay", key: "stations" })} />
            <Toggle label="Recommended sites" checked={s.overlays.recommendations} onChange={() => dispatch({ type: "toggleOverlay", key: "recommendations" })} />
            <Toggle label="Blind-spot clusters" checked={s.overlays.clusters} onChange={() => dispatch({ type: "toggleOverlay", key: "clusters" })} />
            <Toggle label="Coverage radius" checked={s.overlays.coverageRings} onChange={() => dispatch({ type: "toggleOverlay", key: "coverageRings" })} />
            <Toggle label="Analysis boundary" checked={s.overlays.boundary} onChange={() => dispatch({ type: "toggleOverlay", key: "boundary" })} />
          </div>
          <div className="space-y-2 border-t border-white/[0.06] pt-2">
            <Slider label="Layer opacity" value={s.opacity} min={0.2} max={1} step={0.05} onChange={(v) => dispatch({ type: "setOpacity", opacity: v })} format={(v) => `${Math.round(v * 100)}%`} />
            <Toggle
              label="Smooth rendering"
              checked={s.smooth}
              onChange={(v) => dispatch({ type: "setSmooth", smooth: v })}
              hint="Off shows the raw analysis cells (the model's actual resolution)."
            />
          </div>
        </div>
      )}
    </div>
  );
}
