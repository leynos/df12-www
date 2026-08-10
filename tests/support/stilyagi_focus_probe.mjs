/* Report how the Stilyagi docs page indicates focus on a filter chip.
 *
 * Driven by tests/test_stilyagi_focus.py, which serves the rendered page and
 * reads the JSON printed here. The chip is the interesting case because it is
 * the one control on the sub-site whose fill is ink while its focus ring is
 * drawn outside it, on the paper filter bar: the two grounds disagree, so a
 * ring coloured for the fill disappears against the bar.
 *
 * Usage: bun tests/support/stilyagi_focus_probe.mjs <url> <namespace>
 *   PLAYWRIGHT_CHROMIUM_EXECUTABLE overrides which browser binary is launched.
 */

import { existsSync } from "node:fs";

const [url, namespace] = process.argv.slice(2);
if (!url || !namespace) {
  console.error("usage: stilyagi_focus_probe.mjs <url> <namespace>");
  process.exit(2);
}

const { chromium } = await import("playwright");

/* Playwright launches the browser revision it was built against, which is not
 * necessarily one of the revisions installed here — the package and the
 * browsers are fetched separately. The caller passes an installed binary when
 * it knows of one; otherwise Playwright's own default applies. */
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const launchOptions = executablePath && existsSync(executablePath) ? { executablePath } : {};

/* Everything below runs in the page: the contrast of the ring against the
 * ground it is painted on is the thing under test, and only the browser knows
 * what that ground composites to. */
function inspect(selector) {
  const parse = (value) => {
    const parts = value.match(/-?[\d.]+/g);
    if (!parts) return null;
    const n = parts.map(Number);
    // color(srgb r g b / a) carries 0-1 channels; rgb()/rgba() carry 0-255.
    return value.startsWith("color(")
      ? [n[0] * 255, n[1] * 255, n[2] * 255, n.length > 3 ? n[3] : 1]
      : [n[0], n[1], n[2], n.length > 3 ? n[3] : 1];
  };
  const channel = (c) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  const luminance = (rgb) =>
    0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
  const contrast = (a, b) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };
  const composite = (fg, bg) => fg.slice(0, 3).map((c, i) => c * fg[3] + bg[i] * (1 - fg[3]));

  // Flatten every background from the page down to `el` onto the paper base,
  // so a translucent surface such as the sticky filter bar resolves.
  const groundOf = (el) => {
    const chain = [];
    for (let node = el; node && node !== document.documentElement; node = node.parentElement) {
      chain.unshift(node);
    }
    let ground = [239, 228, 206];
    for (const node of chain) {
      const bg = parse(getComputedStyle(node).backgroundColor);
      if (bg && bg[3] > 0) ground = composite(bg, ground);
    }
    return ground;
  };

  const el = document.querySelector(selector);
  const style = getComputedStyle(el);
  const offset = Number.parseFloat(style.outlineOffset);
  // A ring at a negative offset is painted over the element's own fill; at a
  // positive one it is painted on whatever surrounds the element.
  const ground = groundOf(offset < 0 ? el : el.parentElement || el);
  const ring = parse(style.outlineColor);
  return {
    classes: el.className,
    fill: style.backgroundColor,
    outlineStyle: style.outlineStyle,
    outlineWidth: Number.parseFloat(style.outlineWidth),
    outlineColor: style.outlineColor,
    outlineOffset: offset,
    displayed: style.display !== "none",
    ground: ground.map(Math.round),
    contrast: Number(contrast(ring, ground).toFixed(2)),
  };
}

const browser = await chromium.launch(launchOptions);
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(url, { waitUntil: "load" });

  const chip = `button[data-ns="${namespace}"]`;
  await page.waitForSelector(chip);

  // Activating by pointer is also the check that pointer focus stays ringless:
  // the chip is focused here, but :focus-visible should not match.
  await page.click(chip);
  const pointer = await page.evaluate(inspect, chip);

  // Hand focus back to the same chip by keyboard, which is what :focus-visible
  // is for. The chip keeps its active classes across this.
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  const keyboard = await page.evaluate(inspect, chip);

  console.log(JSON.stringify({ pointer, keyboard }));
} finally {
  await browser.close();
}
