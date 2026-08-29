/* The drawer harness's own contract: what `setUp` borrows, `tearDown` returns.
 *
 * `evaluateScript` runs the shipped scripts against this process's
 * `globalThis`, so whatever `setUp` installs there outlives the test file
 * unless `tearDown` puts the previous values back. These seed sentinels
 * first, so restoration is asserted by identity rather than by everything
 * happening to be `undefined`.
 */
import { afterEach, describe, expect, test } from "bun:test";

import { setUp, tearDown } from "./helpers/weaver-drawer.mjs";

const GLOBALS = ["df12WeaverNavTelemetry", "df12WeaverTelemetry", "df12WeaverCopy"];

/* Belt and braces: if an assertion throws before a test's own tearDown call,
   this still runs, and a second call after a manual one is a no-op. */
afterEach(tearDown);

/* Seed one distinct sentinel per global, run the scenario, and hand back the
   sentinels for the identity assertions; the seeds are swept afterwards so
   they cannot become another test's "pre-setup" state. */
function withSentinels(scenario) {
  const sentinels = {};
  for (const name of GLOBALS) {
    sentinels[name] = () => name;
    globalThis[name] = sentinels[name];
  }
  try {
    scenario();
    for (const name of GLOBALS) {
      expect(globalThis[name]).toBe(sentinels[name]);
    }
  } finally {
    for (const name of GLOBALS) {
      delete globalThis[name];
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
});
