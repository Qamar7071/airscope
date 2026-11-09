// US EPA AQI for PM2.5 (breakpoints revised 7 February 2024). Mirrors backend/ml/aqi.py.
// The AQI is defined for 24-hour means; AirScope applies it to hourly estimates for orientation only.

export interface AqiBand {
  lo: number;
  hi: number;
  iLo: number;
  iHi: number;
  category: string;
  short: string;
  color: string;
  text: string; // readable ink on top of the band colour
}

export const AQI_BANDS: AqiBand[] = [
  { lo: 0.0, hi: 9.0, iLo: 0, iHi: 50, category: "Good", short: "Good", color: "#00e400", text: "#0b0d10" },
  { lo: 9.1, hi: 35.4, iLo: 51, iHi: 100, category: "Moderate", short: "Moderate", color: "#ffff00", text: "#0b0d10" },
  { lo: 35.5, hi: 55.4, iLo: 101, iHi: 150, category: "Unhealthy for Sensitive Groups", short: "USG", color: "#ff7e00", text: "#0b0d10" },
  { lo: 55.5, hi: 125.4, iLo: 151, iHi: 200, category: "Unhealthy", short: "Unhealthy", color: "#ff0000", text: "#ffffff" },
  { lo: 125.5, hi: 225.4, iLo: 201, iHi: 300, category: "Very Unhealthy", short: "Very unhealthy", color: "#8f3f97", text: "#ffffff" },
  { lo: 225.5, hi: 325.4, iLo: 301, iHi: 500, category: "Hazardous", short: "Hazardous", color: "#7e0023", text: "#ffffff" },
];

export const WHO_24H = 15; // µg/m³, WHO 2021 guideline (24-hour mean)

const truncate = (c: number) => Math.floor(c * 10) / 10;

export function aqiBand(pm: number | null | undefined): AqiBand | null {
  if (pm == null || !Number.isFinite(pm) || pm < 0) return null;
  const c = truncate(pm);
  return AQI_BANDS.find((b) => c <= b.hi) ?? AQI_BANDS[AQI_BANDS.length - 1];
}

export function pm25ToAqi(pm: number | null | undefined): number | null {
  if (pm == null || !Number.isFinite(pm) || pm < 0) return null;
  const c = truncate(pm);
  for (const b of AQI_BANDS) {
    if (c <= b.hi) return Math.round(((b.iHi - b.iLo) / (b.hi - b.lo)) * (c - b.lo) + b.iLo);
  }
  const b = AQI_BANDS[AQI_BANDS.length - 1];
  return Math.min(999, Math.round(((b.iHi - b.iLo) / (b.hi - b.lo)) * (c - b.lo) + b.iLo));
}

export function aqiCategory(pm: number | null | undefined): string | null {
  return aqiBand(pm)?.category ?? null;
}

export function aqiColor(pm: number | null | undefined): string {
  return aqiBand(pm)?.color ?? "#7f8792";
}

// Continuous colour for map rendering. Hues stay inside each EPA category, but lightness and
// saturation vary within a band so that spatial contrast stays visible when a whole city sits in
// one category (common in winter). The legend shows the categories themselves.
const ANCHORS: [number, [number, number, number]][] = [
  [0, [0, 200, 80]],
  [9, [120, 228, 0]],
  [22, [255, 255, 0]],
  [35.4, [255, 205, 0]],
  [45, [255, 126, 0]],
  [55.4, [255, 84, 0]],
  [90, [228, 0, 0]],
  [125.4, [170, 0, 45]],
  [175, [143, 63, 151]],
  [225.4, [104, 30, 128]],
  [275, [126, 0, 35]],
  [420, [72, 0, 18]],
];

export function aqiRgb(pm: number): [number, number, number] {
  if (pm <= ANCHORS[0][0]) return ANCHORS[0][1];
  for (let i = 1; i < ANCHORS.length; i++) {
    const [x1, c1] = ANCHORS[i];
    if (pm <= x1) {
      const [x0, c0] = ANCHORS[i - 1];
      const t = (pm - x0) / (x1 - x0);
      return [0, 1, 2].map((k) => Math.round(c0[k] + t * (c1[k] - c0[k]))) as [number, number, number];
    }
  }
  return ANCHORS[ANCHORS.length - 1][1];
}
