/* Behavioural tests for the Weaver sidebar drawer.
 *
 * The drawer is modal — it installs a backdrop and locks body scrolling — so
 * the assertions that matter are about focus: that opening moves it inside,
 * that Tab cannot carry it out to the obscured page behind, and that closing
 * puts it back where it was. See `helpers/mobile-nav-harness.mjs` for why
 * these run against a real DOM rather than the fake used elsewhere.
 */
import { beforeEach, describe, expect, test } from "bun:test";
import { Window } from "happy-dom";
import {
  click,
  evaluateScript,
  generatedTransitionSequences,
  installMatchMedia,
  pressKey,
  pressTab,
  stubLayout,
} from "./helpers/mobile-nav-harness.mjs";

const SCRIPT = "public/weaver/assets/js/mobile-nav.js";

/* Build a page with the sidebar markup `templates/weaver/` renders, load the
   drawer into it, and hand back the parts a test needs to drive. */
function setUp({ links = ["/install", "/docs"] } = {}) {
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
    dom.document.body.style.overflowX = "hidden";
    click(dom.window, dom.toggle);
    expect(dom.document.body.style.overflowX).toBe("hidden");
    click(dom.window, dom.toggle);
    expect(dom.document.body.style.overflowX).toBe("hidden");
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
  const sequences = generatedTransitionSequences(1217);

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
