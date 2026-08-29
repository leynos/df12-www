/* Tests for the Stilyagi docs page's widgets.
 *
 * `matchesFilter` is the catalogue's whole decision: given a row's namespace
 * and its precomputed searchable text, plus the selected chip and the search
 * box contents, it decides whether the row stays visible. The DOM suites
 * then check the wiring: rows actually hide, the chip row and the select
 * stay in step, the suppression tabs move selection and focus, and the
 * section rail follows the observer.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { createRequire } from "node:module";
import fc from "fast-check";
import {
  CATALOGUE_FIXTURE,
  click,
  installIntersectionObserver,
  mount,
  pressKey,
  RAIL_FIXTURE,
  reset,
  TABS_FIXTURE,
} from "./helpers/stilyagi.mjs";

const require = createRequire(import.meta.url);
const { matchesFilter } = require("../../public/stilyagi/assets/js/docs.js");

const HAYSTACK = "md201 heading depth headings must not skip levels";

describe("matchesFilter", () => {
  test('the "all" chip with no query keeps every row', () => {
    expect(matchesFilter("md", HAYSTACK, "all", "")).toBe(true);
    expect(matchesFilter("pydoc", "", "all", "")).toBe(true);
  });

  test("a namespace chip keeps only its own rows", () => {
    expect(matchesFilter("md", HAYSTACK, "md", "")).toBe(true);
    expect(matchesFilter("pydoc", HAYSTACK, "md", "")).toBe(false);
  });

  test("the query matches the rule id as well as its prose", () => {
    expect(matchesFilter("md", HAYSTACK, "all", "md201")).toBe(true);
    expect(matchesFilter("md", HAYSTACK, "all", "skip levels")).toBe(true);
  });

  test("the query is case-insensitive and ignores surrounding space", () => {
    expect(matchesFilter("md", HAYSTACK, "all", "  HEADING ")).toBe(true);
  });

  test("namespace and query must both hold", () => {
    // The row's text matches, but it belongs to another namespace.
    expect(matchesFilter("md", HAYSTACK, "pydoc", "heading")).toBe(false);
  });

  test("a query with no match hides the row", () => {
    expect(matchesFilter("md", HAYSTACK, "all", "oxford comma")).toBe(false);
  });

  test("a whitespace-only query is treated as empty", () => {
    expect(matchesFilter("md", HAYSTACK, "all", "   ")).toBe(true);
  });

  test("a row with no searchable text survives only an empty query", () => {
    expect(matchesFilter("md", undefined, "all", "")).toBe(true);
    expect(matchesFilter("md", undefined, "all", "heading")).toBe(false);
  });
});

describe("the catalogue filter in the document", () => {
  afterEach(reset);

  const chips = () => [...document.querySelectorAll(".filter-chip[data-ns]")];
  const chip = (ns) => document.querySelector(`.filter-chip[data-ns="${ns}"]`);
  const select = () => document.querySelector(".filter-select");
  const search = () => document.querySelector("#rule-search");
  const rows = () => [...document.querySelectorAll(".rules-table tbody tr[data-ns]")];
  const emptyRow = () => document.querySelector(".rules-table tbody .empty-row");
  const visibleCodes = () =>
    rows()
      .filter((row) => !row.hidden)
      .map((row) => row.querySelector(".id").textContent);

  const type = (value) => {
    search().value = value;
    search().dispatchEvent(new window.Event("input", { bubbles: true }));
  };

  test("a restored search string is applied at load, not just on input", () => {
    // A reload or back-navigation restores the box's text but fires no
    // `input` event; the rows must settle against it anyway.
    mount(CATALOGUE_FIXTURE, "docs", {
      before: (doc) => {
        doc.querySelector("#rule-search").value = "heading";
      },
    });
    expect(visibleCodes()).toEqual(["MD201"]);
  });

  test("a restored select value is applied at load and the chips follow", () => {
    mount(CATALOGUE_FIXTURE, "docs", {
      before: (doc) => {
        doc.querySelector(".filter-select").value = "pydoc";
      },
    });
    expect(visibleCodes()).toEqual(["PYDOC101"]);
    expect(chip("pydoc").getAttribute("aria-pressed")).toBe("true");
    expect(chip("pydoc").classList.contains("active")).toBe(true);
    expect(chip("all").getAttribute("aria-pressed")).toBe("false");
    expect(chip("all").classList.contains("active")).toBe(false);
  });

  test("clicking a chip filters the rows and keeps the select in step", () => {
    mount(CATALOGUE_FIXTURE, "docs");
    click(chip("md"));

    expect(visibleCodes()).toEqual(["MD201", "MD401"]);
    expect(select().value).toBe("md");
    expect(chip("md").getAttribute("aria-pressed")).toBe("true");
    expect(chip("md").classList.contains("active")).toBe(true);
    // The namespace tint is worn only while the chip is selected.
    expect(chip("md").classList.contains("ns-md")).toBe(true);
    for (const other of chips().filter((c) => c !== chip("md"))) {
      expect(other.getAttribute("aria-pressed")).toBe("false");
      expect(other.classList.contains("active")).toBe(false);
    }
  });

  test("changing the select filters the rows and keeps the chips in step", () => {
    mount(CATALOGUE_FIXTURE, "docs");
    select().value = "pydoc";
    select().dispatchEvent(new window.Event("change", { bubbles: true }));

    expect(visibleCodes()).toEqual(["PYDOC101"]);
    expect(chip("pydoc").getAttribute("aria-pressed")).toBe("true");
    expect(chip("md").getAttribute("aria-pressed")).toBe("false");
    expect(chip("all").getAttribute("aria-pressed")).toBe("false");
  });

  test("typing narrows the rows within the selected namespace", () => {
    mount(CATALOGUE_FIXTURE, "docs");
    click(chip("md"));
    type("link");
    expect(visibleCodes()).toEqual(["MD401"]);

    // The query matches a PyDoc row too, but the namespace still holds.
    type("docstring");
    expect(visibleCodes()).toEqual([]);
  });

  test("the empty row shows only while no rule matches", () => {
    mount(CATALOGUE_FIXTURE, "docs");
    expect(emptyRow().hidden).toBe(true);

    type("no such rule anywhere");
    expect(visibleCodes()).toEqual([]);
    expect(emptyRow().hidden).toBe(false);

    type("");
    expect(visibleCodes()).toEqual(["MD201", "MD401", "PYDOC101"]);
    expect(emptyRow().hidden).toBe(true);
  });

  test("row visibility always agrees with matchesFilter", () => {
    // The pure function is the oracle: whatever chip and query the reader
    // lands on, each row's `hidden` must be its answer negated, and the
    // empty row must show exactly when nothing survives.
    const queryArbitrary = fc.oneof(
      fc.constantFrom("", "heading", "link", "docstring", " MD201 ", "no such rule"),
      fc.string({ maxLength: 12 }),
    );
    fc.assert(
      fc.property(fc.constantFrom("all", "md", "pydoc"), queryArbitrary, (namespace, query) => {
        mount(CATALOGUE_FIXTURE, "docs");
        if (namespace !== "all") click(chip(namespace));
        type(query);

        let visible = 0;
        for (const row of rows()) {
          const show = matchesFilter(row.dataset.ns, row.dataset.search, namespace, query);
          expect(row.hidden).toBe(!show);
          if (show) visible += 1;
        }
        expect(emptyRow().hidden).toBe(visible !== 0);
      }),
    );
  });
});

describe("the suppression tabs in the document", () => {
  afterEach(reset);

  const tabs = () => [...document.querySelectorAll('[role="tab"][data-tab]')];
  const tab = (key) => document.querySelector(`[role="tab"][data-tab="${key}"]`);
  const panel = (key) => document.querySelector(`[data-panel="${key}"]`);

  /* Exactly the tab for `key` is selected: `aria-selected`, the roving
     `tabindex`, `.active`, and its panel alone shown. */
  const expectSelected = (key) => {
    for (const t of tabs()) {
      const active = t.dataset.tab === key;
      expect(t.getAttribute("aria-selected")).toBe(String(active));
      expect(t.tabIndex).toBe(active ? 0 : -1);
      expect(t.classList.contains("active")).toBe(active);
      expect(panel(t.dataset.tab).hidden).toBe(!active);
    }
  };

  test("the markup's selected tab is settled into the roving tab order", () => {
    mount(TABS_FIXTURE, "docs");
    expectSelected("md");
  });

  test("clicking a tab moves selection, the panels, and the tab order", () => {
    mount(TABS_FIXTURE, "docs");
    click(tab("py"));
    expectSelected("py");
  });

  test("ArrowRight moves selection and focus, wrapping past the end", () => {
    mount(TABS_FIXTURE, "docs");
    tab("md").focus();

    const first = pressKey(tab("md"), "ArrowRight");
    expect(first.defaultPrevented).toBe(true);
    expectSelected("py");
    expect(document.activeElement).toBe(tab("py"));

    pressKey(tab("py"), "ArrowRight");
    expectSelected("md");
    expect(document.activeElement).toBe(tab("md"));
  });

  test("ArrowLeft moves selection and focus, wrapping past the start", () => {
    mount(TABS_FIXTURE, "docs");
    tab("md").focus();

    pressKey(tab("md"), "ArrowLeft");
    expectSelected("py");
    expect(document.activeElement).toBe(tab("py"));

    pressKey(tab("py"), "ArrowLeft");
    expectSelected("md");
    expect(document.activeElement).toBe(tab("md"));
  });

  test("ArrowDown and ArrowUp move like ArrowRight and ArrowLeft", () => {
    mount(TABS_FIXTURE, "docs");
    tab("md").focus();

    pressKey(tab("md"), "ArrowDown");
    expectSelected("py");

    pressKey(tab("py"), "ArrowUp");
    expectSelected("md");
  });

  test("any arrow-key sequence keeps exactly one tab selected and focused", () => {
    // Modular arithmetic over the tab count is the oracle: selection,
    // the roving tabindex, panel visibility, and focus must all agree
    // with it after every keystroke, however long the sequence.
    const keyArbitrary = fc.constantFrom("ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp");
    fc.assert(
      fc.property(fc.array(keyArbitrary, { maxLength: 16 }), (keys) => {
        mount(TABS_FIXTURE, "docs");
        tab("md").focus();
        let index = 0;
        for (const key of keys) {
          pressKey(document.activeElement, key);
          const step = key === "ArrowRight" || key === "ArrowDown" ? 1 : -1;
          index = (index + step + tabs().length) % tabs().length;
          expectSelected(tabs()[index].dataset.tab);
          expect(document.activeElement).toBe(tabs()[index]);
        }
      }),
    );
  });

  test("arrow keys pressed outside the tabs are ignored", () => {
    mount(TABS_FIXTURE, "docs");
    // Nothing inside the tablist holds focus, so there is no position to
    // step from and the keystroke is left alone.
    const event = pressKey(tab("md").parentElement, "ArrowRight");
    expect(event.defaultPrevented).toBe(false);
    expectSelected("md");
  });
});

describe("the section rail in the document", () => {
  afterEach(reset);

  const links = () => [...document.querySelectorAll('.side-toc a[href^="#"]')];
  const activeHrefs = () =>
    links()
      .filter((link) => link.classList.contains("active"))
      .map((link) => link.getAttribute("href"));

  test("every section named by the rail is observed", () => {
    const observer = installIntersectionObserver();
    mount(RAIL_FIXTURE, "docs");
    expect(observer.observed.map((section) => section.id)).toEqual([
      "catalogue",
      "config",
      "suppress",
    ]);
  });

  test("an intersecting section marks exactly its own link active", () => {
    const observer = installIntersectionObserver();
    mount(RAIL_FIXTURE, "docs");

    observer.intersect(document.getElementById("config"));
    expect(activeHrefs()).toEqual(["#config"]);

    observer.intersect(document.getElementById("suppress"));
    expect(activeHrefs()).toEqual(["#suppress"]);
  });

  test("a section leaving the viewport moves nothing", () => {
    const observer = installIntersectionObserver();
    mount(RAIL_FIXTURE, "docs");

    observer.intersect(document.getElementById("config"));
    observer.intersect(document.getElementById("suppress"), false);
    expect(activeHrefs()).toEqual(["#config"]);
  });
});
