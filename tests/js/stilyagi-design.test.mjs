/* Tests for the Stilyagi design page's capability planner.
 *
 * The planner's whole job is to answer two questions from the enabled
 * ruleset: which linguistic providers must load, and what that costs at
 * start-up.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";

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
