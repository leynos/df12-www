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
import { existsSync, mkdirSync, rmdirSync, rmSync, writeFileSync } from "node:fs";
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

/* The excluded trees, and a file each one would reject if it were in scope.
   Asserting the strings in biome.jsonc would only prove the file says what it
   says; putting a misformatted fixture inside each tree proves Biome agrees. */
const EXCLUSIONS = [
  {
    tree: "tests/cassettes",
    fixture: join("tests", "cassettes", "exclusion-probe.json"),
    contents: '{"recorded":    true,\n     "by": "betamax"}\n',
  },
  {
    tree: "reference",
    fixture: join("reference", "exclusion-probe.html"),
    contents: "<!DOCTYPE html>\n<html><body><p   >kept as written</p></body></html>\n",
  },
  {
    tree: "src/static/**/vendor",
    fixture: join("src", "static", "netsuke", "assets", "js", "vendor", "exclusion-probe.js"),
    contents: "const   vendored   =   1;\nexport { vendored };\n",
  },
];

describe("the Biome configuration", () => {
  const written = [];
  const created = [];

  afterEach(() => {
    while (written.length) rmSync(written.pop(), { force: true });
    /* Directories the fixtures had to invent go too, so a run leaves the tree
       exactly as it found it. Only ever empty ones, and only ones this file
       created. */
    while (created.length) rmdirSync(created.pop());
  });

  for (const { tree, fixture, contents } of EXCLUSIONS) {
    test(`keeps ${tree} out of scope, so the gate ignores what is written there`, () => {
      const path = join(REPO_ROOT, fixture);
      if (!existsSync(dirname(path))) {
        mkdirSync(dirname(path), { recursive: true });
        created.push(dirname(path));
      }
      written.push(path);
      writeFileSync(path, contents);

      /* The same content inside a scanned tree fails the gate, so a pass here
         is the exclusion doing the work rather than the fixture being clean. */
      expect(make("lint").status).toBe(0);
    });
  }

  test("a misformatted file in a scanned tree does fail, so the probes mean something", () => {
    const path = join(REPO_ROOT, "src", "static", "netsuke", "assets", "js", "scope-probe.js");
    written.push(path);
    writeFileSync(path, "const   scoped   =   1;\nexport { scoped };\n");
    expect(make("lint").status).not.toBe(0);
  });

  test("parses the Tailwind directives the entrypoints use", () => {
    /* Both entrypoints open with `@source`; without the parser option Biome
       reports them as parse errors rather than checking them. */
    const { status, stdout } = spawnSync("bunx", ["biome", "check", "src/styles"], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    });
    expect(stdout).not.toContain("Tailwind-specific syntax is disabled");
    expect(status).toBe(0);
  });
});
