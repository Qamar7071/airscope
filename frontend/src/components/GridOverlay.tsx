import L from "leaflet";
import { useMemo } from "react";
import { ImageOverlay } from "react-leaflet";
import type { GridGeometry, NumArr } from "../types";
import type { RGBA } from "../utils/colors";

/** Paint one value per grid cell into a tiny canvas (row 0 = north) and return a PNG data URL. */
export function renderGridImage(geom: GridGeometry, values: NumArr, color: (v: number) => RGBA | null): string {
  const canvas = document.createElement("canvas");
  canvas.width = geom.ncols;
  canvas.height = geom.nrows;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  const img = ctx.createImageData(geom.ncols, geom.nrows);
  const n = Math.min(values.length, geom.nrows * geom.ncols);
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v == null || !geom.mask[i]) continue;
    const c = color(v);
    if (c) img.data.set(c, i * 4);
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL("image/png");
}

export interface GridOverlayProps {
  geometry: GridGeometry;
  values: NumArr | undefined;
  color: (v: number) => RGBA | null;
  opacity: number;
  smooth: boolean;
}

/**
 * Renders a city grid layer as a single image overlay: fast (one <img>, no per-cell DOM)
 * and, with browser bilinear scaling, a smooth field. "Crisp" mode shows the raw cells.
 */
export function GridOverlay({ geometry, values, color, opacity, smooth }: GridOverlayProps) {
  const url = useMemo(() => (values ? renderGridImage(geometry, values, color) : ""), [geometry, values, color]);
  const bounds = useMemo(
    () => L.latLngBounds([geometry.south, geometry.west], [geometry.north, geometry.east]),
    [geometry.south, geometry.west, geometry.north, geometry.east],
  );
  if (!values || !url) return null;
  return <ImageOverlay key={smooth ? "smooth" : "crisp"} url={url} bounds={bounds} opacity={opacity} className={smooth ? "grid-smooth" : "grid-crisp"} />;
}
