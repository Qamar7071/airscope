import type { GridGeometry, Locality } from "../types";

const R = 6371.0088;

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Flat grid index (row-major, row 0 = north) for a coordinate, or -1 outside the domain. */
export function cellIndex(g: GridGeometry, lat: number, lon: number): number {
  if (lat < g.south || lat > g.north || lon < g.west || lon > g.east) return -1;
  const row = Math.min(g.nrows - 1, Math.floor((g.north - lat) / g.dlat));
  const col = Math.min(g.ncols - 1, Math.floor((lon - g.west) / g.dlon));
  const idx = row * g.ncols + col;
  return g.mask[idx] ? idx : -1;
}

export function cellCenter(g: GridGeometry, idx: number): { lat: number; lon: number } {
  const row = Math.floor(idx / g.ncols);
  const col = idx % g.ncols;
  return { lat: g.north - (row + 0.5) * g.dlat, lon: g.west + (col + 0.5) * g.dlon };
}

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

function bearing(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const y = Math.sin(toRad(lon2 - lon1)) * Math.cos(toRad(lat2));
  const x = Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) - Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lon2 - lon1));
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

export function describeLocation(localities: Locality[] | undefined, lat: number, lon: number): string {
  if (!localities?.length) return `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  let best = localities[0];
  let bestD = Infinity;
  for (const l of localities) {
    const d = haversineKm(lat, lon, l.lat, l.lon);
    if (d < bestD) {
      bestD = d;
      best = l;
    }
  }
  if (bestD < 0.6) return best.name;
  const dir = COMPASS[Math.round(bearing(best.lat, best.lon, lat, lon) / 45) % 8];
  return `${bestD.toFixed(1)} km ${dir} of ${best.name}`;
}
