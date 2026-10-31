/**
 * @file Tests for the wireframe scope beam.
 *
 * The beam redraws the hero scene's SVG strokes on a canvas, so its pure
 * geometry decides where every line and pulse lands: the path parser reads
 * the generator's `M`/`L` paths, `cumulative` measures them, and `pointAt`
 * walks a pulse along them. `nextGlitchAt` keeps the deflection glitch rare.
 * The canvas drawing itself is checked by eye in a browser; these tests hold
 * the arithmetic it stands on.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const SCRIPT = join("public", "wireframe", "assets", "js", "scope.js");
const { parsePath, cumulative, pointAt, nextGlitchAt, PERSISTENCE } = require(`../../${SCRIPT}`);

describe("parsePath", () => {
  test("reads the generator's move-and-line paths as points", () => {
    expect(parsePath("M10.5 20 L30 40.25 L-5 0")).toEqual([
      [10.5, 20],
      [30, 40.25],
      [-5, 0],
    ]);
  });

  test("ignores a dangling coordinate rather than inventing a point", () => {
    expect(parsePath("M1 2 L3")).toEqual([[1, 2]]);
  });
});

describe("cumulative and pointAt", () => {
  const points = [
    [0, 0],
    [3, 4],
    [3, 10],
  ];
  const lengths = cumulative(points);

  test("measures the running length at each vertex", () => {
    expect(lengths).toEqual([0, 5, 11]);
  });

  test("interpolates within a segment", () => {
    expect(pointAt(points, lengths, 2.5)).toEqual([1.5, 2]);
    expect(pointAt(points, lengths, 8)).toEqual([3, 7]);
  });

  test("clamps to the ends of the path", () => {
    expect(pointAt(points, lengths, -4)).toEqual([0, 0]);
    expect(pointAt(points, lengths, 99)).toEqual([3, 10]);
  });
});

describe("nextGlitchAt", () => {
  test("waits between six and ten seconds", () => {
    expect(nextGlitchAt(1000, () => 0)).toBe(7000);
    expect(nextGlitchAt(1000, () => 1)).toBe(11000);
  });
});

test("phosphor decay neither clears outright nor burns in", () => {
  expect(PERSISTENCE).toBeGreaterThan(0.05);
  expect(PERSISTENCE).toBeLessThan(0.6);
});
