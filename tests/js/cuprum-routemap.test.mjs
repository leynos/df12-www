/**
 * @file Tests for the Cuprum route map's scroll-spy and drop-down.
 *
 * `pickActiveIndex` decides which section is being read. The DOM suite
 * mounts a route map shaped like the `routemap` macro in
 * `templates/cuprum/components.jinja` — a strip and a drop-down listing the
 * same sections — places the sections by stubbing their layout, evaluates
 * the compiled script against the global happy-dom document, and checks the
 * mark, the summary, and how the drop-down closes.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const SCRIPT = join("public", "cuprum", "assets", "js", "routemap.js");
const { pickActiveIndex } = require(`../../${SCRIPT}`);

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
});

describe("the route map in the document", () => {
  afterEach(() => {
    document.body.innerHTML = "";
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
