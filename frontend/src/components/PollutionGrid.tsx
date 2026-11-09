import { useMemo } from "react";
import type { GridResponse } from "../types";
import { RAMPS, pm25Color, robustDomain, seqColor } from "../utils/colors";
import { GridOverlay } from "./GridOverlay";

export const pmDomain = (grid: GridResponse): [number, number] => robustDomain(grid.layers.pm25 ?? []);

/**
 * Estimated PM2.5. "aqi": US EPA AQI category colours (absolute, health-oriented).
 * "relative": single-hue ramp over the city's own 2nd-98th percentile range, to reveal
 * within-city contrast when the whole city falls in one AQI category.
 */
export default function PollutionGrid({ grid, opacity, smooth, scale }: { grid: GridResponse; opacity: number; smooth: boolean; scale: "aqi" | "relative" }) {
  const domain = useMemo(() => pmDomain(grid), [grid]);
  const color = useMemo(() => (scale === "relative" ? seqColor(RAMPS.orange, domain, 70, 230) : pm25Color), [scale, domain]);
  return <GridOverlay geometry={grid.geometry} values={grid.layers.pm25} color={color} opacity={opacity} smooth={smooth} />;
}
