// Colour scales for map layers. Dark-mode semantics: low values recede towards the
// dark basemap (dark + transparent), high values are bright. Every sequential scale is a
// single hue; the gap layer uses the reserved status steps because it encodes severity.
import { aqiRgb } from "./aqi";

export type RGBA = [number, number, number, number];

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

export function interpolateStops(stops: string[], t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const a = hexToRgb(stops[i]);
  const b = hexToRgb(stops[i + 1]);
  return [0, 1, 2].map((k) => Math.round(a[k] + f * (b[k] - a[k]))) as [number, number, number];
}

export const RAMPS = {
  violet: ["#2e1065", "#4c1d95", "#6d28d9", "#8b5cf6", "#c4b5fd", "#ede9fe"],
  blue: ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"],
  teal: ["#042f2e", "#115e59", "#0f766e", "#14b8a6", "#5eead4", "#ccfbf1"],
  orange: ["#431407", "#7c2d12", "#c2410c", "#f97316", "#fdba74", "#ffedd5"],
};

export const GAP_COLORS: Record<string, string> = {
  low: "#3a414c",
  moderate: "#fab219", // status: warning
  high: "#ec835a", // status: serious
  critical: "#d03b3b", // status: critical
};

export function cssGradient(stops: string[]): string {
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

export const GAP_GRADIENT = "linear-gradient(to right, rgba(250,178,25,0.15), #fab219 33%, #ec835a 60%, #d03b3b 85%, #ff4d6d)";

// ---------------------------------------------------------------- layer colour functions

export function pm25Color(v: number): RGBA {
  const [r, g, b] = aqiRgb(v);
  return [r, g, b, 215];
}

export function seqColor(ramp: string[], domain: [number, number], alphaMin = 70, alphaMax = 225) {
  const [lo, hi] = domain;
  const span = hi - lo || 1;
  return (v: number): RGBA => {
    const t = Math.min(1, Math.max(0, (v - lo) / span));
    const [r, g, b] = interpolateStops(ramp, t);
    return [r, g, b, Math.round(alphaMin + t * (alphaMax - alphaMin))];
  };
}

export function gapColor(v: number): RGBA | null {
  if (v < 0.3) return [58, 65, 76, 18];
  const stops: [number, [number, number, number], number][] = [
    [0.3, [250, 178, 25], 22],
    [0.45, [250, 178, 25], 80],
    [0.6, [236, 131, 90], 165],
    [0.75, [222, 52, 52], 220],
    [1.0, [255, 77, 109], 240],
  ];
  for (let i = 1; i < stops.length; i++) {
    if (v <= stops[i][0]) {
      const [x0, c0, a0] = stops[i - 1];
      const [x1, c1, a1] = stops[i];
      const t = (v - x0) / (x1 - x0);
      return [
        Math.round(c0[0] + t * (c1[0] - c0[0])),
        Math.round(c0[1] + t * (c1[1] - c0[1])),
        Math.round(c0[2] + t * (c1[2] - c0[2])),
        Math.round(a0 + t * (a1 - a0)),
      ];
    }
  }
  return [255, 77, 109, 235];
}

/** Robust [p2, p98] domain of the non-null values. */
export function robustDomain(values: (number | null)[], lo = 0.02, hi = 0.98): [number, number] {
  const v = values.filter((x): x is number => x != null && Number.isFinite(x)).sort((a, b) => a - b);
  if (!v.length) return [0, 1];
  const q = (p: number) => v[Math.min(v.length - 1, Math.max(0, Math.round(p * (v.length - 1))))];
  const a = q(lo);
  const b = q(hi);
  return a === b ? [a, a + 1] : [a, b];
}
