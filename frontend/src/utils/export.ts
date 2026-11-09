import type { Site } from "../types";

function download(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function csvCell(v: unknown): string {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function sitesToCsv(sites: Site[]): string {
  const header = ["rank", "latitude", "longitude", "location", "pm25_ugm3", "aqi_category", "gap_index", "population_density_per_km2",
    "nearest_station_km", "newly_covered_population", "reasons"];
  const rows = sites.map((s) => [s.rank, s.lat, s.lon, s.location.label, s.pm25, s.aqi_category, s.gap_index, s.population_density,
    s.nearest_station_km, s.newly_covered_population, s.reasons.join(" | ")].map(csvCell).join(","));
  return [header.join(","), ...rows].join("\n");
}

export function sitesToGeoJson(sites: Site[], meta: Record<string, unknown>): string {
  return JSON.stringify({
    type: "FeatureCollection",
    metadata: meta,
    features: sites.map((s) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      properties: { ...s, location: s.location.label },
    })),
  }, null, 2);
}

export function exportSites(sites: Site[], format: "csv" | "geojson", cityId: string, meta: Record<string, unknown>): void {
  const stamp = new Date().toISOString().slice(0, 10);
  if (format === "csv") download(`airscope_${cityId}_recommended_sites_${stamp}.csv`, sitesToCsv(sites), "text/csv");
  else download(`airscope_${cityId}_recommended_sites_${stamp}.geojson`, sitesToGeoJson(sites, meta), "application/geo+json");
}
