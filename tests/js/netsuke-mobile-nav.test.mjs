/* Behavioural tests for the Netsuke navbar menu.
 *
 * This menu is a dropdown, not a modal: it neither dims the page nor locks
 * scrolling, and a click anywhere outside it closes it. Focus is still cycled
 * between the toggle and the menu's items while it is open, which is what
 * most of these assertions are about. See `helpers/mobile-nav-harness.mjs`
 * for why they run against a real DOM.
 */
import { beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
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

const SCRIPT = "public/netsuke/assets/js/mobile-nav.js";
const PAGE = "https://netsuke.example/docs/";
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const RENDERED_PAGES = [
  ["homepage", "public/netsuke/index.html"],
  ["documentation page", "public/netsuke/docs/index.html"],
];

beforeAll(() => {
  const result = spawnSync("uv", ["run", "pages", "generate", "--site", "netsuke"], {
    cwd: REPO_ROOT,
    encoding: "utf8",
  });
  expect(`${result.stdout ?? ""}${result.stderr ?? ""}`).not.toContain("Traceback");
  expect(result.status).toBe(0);
});

/* Build a page with the navbar markup `templates/netsuke/` renders, load the
   menu into it, and hand back the parts a test needs to drive. */
function setUp({
  items = ['<a href="/docs/">Docs</a>', '<a href="/examples/">Examples</a>'],
} = {}) {
  const window = new Window({ url: PAGE });
  const { document } = window;
  document.body.innerHTML = `
    <a href="/elsewhere" id="outside">Outside</a>
    <nav id="navbar" data-mobile-nav>
      <button
        id="navbar-mobile-toggle"
        data-mobile-nav-toggle
        class="hidden"
        aria-expanded="false"
        aria-controls="navbar-mobile-menu"
        aria-label="Open menu"
      >
        <span class="hm-hamburger__open"></span>
        <span class="hm-hamburger__close"></span>
      </button>
      <div id="navbar-mobile-menu" data-mobile-nav-menu>${items.join("")}</div>
    </nav>`;
  stubLayout(window);
  const media = installMatchMedia(window);
  evaluateScript(window, SCRIPT);

  const menu = document.querySelector("[data-mobile-nav-menu]");
  return {
    window,
    document,
    media,
    menu,
    toggle: document.querySelector("[data-mobile-nav-toggle]"),
    isOpen: () => menu.classList.contains("is-open"),
  };
}

describe("initial state", () => {
  let dom;
  beforeEach(() => {
    dom = setUp();
  });

  test("the menu starts collapsed, with its ARIA state closed", () => {
    expect(dom.isOpen()).toBe(false);
    expect(dom.toggle.getAttribute("aria-expanded")).toBe("false");
    expect(dom.toggle.getAttribute("aria-label")).toBe("Open menu");
  });

  test("the toggle is revealed, since script is evidently running", () => {
    expect(dom.toggle.classList.contains("hidden")).toBe(false);
  });

  test("markup rendered open as a no-JS fallback is collapsed at once", () => {
    const dom2 = setUp();
    expect(dom2.menu.classList.contains("hidden")).toBe(true);
  });
});

describe("opening and closing", () => {
  let dom;
  beforeEach(() => {
    dom = setUp();
  });

  test("the toggle opens the menu and updates its ARIA state and label", () => {
    click(dom.window, dom.toggle);
    expect(dom.isOpen()).toBe(true);
    expect(dom.toggle.getAttribute("aria-expanded")).toBe("true");
    expect(dom.toggle.getAttribute("aria-label")).toBe("Close menu");
  });

  test("the toggle closes it again, restoring the ARIA state and label", () => {
    click(dom.window, dom.toggle);
    click(dom.window, dom.toggle);
    expect(dom.isOpen()).toBe(false);
    expect(dom.toggle.getAttribute("aria-expanded")).toBe("false");
    expect(dom.toggle.getAttribute("aria-label")).toBe("Open menu");
  });

  test("the hamburger and close icons swap over", () => {
    const open = dom.toggle.querySelector(".hm-hamburger__open");
    const shut = dom.toggle.querySelector(".hm-hamburger__close");
    click(dom.window, dom.toggle);
    expect(open.style.display).toBe("none");
    expect(shut.style.display).toBe("");
    click(dom.window, dom.toggle);
    expect(open.style.display).toBe("");
    expect(shut.style.display).toBe("none");
  });

  test("opening moves focus to the first item in the menu", () => {
    click(dom.window, dom.toggle);
    expect(dom.document.activeElement.getAttribute("href")).toBe("/docs/");
  });

  test("Escape closes the menu and returns focus to the toggle", () => {
    click(dom.window, dom.toggle);
    pressKey(dom.window, dom.document.body, "Escape");
    expect(dom.isOpen()).toBe(false);
    expect(dom.document.activeElement).toBe(dom.toggle);
  });

  test("Escape is ignored while the menu is closed", () => {
    dom.document.getElementById("outside").focus();
    pressKey(dom.window, dom.document.body, "Escape");
    expect(dom.isOpen()).toBe(false);
    expect(dom.document.activeElement.id).toBe("outside");
  });

  test("a click outside the navbar and the menu closes it", () => {
    click(dom.window, dom.toggle);
    click(dom.window, dom.document.getElementById("outside"));
    expect(dom.isOpen()).toBe(false);
  });

  test("a click inside the menu does not close it by itself", () => {
    click(dom.window, dom.toggle);
    click(dom.window, dom.menu);
    expect(dom.isOpen()).toBe(true);
  });

  test("widening past the breakpoint closes an open menu", () => {
    click(dom.window, dom.toggle);
    dom.media.cross(true);
    expect(dom.isOpen()).toBe(false);
    expect(dom.menu.classList.contains("hidden")).toBe(true);
  });
});

describe("choosing a link", () => {
  test("a same-page anchor closes the menu, since nothing navigates", () => {
    const dom = setUp({ items: ['<a href="#install">Install</a>'] });
    click(dom.window, dom.toggle);
    click(dom.window, dom.menu.querySelector("a"));
    expect(dom.isOpen()).toBe(false);
  });

  test("a link to another page leaves the menu to the navigation", () => {
    const dom = setUp({ items: ['<a href="/examples/">Examples</a>'] });
    click(dom.window, dom.toggle);
    click(dom.window, dom.menu.querySelector("a"));
    expect(dom.isOpen()).toBe(true);
  });
});

describe("focus trap with a populated menu", () => {
  let dom;
  let first;
  let last;
  beforeEach(() => {
    dom = setUp();
    click(dom.window, dom.toggle);
    const items = dom.menu.querySelectorAll("a[href]");
    first = items[0];
    last = items[items.length - 1];
  });

  test("Tab from the last item wraps to the first", () => {
    last.focus();
    const event = pressKey(dom.window, last, "Tab");
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(first);
  });

  test("Shift+Tab from the first item wraps to the last", () => {
    first.focus();
    const event = pressKey(dom.window, first, "Tab", { shiftKey: true });
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(last);
  });

  test("Tab from the toggle enters the menu at the first item", () => {
    dom.toggle.focus();
    const event = pressKey(dom.window, dom.toggle, "Tab");
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(first);
  });

  test("Shift+Tab from the toggle enters the menu at the last item", () => {
    dom.toggle.focus();
    const event = pressKey(dom.window, dom.toggle, "Tab", { shiftKey: true });
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(last);
  });

  test("the trap does not act while the menu is closed", () => {
    click(dom.window, dom.toggle);
    dom.toggle.focus();
    const event = pressKey(dom.window, dom.toggle, "Tab");
    expect(event.defaultPrevented).toBe(false);
  });
});

describe("focus trap with nothing focusable in the menu", () => {
  let dom;
  beforeEach(() => {
    dom = setUp({ items: ["<p>Nothing to choose from</p>"] });
    click(dom.window, dom.toggle);
  });

  test("opening falls back to focusing the menu itself", () => {
    expect(dom.document.activeElement).toBe(dom.menu);
    expect(dom.menu.getAttribute("tabindex")).toBe("-1");
  });

  test("Tab hands focus back to the toggle rather than out of the menu", () => {
    const event = pressKey(dom.window, dom.menu, "Tab");
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(dom.toggle);
  });

  test("Tab from the toggle returns to the menu, so focus cycles", () => {
    dom.toggle.focus();
    const event = pressKey(dom.window, dom.toggle, "Tab");
    expect(event.defaultPrevented).toBe(true);
    expect(dom.document.activeElement).toBe(dom.menu);
  });

  test("focus never reaches the page outside the open menu", () => {
    const outside = dom.document.getElementById("outside");
    for (let i = 0; i < 6; i += 1) {
      pressKey(dom.window, dom.document.activeElement, "Tab");
      expect(dom.document.activeElement).not.toBe(outside);
    }
  });
});

describe("bounded navigation state machine", () => {
  const menuSizes = [0, 1, 3, 6];
  const sequences = generatedTransitionSequences(1201);

  for (const menuSize of menuSizes) {
    test(`preserves state and focus invariants with ${menuSize} menu items`, () => {
      const items = Array.from(
        { length: menuSize },
        (_, index) => `<a href="/item-${index}/">Item ${index}</a>`,
      );

      for (const sequence of sequences) {
        const dom = setUp({ items });
        const outside = dom.document.getElementById("outside");
        const menuItems = [...dom.menu.querySelectorAll("a[href]")];
        const focusCycle = [outside, dom.toggle, ...menuItems];
        const trappedFocus = new Set([dom.toggle, ...(menuItems.length ? menuItems : [dom.menu])]);
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
            expectedOpen ? "Close menu" : "Open menu",
          );
          if (expectedOpen) expect(trappedFocus.has(dom.document.activeElement)).toBe(true);
        }
      }
    });
  }
});

describe("the markup contract", () => {
  for (const [name, relativePath] of RENDERED_PAGES) {
    test(`the real ${name} renders every data hook the shipped script needs`, () => {
      const window = new Window({ url: PAGE });
      window.document.documentElement.innerHTML = readFileSync(
        join(REPO_ROOT, relativePath),
        "utf8",
      );
      const root = window.document.querySelector("[data-mobile-nav]");
      const toggle = root?.querySelector("[data-mobile-nav-toggle]");
      const menu = root?.querySelector("[data-mobile-nav-menu]");

      expect(root).not.toBeNull();
      expect(toggle).not.toBeNull();
      expect(menu).not.toBeNull();

      stubLayout(window);
      installMatchMedia(window);
      evaluateScript(window, SCRIPT);
      expect(toggle.classList.contains("hidden")).toBe(false);
      click(window, toggle);
      expect(menu.classList.contains("is-open")).toBe(true);
    });
  }

  test("is the data attributes alone, so markup carrying no ids still works", () => {
    const window = new Window({ url: PAGE });
    window.document.body.innerHTML = `
      <nav data-mobile-nav>
        <button data-mobile-nav-toggle class="hidden" aria-expanded="false" aria-label="Open menu"></button>
        <div data-mobile-nav-menu><a href="/docs/">Docs</a></div>
      </nav>`;
    stubLayout(window);
    installMatchMedia(window);
    evaluateScript(window, SCRIPT);

    const toggle = window.document.querySelector("[data-mobile-nav-toggle]");
    const menu = window.document.querySelector("[data-mobile-nav-menu]");
    expect(toggle.classList.contains("hidden")).toBe(false);
    click(window, toggle);
    expect(menu.classList.contains("is-open")).toBe(true);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
  });

  test("initializes every root and keeps each toggle scoped to its own menu", () => {
    const window = new Window({ url: PAGE });
    window.document.body.innerHTML = `
      <nav data-mobile-nav id="first">
        <button data-mobile-nav-toggle class="hidden"></button>
        <div data-mobile-nav-menu><a href="/a/">A</a></div>
      </nav>
      <nav data-mobile-nav id="second">
        <button data-mobile-nav-toggle class="hidden"></button>
        <div data-mobile-nav-menu><a href="/b/">B</a></div>
      </nav>`;
    stubLayout(window);
    installMatchMedia(window);
    evaluateScript(window, SCRIPT);

    const first = window.document.getElementById("first");
    const second = window.document.getElementById("second");
    const firstToggle = first.querySelector("[data-mobile-nav-toggle]");
    const secondToggle = second.querySelector("[data-mobile-nav-toggle]");
    const firstMenu = first.querySelector("[data-mobile-nav-menu]");
    const secondMenu = second.querySelector("[data-mobile-nav-menu]");

    expect(firstToggle.classList.contains("hidden")).toBe(false);
    expect(secondToggle.classList.contains("hidden")).toBe(false);

    click(window, firstToggle);
    expect(firstMenu.classList.contains("is-open")).toBe(true);
    expect(secondMenu.classList.contains("is-open")).toBe(false);

    click(window, firstToggle);
    click(window, secondToggle);
    expect(firstMenu.classList.contains("is-open")).toBe(false);
    expect(secondMenu.classList.contains("is-open")).toBe(true);
  });
});

describe("markup the menu declines to enhance", () => {
  test("a page missing the menu pane is left untouched", () => {
    const window = new Window({ url: PAGE });
    window.document.body.innerHTML =
      '<nav id="navbar" data-mobile-nav><button data-mobile-nav-toggle class="hidden"></button></nav>';
    stubLayout(window);
    installMatchMedia(window);
    evaluateScript(window, SCRIPT);
    expect(
      window.document.querySelector("[data-mobile-nav-toggle]").classList.contains("hidden"),
    ).toBe(true);
  });
});
