/**
 * @file Tests that the TypeScript gate actually gates.
 *
 * `make typecheck` runs `tsc --noEmit` over the browser project and the build
 * scripts project. The compile step uses swc, which strips types without
 * checking them, so this gate is the only thing standing between a wrongly
 * typed module and the published site. A test that only asserted the tree is
 * currently clean would not prove the wiring: the gate could be passing
 * because it checks nothing. So, as `lint-gate.test.mjs` does for Biome,
 * these introduce a type error into each project in turn and require the
 * gate to fail on it, then prove the vendor exclusion by putting the same
 * error where the gate must not look.
 *
 * Each fixture is written inside a tree the projects already include and is
 * removed in `afterEach` whether the assertion passed or not.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, rmdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const BROWSER_FIXTURE = join(
  REPO_ROOT,
  "src",
  "static",
  "netsuke",
  "assets",
  "js",
  "typecheck-gate-fixture.ts",
);
const SCRIPTS_FIXTURE = join(REPO_ROOT, "scripts", "typecheck-gate-fixture.ts");
const VENDOR_DIR = join(REPO_ROOT, "src", "static", "netsuke", "assets", "js", "vendor");
const VENDOR_FIXTURE = join(VENDOR_DIR, "typecheck-gate-fixture.ts");

/* A classic-script fixture with one deliberate error. Written in the house
   shape so that the failure is attributable to the checker rather than to the
   file being an unexpected kind of module. */
const BAD_BROWSER = `(() => {
  "use strict";
  const count: number = document.title;
  return count;
})();
`;

/* A module fixture for the scripts project, with the same class of error. */
const BAD_SCRIPT = `/** A fixture. @module */
export const count: number = "not a number";
`;

/* A fixture the checker would reject if it were in scope. The wrong type is
   marked with a suppression that itself becomes an error when it suppresses
   nothing, so the file fails on either reading if it is ever checked. */
const BAD_VENDORED = `// @ts-expect-error vendored code is not checked
const count: number = "not a number";
export { count };
`;

/* Run the gate and report how it exited. */
function typecheck() {
  const result = spawnSync("make", ["typecheck-js"], {
    cwd: REPO_ROOT,
    encoding: "utf8",
    env: { ...process.env, MAKEFLAGS: "" },
  });
  return { status: result.status, output: `${result.stdout ?? ""}${result.stderr ?? ""}` };
}

const written = [];
const created = [];

afterEach(() => {
  while (written.length) rmSync(written.pop(), { force: true });
  while (created.length) rmdirSync(created.pop());
});

describe("the typecheck-js target", () => {
  test("runs tsc over both projects", () => {
    const { status, output } = typecheck();
    expect(status).toBe(0);
    expect(output).toContain("tsc -p tsconfig.browser.json --noEmit");
    expect(output).toContain("tsc -p tsconfig.scripts.json --noEmit");
  });

  test("fails on a type error in a browser script, and passes once it is removed", () => {
    expect(existsSync(BROWSER_FIXTURE)).toBe(false);
    written.push(BROWSER_FIXTURE);
    writeFileSync(BROWSER_FIXTURE, BAD_BROWSER);

    const dirty = typecheck();
    expect(dirty.status).not.toBe(0);
    expect(dirty.output).toContain("typecheck-gate-fixture.ts");
    expect(dirty.output).toContain("error TS2322");

    rmSync(written.pop());
    expect(typecheck().status).toBe(0);
  });

  test("fails on a type error in a build script too", () => {
    written.push(SCRIPTS_FIXTURE);
    writeFileSync(SCRIPTS_FIXTURE, BAD_SCRIPT);

    const dirty = typecheck();
    expect(dirty.status).not.toBe(0);
    expect(dirty.output).toContain("scripts/typecheck-gate-fixture.ts");
    expect(dirty.output).toContain("error TS2322");
  });

  test("keeps vendored code out of scope, so the gate ignores what is written there", () => {
    if (!existsSync(VENDOR_DIR)) {
      mkdirSync(VENDOR_DIR, { recursive: true });
      created.push(VENDOR_DIR);
    }
    written.push(VENDOR_FIXTURE);
    writeFileSync(VENDOR_FIXTURE, BAD_VENDORED);
    /* The same file at BROWSER_FIXTURE fails the gate, so a pass here is the
       exclusion doing the work rather than the fixture being clean. */
    expect(typecheck().status).toBe(0);
  });

  test("leaves no fixture behind", () => {
    expect(existsSync(BROWSER_FIXTURE)).toBe(false);
    expect(existsSync(SCRIPTS_FIXTURE)).toBe(false);
    expect(existsSync(VENDOR_FIXTURE)).toBe(false);
  });
});
