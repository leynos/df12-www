/**
 * @file Tests for the Stilyagi design page's IR inspector and capability planner.
 *
 * The planner's whole job is to answer two questions from the enabled
 * ruleset: which linguistic providers must load, and what that costs at
 * start-up. The DOM suites then check the wiring: the inspector previews on
 * hover without announcing an activation, activation moves `aria-pressed`
 * and the footer, and the planner's toggles drive the provider cards and
 * the summary counters. The suite mounts INSPECTOR_FIXTURE and
 * PLANNER_FIXTURE from `helpers/stilyagi.mjs` into happy-dom before
 * evaluating the widget script against them.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { createRequire } from "node:module";
import {
  click,
  hover,
  INSPECTOR_FIXTURE,
  mount,
  PLANNER_FIXTURE,
  pressKey,
  reset,
  unhover,
} from "./helpers/stilyagi.mjs";

const require = createRequire(import.meta.url);
const { requiredCapabilities, coldStartFor } = require("../../public/stilyagi/assets/js/design.js");

describe("requiredCapabilities", () => {
  test("the core extractor loads even with no rules enabled", () => {
    expect([...requiredCapabilities([])]).toEqual(["core"]);
  });

  test("rules declaring no capability add nothing", () => {
    expect([...requiredCapabilities(["", "", ""])]).toEqual(["core"]);
  });

  test("each declared capability is pulled in", () => {
    const caps = requiredCapabilities(["grammar", "spell"]);
    expect([...caps].sort()).toEqual(["core", "grammar", "spell"]);
  });

  test("a rule may declare several capabilities at once", () => {
    const caps = requiredCapabilities(["grammar terminology"]);
    expect([...caps].sort()).toEqual(["core", "grammar", "terminology"]);
  });

  test("a capability required twice is only counted once", () => {
    const caps = requiredCapabilities(["spell", "spell"]);
    expect([...caps].sort()).toEqual(["core", "spell"]);
  });

  test("missing capability strings are tolerated", () => {
    expect([...requiredCapabilities([undefined, null])]).toEqual(["core"]);
  });
});

describe("coldStartFor", () => {
  test("the core extractor alone starts cold in milliseconds", () => {
    expect(coldStartFor(new Set(["core"]))).toBe("40 ms");
  });

  test("the spellchecker dominates when it is the only provider", () => {
    expect(coldStartFor(new Set(["core", "spell"]))).toBe("260 ms");
  });

  test("grammar is the heaviest provider and wins outright", () => {
    expect(coldStartFor(new Set(["core", "spell", "grammar"]))).toBe("1.4 s");
  });

  test("terminology alone does not move the estimate", () => {
    expect(coldStartFor(new Set(["core", "terminology"]))).toBe("40 ms");
  });
});

describe("the IR inspector in the document", () => {
  afterEach(reset);

  const span = (id) => document.querySelector(`.region[data-region="${id}"]`);
  const node = (id) => document.querySelector(`.tree-node[data-region="${id}"]`);
  const footLabel = () => document.querySelector("[data-ir-label]").textContent;
  const footRange = () => document.querySelector("[data-ir-range]").textContent;
  const pressedByRegion = () =>
    Object.fromEntries(
      [...document.querySelectorAll(".tree-node")].map((n) => [
        n.dataset.region,
        n.getAttribute("aria-pressed"),
      ]),
    );

  // The fixture ships with the link node pressed, as the template does.
  const SHIPPED_PRESSED = { "h1-1": "false", "p-1": "false", "link-1": "true" };

  test("the footer settles on the shipped pressed node at load", () => {
    mount(INSPECTOR_FIXTURE, "design");
    expect(footLabel()).toBe("Link");
    expect(footRange()).toBe("[136,172]");
  });

  test("hovering a source span previews without touching aria-pressed", () => {
    mount(INSPECTOR_FIXTURE, "design");
    hover(span("p-1"));

    expect(span("p-1").classList.contains("active")).toBe(true);
    expect(node("p-1").classList.contains("active")).toBe(true);
    expect(footLabel()).toBe("Paragraph");
    expect(footRange()).toBe("[24,173]");
    // A preview is not an activation: telling assistive technology the
    // button under the pointer was pressed would be a lie.
    expect(pressedByRegion()).toEqual(SHIPPED_PRESSED);
  });

  test("hovering a tree node previews without touching aria-pressed", () => {
    mount(INSPECTOR_FIXTURE, "design");
    hover(node("h1-1"));

    expect(span("h1-1").classList.contains("active")).toBe(true);
    expect(footLabel()).toBe("Heading depth=1");
    expect(footRange()).toBe("[0,22]");
    expect(pressedByRegion()).toEqual(SHIPPED_PRESSED);
  });

  test("leaving a preview restores the chosen region", () => {
    mount(INSPECTOR_FIXTURE, "design");
    hover(span("p-1"));
    unhover(span("p-1"));

    expect(footLabel()).toBe("Link");
    expect(footRange()).toBe("[136,172]");
    expect(span("link-1").classList.contains("active")).toBe(true);
    expect(span("p-1").classList.contains("active")).toBe(false);
  });

  test("clicking a tree node presses it and reports it in the footer", () => {
    mount(INSPECTOR_FIXTURE, "design");
    click(node("h1-1"));

    expect(pressedByRegion()).toEqual({ "h1-1": "true", "p-1": "false", "link-1": "false" });
    expect(footLabel()).toBe("Heading depth=1");
    expect(footRange()).toBe("[0,22]");

    // The choice sticks: a later preview restores to it, not to the link.
    hover(span("p-1"));
    unhover(span("p-1"));
    expect(footLabel()).toBe("Heading depth=1");
  });

  test("Enter on a tree node activates it and takes over the keystroke", () => {
    mount(INSPECTOR_FIXTURE, "design");
    const event = pressKey(node("p-1"), "Enter");

    expect(event.defaultPrevented).toBe(true);
    expect(pressedByRegion()).toEqual({ "h1-1": "false", "p-1": "true", "link-1": "false" });
    expect(footLabel()).toBe("Paragraph");
  });

  test("the source spans are plain text, with no focus or key behaviour", () => {
    mount(INSPECTOR_FIXTURE, "design");

    // Not focusable, so `focus` and `keydown` handlers could never fire on
    // them anyway; the widget must not pretend otherwise.
    expect(span("p-1").hasAttribute("tabindex")).toBe(false);
    span("p-1").dispatchEvent(new window.Event("focus"));
    const event = pressKey(span("p-1"), "Enter");

    expect(event.defaultPrevented).toBe(false);
    expect(footLabel()).toBe("Link");
    expect(pressedByRegion()).toEqual(SHIPPED_PRESSED);
  });
});

describe("the capability planner in the document", () => {
  afterEach(reset);

  const toggle = (code) => document.querySelector(`.rule-toggle[data-code="${code}"]`);
  const provider = (name) => document.querySelector(`.provider[data-provider="${name}"]`);
  const tag = (name) => provider(name).querySelector("[data-provider-tag]").textContent;
  const summary = () => ({
    rules: document.querySelector("[data-plan-rules]").textContent,
    providers: document.querySelector("[data-plan-providers]").textContent,
    coldStart: document.querySelector("[data-plan-coldstart]").textContent,
  });

  const expectLoaded = (name, loaded) => {
    expect(provider(name).classList.contains("loaded")).toBe(loaded);
    expect(provider(name).classList.contains("skipped")).toBe(!loaded);
    expect(tag(name)).toBe(loaded ? "Loaded" : "Skipped");
  };

  test("enabling a grammar rule loads its provider and reprices the plan", () => {
    mount(PLANNER_FIXTURE, "design");
    click(toggle("GRAM301"));

    expect(toggle("GRAM301").getAttribute("aria-checked")).toBe("true");
    expect(toggle("GRAM301").classList.contains("on")).toBe(true);
    expectLoaded("grammar", true);
    expectLoaded("core", true);
    expectLoaded("spell", false);
    // The provider count keeps the leading space the template writes.
    expect(summary()).toEqual({ rules: "2", providers: " 1", coldStart: "1.4 s" });
  });

  test("disabling the rule again skips the provider and restores the plan", () => {
    mount(PLANNER_FIXTURE, "design");
    click(toggle("GRAM301"));
    click(toggle("GRAM301"));

    expect(toggle("GRAM301").getAttribute("aria-checked")).toBe("false");
    expect(toggle("GRAM301").classList.contains("on")).toBe(false);
    expectLoaded("grammar", false);
    expectLoaded("core", true);
    expect(summary()).toEqual({ rules: "1", providers: " 0", coldStart: "40 ms" });
  });

  test("the spellchecker sets the cold start when it is the heaviest", () => {
    mount(PLANNER_FIXTURE, "design");
    click(toggle("SPELL101"));

    expectLoaded("spell", true);
    expect(summary()).toEqual({ rules: "2", providers: " 1", coldStart: "260 ms" });
  });

  test("terminology loads its provider without moving the cold start", () => {
    mount(PLANNER_FIXTURE, "design");
    click(toggle("TERM201"));

    expectLoaded("terminology", true);
    expect(summary()).toEqual({ rules: "2", providers: " 1", coldStart: "40 ms" });
  });

  test("Space toggles a rule and takes over the keystroke", () => {
    mount(PLANNER_FIXTURE, "design");
    const event = pressKey(toggle("GRAM301"), " ");

    expect(event.defaultPrevented).toBe(true);
    expect(toggle("GRAM301").getAttribute("aria-checked")).toBe("true");
    expectLoaded("grammar", true);
  });
});
