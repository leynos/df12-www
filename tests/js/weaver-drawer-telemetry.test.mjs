/* What the Weaver drawer reports, and what it must never report.
 *
 * The schema itself is covered in `weaver-telemetry.test.mjs`, against the
 * module. These are about the drawer: that it says nothing when the page did
 * not load the hook, that each lifecycle point produces the event it should,
 * and that no page path, navigation label or origin reaches an event.
 */
import { afterEach, describe, expect, test } from "bun:test";

import { click, pressKey } from "./helpers/mobile-nav-harness.mjs";
import { setUp, tearDown } from "./helpers/weaver-drawer.mjs";

/* `telemetry.js` and the sink both live on the process global while a test
   runs, since that is where `evaluateScript` puts a script's `globalThis`.
   Leaving them there would let one test's sink collect another's events. */
afterEach(tearDown);

describe("telemetry", () => {
  test("says nothing at all when the page did not load the hook", () => {
    /* A sink is installed; `telemetry.js` is not. The drawer has nothing to
       report through, so it must report nothing — and the sink is there to
       catch it if some future change reaches past the module. */
    const dom = setUp({ telemetry: false });
    click(dom.window, dom.toggle);
    pressKey(dom.window, dom.document, "Escape");
    expect(dom.isOpen()).toBe(false);
    expect(dom.events).toEqual([]);
  });

  test("reports that the drawer was built", () => {
    const dom = setUp({ telemetry: true });
    expect(dom.events).toEqual([
      { component: "weaver-mobile-nav", operation: "drawer", outcome: "initialized" },
    ]);
  });

  test("reports opening", () => {
    const dom = setUp({ telemetry: true });
    dom.events.length = 0;
    click(dom.window, dom.toggle);
    expect(dom.events).toEqual([
      { component: "weaver-mobile-nav", operation: "drawer", outcome: "opened" },
    ]);
  });

  test("attributes each close to what caused it", () => {
    const closes = [
      ["toggle", (dom) => click(dom.window, dom.toggle)],
      ["backdrop", (dom) => click(dom.window, dom.backdrop)],
      ["nav-link", (dom) => click(dom.window, dom.nav.querySelector("a"))],
      ["escape", (dom) => pressKey(dom.window, dom.document, "Escape")],
      ["breakpoint", (dom) => dom.media.cross(true)],
    ];
    for (const [reason, act] of closes) {
      const dom = setUp({ telemetry: true });
      click(dom.window, dom.toggle);
      dom.events.length = 0;
      act(dom);

      expect(dom.isOpen()).toBe(false);
      const closed = dom.events.filter((e) => e.outcome === "closed");
      expect(closed).toEqual([
        { component: "weaver-mobile-nav", operation: "drawer", outcome: "closed", reason },
      ]);
    }
  });

  test("reports where focus went when the drawer closed", () => {
    /* Nothing held focus before opening, so it falls back to the toggle. */
    const fallback = setUp({ telemetry: true });
    click(fallback.window, fallback.toggle);
    fallback.events.length = 0;
    pressKey(fallback.window, fallback.document, "Escape");
    expect(fallback.events.filter((e) => e.outcome === "focus-restored")).toEqual([
      {
        component: "weaver-mobile-nav",
        operation: "drawer",
        outcome: "focus-restored",
        reason: "toggle-fallback",
      },
    ]);

    /* Something did hold it, so focus goes back there. */
    const restored = setUp({ telemetry: true });
    restored.document.getElementById("outside").focus();
    click(restored.window, restored.toggle);
    restored.events.length = 0;
    pressKey(restored.window, restored.document, "Escape");
    expect(restored.events.filter((e) => e.outcome === "focus-restored")).toEqual([
      {
        component: "weaver-mobile-nav",
        operation: "drawer",
        outcome: "focus-restored",
        reason: "saved-element",
      },
    ]);
  });

  test("carries no page, label or identifier in any drawer event", () => {
    const dom = setUp({ telemetry: true, links: ["/weaver/install/", "/weaver/docs/"] });
    click(dom.window, dom.toggle);
    click(dom.window, dom.nav.querySelector("a"));

    expect(dom.events.length).toBeGreaterThan(0);
    const payload = JSON.stringify(dom.events);
    for (const forbidden of ["/weaver/", "install", "docs", "weaver.example", "https://"]) {
      expect(payload).not.toContain(forbidden);
    }
    for (const event of dom.events) {
      expect(Object.keys(event).sort()).toEqual(
        ["component", "operation", "outcome", "reason"].filter((f) => f in event).sort(),
      );
    }
  });
});
