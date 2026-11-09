import L from "leaflet";
import { useMemo } from "react";
import { Marker, Tooltip } from "react-leaflet";
import type { Cluster, GapsResponse, GridGeometry } from "../types";
import { gapColor } from "../utils/colors";
import { fmtCompact, fmtKm } from "../utils/formatting";
import { GridOverlay } from "./GridOverlay";

/** Monitoring Gap Index field (0-1) using the reserved severity (status) colours. */
export default function GapLayer({ gaps, geometry, opacity, smooth }: { gaps: GapsResponse; geometry: GridGeometry; opacity: number; smooth: boolean }) {
  return <GridOverlay geometry={geometry} values={gaps.gap_index} color={gapColor} opacity={Math.min(1, opacity + 0.1)} smooth={smooth} />;
}

const clusterIcon = (id: string) =>
  L.divIcon({ className: "", html: `<div class="cluster-label" aria-hidden="true">${id}</div>`, iconSize: [26, 26], iconAnchor: [13, 13] });

/** Labels at the centroid of each critical blind-spot cluster. */
export function ClusterMarkers({ clusters, onSelect }: { clusters: Cluster[]; onSelect: (c: Cluster) => void }) {
  const icons = useMemo(() => Object.fromEntries(clusters.map((c) => [c.id, clusterIcon(c.id)])), [clusters]);
  return (
    <>
      {clusters.map((c) => (
        <Marker
          key={c.id}
          position={[c.centroid.lat, c.centroid.lon]}
          icon={icons[c.id]}
          keyboard
          title={`Blind spot ${c.id}: ${c.location.label}`}
          eventHandlers={{ click: () => onSelect(c) }}
        >
          <Tooltip className="airscope-tip" direction="top" offset={[0, -14]}>
            <div className="font-semibold">Blind spot {c.id} · {c.location.label}</div>
            <div className="text-txt-secondary">
              {c.area_km2} km² · ~{fmtCompact(c.population)} residents · {fmtKm(c.distance_to_nearest_station_km)} to nearest monitor
            </div>
          </Tooltip>
        </Marker>
      ))}
    </>
  );
}
