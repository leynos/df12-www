/**
 * @file The drawer harness's own contract: what `setUp` borrows, `tearDown`
 * returns.
 *
 * `evaluateScript` runs the shipped scripts against this process's
 * `globalThis`, so whatever `setUp` installs there outlives the test file
 * unless `tearDown` puts the previous values back. These suites seed
 * sentinels first, so restoration is asserted by identity rather than by
 * everything happening to be `undefined`. Drive them with `bun test`; each
 * test wraps its scenario in `withSentinels`, which owns the seeding and the
 * cleanup.
 */
import { afterEach, describe, expect, test } from "bun:test";
import fc from "fast-check";

import { setUp, tearDown } from "./helpers/weaver-drawer.mjs";

const GLOBALS = ["df12WeaverNavTelemetry", "df12WeaverTelemetry", "df12WeaverCopy"];

/* Belt and braces: if an assertion throws before a test's own tearDown call,
   this still runs, and a second call after a manual one is a no-op. */
afterEach(tearDown);

/* Seed one distinct sentinel per global, run the scenario, and assert the
   sentinels came back by identity. The pre-seeding property descriptors are
   snapshotted and restored — not merely deleted — and `tearDown` runs in the
   cleanup itself, so a scenario that throws after `setUp` cannot leave the
   file-level `afterEach` to resurrect the sentinels as another test's
   "pre-setup" state. */
function withSentinels(scenario) {
  const descriptors = {};
  const sentinels = {};
  for (const name of GLOBALS) {
    descriptors[name] = Object.getOwnPropertyDescriptor(globalThis, name);
    sentinels[name] = () => name;
    globalThis[name] = sentinels[name];
  }
  try {
    scenario();
    for (const name of GLOBALS) {
      expect(globalThis[name]).toBe(sentinels[name]);
    }
  } finally {
    try {
      tearDown();
      /* Asserted here, before the descriptor restoration below, so a failing
         scenario still verifies that `tearDown` itself put the borrowed
         values back — the restoration must not mask a `tearDown` that did
         not do its job. */
      for (const name of GLOBALS) {
        expect(globalThis[name]).toBe(sentinels[name]);
      }
    } finally {
      /* Restored even when the verification above throws, so a failed
         teardown cannot leave the sentinels installed to contaminate
         whichever test runs next. */
      for (const name of GLOBALS) {
        if (descriptors[name] === undefined) {
          delete globalThis[name];
        } else {
          Object.defineProperty(globalThis, name, descriptors[name]);
        }
      }
    }
  }
}

describe("the harness returns the globals it borrowed", () => {
  test("after a setup without telemetry", () => {
    withSentinels(() => {
      setUp({ telemetry: false });
      tearDown();
    });
  });

  test("after a setup with telemetry", () => {
    withSentinels(() => {
      setUp({ telemetry: true });
      tearDown();
    });
  });

  test("after several setups in one test", () => {
    /* The snapshot is taken on the first `setUp` and only then, so a test
       driving both modes still gets its file's original state back. */
    withSentinels(() => {
      setUp({ telemetry: false });
      setUp({ telemetry: true });
      tearDown();
    });
  });

  test("even when the scenario itself fails", () => {
    /* A scenario that throws after `setUp` never reaches its own
       `tearDown`; the cleanup must still restore the true pre-sentinel
       state rather than leaving the file-level `afterEach` to reinstate
       the sentinels. */
    /* Earlier suites in the same process may have left these as own
       properties holding `undefined`; the promise is the exact descriptor
       state from before the sentinels, whatever it was. */
    const before = GLOBALS.map((name) => Object.getOwnPropertyDescriptor(globalThis, name));
    expect(() =>
      withSentinels(() => {
        setUp({ telemetry: true });
        throw new Error("the scenario failed");
      }),
    ).toThrow("the scenario failed");
    GLOBALS.forEach((name, index) => {
      expect(Object.getOwnPropertyDescriptor(globalThis, name)).toEqual(before[index]);
    });
  });

  test("whatever trace of setups, modes, and failures a test takes", () => {
    /* The example tests pin four representative traces; this generates the
       rest. A trace is a sequence of setUp calls in either telemetry mode,
       any of which may be followed by an injected scenario failure, ending
       in `tearDown` — after which the sentinels must be back by identity
       (asserted inside `withSentinels`) and the pre-sentinel descriptors
       must be back exactly (asserted here). */
    const steps = fc.array(fc.record({ telemetry: fc.boolean(), fails: fc.boolean() }), {
      minLength: 1,
      maxLength: 4,
    });
    const before = GLOBALS.map((name) => Object.getOwnPropertyDescriptor(globalThis, name));
    fc.assert(
      fc.property(steps, (trace) => {
        withSentinels(() => {
          for (const step of trace) {
            setUp({ telemetry: step.telemetry });
            if (step.fails) {
              try {
                throw new Error("an injected scenario failure");
              } catch {
                /* The failure is the test's own; what matters is that the
                   trace continues and restoration still holds at the end. */
              }
            }
          }
          tearDown();
        });
        for (const [index, name] of GLOBALS.entries()) {
          expect(Object.getOwnPropertyDescriptor(globalThis, name)).toEqual(before[index]);
        }
      }),
    );
  });

  test("a trace that aborts mid-way still restores the descriptors", () => {
    /* Complementing the caught-failure property above: here the failure
       propagates out of the scenario, so `withSentinels`' cleanup path is
       the only thing standing between the sentinels and the next test. */
    const positions = fc.record({
      setups: fc.integer({ min: 1, max: 3 }),
      telemetry: fc.boolean(),
    });
    const before = GLOBALS.map((name) => Object.getOwnPropertyDescriptor(globalThis, name));
    fc.assert(
      fc.property(positions, ({ setups, telemetry }) => {
        expect(() =>
          withSentinels(() => {
            for (let i = 0; i < setups; i += 1) {
              setUp({ telemetry });
            }
            throw new Error("the trace aborted");
          }),
        ).toThrow("the trace aborted");
        for (const [index, name] of GLOBALS.entries()) {
          expect(Object.getOwnPropertyDescriptor(globalThis, name)).toEqual(before[index]);
        }
      }),
    );
  });
});
