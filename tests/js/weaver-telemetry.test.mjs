/* Tests for the Weaver chrome's optional telemetry hook.
 *
 * The promise this module makes is negative — that certain things *cannot*
 * leave the page — and a negative is only worth as much as the test that
 * tries to break it. So these do two jobs: pin the schema each event must
 * have, and try to get page data, clipboard contents and identifiers into one.
 *
 * The module is required from `public/`, the copy the browser is served, as
 * the other suites here do.
 */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";

const telemetry = require("../../public/weaver/assets/js/telemetry.js");

/* Every field name any event may carry. */
const ALLOWED_FIELDS = ["component", "operation", "outcome", "reason"];

let events;

beforeEach(() => {
  events = [];
  globalThis.df12WeaverNavTelemetry = (event) => events.push(event);
});

afterEach(() => {
  globalThis.df12WeaverNavTelemetry = undefined;
  globalThis.navigator = undefined;
});

describe("the hook", () => {
  test("is a no-op when the host installs nothing", () => {
    globalThis.df12WeaverNavTelemetry = undefined;
    expect(() =>
      telemetry.emit(telemetry.OPERATIONS.drawer, telemetry.OUTCOMES.opened),
    ).not.toThrow();
    expect(events).toEqual([]);
  });

  test("is a no-op when the host installs something that is not a function", () => {
    globalThis.df12WeaverNavTelemetry = { collect: true };
    telemetry.emit(telemetry.OPERATIONS.drawer, telemetry.OUTCOMES.opened);
    expect(events).toEqual([]);
  });

  test("survives a sink that throws, because observability is optional", () => {
    globalThis.df12WeaverNavTelemetry = () => {
      throw new Error("the collector is down");
    };
    expect(() =>
      telemetry.emit(telemetry.OPERATIONS.drawer, telemetry.OUTCOMES.opened),
    ).not.toThrow();
  });
});

describe("the event schema", () => {
  test("carries the component, the operation and the outcome", () => {
    telemetry.emit(telemetry.OPERATIONS.drawer, telemetry.OUTCOMES.opened);
    expect(events).toEqual([
      { component: "weaver-mobile-nav", operation: "drawer", outcome: "opened" },
    ]);
  });

  test("carries a reason only when one is given", () => {
    telemetry.emit(
      telemetry.OPERATIONS.drawer,
      telemetry.OUTCOMES.closed,
      telemetry.REASONS.escape,
    );
    expect(events[0].reason).toBe("escape");

    events.length = 0;
    telemetry.emit(telemetry.OPERATIONS.drawer, telemetry.OUTCOMES.opened);
    expect("reason" in events[0]).toBe(false);
  });

  test("has no field outside the fixed set", () => {
    for (const outcome of Object.values(telemetry.OUTCOMES)) {
      for (const reason of [undefined, ...Object.values(telemetry.REASONS)]) {
        events.length = 0;
        telemetry.emit(telemetry.OPERATIONS.drawer, outcome, reason);
        for (const event of events) {
          expect(Object.keys(event).sort()).toEqual(
            ALLOWED_FIELDS.filter((f) => f in event).sort(),
          );
        }
      }
    }
  });

  test("drops an operation, outcome or reason outside its vocabulary", () => {
    /* A caller passing something unrecognised is a bug in the caller, and
       widening the schema at runtime would break the promise this module
       makes about what can leave the page. */
    telemetry.emit("navigate", telemetry.OUTCOMES.opened);
    telemetry.emit(telemetry.OPERATIONS.drawer, "/weaver/install/");
    telemetry.emit(telemetry.OPERATIONS.drawer, telemetry.OUTCOMES.closed, "user-42");
    expect(events).toEqual([]);
  });

  test("refuses a payload smuggled in as an operation", () => {
    telemetry.emit({ path: "/weaver/safety/" }, telemetry.OUTCOMES.opened);
    expect(events).toEqual([]);
  });
});

describe("the copy seam", () => {
  test("reports success without reporting what was copied", async () => {
    const written = [];
    globalThis.navigator = { clipboard: { writeText: async (t) => written.push(t) } };

    expect(await telemetry.copy("cargo install weaver")).toBe(true);

    expect(written).toEqual(["cargo install weaver"]);
    expect(events).toEqual([
      { component: "weaver-mobile-nav", operation: "clipboard", outcome: "copied" },
    ]);
    expect(JSON.stringify(events)).not.toContain("cargo");
  });

  test("reports a refusal as a bounded reason", async () => {
    globalThis.navigator = {
      clipboard: {
        writeText: async () => {
          throw new Error("NotAllowedError: /weaver/install/ denied");
        },
      },
    };

    expect(await telemetry.copy("weaver --capabilities")).toBe(false);

    expect(events).toEqual([
      {
        component: "weaver-mobile-nav",
        operation: "clipboard",
        outcome: "failed",
        reason: "rejected",
      },
    ]);
    /* The rejection carried a path; the event must not. */
    expect(JSON.stringify(events)).not.toContain("/weaver/");
  });

  test("reports an absent clipboard rather than throwing", async () => {
    globalThis.navigator = {};

    expect(await telemetry.copy("cargo install weaver")).toBe(false);

    expect(events[0]).toEqual({
      component: "weaver-mobile-nav",
      operation: "clipboard",
      outcome: "failed",
      reason: "unavailable",
    });
  });

  test("copies nothing anywhere when no sink is installed", async () => {
    globalThis.df12WeaverNavTelemetry = undefined;
    const written = [];
    globalThis.navigator = { clipboard: { writeText: async (t) => written.push(t) } };

    expect(await telemetry.copy("cargo install weaver")).toBe(true);

    /* The copy still happens; only the reporting is optional. */
    expect(written).toEqual(["cargo install weaver"]);
    expect(events).toEqual([]);
  });
});
