/**
 * @file Pure colour arithmetic for the Stilyagi style probe.
 *
 * The probe evaluates its inspection function inside the page, where module
 * imports cannot reach, so these helpers are written as named function
 * declarations: the probe serializes them with `Function.prototype.toString`
 * and injects the source as a script tag, which defines them as globals the
 * in-page code can call. Keeping them here rather than inline in the probe
 * is what lets `tests/js/stilyagi-probe-helpers.test.mjs` exercise them
 * directly.
 */

/**
 * Read a computed CSS colour into `[r, g, b, alpha]` channels.
 *
 * Chromium reports computed colours as `rgb(...)`, `rgba(...)`, or — for
 * wide-gamut declarations — `color(srgb ...)` whose channels run 0-1 and are
 * scaled up to the 0-255 range the other forms use. A value carrying no
 * number at all (`transparent` never reaches a computed style, but a guard
 * costs nothing) comes back as `null`.
 *
 * @param {string} value - A computed colour string.
 * @returns {[number, number, number, number] | null} Channels on 0-255 with
 *   alpha on 0-1, or null when the value carries no numbers.
 */
export function parseCssColor(value) {
  const parts = value.match(/-?[\d.]+/g);
  if (!parts) return null;
  const n = parts.map(Number);
  // color(srgb r g b / a) carries 0-1 channels; rgb()/rgba() carry 0-255.
  return value.startsWith("color(")
    ? [n[0] * 255, n[1] * 255, n[2] * 255, n.length > 3 ? n[3] : 1]
    : [n[0], n[1], n[2], n.length > 3 ? n[3] : 1];
}

/**
 * Composite a translucent foreground onto an opaque background.
 *
 * Standard source-over alpha blending, per channel. The background's own
 * alpha is taken as 1 because the probe always composites onto a ground it
 * has already resolved to an opaque colour.
 *
 * @param {[number, number, number, number]} fg - Foreground with alpha.
 * @param {[number, number, number]} bg - Opaque background channels.
 * @returns {[number, number, number]} The blended opaque colour.
 */
export function compositeOver(fg, bg) {
  return fg.slice(0, 3).map((c, i) => c * fg[3] + bg[i] * (1 - fg[3]));
}
