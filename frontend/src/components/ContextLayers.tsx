import { useMemo } from "react";
import type { GridResponse, NumArr } from "../types";
import { RAMPS, robustDomain, seqColor } from "../utils/colors";
import { GridOverlay } from "./GridOverlay";

export function populationDomain(values: NumArr): [number, number] {
  const logs = values.map((v) => (v == null ? null : Math.log10(Math.max(v, 1))));
  const [lo, hi] = robustDomain(logs, 0.02, 0.995);
  return [Math.max(1.5, lo), hi];
}

/** Population density (persons/km²) on a log scale, single blue ramp. */
export function PopulationLayer({ grid, opacity, smooth }: { grid: GridResponse; opacity: number; smooth: boolean }) {
  const values = useMemo(() => grid.layers.population.map((v) => (v == null ? null : Math.log10(Math.max(v, 1)))), [grid]);
  const domain = useMemo(() => populationDomain(grid.layers.population), [grid]);
  const color = useMemo(() => seqColor(RAMPS.blue, domain, 40, 215), [domain]);
  return <GridOverlay geometry={grid.geometry} values={values} color={color} opacity={opacity} smooth={smooth} />;
}

/** Probability that at least one station represents the cell (0-1), single teal ramp. */
const coverageColor = seqColor(RAMPS.teal, [0, 1], 25, 225);
export function CoverageLayer({ grid, opacity, smooth }: { grid: GridResponse; opacity: number; smooth: boolean }) {
  return <GridOverlay geometry={grid.geometry} values={grid.layers.coverage} color={coverageColor} opacity={opacity} smooth={smooth} />;
}

/** Demo only: mean absolute error of the estimate against the synthetic truth (OSSE). */
export function osseDomain(grid: GridResponse): [number, number] {
  const [, hi] = robustDomain(grid.layers.osse_error ?? []);
  return [0, hi];
}
export function OsseErrorLayer({ grid, opacity, smooth }: { grid: GridResponse; opacity: number; smooth: boolean }) {
  const domain = useMemo(() => osseDomain(grid), [grid]);
  const color = useMemo(() => seqColor(RAMPS.orange, domain, 50, 225), [domain]);
  return <GridOverlay geometry={grid.geometry} values={grid.layers.osse_error} color={color} opacity={opacity} smooth={smooth} />;
}
