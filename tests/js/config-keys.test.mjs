/* Tests for the config-keys component.
 *
 * `nextTabIndex` is the pure decision behind the narrow-viewport
 * tablist: given the selected tab, the key pressed, and how many tabs
 * there are, it returns the tab to move to, or -1 for a key the widget
 * should leave to the browser.
 *
 * `createConfigKeys` is the component proper. It takes its `document`
 * and `matchMedia` as injected dependencies, in the same shape
 * `copy-buttons.js` uses, so these tests drive it with the minimal fake
 * DOM below rather than a browser engine. The lifecycle assertions
 * cover what the component actually risks getting wrong: the ARIA it
 * swaps between modes, which panel is visible, where each paragraph
 * lives, and whether a breakpoint crossing puts it all back.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { createConfigKeys, nextTabIndex } = require("../../public/netsuke/assets/js/config-keys.js");

const COUNT = 3;
const KEYS = ["build", "output", "network"];

/* A DOM node with just enough behaviour for this component: attributes,
   classes, children with a real parent link, and event listeners that
   tests can fire directly. */
function el(tag, attrs = {}) {
  const node = {
    tagName: tag.toUpperCase(),
    children: [],
    parentNode: null,
    listeners: new Map(),
    attrs: new Map(Object.entries(attrs)),
    id: attrs.id ?? "",
    className: attrs.class ?? "",
    textContent: "",
    hidden: false,
    tabIndex: 0,
    focused: false,
    classes: new Set((attrs.class ?? "").split(" ").filter(Boolean)),
    setAttribute(name, value) {
      node.attrs.set(name, String(value));
    },
    getAttribute(name) {
      return node.attrs.has(name) ? node.attrs.get(name) : null;
    },
    removeAttribute(name) {
      node.attrs.delete(name);
    },
    focus() {
      node.focused = true;
    },
    addEventListener(type, fn) {
      if (!node.listeners.has(type)) node.listeners.set(type, []);
      node.listeners.get(type).push(fn);
    },
    fire(type, event = {}) {
      for (const fn of node.listeners.get(type) ?? []) fn(event);
    },
    append(child) {
      if (child.parentNode) child.parentNode.remove(child);
      child.parentNode = node;
      node.children.push(child);
    },
    appendChild(child) {
      node.append(child);
    },
    remove(child) {
      const i = node.children.indexOf(child);
      if (i !== -1) node.children.splice(i, 1);
    },
    insertBefore(child, ref) {
      if (child.parentNode) child.parentNode.remove(child);
      child.parentNode = node;
      const i = node.children.indexOf(ref);
      node.children.splice(i === -1 ? node.children.length : i, 0, child);
    },
    replaceChild(fresh, stale) {
      const i = node.children.indexOf(stale);
      if (i === -1) return;
      node.children[i] = fresh;
      fresh.parentNode = node;
      stale.parentNode = null;
    },
    matches(selector) {
      const m = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(selector);
      if (!m) return false;
      if (!node.attrs.has(m[1])) return false;
      return m[2] === undefined || node.attrs.get(m[1]) === m[2];
    },
    descendants() {
      return node.children.flatMap((c) => [c, ...c.descendants()]);
    },
    querySelectorAll(selector) {
      return node.descendants().filter((c) => c.matches(selector));
    },
    querySelector(selector) {
      return node.querySelectorAll(selector)[0] ?? null;
    },
  };
  node.classList = {
    add: (n) => node.classes.add(n),
    remove: (n) => node.classes.delete(n),
    contains: (n) => node.classes.has(n),
    toggle: (n, force) => (force ? node.classes.add(n) : node.classes.delete(n)),
  };
  return node;
}

/* A document stand-in exposing only what the component reaches for:
   element creation, a body to append the live region to, and query methods
   over the mounted tree. */
function fakeDocument() {
  return { createElement: (tag) => el(tag) };
}

/* A matchMedia whose result the test flips, then re-applies through the
   controller — the component listens for a `change` event in the
   browser, which this stands in for. */
function fakeMedia(matches) {
  return {
    matches,
    addEventListener() {},
    addListener() {},
  };
}

/* The markup the configuration page emits, reduced to what the
   component reads. */
function buildRoot({ omitLabelFor = null, panels = KEYS } = {}) {
  const root = el("div", { "data-config-keys": "" });
  const labels = el("div", { "data-config-keys-labels": "" });
  const panelList = el("div", { "data-config-keys-panels": "" });
  root.append(labels);
  root.append(panelList);

  for (const key of KEYS) {
    const wrapper = el("div", { "data-config-keys-key": key });
    if (key !== omitLabelFor) {
      const span = el("span", {
        "data-config-keys-label": key,
        id: `label-${key}`,
        class: "hm-config-keys__label",
      });
      span.textContent = key;
      wrapper.append(span);
    }
    const note = el("p", { "data-config-keys-note": key, id: `note-${key}` });
    wrapper.append(note);
    labels.append(wrapper);
  }
  for (const key of panels) {
    panelList.append(el("div", { "data-config-keys-panel": key, id: `panel-${key}` }));
  }
  return { root, labels, panelList };
}

/* Build the markup the component expects and hand back the root plus the
   handles a test needs to assert on it. */
function mount(matches, options) {
  const { root, labels, panelList } = buildRoot(options);
  const media = fakeMedia(matches);
  const controller = createConfigKeys(root, {
    document: fakeDocument(),
    matchMedia: () => media,
  });
  const find = (sel) => root.querySelectorAll(sel);
  return {
    root,
    labels,
    panelList,
    media,
    controller,
    tabs: () => find("[data-config-keys-label]"),
    panels: () => find("[data-config-keys-panel]"),
    notes: () => find("[data-config-keys-note]"),
  };
}

describe("nextTabIndex", () => {
  test("Right and Down both advance", () => {
    expect(nextTabIndex(0, "ArrowRight", COUNT)).toBe(1);
    expect(nextTabIndex(0, "ArrowDown", COUNT)).toBe(1);
  });

  test("Left and Up both retreat", () => {
    expect(nextTabIndex(2, "ArrowLeft", COUNT)).toBe(1);
    expect(nextTabIndex(2, "ArrowUp", COUNT)).toBe(1);
  });

  test("advancing past the last tab wraps to the first", () => {
    expect(nextTabIndex(COUNT - 1, "ArrowRight", COUNT)).toBe(0);
  });

  test("retreating from the first tab wraps to the last", () => {
    expect(nextTabIndex(0, "ArrowLeft", COUNT)).toBe(COUNT - 1);
  });

  test("Home and End jump to the ends", () => {
    expect(nextTabIndex(1, "Home", COUNT)).toBe(0);
    expect(nextTabIndex(1, "End", COUNT)).toBe(COUNT - 1);
  });

  test("keys the widget does not own are left alone", () => {
    // -1 tells the handler not to preventDefault, so Tab still moves
    // focus out of the strip and typing still reaches the page.
    expect(nextTabIndex(0, "Tab", COUNT)).toBe(-1);
    expect(nextTabIndex(0, "Enter", COUNT)).toBe(-1);
    expect(nextTabIndex(0, "a", COUNT)).toBe(-1);
  });

  test("an empty strip has nowhere to move", () => {
    expect(nextTabIndex(0, "ArrowRight", 0)).toBe(-1);
    expect(nextTabIndex(0, "Home", 0)).toBe(-1);
  });

  test("a single tab always resolves to itself", () => {
    expect(nextTabIndex(0, "ArrowRight", 1)).toBe(0);
    expect(nextTabIndex(0, "ArrowLeft", 1)).toBe(0);
  });

  test("an unmarked wide-mode state still advances into range", () => {
    // Wide mode can clear the mark (selected = -1); crossing to narrow
    // must not leave the arrow keys computing a negative index.
    expect(nextTabIndex(-1, "ArrowRight", COUNT)).toBe(0);
    expect(nextTabIndex(-1, "ArrowLeft", COUNT)).toBe(COUNT - 1);
  });
});

describe("createConfigKeys: contract", () => {
  test("a group whose markup satisfies the contract is upgraded", () => {
    const ui = mount(false);
    expect(ui.controller).not.toBeNull();
    expect(ui.root.classList.contains("is-enhanced")).toBe(true);
  });

  test("a key missing its label leaves the markup untouched", () => {
    // Bailing late would leave a half-upgraded group, which reads
    // worse than one the script never reached.
    const ui = mount(false, { omitLabelFor: "output" });
    expect(ui.controller).toBeNull();
    expect(ui.root.classList.contains("is-enhanced")).toBe(false);
    expect(ui.labels.getAttribute("role")).toBeNull();
    expect(ui.panels().every((p) => p.hidden === false)).toBe(true);
    expect(
      ui.notes().every((n) => n.parentNode.getAttribute("data-config-keys-key") !== null),
    ).toBe(true);
  });

  test("a panel count that does not match the keys is refused", () => {
    const ui = mount(false, { panels: ["build", "output"] });
    expect(ui.controller).toBeNull();
    expect(ui.root.classList.contains("is-enhanced")).toBe(false);
  });
});

describe("createConfigKeys: narrow mode", () => {
  test("the labels become a tablist of buttons", () => {
    const ui = mount(false);
    expect(ui.labels.getAttribute("role")).toBe("tablist");
    const tabs = ui.tabs();
    expect(tabs.map((t) => t.tagName)).toEqual(["BUTTON", "BUTTON", "BUTTON"]);
    expect(tabs.map((t) => t.getAttribute("role"))).toEqual(["tab", "tab", "tab"]);
    expect(tabs.map((t) => t.getAttribute("aria-controls"))).toEqual([
      "panel-build",
      "panel-output",
      "panel-network",
    ]);
  });

  test("exactly one tab is selected and reachable", () => {
    const ui = mount(false);
    expect(ui.tabs().map((t) => t.getAttribute("aria-selected"))).toEqual([
      "true",
      "false",
      "false",
    ]);
    expect(ui.tabs().map((t) => t.tabIndex)).toEqual([0, -1, -1]);
  });

  test("only the selected panel is shown, and its note moves above it", () => {
    const ui = mount(false);
    expect(ui.panels().map((p) => p.hidden)).toEqual([false, true, true]);
    expect(ui.notes().map((n) => n.hidden)).toEqual([false, true, true]);
    // Each note now sits in the panels column, describing its panel.
    expect(ui.notes().every((n) => n.parentNode === ui.panelList)).toBe(true);
    expect(ui.panels().map((p) => p.getAttribute("aria-describedby"))).toEqual([
      "note-build",
      "note-output",
      "note-network",
    ]);
  });

  test("clicking a tab moves the selection and the visible panel", () => {
    const ui = mount(false);
    ui.tabs()[2].fire("click");
    expect(ui.tabs().map((t) => t.getAttribute("aria-selected"))).toEqual([
      "false",
      "false",
      "true",
    ]);
    expect(ui.panels().map((p) => p.hidden)).toEqual([true, true, false]);
    expect(ui.notes().map((n) => n.hidden)).toEqual([true, true, false]);
  });

  test("an arrow key moves the selection and takes focus with it", () => {
    const ui = mount(false);
    let defaultPrevented = false;
    ui.labels.fire("keydown", {
      key: "ArrowRight",
      preventDefault: () => {
        defaultPrevented = true;
      },
    });
    expect(defaultPrevented).toBe(true);
    expect(ui.tabs()[1].getAttribute("aria-selected")).toBe("true");
    expect(ui.tabs()[1].focused).toBe(true);
    expect(ui.tabs()[1].tabIndex).toBe(0);
  });

  test("a key the widget does not own is left to the browser", () => {
    const ui = mount(false);
    let defaultPrevented = false;
    ui.labels.fire("keydown", {
      key: "Tab",
      preventDefault: () => {
        defaultPrevented = true;
      },
    });
    expect(defaultPrevented).toBe(false);
    expect(ui.tabs()[0].getAttribute("aria-selected")).toBe("true");
  });
});

describe("createConfigKeys: wide mode", () => {
  test("the labels stay inert text and every panel is shown", () => {
    const ui = mount(true);
    expect(ui.labels.getAttribute("role")).toBe("group");
    const tabs = ui.tabs();
    expect(tabs.map((t) => t.tagName)).toEqual(["SPAN", "SPAN", "SPAN"]);
    expect(tabs.every((t) => t.getAttribute("role") === null)).toBe(true);
    expect(ui.panels().map((p) => p.hidden)).toEqual([false, false, false]);
    expect(ui.panels().map((p) => p.getAttribute("role"))).toEqual(["group", "group", "group"]);
  });

  test("each note stays beside its label, and nothing is marked", () => {
    const ui = mount(true);
    expect(
      ui.notes().every((n) => n.parentNode.getAttribute("data-config-keys-key") !== null),
    ).toBe(true);
    expect(ui.notes().every((n) => n.hidden === false)).toBe(true);
    expect(ui.panels().every((p) => p.classList.contains("is-active"))).toBe(false);
  });

  test("no panel claims a description it no longer sits beside", () => {
    const ui = mount(true);
    expect(ui.panels().every((p) => p.getAttribute("aria-describedby") === null)).toBe(true);
  });
});

describe("createConfigKeys: crossing the breakpoint", () => {
  test("narrow to wide restores the spans, the notes, and every panel", () => {
    const ui = mount(false);
    expect(ui.tabs()[0].tagName).toBe("BUTTON");

    ui.media.matches = true;
    ui.controller.applyMode();

    expect(ui.labels.getAttribute("role")).toBe("group");
    expect(ui.tabs().map((t) => t.tagName)).toEqual(["SPAN", "SPAN", "SPAN"]);
    expect(ui.panels().every((p) => p.hidden === false)).toBe(true);
    expect(
      ui.notes().every((n) => n.parentNode.getAttribute("data-config-keys-key") !== null),
    ).toBe(true);
    expect(ui.panels().every((p) => p.getAttribute("aria-describedby") === null)).toBe(true);
  });

  test("wide to narrow rebuilds a tablist with one tab selected", () => {
    const ui = mount(true);

    ui.media.matches = false;
    ui.controller.applyMode();

    expect(ui.labels.getAttribute("role")).toBe("tablist");
    expect(ui.tabs().map((t) => t.tagName)).toEqual(["BUTTON", "BUTTON", "BUTTON"]);
    expect(ui.tabs().map((t) => t.getAttribute("aria-selected"))).toEqual([
      "true",
      "false",
      "false",
    ]);
    expect(ui.panels().map((p) => p.hidden)).toEqual([false, true, true]);
    expect(ui.notes().every((n) => n.parentNode === ui.panelList)).toBe(true);
  });

  test("a selection made narrow does not survive as a stale mark wide", () => {
    const ui = mount(false);
    ui.tabs()[2].fire("click");

    ui.media.matches = true;
    ui.controller.applyMode();

    expect(ui.panels().every((p) => p.classList.contains("is-active"))).toBe(false);
    expect(ui.panels().every((p) => p.hidden === false)).toBe(true);
  });
});
