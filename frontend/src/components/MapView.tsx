import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { Circle, GeoJSON, MapContainer, Pane, Popup, TileLayer, ZoomControl, useMap, useMapEvents } from "react-leaflet";
import { useCity, useCities, useGaps, useGrid, useRecommendations, useStations } from "../hooks/useAirScopeData";
import { useCityStatus } from "../hooks/useCityStatus";
import { useAppState, useDispatch, useTimeParam, type FocusRequest } from "../state/store";
import type { CitySummary, GridGeometry } from "../types";
import { cellIndex } from "../utils/geo";
import CellInspector from "./CellInspector";
import { CoverageLayer, OsseErrorLayer, PopulationLayer } from "./ContextLayers";
import GapLayer, { ClusterMarkers } from "./GapLayer";
import PollutionGrid from "./PollutionGrid";
import RecommendationPins, { SimulatedSites } from "./RecommendationPins";
import StationMarkers from "./StationMarkers";
import { useToast } from "./Toast";
import UncertaintyLayer from "./UncertaintyLayer";

const CARTO_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

function FitCity({ city, sidebarOpen, drawerOpen }: { city?: CitySummary; sidebarOpen: boolean; drawerOpen: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!city) return;
    const b = L.latLngBounds([city.bbox.south, city.bbox.west], [city.bbox.north, city.bbox.east]);
    const wide = window.innerWidth >= 1024;
    map.fitBounds(b, {
      paddingTopLeft: [wide && sidebarOpen ? 410 : 24, 92],
      paddingBottomRight: [wide ? (drawerOpen ? 400 : 270) : 24, 110],
      animate: false,
    });
    // refit when the city changes or the visible map area changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [city?.id, sidebarOpen, drawerOpen, map]);
  return null;
}

function FocusHandler({ focus }: { focus: FocusRequest | null }) {
  const map = useMap();
  useEffect(() => {
    if (focus) map.flyTo([focus.lat, focus.lon], focus.zoom ?? Math.max(map.getZoom(), 14), { duration: 0.8 });
  }, [focus, map]);
  return null;
}

function ClickHandler({ geometry, simulate, onInspect, onAddSite, onOutside }: {
  geometry?: GridGeometry;
  simulate: boolean;
  onInspect: (lat: number, lon: number, idx: number) => void;
  onAddSite: (lat: number, lon: number) => void;
  onOutside: () => void;
}) {
  const map = useMapEvents({
    click(e) {
      if (!geometry) return;
      const idx = cellIndex(geometry, e.latlng.lat, e.latlng.lng);
      if (idx < 0) {
        if (simulate) onOutside();
        return;
      }
      if (simulate) onAddSite(e.latlng.lat, e.latlng.lng);
      else onInspect(e.latlng.lat, e.latlng.lng, idx);
    },
  });
  useEffect(() => {
    const el = map.getContainer();
    el.classList.toggle("simulate-mode", simulate);
  }, [simulate, map]);
  return null;
}

export default function MapView() {
  const s = useAppState();
  const dispatch = useDispatch();
  const toast = useToast();
  const timeParam = useTimeParam();
  const cities = useCities();
  const city = cities.data?.find((c) => c.id === s.cityId);
  const { ready } = useCityStatus(s.cityId);
  const detail = useCity(s.cityId);
  const grid = useGrid(s.cityId, timeParam, ready);
  const gaps = useGaps(s.cityId, s.weights, ready);
  const showRecs = s.overlays.recommendations || s.step === "placement";
  const recs = useRecommendations(s.cityId, s.weights, s.placement, ready && showRecs);
  const stations = useStations(s.cityId, timeParam);
  const [inspect, setInspect] = useState<{ lat: number; lon: number; idx: number } | null>(null);

  useEffect(() => setInspect(null), [s.cityId]);
  useEffect(() => {
    if (s.simulate) setInspect(null);
  }, [s.simulate]);

  const g = grid.data;
  const boundary = useMemo(() => (city ? ({ type: "Feature", properties: {}, geometry: city.boundary } as GeoJSON.Feature) : null), [city]);
  const copy = (text: string) => {
    navigator.clipboard?.writeText(text).then(
      () => toast.push({ kind: "success", title: "Coordinates copied", description: text }),
      () => toast.push({ kind: "error", title: "Could not access the clipboard", description: text }),
    );
  };

  return (
    <MapContainer
      center={[33.69, 73.06]}
      zoom={12}
      minZoom={9}
      maxZoom={17}
      zoomControl={false}
      zoomSnap={0.25}
      zoomDelta={0.5}
      preferCanvas
      className="absolute inset-0 z-0"
      attributionControl
      worldCopyJump={false}
    >
      <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png" attribution={CARTO_ATTR} subdomains="abcd" maxZoom={19} />
      <Pane name="grid" style={{ zIndex: 350 }}>
        {g && s.layer === "pm25" && g.pm25_available && <PollutionGrid grid={g} opacity={s.opacity} smooth={s.smooth} scale={s.pmScale} />}
        {g && s.layer === "uncertainty" && g.pm25_available && <UncertaintyLayer grid={g} opacity={s.opacity} smooth={s.smooth} />}
        {g && s.layer === "gaps" && gaps.data && <GapLayer gaps={gaps.data} geometry={g.geometry} opacity={s.opacity} smooth={s.smooth} />}
        {g && s.layer === "population" && <PopulationLayer grid={g} opacity={s.opacity} smooth={s.smooth} />}
        {g && s.layer === "coverage" && <CoverageLayer grid={g} opacity={s.opacity} smooth={s.smooth} />}
        {g && s.layer === "osse_error" && g.layers.osse_error && <OsseErrorLayer grid={g} opacity={s.opacity} smooth={s.smooth} />}
      </Pane>
      <Pane name="labels" style={{ zIndex: 450, pointerEvents: "none" }}>
        <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png" subdomains="abcd" maxZoom={19} />
      </Pane>
      <ZoomControl position="bottomright" />
      <FitCity city={city} sidebarOpen={s.sidebarOpen} drawerOpen={s.drawerOpen} />
      <FocusHandler focus={s.focus} />
      <ClickHandler
        geometry={g?.geometry}
        simulate={s.simulate}
        onInspect={(lat, lon, idx) => setInspect({ lat, lon, idx })}
        onAddSite={(lat, lon) => {
          if (s.simSites.length >= 10) {
            toast.push({ kind: "info", title: "Up to 10 hypothetical sensors", description: "Remove one to add another." });
            return;
          }
          dispatch({ type: "addSimSite", lat, lon });
        }}
        onOutside={() => toast.push({ kind: "info", title: "Outside the analysis domain", description: "Hypothetical sensors must be placed inside the city boundary." })}
      />
      {boundary && s.overlays.boundary && (
        <GeoJSON key={city?.id} data={boundary} style={{ color: "#38d3ec", weight: 1.5, opacity: 0.75, dashArray: "6 6", fill: false }} interactive={false} />
      )}
      {s.overlays.coverageRings && stations.data?.stations.filter((st) => st.usable).map((st) => (
        <Circle
          key={`ring-${st.id}`}
          center={[st.lat, st.lon]}
          radius={(city?.coverage_radius_km ?? 2) * 1000}
          pathOptions={{ color: "#7ee7f5", weight: 1, opacity: 0.6, dashArray: "4 5", fillColor: "#7ee7f5", fillOpacity: 0.04 }}
          interactive={false}
        />
      ))}
      {s.overlays.clusters && gaps.data && (
        <ClusterMarkers clusters={gaps.data.clusters} onSelect={(c) => dispatch({ type: "focus", lat: c.centroid.lat, lon: c.centroid.lon, zoom: 14 })} />
      )}
      {s.overlays.stations && stations.data && (
        <StationMarkers
          stations={stations.data.stations}
          hourly={s.timeMode === "hourly"}
          selected={s.selectedStation}
          onShowSeries={(id) => {
            dispatch({ type: "selectStation", stationId: id });
            dispatch({ type: "openCharts", tab: "station" });
          }}
        />
      )}
      {showRecs && s.overlays.recommendations && recs.data && <RecommendationPins sites={recs.data.sites} onCopy={copy} />}
      <SimulatedSites
        sites={s.simSites}
        onMove={(id, lat, lon) => {
          if (g && cellIndex(g.geometry, lat, lon) < 0) {
            toast.push({ kind: "info", title: "Outside the analysis domain", description: "The sensor was kept at its previous position." });
            dispatch({ type: "moveSimSite", id, lat: s.simSites.find((x) => x.id === id)!.lat, lon: s.simSites.find((x) => x.id === id)!.lon });
            return;
          }
          dispatch({ type: "moveSimSite", id, lat, lon });
        }}
        onRemove={(id) => dispatch({ type: "removeSimSite", id })}
      />
      {inspect && g && (
        <Popup position={[inspect.lat, inspect.lon]} eventHandlers={{ remove: () => setInspect(null) }} minWidth={250}>
          <CellInspector
            idx={inspect.idx}
            lat={inspect.lat}
            lon={inspect.lon}
            grid={g}
            gaps={gaps.data}
            localities={detail.data?.localities}
            onSimulate={() => {
              dispatch({ type: "setStep", step: "placement" });
              dispatch({ type: "addSimSite", lat: inspect.lat, lon: inspect.lon });
              setInspect(null);
              toast.push({ kind: "success", title: "Hypothetical sensor added", description: "Its impact is shown in the placement drawer." });
            }}
          />
        </Popup>
      )}
    </MapContainer>
  );
}
