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
    tearDown();
    for (const name of GLOBALS) {
      if (descriptors[name] === undefined) {
        delete globalThis[name];
      } else {
        Object.defineProperty(globalThis, name, descriptors[name]);
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
    expect(() =>
      withSentinels(() => {
        setUp({ telemetry: true });
        throw new Error("the scenario failed");
      }),
    ).toThrow("the scenario failed");
    for (const name of GLOBALS) {
      expect(Object.getOwnPropertyDescriptor(globalThis, name)).toBeUndefined();
    }
  });
});
