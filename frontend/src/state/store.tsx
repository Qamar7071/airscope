import { createContext, useContext, useMemo, useReducer, type Dispatch, type ReactNode } from "react";
import type { ChartTab, GapWeights, LayerId, PlacementParams, SimSite, StepId } from "../types";

export const DEFAULT_WEIGHTS: GapWeights = { coverage: 0.5, uncertainty: 0.5, pollution: 0.5, population: 0.5, balance: 0.5 };
export const DEFAULT_PLACEMENT: PlacementParams = {
  k: 5,
  strategy: "coverage",
  min_spacing_km: 2,
  min_station_distance_km: 1.5,
  min_population_density: 200,
};

export interface Overlays {
  stations: boolean;
  recommendations: boolean;
  coverageRings: boolean;
  boundary: boolean;
  clusters: boolean;
}

export interface FocusRequest {
  lat: number;
  lon: number;
  zoom?: number;
  key: number;
}

export interface UIState {
  cityId: string | null;
  step: StepId;
  layer: LayerId;
  overlays: Overlays;
  opacity: number;
  smooth: boolean;
  pmScale: "aqi" | "relative";
  timeMode: "period" | "hourly";
  time: string | null;
  playing: boolean;
  weights: GapWeights;
  placement: PlacementParams;
  simulate: boolean;
  simSites: SimSite[];
  selectedStation: string | null;
  focus: FocusRequest | null;
  chartsOpen: boolean;
  chartTab: ChartTab;
  drawerOpen: boolean;
  aboutOpen: boolean;
  sidebarOpen: boolean;
}

const initialState: UIState = {
  cityId: null,
  step: "pollution",
  layer: "pm25",
  overlays: { stations: true, recommendations: false, coverageRings: false, boundary: true, clusters: false },
  opacity: 0.72,
  smooth: true,
  pmScale: "aqi",
  timeMode: "period",
  time: null,
  playing: false,
  weights: DEFAULT_WEIGHTS,
  placement: DEFAULT_PLACEMENT,
  simulate: false,
  simSites: [],
  selectedStation: null,
  focus: null,
  chartsOpen: false,
  chartTab: "station",
  drawerOpen: false,
  aboutOpen: false,
  sidebarOpen: true,
};

// Each insight step sets up the map to answer its question.
const STEP_PRESETS: Record<StepId, { layer: LayerId; overlays: Partial<Overlays> }> = {
  pollution: { layer: "pm25", overlays: { stations: true, recommendations: false, coverageRings: false, clusters: false } },
  coverage: { layer: "coverage", overlays: { stations: true, recommendations: false, coverageRings: true, clusters: false } },
  uncertainty: { layer: "uncertainty", overlays: { stations: true, recommendations: false, coverageRings: false, clusters: false } },
  gaps: { layer: "gaps", overlays: { stations: true, recommendations: false, coverageRings: false, clusters: true } },
  placement: { layer: "gaps", overlays: { stations: true, recommendations: true, coverageRings: true, clusters: false } },
  evidence: { layer: "uncertainty", overlays: { stations: true, recommendations: false, coverageRings: false, clusters: false } },
};

export type Action =
  | { type: "setCity"; cityId: string }
  | { type: "setStep"; step: StepId; osseAvailable?: boolean }
  | { type: "setLayer"; layer: LayerId }
  | { type: "toggleOverlay"; key: keyof Overlays }
  | { type: "setOpacity"; opacity: number }
  | { type: "setSmooth"; smooth: boolean }
  | { type: "setPmScale"; scale: "aqi" | "relative" }
  | { type: "setTimeMode"; mode: "period" | "hourly"; latest?: string | null }
  | { type: "setTime"; time: string }
  | { type: "setPlaying"; playing: boolean }
  | { type: "setWeights"; weights: Partial<GapWeights> }
  | { type: "resetWeights" }
  | { type: "setPlacement"; placement: Partial<PlacementParams> }
  | { type: "resetPlacement" }
  | { type: "setSimulate"; simulate: boolean }
  | { type: "addSimSite"; lat: number; lon: number }
  | { type: "moveSimSite"; id: string; lat: number; lon: number }
  | { type: "removeSimSite"; id: string }
  | { type: "clearSimSites" }
  | { type: "selectStation"; stationId: string | null }
  | { type: "focus"; lat: number; lon: number; zoom?: number }
  | { type: "openCharts"; tab?: ChartTab }
  | { type: "setChartsOpen"; open: boolean }
  | { type: "setChartTab"; tab: ChartTab }
  | { type: "setDrawerOpen"; open: boolean }
  | { type: "setAboutOpen"; open: boolean }
  | { type: "setSidebarOpen"; open: boolean };

let simCounter = 0;

function reducer(state: UIState, a: Action): UIState {
  switch (a.type) {
    case "setCity":
      if (a.cityId === state.cityId) return state;
      return { ...state, cityId: a.cityId, time: null, timeMode: "period", playing: false, simSites: [], simulate: false, selectedStation: null, focus: null };
    case "setStep": {
      const preset = STEP_PRESETS[a.step];
      const layer = a.step === "evidence" && a.osseAvailable ? "osse_error" : preset.layer;
      return {
        ...state,
        step: a.step,
        layer,
        overlays: { ...state.overlays, ...preset.overlays },
        drawerOpen: a.step === "placement",
        simulate: a.step === "placement" ? state.simulate : false,
      };
    }
    case "setLayer":
      return { ...state, layer: a.layer };
    case "toggleOverlay":
      return { ...state, overlays: { ...state.overlays, [a.key]: !state.overlays[a.key] } };
    case "setOpacity":
      return { ...state, opacity: a.opacity };
    case "setSmooth":
      return { ...state, smooth: a.smooth };
    case "setPmScale":
      return { ...state, pmScale: a.scale };
    case "setTimeMode":
      return { ...state, timeMode: a.mode, time: a.mode === "hourly" ? state.time ?? a.latest ?? null : state.time, playing: false };
    case "setTime":
      return { ...state, time: a.time };
    case "setPlaying":
      return { ...state, playing: a.playing };
    case "setWeights":
      return { ...state, weights: { ...state.weights, ...a.weights } };
    case "resetWeights":
      return { ...state, weights: DEFAULT_WEIGHTS };
    case "setPlacement":
      return { ...state, placement: { ...state.placement, ...a.placement } };
    case "resetPlacement":
      return { ...state, placement: DEFAULT_PLACEMENT };
    case "setSimulate":
      return { ...state, simulate: a.simulate, drawerOpen: a.simulate ? true : state.drawerOpen };
    case "addSimSite":
      if (state.simSites.length >= 10) return state;
      simCounter += 1;
      return { ...state, simSites: [...state.simSites, { id: `sim-${simCounter}`, lat: a.lat, lon: a.lon }], drawerOpen: true };
    case "moveSimSite":
      return { ...state, simSites: state.simSites.map((s) => (s.id === a.id ? { ...s, lat: a.lat, lon: a.lon } : s)) };
    case "removeSimSite":
      return { ...state, simSites: state.simSites.filter((s) => s.id !== a.id) };
    case "clearSimSites":
      return { ...state, simSites: [] };
    case "selectStation":
      return { ...state, selectedStation: a.stationId };
    case "focus":
      return { ...state, focus: { lat: a.lat, lon: a.lon, zoom: a.zoom, key: Date.now() } };
    case "openCharts":
      return { ...state, chartsOpen: true, chartTab: a.tab ?? state.chartTab };
    case "setChartsOpen":
      return { ...state, chartsOpen: a.open };
    case "setChartTab":
      return { ...state, chartTab: a.tab };
    case "setDrawerOpen":
      return { ...state, drawerOpen: a.open };
    case "setAboutOpen":
      return { ...state, aboutOpen: a.open };
    case "setSidebarOpen":
      return { ...state, sidebarOpen: a.open };
    default:
      return state;
  }
}

const StateCtx = createContext<UIState>(initialState);
const DispatchCtx = createContext<Dispatch<Action>>(() => undefined);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const memoState = useMemo(() => state, [state]);
  return (
    <StateCtx.Provider value={memoState}>
      <DispatchCtx.Provider value={dispatch}>{children}</DispatchCtx.Provider>
    </StateCtx.Provider>
  );
}

export const useAppState = () => useContext(StateCtx);
export const useDispatch = () => useContext(DispatchCtx);

/** Time parameter sent to the API for map layers that follow the time control. */
export function useTimeParam(): string | null {
  const s = useAppState();
  if (s.timeMode === "period") return "period";
  return s.time;
}
