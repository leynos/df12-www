/**
 * @file Tests for rstest-bdd's optional telemetry hook.
 *
 * The promise this module makes is negative — that certain things *cannot*
 * leave the page — and a negative is only worth as much as the test that
 * tries to break it. So these do two jobs: pin the schema each event must
 * have, and try to get page data and identifiers into one. What the copy
 * buttons and the storybook report through it is covered in their own
 * suites.
 *
 * The module is required from `public/`, the copy the browser is served, as
 * the other suites here do.
 */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const telemetry = require("../../public/rstest-bdd/assets/js/telemetry.js");

/* Every field name any event may carry. */
const ALLOWED_FIELDS = ["component", "operation", "outcome", "reason"];

let events;

beforeEach(() => {
  events = [];
  globalThis.df12RstestBddTelemetrySink = (event) => events.push(event);
});

afterEach(() => {
  globalThis.df12RstestBddTelemetrySink = undefined;
});

describe("the hook", () => {
  test("installs its API on the global object", () => {
    expect(typeof globalThis.df12RstestBddTelemetry.emit).toBe("function");
  });

  test("is a no-op when the host installs nothing", () => {
    globalThis.df12RstestBddTelemetrySink = undefined;
    expect(() =>
      telemetry.emit(telemetry.OPERATIONS.clipboard, telemetry.OUTCOMES.copied),
    ).not.toThrow();
    expect(events).toEqual([]);
  });

  test("is a no-op when the host installs something that is not a function", () => {
    globalThis.df12RstestBddTelemetrySink = { collect: true };
    telemetry.emit(telemetry.OPERATIONS.clipboard, telemetry.OUTCOMES.copied);
    expect(events).toEqual([]);
  });

  test("survives a sink that throws, because observability is optional", () => {
    globalThis.df12RstestBddTelemetrySink = () => {
      throw new Error("the collector is down");
    };
    expect(() =>
      telemetry.emit(telemetry.OPERATIONS.storybook, telemetry.OUTCOMES.initialized),
    ).not.toThrow();
  });

  test("keeps its vocabularies closed", () => {
    for (const vocabulary of [
      telemetry.COMPONENTS,
      telemetry.OPERATIONS,
      telemetry.OUTCOMES,
      telemetry.REASONS,
    ]) {
      expect(Object.isFrozen(vocabulary)).toBe(true);
    }
  });
});

describe("the event schema", () => {
  test("declares exactly the agreed vocabularies", () => {
    expect(Object.values(telemetry.COMPONENTS).sort()).toEqual([
      "rstest-bdd-copy-button",
      "rstest-bdd-storybook",
    ]);
    expect(Object.values(telemetry.OPERATIONS).sort()).toEqual(["clipboard", "storybook"]);
    expect(Object.values(telemetry.OUTCOMES).sort()).toEqual([
      "copied",
      "failed",
      "initialized",
      "navigated",
    ]);
    expect(Object.values(telemetry.REASONS).sort()).toEqual([
      "next",
      "previous",
      "rejected",
      "scroll",
      "tab",
      "unavailable",
    ]);
  });

  test("carries the component, the operation and the outcome", () => {
    telemetry.emit(telemetry.OPERATIONS.clipboard, telemetry.OUTCOMES.copied);
    expect(events).toEqual([
      { component: "rstest-bdd-copy-button", operation: "clipboard", outcome: "copied" },
    ]);
  });

  test("carries a reason only when one is given", () => {
    telemetry.emit(
      telemetry.OPERATIONS.storybook,
      telemetry.OUTCOMES.navigated,
      telemetry.REASONS.tab,
    );
    expect(events[0].reason).toBe("tab");

    events.length = 0;
    telemetry.emit(telemetry.OPERATIONS.storybook, telemetry.OUTCOMES.initialized);
    expect("reason" in events[0]).toBe(false);
  });

  test("has no field outside the fixed set, for every combination", () => {
    for (const operation of Object.values(telemetry.OPERATIONS)) {
      for (const outcome of Object.values(telemetry.OUTCOMES)) {
        for (const reason of [undefined, ...Object.values(telemetry.REASONS)]) {
          events.length = 0;
          telemetry.emit(operation, outcome, reason);
          /* Without this the check below is vacuous: a version that emitted
             nothing at all would satisfy it. */
          expect(events.length).toBe(1);
          const [event] = events;
          expect(Object.keys(event).sort()).toEqual(
            reason === undefined
              ? ["component", "operation", "outcome"]
              : [...ALLOWED_FIELDS].sort(),
          );
          expect(event).toEqual({
            component: telemetry.COMPONENTS[operation],
            operation,
            outcome,
            ...(reason === undefined ? {} : { reason }),
          });
        }
      }
    }
  });

  test("drops an operation, outcome or reason outside its vocabulary", () => {
    /* A caller passing something unrecognised is a bug in the caller, and
       widening the schema at runtime would break the promise this module
       makes about what can leave the page. */
    telemetry.emit("navigate", telemetry.OUTCOMES.navigated);
    telemetry.emit(telemetry.OPERATIONS.storybook, "chapter-03");
    telemetry.emit(telemetry.OPERATIONS.storybook, telemetry.OUTCOMES.navigated, "/rstest-bdd/");
    telemetry.emit(telemetry.OPERATIONS.clipboard, telemetry.OUTCOMES.copied, "cargo test");
    expect(events).toEqual([]);
  });

  test("refuses a payload smuggled in as an operation", () => {
    telemetry.emit({ chapter: "The lantern picnic" }, telemetry.OUTCOMES.navigated);
    telemetry.emit(telemetry.OPERATIONS.clipboard, { text: "cargo test" });
    telemetry.emit(telemetry.OPERATIONS.storybook, telemetry.OUTCOMES.navigated, {
      path: "/rstest-bdd/#chapter-02",
    });
    expect(events).toEqual([]);
  });
});
