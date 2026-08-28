/* Behavioural tests for the Weaver sidebar drawer.
 *
 * The drawer is modal — it installs a backdrop and locks body scrolling — so
 * the assertions that matter are about focus: that opening moves it inside,
 * that Tab cannot carry it out to the obscured page behind, and that closing
 * puts it back where it was. See `helpers/mobile-nav-harness.mjs` for why
 * these run against a real DOM rather than the fake used elsewhere.
 */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { Window } from "happy-dom";
import {
  click,
  evaluateScript,
  exhaustiveTransitionSequences,
  installMatchMedia,
  pressKey,
  pressTab,
  stubLayout,
} from "./helpers/mobile-nav-harness.mjs";

const SCRIPT = "public/weaver/assets/js/mobile-nav.js";
const TELEMETRY = "public/weaver/assets/js/telemetry.js";

/* Build a page with the sidebar markup `templates/weaver/` renders, load the
   drawer into it, and hand back the parts a test needs to drive. */
function setUp({ links = ["/install", "/docs"], telemetry = false } = {}) {
  const window = new Window({ url: "https://weaver.example/docs/" });
  const { document } = window;
  document.body.innerHTML = `
    <a href="/elsewhere" id="outside">Outside</a>
    <aside id="sidebar">
      <div data-mobile-nav-header><h1>WEAVER</h1></div>
      <nav>${links.map((href) => `<a href="${href}">${href}</a>`).join("")}</nav>
    </aside>`;
  stubLayout(window);
  const media = installMatchMedia(window);
  /* The drawer reports through `telemetry.js` when the page loaded it, and
     works the same when it did not. Both are worth exercising, so the script
     is only present when a test asks for it. */
  /* The sink is installed either way, so a test asserting the drawer stays
     silent has something that would catch it if it did not. Only the script
     that reports through it is conditional. `evaluateScript` runs a script
     through `new Function`, so its `globalThis` is this process's rather than
     the happy-dom window's; in a browser the two are the same object, and
     here `afterEach` takes the sink away again. */
  const events = [];
  globalThis.df12WeaverNavTelemetry = (event) => events.push(event);
  if (telemetry) {
    evaluateScript(window, TELEMETRY);
  }
  evaluateScript(window, SCRIPT);

  const sidebar = document.getElementById("sidebar");
  return {
    window,
    document,
    media,
    sidebar,
    nav: sidebar.querySelector("nav"),
    toggle: document.getElementById("mobile-nav-toggle"),
    backdrop: document.getElementById("mobile-nav-backdrop"),
    isOpen: () => sidebar.classList.contains("mobile-nav-open"),
    events,
  };
}

describe("initial state", () => {
  let dom;
  beforeEach(() => {
    dom = setUp();
  });

  test("the drawer starts closed, with a toggle the script built", () => {
    expect(dom.toggle).not.toBeNull();
    expect(dom.isOpen()).toBe(false);
    expect(dom.toggle.getAttribute("aria-expanded")).toBe("false");
    expect(dom.toggle.getAttribute("aria-label")).toBe("Open navigation menu");
  });

  test("the toggle is the brand mark, and carries no glyph markup of its own", () => {
    /* The button *is* the brand mark: the glyph and the block of indigo both
       come from `.weaver-brand-mark` in weaver/chrome.css. Before that it
       carried a Font Awesome `<i>`, which rendered as an empty box once the
       CDN went away — visible on the page and invisible to a test that only
       checked the toggle existed. The class is assigned at runtime, so a
       source grep would not catch its loss either. */
    expect(dom.toggle.className).toBe("weaver-brand-mark");
    expect(dom.toggle.querySelector("i")).toBeNull();
    expect(dom.toggle.querySelector("svg")).toBeNull();
    expect(dom.toggle.innerHTML.trim()).toBe("");
    expect(dom.toggle.textContent.trim()).toBe("");
  });

  test("the toggle points at the nav it controls, naming it if need be", () => {
    expect(dom.nav.id).toBe("sidebar-nav");
    expect(dom.toggle.getAttribute("aria-controls")).toBe("sidebar-nav");
  });

  test("the root element advertises that the drawer is available", () => {
    expect(dom.document.documentElement.classList.contains("has-mobile-nav")).toBe(true);
  });

  test("a backdrop is inserted after the sidebar", () => {
    expect(dom.backdrop).not.toBeNull();
    expect(dom.sidebar.nextSibling).toBe(dom.backdrop);
  });
});

describe("opening and closing", () => {
  let dom;
  beforeEach(() => {
    dom = setUp();
  });

  test("the toggle opens the drawer and updates its ARIA state and label", () => {
    click(dom.window, dom.toggle);
    expect(dom.isOpen()).toBe(true);
    expect(dom.toggle.getAttribute("aria-expanded")).toBe("true");
    expect(dom.toggle.getAttribute("aria-label")).toBe("Close navigation menu");
  });

  test("the toggle closes it again, restoring the ARIA state and label", () => {
    click(dom.window, dom.toggle);
    click(dom.window, dom.toggle);
    expect(dom.isOpen()).toBe(false);
    expect(dom.toggle.getAttribute("aria-expanded")).toBe("false");
    expect(dom.toggle.getAttribute("aria-label")).toBe("Open navigation menu");
  });

  test("opening locks page scrolling and closing gives it back", () => {
    dom.document.body.style.overflowY = "auto";
    click(dom.window, dom.toggle);
    expect(dom.document.body.style.overflowY).toBe("hidden");
    click(dom.window, dom.toggle);
    expect(dom.document.body.style.overflowY).toBe("auto");
  });

  test("the lock never touches the horizontal axis", () => {
    // The body carries `overflow-x: hidden` as a class, and that clip is what
    // keeps the page from scrolling sideways. Locking with `style.overflow`
    // would set both axes, replacing that clip for the duration of the drawer
    // and then removing both on close. The drawer only ever needed to stop the
    // page scrolling underneath it, so it must leave the horizontal axis
    // exactly as it found it.
    //
    // Starting from no inline value is what gives the assertion teeth. Seeding
    // `overflowX = "hidden"` first made the expected value identical to the
    // seeded one, so a drawer that wrote `hidden` itself — exactly the bug this
    // guards — would have passed. Empty is a value only the drawer can spoil.
    expect(dom.document.body.style.overflowX).toBe("");
    click(dom.window, dom.toggle);
    expect(dom.document.body.style.overflowX).toBe("");
    click(dom.window, dom.toggle);
    expect(dom.document.body.style.overflowX).toBe("");
  });

  test("opening moves focus to the first item in the nav", () => {
    click(dom.window, dom.toggle);
    expect(dom.document.activeElement.getAttribute("href")).toBe("/install");
  });

  test("the backdrop closes the drawer", () => {
    click(dom.window, dom.toggle);
    click(dom.window, dom.backdrop);
    expect(dom.isOpen()).toBe(false);
  });

  test("choosing a nav link closes the drawer", () => {
    click(dom.window, dom.toggle);
    click(dom.window, dom.nav.querySelector('a[href="/docs"]'));
    expect(dom.isOpen()).toBe(false);
  });

  test("Escape closes the drawer and returns focus to the toggle", () => {
    dom.toggle.focus();
    click(dom.window, dom.toggle);
    expect(dom.document.activeElement).not.toBe(dom.toggle);
    pressKey(dom.window, dom.document.body, "Escape");
    expect(dom.isOpen()).toBe(false);
    expect(dom.document.activeElement).toBe(dom.toggle);
  });

  /* The two tests below are the only ones that can tell the restore apart
     from its fallback. Everywhere else in this file the drawer is opened
     either with nothing focused — so the saved element is `<body>`, which the
     restore declines — or with the toggle focused, which is what it falls
     back to anyway. Both paths converge on the toggle, so `isConnected` could
     be deleted from mobile-nav.js and the rest of the suite would stay green. */
  test("closing returns focus to whatever held it before opening", () => {
    const outside = dom.document.getElementById("outside");
    outside.focus();
    click(dom.window, dom.toggle);
    expect(dom.document.activeElement).not.toBe(outside);

    pressKey(dom.window, dom.document.body, "Escape");
    expect(dom.isOpen()).toBe(false);
    expect(dom.document.activeElement).toBe(outside);
  });

  test("a saved element removed while open gives the toggle the focus", () => {
    const outside = dom.document.getElementById("outside");
    outside.focus();
    click(dom.window, dom.toggle);

    // Whatever held focus is gone by the time the drawer closes — a route
    // change, or a menu that unmounted behind the backdrop. Focusing it would
    // put the caret nowhere, so the toggle takes it instead.
    outside.remove();
    expect(outside.isConnected).toBe(false);

    pressKey(dom.window, dom.document.body, "Escape");
    expect(dom.isOpen()).toBe(false);
    expect(dom.document.activeElement).toBe(dom.toggle);
  });

  test("Escape is ignored while the drawer is closed", () => {
    dom.document.getElementById("outside").focus();
    pressKey(dom.window, dom.document.body, "Escape");
    expect(dom.isOpen()).toBe(false);
    expect(dom.document.activeElement.id).toBe("outside");
  });

  test("widening past the breakpoint closes an open drawer", () => {
    click(dom.window, dom.toggle);
    dom.media.cross(true);
    expect(dom.isOpen()).toBe(false);
    expect(dom.document.body.style.overflow).toBe("");
  });

  test("a breakpoint crossing leaves a closed drawer alone", () => {
    dom.media.cross(true);
    expect(dom.isOpen()).toBe(false);
    expect(dom.toggle.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("focus trap with a populated nav", () => {
  let dom;
  let first;
  let last;
  beforeEach(() => {
    dom = setUp();
    click(dom.window, dom.toggle);
    const items = dom.nav.querySelectorAll("a[href]");
    first = items[0];
    last = items[items.length - 1];
  });

  test("Tab from the last item wraps to the toggle", () => {
    last.focus();
    const event = pressKey(dom.window, last, "Tab");
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(dom.toggle);
  });

  test("Shift+Tab from the first item wraps to the last", () => {
    first.focus();
    const event = pressKey(dom.window, first, "Tab", { shiftKey: true });
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(last);
  });

  test("Tab from the toggle enters the nav at the first item", () => {
    dom.toggle.focus();
    const event = pressKey(dom.window, dom.toggle, "Tab");
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(first);
  });

  test("Shift+Tab from the toggle wraps back to the last item", () => {
    dom.toggle.focus();
    const event = pressKey(dom.window, dom.toggle, "Tab", { shiftKey: true });
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(last);
  });

  test("Tab in the middle of the nav is left to the browser", () => {
    first.focus();
    const event = pressKey(dom.window, first, "Tab");
    expect(event.defaultPrevented).toBe(false);
  });

  test("the trap is lifted once the drawer closes", () => {
    last.focus();
    click(dom.window, dom.toggle);
    const event = pressKey(dom.window, dom.document.body, "Tab");
    expect(event.defaultPrevented).toBe(false);
  });
});

describe("focus trap with nothing focusable in the nav", () => {
  let dom;
  beforeEach(() => {
    dom = setUp({ links: [] });
    click(dom.window, dom.toggle);
  });

  test("opening falls back to focusing the nav itself", () => {
    expect(dom.document.activeElement).toBe(dom.nav);
    expect(dom.nav.getAttribute("tabindex")).toBe("-1");
  });

  test("Tab moves from the nav to the toggle rather than out of the drawer", () => {
    const event = pressKey(dom.window, dom.nav, "Tab");
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(dom.toggle);
  });

  test("Tab from the toggle returns to the nav, so focus cycles", () => {
    dom.toggle.focus();
    const event = pressKey(dom.window, dom.toggle, "Tab");
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(dom.nav);
  });

  test("Shift+Tab is trapped just as Tab is", () => {
    const event = pressKey(dom.window, dom.nav, "Tab", { shiftKey: true });
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(dom.toggle);
  });

  test("focus never reaches the page behind the drawer", () => {
    const outside = dom.document.getElementById("outside");
    for (let i = 0; i < 6; i += 1) {
      pressKey(dom.window, dom.document.activeElement, "Tab");
      expect(dom.document.activeElement).not.toBe(outside);
    }
  });
});

describe("bounded navigation state machine", () => {
  const menuSizes = [0, 1, 3, 6];
  /* Every trace up to this length, not a sample of them — see the harness for
     why exhaustive enumeration suits a state machine this small better than a
     generator library would. */
  const sequences = exhaustiveTransitionSequences({ depth: 4 });

  for (const menuSize of menuSizes) {
    test(`preserves state and focus invariants with ${menuSize} nav items`, () => {
      const links = Array.from({ length: menuSize }, (_, index) => `/item-${index}`);

      for (const sequence of sequences) {
        const dom = setUp({ links });
        const outside = dom.document.getElementById("outside");
        const navItems = [...dom.nav.querySelectorAll("a[href]")];
        const focusCycle = [outside, dom.toggle, ...navItems];
        const trappedFocus = new Set([dom.toggle, ...(navItems.length ? navItems : [dom.nav])]);
        let expectedOpen = false;

        for (const transition of sequence) {
          if (transition === "toggle") {
            click(dom.window, dom.toggle);
            expectedOpen = !expectedOpen;
          } else if (transition === "tab" || transition === "shift-tab") {
            pressTab(dom.window, focusCycle, { shiftKey: transition === "shift-tab" });
          } else if (transition === "escape") {
            pressKey(dom.window, dom.document.activeElement, "Escape");
            expectedOpen = false;
          } else if (transition === "wide") {
            dom.media.cross(true);
            expectedOpen = false;
          } else {
            dom.media.cross(false);
          }

          expect(dom.isOpen()).toBe(expectedOpen);
          expect(dom.toggle.getAttribute("aria-expanded")).toBe(String(expectedOpen));
          expect(dom.toggle.getAttribute("aria-label")).toBe(
            expectedOpen ? "Close navigation menu" : "Open navigation menu",
          );
          if (expectedOpen) expect(trappedFocus.has(dom.document.activeElement)).toBe(true);
        }
      }
    });
  }
});

describe("markup the drawer declines to enhance", () => {
  test("a page with no sidebar is left untouched", () => {
    const window = new Window({ url: "https://weaver.example/" });
    window.document.body.innerHTML = "<main>No sidebar here</main>";
    stubLayout(window);
    installMatchMedia(window);
    evaluateScript(window, SCRIPT);
    expect(window.document.getElementById("mobile-nav-toggle")).toBeNull();
    expect(window.document.documentElement.classList.contains("has-mobile-nav")).toBe(false);
  });

  test("a sidebar with no header is left untouched", () => {
    const window = new Window({ url: "https://weaver.example/" });
    window.document.body.innerHTML = '<aside id="sidebar"><nav><a href="/a">A</a></nav></aside>';
    stubLayout(window);
    installMatchMedia(window);
    evaluateScript(window, SCRIPT);
    expect(window.document.getElementById("mobile-nav-toggle")).toBeNull();
  });
});

afterEach(() => {
  /* `telemetry.js` and the sink both live on the process global while a test
     runs, since that is where `evaluateScript` puts a script's `globalThis`.
     Leaving them there would let one test's sink collect another's events. */
  globalThis.df12WeaverNavTelemetry = undefined;
  globalThis.df12WeaverTelemetry = undefined;
  globalThis.df12WeaverCopy = undefined;
});

describe("telemetry", () => {
  test("says nothing at all when the page did not load the hook", () => {
    /* A sink is installed; `telemetry.js` is not. The drawer has nothing to
       report through, so it must report nothing — and the sink is there to
       catch it if some future change reaches past the module. */
    const dom = setUp();
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
