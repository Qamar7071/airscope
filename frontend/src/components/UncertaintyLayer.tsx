import { useMemo } from "react";
import type { GridResponse } from "../types";
import { RAMPS, robustDomain, seqColor } from "../utils/colors";
import { GridOverlay } from "./GridOverlay";

/**
 * Relative uncertainty: half-width of the calibrated 90 % interval as a share of the estimate.
 * Single-hue (violet) ramp; the domain is the robust 2nd-98th percentile range of the city.
 */
export function uncertaintyDomain(grid: GridResponse): [number, number] {
  return robustDomain(grid.layers.relative_uncertainty ?? []);
}

export default function UncertaintyLayer({ grid, opacity, smooth }: { grid: GridResponse; opacity: number; smooth: boolean }) {
  const domain = useMemo(() => uncertaintyDomain(grid), [grid]);
  const color = useMemo(() => seqColor(RAMPS.violet, domain, 60, 225), [domain]);
  return <GridOverlay geometry={grid.geometry} values={grid.layers.relative_uncertainty} color={color} opacity={opacity} smooth={smooth} />;
}
