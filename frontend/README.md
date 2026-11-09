# AirScope frontend

React 18 + Vite + TypeScript + Tailwind CSS, with React Leaflet (CARTO Dark Matter
basemap), Recharts, Framer Motion, Lucide icons, Axios and TanStack Query.

## Run

```bash
npm install
npm run dev
```

The dev server runs on http://127.0.0.1:5173 and proxies `/api` to the backend at
http://127.0.0.1:8000 (override with `AIRSCOPE_API_PROXY`). To call a backend on another
origin directly, set `VITE_API_BASE_URL` (see `.env.example`).

| Script | Purpose |
|---|---|
| `npm run dev` | Development server with hot reload |
| `npm run build` | Type-check and build to `dist/` (served by the Flask backend) |
| `npm run typecheck` | TypeScript only |
| `npm test` | Vitest unit tests (AQI, colour scales, formatting, grid geometry, CSV export) |

## Structure

```
src/
├── App.tsx                 layout: map + floating panels
├── main.tsx                providers (React Query, app state, toasts)
├── components/
│   ├── MapView.tsx         basemap, label pane above data, layers, click-to-inspect / click-to-simulate
│   ├── GridOverlay.tsx     paints a grid layer into one image overlay (fast, smooth or crisp)
│   ├── PollutionGrid.tsx, UncertaintyLayer.tsx, GapLayer.tsx, ContextLayers.tsx
│   ├── StationMarkers.tsx, RecommendationPins.tsx (incl. draggable simulated sensors), CellInspector.tsx
│   ├── Sidebar.tsx + steps/   six-step insight navigator (Pollution → Evidence)
│   ├── MetricsPanel.tsx, RecommendationsDrawer.tsx, AQILegend.tsx, LayerControls.tsx, TimeControl.tsx
│   ├── ChartsPanel.tsx + charts/   validation, uncertainty, drivers, coverage curve, OSSE, weather
│   ├── Header.tsx, TrainingOverlay.tsx, AboutModal.tsx, Toast.tsx, ui.tsx
├── hooks/useAirScopeData.ts   all API queries (retries quietly while models train)
├── services/api.ts            typed Axios client and error normalisation
├── state/store.tsx            UI state (reducer + context)
├── types/index.ts             API types
└── utils/                     aqi, colours, formatting, geo, export
```

## Design notes

* **Dark, map-first layout.** Glass panels float over a full-screen map; the insight
  navigator walks through the platform's six questions and sets up the map for each.
* **Colour has a job.** PM2.5 uses US EPA AQI colours (or a relative single-hue scale);
  uncertainty, population, coverage and OSSE error use single-hue ramps where low values
  recede into the dark basemap; the gap index uses the reserved severity colours. Chart
  series use a categorical palette validated for colour-vision deficiency against the
  panel surface.
* **Honest labelling.** A data-mode badge (DEMO / LIVE / stale / fallback) is always
  visible; charts and evidence cards repeat the synthetic-data note.
* **Accessibility.** Every chart has a table view, legends accompany multi-series charts,
  controls are keyboard reachable with visible focus, and motion respects
  `prefers-reduced-motion`.
* **Offline behaviour.** Without internet the basemap tiles are missing, but all data
  layers, markers and charts still render on the dark background.
