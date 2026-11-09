// Number, time and coordinate formatting. Pakistan Standard Time is UTC+5 (no DST).

const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export function fmtInt(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "–" : nf0.format(v);
}

export function fmt1(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "–" : nf1.format(v);
}

export function fmtNum(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

/** Compact human number: 1,284 / 12.9K / 4.2M */
export function fmtCompact(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1e6) return `${(v / 1e6).toFixed(a >= 1e7 ? 1 : 2)}M`;
  if (a >= 1e4) return `${(v / 1e3).toFixed(1)}K`;
  return nf0.format(v);
}

export function fmtSignedCompact(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const s = v > 0 ? "+" : v < 0 ? "−" : "±";
  return `${s}${fmtCompact(Math.abs(v))}`;
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  return v == null || !Number.isFinite(v) ? "–" : `${v.toFixed(digits)}%`;
}

export function fmtSignedPct(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const s = v > 0 ? "+" : v < 0 ? "−" : "±";
  return `${s}${Math.abs(v).toFixed(digits)}%`;
}

export function fmtSigned(v: number | null | undefined, digits = 1, unit = ""): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const s = v > 0 ? "+" : v < 0 ? "−" : "±";
  return `${s}${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: digits })}${unit}`;
}

export function fmtPm(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "–" : `${Math.round(v)} µg/m³`;
}

export function fmtKm(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "–" : `${v < 10 ? v.toFixed(1) : Math.round(v)} km`;
}

export function fmtCoord(lat: number, lon: number): string {
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

const TZ = "Asia/Karachi";

export function fmtLocalTime(iso: string | null | undefined, timeZone = TZ): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { timeZone, weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
}

export function fmtShortDate(iso: string, timeZone = TZ): string {
  return new Date(iso).toLocaleString("en-GB", { timeZone, day: "2-digit", month: "short" });
}

export function fmtHour(iso: string, timeZone = TZ): string {
  return new Date(iso).toLocaleString("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hour12: false });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
