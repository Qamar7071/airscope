import L from "leaflet";
import { Copy, Trash2 } from "lucide-react";
import { useMemo } from "react";
import { Marker, Popup } from "react-leaflet";
import type { SimSite, Site } from "../types";
import { aqiBand } from "../utils/aqi";
import { fmtCompact, fmtCoord, fmtInt, fmtKm, fmtPm } from "../utils/formatting";
import { AqiBadge } from "./ui";

const recIcon = (rank: number) =>
  L.divIcon({
    className: "",
    html: `<div class="rec-pin"><span class="ring animate-pulse-ring"></span><span class="core">${rank}</span></div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -14],
  });

const simIcon = (n: number) =>
  L.divIcon({
    className: "",
    html: `<div class="rec-pin sim-pin"><span class="ring"></span><span class="core">S${n}</span></div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -14],
  });

export function SiteDetails({ site, onCopy }: { site: Site; onCopy: (text: string) => void }) {
  const band = aqiBand(site.pm25);
  return (
    <div className="space-y-2">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-300">Recommended site #{site.rank}</div>
        <div className="text-[13px] font-semibold text-txt-primary">{site.location.label}</div>
        <button className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-txt-muted hover:text-txt-primary" onClick={() => onCopy(fmtCoord(site.lat, site.lon))}>
          <Copy className="h-3 w-3" /> {fmtCoord(site.lat, site.lon)}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        {site.pm25 != null && <span className="font-semibold">{fmtPm(site.pm25)}</span>}
        {band && <AqiBadge category={band.short} color={band.color} textColor={band.text} />}
        <span className="text-txt-secondary">Gap index {site.gap_index.toFixed(2)}</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11.5px]">
        <dt className="text-txt-muted">Population density</dt>
        <dd className="text-right">{fmtInt(site.population_density)} /km²</dd>
        <dt className="text-txt-muted">Nearest monitor</dt>
        <dd className="text-right">{fmtKm(site.nearest_station_km)}</dd>
        <dt className="text-txt-muted">Newly covered residents</dt>
        <dd className="text-right">{fmtCompact(site.newly_covered_population)}</dd>
      </dl>
      <ul className="list-disc space-y-0.5 pl-4 text-[11.5px] text-txt-secondary">
        {site.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}

export default function RecommendationPins({ sites, onCopy }: { sites: Site[]; onCopy: (text: string) => void }) {
  const icons = useMemo(() => sites.map((s) => recIcon(s.rank)), [sites]);
  return (
    <>
      {sites.map((s, i) => (
        <Marker key={`${s.rank}-${s.lat}-${s.lon}`} position={[s.lat, s.lon]} icon={icons[i]} title={`Recommended site ${s.rank}: ${s.location.label}`} zIndexOffset={500}>
          <Popup minWidth={250} maxWidth={300}>
            <SiteDetails site={s} onCopy={onCopy} />
          </Popup>
        </Marker>
      ))}
    </>
  );
}

export function SimulatedSites({ sites, onMove, onRemove }: {
  sites: SimSite[];
  onMove: (id: string, lat: number, lon: number) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <>
      {sites.map((s, i) => (
        <Marker
          key={s.id}
          position={[s.lat, s.lon]}
          icon={simIcon(i + 1)}
          draggable
          title={`Hypothetical sensor S${i + 1} (drag to move)`}
          zIndexOffset={600}
          eventHandlers={{
            dragend: (e) => {
              const ll = (e.target as L.Marker).getLatLng();
              onMove(s.id, ll.lat, ll.lng);
            },
          }}
        >
          <Popup minWidth={200}>
            <div className="space-y-2 text-[12px]">
              <div className="font-semibold">Hypothetical sensor S{i + 1}</div>
              <div className="text-txt-muted">{fmtCoord(s.lat, s.lon)} · drag the pin to move it</div>
              <button className="btn-ghost w-full" onClick={() => onRemove(s.id)}>
                <Trash2 className="h-3.5 w-3.5" /> Remove
              </button>
            </div>
          </Popup>
        </Marker>
      ))}
    </>
  );
}
