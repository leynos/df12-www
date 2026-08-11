/* Behavioural tests for the Netsuke navbar menu.
 *
 * This menu is a dropdown, not a modal: it neither dims the page nor locks
 * scrolling, and a click anywhere outside it closes it. Focus is still cycled
 * between the toggle and the menu's items while it is open, which is what
 * most of these assertions are about. See `helpers/mobile-nav-harness.mjs`
 * for why they run against a real DOM.
 */
import { beforeEach, describe, expect, test } from "bun:test";
import { Window } from "happy-dom";
import {
  click,
  evaluateScript,
  installMatchMedia,
  pressKey,
  stubLayout,
} from "./helpers/mobile-nav-harness.mjs";

const SCRIPT = "public/netsuke/assets/js/mobile-nav.js";
const PAGE = "https://netsuke.example/docs/";

/* Build a page with the navbar markup `templates/netsuke/` renders, load the
   menu into it, and hand back the parts a test needs to drive. */
function setUp({
  items = ['<a href="/docs/">Docs</a>', '<a href="/examples/">Examples</a>'],
} = {}) {
  const window = new Window({ url: PAGE });
  const { document } = window;
  document.body.innerHTML = `
    <a href="/elsewhere" id="outside">Outside</a>
    <header id="navbar">
      <button id="navbar-mobile-toggle" class="hidden" aria-expanded="false" aria-label="Open menu">
        <span class="hm-hamburger__open"></span>
        <span class="hm-hamburger__close"></span>
      </button>
    </header>
    <div id="navbar-mobile-menu">${items.join("")}</div>`;
  stubLayout(window);
  const media = installMatchMedia(window);
  evaluateScript(window, SCRIPT);

  const menu = document.getElementById("navbar-mobile-menu");
  return {
    window,
    document,
    media,
    menu,
    toggle: document.getElementById("navbar-mobile-toggle"),
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

describe("markup the menu declines to enhance", () => {
  test("a page missing the menu pane is left untouched", () => {
    const window = new Window({ url: PAGE });
    window.document.body.innerHTML =
      '<header id="navbar"><button id="navbar-mobile-toggle" class="hidden"></button></header>';
    stubLayout(window);
    installMatchMedia(window);
    evaluateScript(window, SCRIPT);
    expect(
      window.document.getElementById("navbar-mobile-toggle").classList.contains("hidden"),
    ).toBe(true);
  });
});
