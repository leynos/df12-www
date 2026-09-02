/* Report the computed styles of selected elements on Stilyagi pages.
 *
 * Driven by tests/test_stilyagi_browser.py, which serves the built public
 * tree and reads the JSON printed here. The probe takes a batch of jobs on
 * stdin so the whole suite pays for one browser launch:
 *
 *   {"jobs": [{"name": ..., "url": ..., "width": ..., "height": ...,
 *              "selectors": ["..."]}]}
 *
 * For each job it loads the page at the given viewport and reports, per
 * selector, the computed properties a migration regression would disturb —
 * display, colours, borders, geometry — plus the effective background
 * ground composited up the ancestor chain, so the caller can measure
 * contrast without guessing what a colour actually sits on. Page-level
 * facts (loaded stylesheet hrefs, scroll versus viewport width) ride along
 * for the layout and asset assertions.
 *
 * Usage: bun tests/support/stilyagi_style_probe.mjs < jobs.json
 *   PLAYWRIGHT_CHROMIUM_EXECUTABLE overrides which browser binary launches.
 */

import { existsSync } from "node:fs";

const spec = JSON.parse(await new Response(process.stdin).text());
if (!spec || !Array.isArray(spec.jobs) || spec.jobs.length === 0) {
  console.error("usage: stilyagi_style_probe.mjs < jobs.json");
  process.exit(2);
}

const { chromium } = await import("playwright");

/* Playwright launches the browser revision it was built against, which is
 * not necessarily one of the revisions installed here — the package and the
 * browsers are fetched separately. The caller passes an installed binary
 * when it knows of one; otherwise Playwright's own default applies. */
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const launchOptions = executablePath && existsSync(executablePath) ? { executablePath } : {};

/* Runs in the page. The effective ground matters because several Stilyagi
 * surfaces are translucent washes over the paper base; only the browser
 * knows what they composite to. */
function inspect(selectors) {
  const parse = (value) => {
    const parts = value.match(/-?[\d.]+/g);
    if (!parts) return null;
    const n = parts.map(Number);
    // color(srgb r g b / a) carries 0-1 channels; rgb()/rgba() carry 0-255.
    return value.startsWith("color(")
      ? [n[0] * 255, n[1] * 255, n[2] * 255, n.length > 3 ? n[3] : 1]
      : [n[0], n[1], n[2], n.length > 3 ? n[3] : 1];
  };
  const composite = (fg, bg) => fg.slice(0, 3).map((c, i) => c * fg[3] + bg[i] * (1 - fg[3]));
  const groundOf = (el) => {
    const chain = [];
    for (let node = el; node; node = node.parentElement) chain.unshift(node);
    let ground = [255, 255, 255];
    for (const node of chain) {
      const bg = parse(getComputedStyle(node).backgroundColor);
      if (bg && bg[3] > 0) ground = composite(bg, ground);
    }
    return ground.map(Math.round);
  };

  const elements = {};
  for (const selector of selectors) {
    const el = document.querySelector(selector);
    if (!el) {
      elements[selector] = { found: false };
      continue;
    }
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    elements[selector] = {
      found: true,
      className: typeof el.className === "string" ? el.className : "",
      display: style.display,
      visibility: style.visibility,
      position: style.position,
      backgroundColor: style.backgroundColor,
      color: style.color,
      borderTopWidth: style.borderTopWidth,
      borderRightWidth: style.borderRightWidth,
      borderBottomWidth: style.borderBottomWidth,
      borderLeftWidth: style.borderLeftWidth,
      borderTopStyle: style.borderTopStyle,
      borderBottomStyle: style.borderBottomStyle,
      borderTopColor: style.borderTopColor,
      borderBottomColor: style.borderBottomColor,
      fontFamily: style.fontFamily,
      textTransform: style.textTransform,
      width: box.width,
      height: box.height,
      // The ground the element's *contents* sit on includes its own fill;
      // the parent ground is what the element itself is seen against.
      contentGround: groundOf(el),
      parentGround: el.parentElement ? groundOf(el.parentElement) : groundOf(el),
    };
  }

  return {
    elements,
    page: {
      stylesheets: [...document.styleSheets]
        .map((sheet) => sheet.href)
        .filter((href) => href !== null)
        .map((href) => new URL(href).pathname),
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    },
  };
}

const browser = await chromium.launch(launchOptions);
try {
  const results = {};
  for (const job of spec.jobs) {
    const page = await browser.newPage({
      viewport: { width: job.width, height: job.height },
    });
    await page.goto(job.url, { waitUntil: "load" });
    results[job.name] = await page.evaluate(inspect, job.selectors);
    await page.close();
  }
  console.log(JSON.stringify(results));
} finally {
  await browser.close();
}
