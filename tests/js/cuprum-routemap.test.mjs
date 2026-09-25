/**
 * @file Tests for the Cuprum route map's scroll-spy and drop-down.
 *
 * `pickActiveIndex` decides which section is being read. The DOM suite
 * mounts a route map shaped like the `routemap` macro in
 * `templates/cuprum/components.jinja` — a strip and a drop-down listing the
 * same sections — places the sections by stubbing their layout, evaluates
 * the compiled script against the global happy-dom document, and checks the
 * mark, the summary, and how the drop-down closes.
 *
 * The controller suite drives `createRouteMapController` through injected
 * fakes — a viewport whose geometry a test sets and whose scroll and resize
 * events it fires by hand, and an animation-frame queue it runs on demand —
 * so the coalescing of events into frames is counted rather than inferred.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import fc from "fast-check";

const require = createRequire(import.meta.url);
const SCRIPT = join("public", "cuprum", "assets", "js", "routemap.js");
const { pickActiveIndex, fragmentId, collectTargets, createRouteMapController } = require(
  `../../${SCRIPT}`,
);

/* happy-dom's document is shared by every test file in the process, so the
   `scrollHeight` the fixtures define is put back as it was after each test. */
const ORIGINAL_SCROLL_HEIGHT = Object.getOwnPropertyDescriptor(
  document.documentElement,
  "scrollHeight",
);

/** Restore `document.documentElement.scrollHeight` to its original definition. */
function restoreScrollHeight() {
  if (ORIGINAL_SCROLL_HEIGHT) {
    Object.defineProperty(document.documentElement, "scrollHeight", ORIGINAL_SCROLL_HEIGHT);
  } else {
    delete document.documentElement.scrollHeight;
  }
}

/* One list of links, as `_routemap_links` renders it. */
const LINKS = `
  <li><a class="cu-routemap__link" href="#problem" data-cu-routemap-link><span class="cu-routemap__num" aria-hidden="true">01</span>Problem</a></li>
  <li><a class="cu-routemap__link" href="#code" data-cu-routemap-link><span class="cu-routemap__num" aria-hidden="true">02</span>Code</a></li>
  <li><a class="cu-routemap__link" href="#output" data-cu-routemap-link><span class="cu-routemap__num" aria-hidden="true">03</span>Output</a></li>
`;

const FIXTURE = `
  <nav class="cu-routemap" aria-label="On this page" data-cu-routemap>
    <ol class="cu-routemap__list">${LINKS}</ol>
    <details class="cu-routemap__menu">
      <summary class="cu-routemap__summary"><span data-cu-routemap-current>Jump to a section</span></summary>
      <ol class="cu-routemap__menu-list">${LINKS}</ol>
    </details>
  </nav>
  <section id="problem"></section>
  <section id="code"></section>
  <section id="output"></section>
  <footer id="elsewhere">Colophon</footer>
`;

/* Stub one element's layout box; happy-dom lays nothing out itself. */
function place(el, top, bottom = top + 400) {
  el.getBoundingClientRect = () => ({ top, bottom, left: 0, right: 0, width: 0, height: 0 });
}

/* Mount the fixture with the route map's foot at 100px and the sections at
   the given tops, then run the script. */
function mount(tops) {
  document.body.innerHTML = FIXTURE;
  // A tall document, so the reader is never at its foot unless a test says so.
  Object.defineProperty(document.documentElement, "scrollHeight", {
    configurable: true,
    value: 10000,
  });
  place(document.querySelector("[data-cu-routemap]"), 60, 100);
  ["problem", "code", "output"].forEach((id, i) => {
    place(document.getElementById(id), tops[i]);
  });
  // The compiled script is a classic IIFE; evaluating it runs `init`
  // immediately because the document has finished loading.
  new Function("module", readFileSync(SCRIPT, "utf8"))(undefined);
}

/* The labels of every link currently marked, in document order. */
function marked() {
  return Array.from(document.querySelectorAll("[data-cu-routemap] [aria-current]")).map(
    (link) => link.textContent,
  );
}

/* A viewport whose geometry a test sets through `state` and whose scroll
   and resize listeners it fires by hand. Defaults to the top of a document
   far taller than the window. */
function fakeViewport() {
  const state = { scrollY: 0, innerHeight: 900, scrollHeight: 10000 };
  const listeners = { scroll: [], resize: [] };
  return {
    state,
    listeners,
    scrollY: () => state.scrollY,
    innerHeight: () => state.innerHeight,
    scrollHeight: () => state.scrollHeight,
    listen(type, listener) {
      listeners[type].push(listener);
    },
    fire(type) {
      for (const listener of listeners[type]) {
        listener();
      }
    },
  };
}

/* An animation-frame queue that runs only when a test says so, counting
   every frame requested of it. */
function fakeFrames() {
  const queue = [];
  const frames = {
    requested: 0,
    requestFrame(callback) {
      frames.requested += 1;
      queue.push(callback);
    },
    run() {
      for (const callback of queue.splice(0)) {
        callback();
      }
    },
  };
  return frames;
}

/* Mount the fixture as `mount` does, but build the controller over a fake
   viewport and frame queue instead of evaluating the script. */
function mountController(tops, markup = FIXTURE) {
  document.body.innerHTML = markup;
  const nav = document.querySelector("[data-cu-routemap]");
  place(nav, 60, 100);
  ["problem", "code", "output"].forEach((id, i) => {
    const section = document.getElementById(id);
    if (section) {
      place(section, tops[i]);
    }
  });
  const viewport = fakeViewport();
  const frames = fakeFrames();
  const controller = createRouteMapController(nav, {
    document,
    viewport,
    requestFrame: frames.requestFrame,
  });
  return { controller, frames, nav, viewport };
}

/* The index `pickActiveIndex` should return, written as the rule states it:
   the last section at the foot of the page, else the last one reached. */
function activeIndexOracle(tops, offset, atBottom) {
  if (atBottom && tops.length > 0) {
    return tops.length - 1;
  }
  return tops.findLastIndex((top) => top <= offset);
}

describe("pickActiveIndex", () => {
  test("picks the last section whose top has passed the offset", () => {
    expect(pickActiveIndex([-500, 80, 900], 124, false)).toBe(1);
  });

  test("reports no section before the first is reached", () => {
    expect(pickActiveIndex([300, 900, 1500], 124, false)).toBe(-1);
  });

  test("picks the final section at the foot of the page", () => {
    expect(pickActiveIndex([-900, -300, 600], 124, true)).toBe(2);
  });

  test("reports nothing for a page without sections", () => {
    expect(pickActiveIndex([], 124, true)).toBe(-1);
  });

  test("agrees with the stated rule for any sorted layout", () => {
    fc.assert(
      fc.property(
        fc.array(fc.integer({ min: -5000, max: 5000 }), { maxLength: 12 }),
        fc.integer({ min: -5000, max: 5000 }),
        fc.boolean(),
        (unsorted, offset, atBottom) => {
          const tops = unsorted.toSorted((a, b) => a - b);
          expect(pickActiveIndex(tops, offset, atBottom)).toBe(
            activeIndexOracle(tops, offset, atBottom),
          );
        },
      ),
    );
  });
});

describe("collectTargets", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    restoreScrollHeight();
  });

  test("drops missing sections and gathers repeated links under one target", () => {
    document.body.innerHTML = `
      <nav data-cu-routemap>
        <a href="#problem" data-cu-routemap-link>one</a>
        <a href="#gone" data-cu-routemap-link>missing</a>
        <a href="#" data-cu-routemap-link>empty</a>
        <a href="#caf%C3%A9" data-cu-routemap-link>encoded</a>
        <a href="#problem" data-cu-routemap-link>again</a>
        <a href="#gone" data-cu-routemap-link>missing again</a>
      </nav>
      <section id="problem"></section>
      <section id="café"></section>`;
    const targets = collectTargets(document, document.querySelector("nav"));
    expect(targets.map((target) => target.id)).toEqual(["problem", "café"]);
    expect(targets[0].links.map((link) => link.textContent)).toEqual(["one", "again"]);
    expect(targets[0].el).toBe(document.getElementById("problem"));
  });

  test("skips a malformed fragment and keeps scanning", () => {
    document.body.innerHTML = `
      <nav data-cu-routemap>
        <a href="#%E0%A4%A" data-cu-routemap-link>malformed</a>
        <a href="#problem" data-cu-routemap-link>one</a>
        <a href="#caf%C3%A9" data-cu-routemap-link>encoded</a>
      </nav>
      <section id="problem"></section>
      <section id="café"></section>`;
    const targets = collectTargets(document, document.querySelector("nav"));
    expect(targets.map((target) => target.id)).toEqual(["problem", "café"]);
  });
});

describe("fragmentId", () => {
  test("decodes a fragment and strips its hash", () => {
    expect(fragmentId("#caf%C3%A9")).toBe("café");
    expect(fragmentId("problem")).toBe("problem");
    expect(fragmentId("#")).toBe("");
  });

  test("returns null for malformed percent-encoding instead of throwing", () => {
    expect(fragmentId("#%E0%A4%A")).toBeNull();
    expect(fragmentId("#%")).toBeNull();
  });
});

describe("the route map controller", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    restoreScrollHeight();
  });

  test("a map that names no section on the page marks and schedules nothing", () => {
    const markup = FIXTURE.replace(/<section id="\w+"><\/section>/g, "");
    const { controller, frames, viewport } = mountController([], markup);
    expect(controller).toBeNull();
    expect(marked()).toEqual([]);
    expect(document.querySelector("[data-cu-routemap-current]").textContent).toBe(
      "Jump to a section",
    );
    expect(viewport.listeners.scroll.length + viewport.listeners.resize.length).toBe(0);
    expect(frames.requested).toBe(0);
  });

  test("a link to a missing section is never marked", () => {
    const markup = FIXTURE.replace('<section id="code"></section>', "");
    const { controller } = mountController([-600, -300, 900], markup);
    expect(controller.targets.map((target) => target.id)).toEqual(["problem", "output"]);
    expect(marked()).toEqual(["01Problem", "01Problem"]);
    expect(document.querySelectorAll("a[href='#code'][aria-current]").length).toBe(0);
  });

  test("a burst of scroll and resize events reads layout once, in a frame", () => {
    const { controller, frames, viewport } = mountController([400, 900, 1500]);
    viewport.fire("scroll");
    viewport.fire("scroll");
    viewport.fire("resize");
    viewport.fire("scroll");
    viewport.fire("resize");
    expect(frames.requested).toBe(1);

    // The sections move, but nothing is read until the frame runs.
    place(document.getElementById("problem"), -600);
    place(document.getElementById("code"), 110);
    expect(marked()).toEqual([]);
    frames.run();
    expect(marked()).toEqual(["02Code", "02Code"]);
    expect(controller.active().id).toBe("code");

    // Once the frame has run, the next event asks for a new one.
    viewport.fire("scroll");
    expect(frames.requested).toBe(2);
  });

  test("scrolling back above every section clears the mark and restores the summary", () => {
    const { frames, viewport } = mountController([-600, 110, 900]);
    expect(marked()).toEqual(["02Code", "02Code"]);
    place(document.getElementById("problem"), 400);
    place(document.getElementById("code"), 900);
    viewport.fire("scroll");
    frames.run();
    expect(marked()).toEqual([]);
    expect(document.querySelector("[data-cu-routemap-current]").textContent).toBe(
      "Jump to a section",
    );
  });

  test("the foot of the page, read from the viewport, marks the last section", () => {
    const { frames, viewport } = mountController([-900, -300, 600]);
    expect(marked()).toEqual(["02Code", "02Code"]);
    viewport.state.scrollY = viewport.state.scrollHeight - viewport.state.innerHeight;
    viewport.fire("scroll");
    frames.run();
    expect(marked()).toEqual(["03Output", "03Output"]);
  });
});

describe("the route map in the document", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    restoreScrollHeight();
  });

  test("marks the section being read in both lists", () => {
    mount([-600, 110, 900]);
    expect(marked()).toEqual(["02Code", "02Code"]);
    expect(document.querySelector("[aria-current]").getAttribute("aria-current")).toBe("location");
  });

  test("names the current section in the drop-down's summary", () => {
    mount([-600, 110, 900]);
    const current = document.querySelector("[data-cu-routemap-current]");
    expect(current.textContent).toBe("02Code");
    expect(current.querySelector(".cu-routemap__num").getAttribute("aria-hidden")).toBe("true");
  });

  test("leaves the fallback words while no section is reached", () => {
    mount([400, 900, 1500]);
    expect(marked()).toEqual([]);
    expect(document.querySelector("[data-cu-routemap-current]").textContent).toBe(
      "Jump to a section",
    );
  });

  test("closes the drop-down once a section is chosen", () => {
    mount([400, 900, 1500]);
    const menu = document.querySelector("details");
    menu.open = true;
    menu.querySelector("a[href='#output']").click();
    expect(menu.open).toBe(false);
  });

  test("closes on Escape and returns focus to the summary", () => {
    mount([400, 900, 1500]);
    const menu = document.querySelector("details");
    menu.open = true;
    menu
      .querySelector("a")
      .dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(menu.open).toBe(false);
    expect(document.activeElement).toBe(menu.querySelector("summary"));
  });

  test("closes on a click outside it", () => {
    mount([400, 900, 1500]);
    const menu = document.querySelector("details");
    menu.open = true;
    document.getElementById("elsewhere").click();
    expect(menu.open).toBe(false);
  });
});

describe("several route maps on one page", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    restoreScrollHeight();
  });

  test("each map marks its own sections and names its own in its summary", () => {
    /* One route map over two sections, its ids prefixed with `prefix`. */
    const routemap = (prefix) => `
      <nav data-cu-routemap id="${prefix}-map">
        <ol><li><a href="#${prefix}-one" data-cu-routemap-link>${prefix} one</a></li>
        <li><a href="#${prefix}-two" data-cu-routemap-link>${prefix} two</a></li></ol>
        <details><summary><span data-cu-routemap-current>Jump</span></summary></details>
      </nav>
      <section id="${prefix}-one"></section>
      <section id="${prefix}-two"></section>`;
    document.body.innerHTML = `${routemap("a")}${routemap("b")}
      <nav data-cu-routemap id="empty-map"><a href="#nowhere" data-cu-routemap-link>x</a></nav>`;
    Object.defineProperty(document.documentElement, "scrollHeight", {
      configurable: true,
      value: 10000,
    });
    for (const nav of document.querySelectorAll("[data-cu-routemap]")) {
      place(nav, 60, 100);
    }
    place(document.getElementById("a-one"), -600);
    place(document.getElementById("a-two"), 900);
    place(document.getElementById("b-one"), -600);
    place(document.getElementById("b-two"), 110);
    new Function("module", readFileSync(SCRIPT, "utf8"))(undefined);

    /* The labels marked inside one map. */
    const markedIn = (id) =>
      Array.from(document.querySelectorAll(`#${id} [aria-current]`)).map((a) => a.textContent);
    expect(markedIn("a-map")).toEqual(["a one"]);
    expect(markedIn("b-map")).toEqual(["b two"]);
    expect(markedIn("empty-map")).toEqual([]);
    expect(document.querySelector("#a-map [data-cu-routemap-current]").textContent).toBe("a one");
    expect(document.querySelector("#b-map [data-cu-routemap-current]").textContent).toBe("b two");
  });
});
