import { describe, expect, it } from "vitest";
import { aqiBand, aqiCategory, aqiRgb, pm25ToAqi } from "./aqi";
import { gapColor, interpolateStops, robustDomain, seqColor } from "./colors";
import { fmtCompact, fmtPct, fmtSignedCompact } from "./formatting";
import { cellCenter, cellIndex, describeLocation, haversineKm } from "./geo";
import { sitesToCsv } from "./export";
import type { GridGeometry, Site } from "../types";

describe("AQI (US EPA 2024 breakpoints)", () => {
  it.each([
    [0, 0, "Good"],
    [9.0, 50, "Good"],
    [9.1, 51, "Moderate"],
    [35.4, 100, "Moderate"],
    [35.5, 101, "Unhealthy for Sensitive Groups"],
    [55.5, 151, "Unhealthy"],
    [125.5, 201, "Very Unhealthy"],
    [225.5, 301, "Hazardous"],
    [325.4, 500, "Hazardous"],
  ])("pm %s -> AQI %s (%s)", (pm, aqi, cat) => {
    expect(pm25ToAqi(pm)).toBe(aqi);
    expect(aqiCategory(pm)).toBe(cat);
  });
  it("handles invalid input", () => {
    expect(pm25ToAqi(null)).toBeNull();
    expect(aqiBand(-1)).toBeNull();
  });
  it("continuous colour stays within the category hue family", () => {
    const [r, g] = aqiRgb(100); // unhealthy -> red
    expect(r).toBeGreaterThan(150);
    expect(g).toBeLessThan(60);
  });
});

describe("colour scales", () => {
  it("interpolates stops and clamps", () => {
    expect(interpolateStops(["#000000", "#ffffff"], 0.5)).toEqual([128, 128, 128]);
    expect(interpolateStops(["#000000", "#ffffff"], 2)).toEqual([255, 255, 255]);
  });
  it("sequential alpha grows with value", () => {
    const f = seqColor(["#000000", "#ffffff"], [0, 10], 10, 200);
    expect(f(0)[3]).toBe(10);
    expect(f(10)[3]).toBe(200);
  });
  it("gap colours get more opaque with severity", () => {
    expect(gapColor(0.9)![3]).toBeGreaterThan(gapColor(0.5)![3]);
  });
  it("robust domain ignores nulls and outliers", () => {
    const vals = [null, ...Array.from({ length: 100 }, (_, i) => i), 10_000];
    const [lo, hi] = robustDomain(vals);
    expect(lo).toBeGreaterThanOrEqual(0);
    expect(hi).toBeLessThan(10_000);
  });
});

describe("formatting", () => {
  it("compact numbers", () => {
    expect(fmtCompact(1284)).toBe("1,284");
    expect(fmtCompact(12_900)).toBe("12.9K");
    expect(fmtCompact(4_200_000)).toBe("4.20M");
    expect(fmtSignedCompact(-428_000)).toBe("−428.0K");
    expect(fmtPct(12.345, 1)).toBe("12.3%");
  });
});

describe("grid geometry", () => {
  const g: GridGeometry = {
    north: 1, south: 0, east: 1, west: 0, nrows: 2, ncols: 2, dlat: 0.5, dlon: 0.5,
    cell_km: 55, cell_area_km2: 3000, n_inside: 3, mask: [1, 1, 0, 1],
  };
  it("row 0 is north and outside cells return -1", () => {
    expect(cellIndex(g, 0.9, 0.1)).toBe(0);
    expect(cellIndex(g, 0.9, 0.9)).toBe(1);
    expect(cellIndex(g, 0.1, 0.1)).toBe(-1); // masked
    expect(cellIndex(g, 2, 2)).toBe(-1);
    expect(cellCenter(g, 3)).toEqual({ lat: 0.25, lon: 0.75 });
  });
  it("haversine and locality labels", () => {
    expect(haversineKm(0, 0, 1, 0)).toBeCloseTo(111.195, 2);
    const locs = [{ name: "F-6", lat: 33.729, lon: 73.076 }];
    expect(describeLocation(locs, 33.729, 73.076)).toBe("F-6");
    expect(describeLocation(locs, 33.70, 73.076)).toMatch(/km S of F-6/);
  });
});

describe("export", () => {
  it("csv escapes commas and quotes", () => {
    const site = {
      rank: 1, lat: 33.6, lon: 73.0, cell_index: 5, location: { name: "A", distance_km: 0, label: 'Near "X", Y' },
      pm25: 80, aqi_category: "Unhealthy", uncertainty_score: 0.5, gap_index: 0.8, population_density: 1000,
      nearest_station_km: 4, objective_gain: 0.1, newly_covered_population: 5000, reasons: ["a", "b"],
    } as Site;
    const csv = sitesToCsv([site]);
    expect(csv.split("\n")[1]).toContain('"Near ""X"", Y"');
  });
});
