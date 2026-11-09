import { AlertTriangle, Loader2 } from "lucide-react";
import { useEffect } from "react";
import AboutModal from "./components/AboutModal";
import AQILegend from "./components/AQILegend";
import ChartsPanel from "./components/ChartsPanel";
import Header from "./components/Header";
import LayerControls from "./components/LayerControls";
import MapView from "./components/MapView";
import RecommendationsDrawer from "./components/RecommendationsDrawer";
import Sidebar from "./components/Sidebar";
import TimeControl from "./components/TimeControl";
import TrainingOverlay from "./components/TrainingOverlay";
import { useCities } from "./hooks/useAirScopeData";
import { useMediaQuery } from "./hooks/useMediaQuery";
import { useAppState, useDispatch } from "./state/store";

function Splash({ error }: { error?: string }) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="glass max-w-md rounded-2xl p-6 text-center">
        {error ? (
          <>
            <AlertTriangle className="mx-auto h-6 w-6 text-status-serious" aria-hidden />
            <h1 className="mt-2 text-base font-semibold">Cannot reach the AirScope backend</h1>
            <p className="mt-1 text-sm text-txt-secondary">{error}</p>
            <p className="mt-3 text-xs text-txt-muted">Start it with <code className="rounded bg-white/10 px-1">make start</code> (or <code className="rounded bg-white/10 px-1">python backend/app.py</code>). This page retries automatically.</p>
          </>
        ) : (
          <>
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-brand-400" aria-hidden />
            <p className="mt-2 text-sm text-txt-secondary">Loading AirScope…</p>
          </>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const s = useAppState();
  const dispatch = useDispatch();
  const cities = useCities();
  const wide = useMediaQuery("(min-width: 1024px)");

  useEffect(() => {
    if (!s.cityId && cities.data?.length) {
      const primary = cities.data.find((c) => c.is_primary) ?? cities.data[0];
      dispatch({ type: "setCity", cityId: primary.id });
    }
  }, [cities.data, s.cityId, dispatch]);

  if (!cities.data) return <Splash error={cities.error ? (cities.error as Error).message : undefined} />;

  return (
    <div className="relative h-full w-full overflow-hidden">
      <MapView />
      {/* floating UI; pointer-events only on panels so the map stays usable */}
      <div className="pointer-events-none absolute inset-0 z-[1000] flex flex-col gap-3 p-3 lg:p-4">
        <div className="pointer-events-auto">
          <Header />
        </div>
        <div className="flex min-h-0 flex-1 gap-3">
          {s.sidebarOpen && wide && (
            <div className="pointer-events-auto min-h-0 w-[380px] shrink-0">
              <Sidebar />
            </div>
          )}
          <div className="relative min-h-0 flex-1">
            <div className="pointer-events-auto absolute right-0 top-0 flex items-start gap-3">
              <LayerControls />
            </div>
            <div className="pointer-events-auto absolute bottom-0 left-0 hidden sm:block">
              <AQILegend />
            </div>
            <div className="pointer-events-auto absolute bottom-0 left-1/2 w-[min(100%,640px)] -translate-x-1/2 sm:left-[calc(50%+120px)] sm:w-[min(calc(100%-260px),620px)]">
              <TimeControl />
            </div>
          </div>
          {s.drawerOpen && (
            <div className="pointer-events-auto hidden min-h-0 w-[360px] shrink-0 md:block">
              <RecommendationsDrawer />
            </div>
          )}
        </div>
        {/* compact insight panel for small screens */}
        {s.sidebarOpen && !wide && (
          <div className="pointer-events-auto h-[45vh] min-h-0">
            <Sidebar />
          </div>
        )}
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[1200] flex justify-center px-3 lg:px-4">
        <div className="pointer-events-auto w-full max-w-[1500px]">
          <ChartsPanel />
        </div>
      </div>
      <TrainingOverlay />
      <AboutModal />
    </div>
  );
}
