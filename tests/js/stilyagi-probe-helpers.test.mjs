/**
 * @file Tests for the Stilyagi style probe's colour arithmetic.
 *
 * `parseCssColor` and `compositeOver` run inside the probed page, where a
 * wrong reading silently skews every contrast the browser contracts
 * measure — a misparsed `color(srgb ...)` channel or a bad alpha blend
 * shifts the computed ground rather than raising an error. These tests
 * pin both functions directly, outside the browser, so the arithmetic is
 * proven before a probe ever leans on it.
 */

import { describe, expect, test } from "bun:test";

import { compositeOver, parseCssColor } from "../support/stilyagi_probe_helpers.mjs";

describe("parseCssColor", () => {
  test("reads the rgb() form Chromium reports opaque colours in", () => {
    expect(parseCssColor("rgb(239, 228, 206)")).toEqual([239, 228, 206, 1]);
  });

  test("carries the alpha channel of an rgba() colour", () => {
    expect(parseCssColor("rgba(15, 15, 15, 0.5)")).toEqual([15, 15, 15, 0.5]);
  });

  test("scales color(srgb ...) channels from 0-1 up to 0-255", () => {
    const [red, green, blue, alpha] = parseCssColor("color(srgb 1 0.5 0 / 0.25)");
    expect([red, blue, alpha]).toEqual([255, 0, 0.25]);
    expect(green).toBeCloseTo(127.5);
  });

  test("defaults a three-channel colour to full opacity", () => {
    expect(parseCssColor("color(srgb 0 0 0)")).toEqual([0, 0, 0, 1]);
  });

  test("returns null for a value carrying no numbers", () => {
    expect(parseCssColor("transparent")).toBeNull();
  });
});

describe("compositeOver", () => {
  test("an opaque foreground replaces the background outright", () => {
    expect(compositeOver([15, 15, 15, 1], [239, 228, 206])).toEqual([15, 15, 15]);
  });

  test("a fully transparent foreground leaves the background alone", () => {
    expect(compositeOver([15, 15, 15, 0], [239, 228, 206])).toEqual([239, 228, 206]);
  });

  test("a half-alpha foreground lands midway, per channel", () => {
    expect(compositeOver([0, 0, 0, 0.5], [200, 100, 50])).toEqual([100, 50, 25]);
  });
});
