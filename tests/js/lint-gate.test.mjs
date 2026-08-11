/* Tests that the Biome gate actually gates.
 *
 * Biome was configured long before it was wired into `make lint`, and for as
 * long as it had to be run by hand its findings accumulated unseen — which is
 * how a `useIterableCallbackReturn` error reached review as a diagnostic
 * nobody had run. A test that only asserted the tree is currently clean would
 * not have caught that: the gate was passing because it was never invoked.
 * So these assert the wiring itself, by introducing a violation and requiring
 * the gate to fail on it.
 *
 * The fixture is written under `src/static/netsuke/assets/js/`, inside the
 * tree Biome already scans, and removed in `afterEach` whether the assertion
 * passed or not. Nothing is left behind for the next run to trip over.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const FIXTURE = join(REPO_ROOT, "src", "static", "netsuke", "assets", "js", "lint-gate-fixture.js");

/* The rule that got through on #48: a `map()` callback that returns nothing.
   Written pre-formatted, so a failure is attributable to the lint rule rather
   than to the formatter. */
const VIOLATION = `(() => {
  "use strict";
  var probe = [1, 2].map((n) => {
    n + 1;
  });
  return probe;
})();
`;

/* Run a make target and report how it exited. */
function make(target) {
  const result = spawnSync("make", [target], {
    cwd: REPO_ROOT,
    encoding: "utf8",
    env: { ...process.env, MAKEFLAGS: "" },
  });
  return { status: result.status, output: `${result.stdout ?? ""}${result.stderr ?? ""}` };
}

afterEach(() => {
  rmSync(FIXTURE, { force: true });
});

describe("the lint target", () => {
  test("runs Biome as well as Ruff", () => {
    const { output } = make("lint");
    expect(output).toContain("ruff check");
    expect(output).toContain("bun run lint:js");
    expect(output).toContain("biome check .");
  });

  test("passes on the tree as committed", () => {
    expect(make("lint").status).toBe(0);
  });

  test("fails on an introduced Biome violation, and passes once it is removed", () => {
    expect(existsSync(FIXTURE)).toBe(false);

    writeFileSync(FIXTURE, VIOLATION);
    const dirty = make("lint");
    expect(dirty.status).not.toBe(0);
    expect(dirty.output).toContain("lint/suspicious/useIterableCallbackReturn");

    rmSync(FIXTURE);
    expect(make("lint").status).toBe(0);
  });

  test("fails on a formatting violation too, since `biome check` covers both", () => {
    writeFileSync(FIXTURE, "const   badlyFormatted   =   1;\nexport { badlyFormatted };\n");
    const dirty = make("lint");
    expect(dirty.status).not.toBe(0);
    expect(dirty.output).toContain("Formatter would have printed");
  });

  test("leaves no fixture behind", () => {
    expect(existsSync(FIXTURE)).toBe(false);
    const tracked = spawnSync("git", ["status", "--porcelain"], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    });
    expect(tracked.stdout).not.toContain("lint-gate-fixture");
  });
});

describe("the Biome configuration", () => {
  const config = readFileSync(join(REPO_ROOT, "biome.jsonc"), "utf8");

  test("keeps generated and vendored trees out of scope", () => {
    for (const excluded of ["!tests/cassettes", "!reference", "!src/static/**/vendor"]) {
      expect(config).toContain(excluded);
    }
  });

  test("parses the Tailwind directives the entrypoints use", () => {
    expect(config).toContain("tailwindDirectives");
    const { status } = spawnSync("bun", ["run", "lint:js"], { cwd: REPO_ROOT, encoding: "utf8" });
    expect(status).toBe(0);
  });
});
