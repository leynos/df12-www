/**
 * @file Tests that the stylelint gate actually gates.
 *
 * `tests/test_stylelint_gate.py` covers the wiring: it replaces `bun` with a
 * cmd-mox double and proves `make stylelint` calls `bun run lint:css` and
 * propagates a non-zero exit. That says nothing about the linter itself. With
 * the double in place the rules never run, so a `stylelint.config.js` that
 * had been loosened into silence — every rule off, or a `files` glob
 * matching nothing — would satisfy every assertion there.
 *
 * These tests close that half by running the real thing. A violation is
 * written into the tree stylelint is configured to scan, and the gate is
 * required to fail on it and to pass again once it is gone. That is the same
 * shape as `lint-gate.test.mjs`, and for the same reason: asserting the
 * configuration says what it says would only prove the file's contents, not
 * that stylelint agrees.
 *
 * The fixture is removed in `afterEach` whether the assertion passed or not,
 * so nothing is left behind for the next run — or for `make all` — to trip
 * over.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { existsSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

/* Inside `src/styles/`, which is the tree `lint:css` scans. A fixture outside
   it would pass by being unseen, which would prove nothing. */
const FIXTURE = join(REPO_ROOT, "src", "styles", "stylelint-gate-fixture.css");

/* Two violations the standard preset reports and `--fix` alone cannot excuse:
   a colour written in the legacy comma form, and a redundant longhand after
   its shorthand. Written otherwise-tidy so a failure is attributable to the
   rules rather than to stray whitespace. */
const VIOLATION = `.stylelint-gate-fixture {
  color: rgba(0, 0, 0, 0.5);
  overflow: hidden;
  overflow-y: hidden;
}
`;

/* CSS the preset accepts, used to prove the gate's verdict tracks the content
   rather than the mere presence of another file. */
const CLEAN = `.stylelint-gate-fixture {
  color: rgb(0 0 0 / 50%);
  overflow: hidden;
}
`;

/* Run a make target and report how it exited. MAKEFLAGS is cleared because
   the suite may itself run under a parent make. */
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

describe("the stylelint target", () => {
  test("passes on the tree as committed", () => {
    expect(existsSync(FIXTURE)).toBe(false);
    expect(make("stylelint").status).toBe(0);
  });

  test("fails on an introduced violation, and passes once it is removed", () => {
    expect(existsSync(FIXTURE)).toBe(false);

    writeFileSync(FIXTURE, VIOLATION);
    const dirty = make("stylelint");
    expect(dirty.status).not.toBe(0);
    expect(dirty.output).toContain("color-function-notation");
    expect(dirty.output).toContain("declaration-block-no-redundant-longhand-properties");

    rmSync(FIXTURE);
    expect(make("stylelint").status).toBe(0);
  });

  test("passes on a conforming file, so the verdict tracks content not presence", () => {
    writeFileSync(FIXTURE, CLEAN);
    expect(make("stylelint").status).toBe(0);
  });

  test("names the offending file, so a failure is actionable", () => {
    writeFileSync(FIXTURE, VIOLATION);
    expect(make("stylelint").output).toContain("stylelint-gate-fixture.css");
  });

  test("leaves no fixture behind", () => {
    expect(existsSync(FIXTURE)).toBe(false);
    const tracked = spawnSync("git", ["status", "--porcelain"], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    });
    expect(tracked.stdout).not.toContain("stylelint-gate-fixture");
  });
});
