/* Tests for the generator that feeds both mobile-navigation suites.
 *
 * `exhaustiveTransitionSequences` supplies every trace the Weaver and Netsuke
 * drawer tests run. Both suites iterate whatever it returns, so if it ever
 * returned an empty array — a wrong comparison in the recursion, a `depth`
 * that stopped one step early — both would pass having asserted nothing at
 * all, and would keep passing. Nothing else in either suite would notice: a
 * loop over no items is not a failure.
 *
 * These are the assertions that make those suites non-vacuous. They pin the
 * count, which is what a silent truncation changes; the shape of every trace,
 * which is what a wrong starting state changes; and the coverage of the
 * transition set, which is what dropping one from `TRANSITIONS` changes.
 */
import { describe, expect, test } from "bun:test";
import { exhaustiveTransitionSequences, TRANSITIONS } from "./helpers/mobile-nav-harness.mjs";

/* The traces of length 2..depth over `TRANSITIONS`, all of them prefixed by
   the opening `toggle`. For depth d that is the sum of |T|^k for k in 1..d-1,
   which for six transitions is 6 + 36 + 216 = 258 at depth 4. Computed here
   rather than hard-coded, so the expectation follows the transition set if a
   transition is ever added. */
function expectedCount(depth) {
  let total = 0;
  for (let k = 1; k < depth; k += 1) total += TRANSITIONS.length ** k;
  return total;
}

describe("exhaustiveTransitionSequences", () => {
  test("returns traces, which is what stops both drawer suites being vacuous", () => {
    const sequences = exhaustiveTransitionSequences({ depth: 4 });
    expect(sequences.length).toBeGreaterThan(0);
    expect(sequences.length).toBe(expectedCount(4));
    expect(sequences.length).toBe(258);
  });

  test("grows as the depth does, so the budget is the depth", () => {
    expect(exhaustiveTransitionSequences({ depth: 2 }).length).toBe(expectedCount(2));
    expect(exhaustiveTransitionSequences({ depth: 3 }).length).toBe(expectedCount(3));
    expect(exhaustiveTransitionSequences({ depth: 5 }).length).toBe(expectedCount(5));
  });

  test("every trace opens the drawer first", () => {
    /* A closed drawer ignores almost everything, so a trace that did not open
       it would prove nothing about the focus trap it is there to exercise. */
    for (const trace of exhaustiveTransitionSequences({ depth: 4 })) {
      expect(trace[0]).toBe("toggle");
    }
  });

  test("every trace is between two and depth transitions long", () => {
    const depth = 4;
    for (const trace of exhaustiveTransitionSequences({ depth })) {
      expect(trace.length).toBeGreaterThanOrEqual(2);
      expect(trace.length).toBeLessThanOrEqual(depth);
    }
  });

  test("every transition appears, so none is enumerated in name only", () => {
    const seen = new Set();
    for (const trace of exhaustiveTransitionSequences({ depth: 4 })) {
      for (const transition of trace) seen.add(transition);
    }
    expect([...seen].sort()).toEqual([...TRANSITIONS].sort());
  });

  test("every transition follows the opening toggle at least once", () => {
    /* Coverage of the set is weaker than it looks if one transition only ever
       appears as the first element. */
    const second = new Set(
      exhaustiveTransitionSequences({ depth: 4 })
        .filter((trace) => trace.length > 1)
        .map((trace) => trace[1]),
    );
    expect([...second].sort()).toEqual([...TRANSITIONS].sort());
  });

  test("no two traces are the same", () => {
    const traces = exhaustiveTransitionSequences({ depth: 4 });
    const unique = new Set(traces.map((trace) => trace.join(",")));
    expect(unique.size).toBe(traces.length);
  });
});
