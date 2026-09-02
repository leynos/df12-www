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

import { compositeOver, parseCssColor } from "./stilyagi_probe_helpers.mjs";

/* The colour helpers run inside the page, where imports cannot reach:
 * their source is injected as a script tag, which defines the named
 * function declarations as globals for `inspect` below to call. Keeping
 * them in a module of their own is what lets the JS suite unit-test them. */
const HELPER_SOURCE = [parseCssColor, compositeOver].map((fn) => fn.toString()).join("\n");

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
  const groundOf = (el) => {
    const chain = [];
    for (let node = el; node; node = node.parentElement) chain.unshift(node);
    let ground = [255, 255, 255];
    for (const node of chain) {
      const bg = parseCssColor(getComputedStyle(node).backgroundColor);
      if (bg && bg[3] > 0) ground = compositeOver(bg, ground);
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
    /* The load event does not wait for web fonts, and the sub-site's tables
     * and labels take their min-content widths from the loaded faces — a
     * probe that reads layout before `document.fonts.ready` measures the
     * fallback fonts and reports nondeterministic geometry. */
    await page.evaluate(() => document.fonts.ready);
    await page.addScriptTag({ content: HELPER_SOURCE });
    results[job.name] = await page.evaluate(inspect, job.selectors);
    await page.close();
  }
  console.log(JSON.stringify(results));
} finally {
  await browser.close();
}
