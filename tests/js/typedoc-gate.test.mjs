/* Regression tests for the TypeDoc documentation gate.
 *
 * Each case runs the repository-pinned executable against an isolated fixture
 * in a temporary directory, so a failure proves something about TypeDoc's
 * validation rather than about the state of this repository. The last case is
 * the exception: it runs the real configuration, which is the assertion that
 * the gate currently passes.
 *
 * The gate exists because `validation.notDocumented` is worthless unless
 * `treatValidationWarningsAsErrors` is also set — TypeDoc reports undocumented
 * API as a warning and exits zero otherwise, so a gate missing that one line
 * looks configured and enforces nothing.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const TYPEDOC = join(REPO_ROOT, "node_modules", ".bin", "typedoc");

const created = [];

afterEach(() => {
  while (created.length) rmSync(created.pop(), { force: true, recursive: true });
});

/* A second, fully documented module. It is here because TypeDoc collapses a
   single entry point into the project root, which is not validated as a
   Module — so a one-file fixture would pass whatever its module comment said,
   and the module cases below would prove nothing. */
const SUPPORT = `/** A documented support module. @module */

/** Return support. */
export function supportFunction(): string {
  return "support";
}
`;

/* Run the pinned TypeDoc over a fixture, under the same validation settings
   the repository uses. Returns its exit status and output. */
function runFixture(source, { treatWarningsAsErrors = true } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "df12-typedoc-"));
  created.push(dir);
  const sourceDir = join(dir, "src");
  mkdirSync(sourceDir);
  writeFileSync(join(sourceDir, "fixture.ts"), source);
  writeFileSync(join(sourceDir, "support.ts"), SUPPORT);
  writeFileSync(
    join(dir, "tsconfig.json"),
    JSON.stringify({
      compilerOptions: { strict: true, noEmit: true, skipLibCheck: true },
      include: ["src/**/*.ts"],
    }),
  );
  writeFileSync(
    join(dir, "typedoc.json"),
    JSON.stringify({
      tsconfig: join(dir, "tsconfig.json"),
      entryPoints: [sourceDir],
      entryPointStrategy: "expand",
      commentStyle: "jsdoc",
      emit: "none",
      validation: { notDocumented: true },
      treatValidationWarningsAsErrors: treatWarningsAsErrors,
      requiredToBeDocumented: ["Module", "Function"],
    }),
  );

  const result = spawnSync(TYPEDOC, ["--options", join(dir, "typedoc.json")], {
    cwd: dir,
    encoding: "utf8",
  });
  return { status: result.status, output: `${result.stdout ?? ""}${result.stderr ?? ""}` };
}

const DOCUMENTED = `/** A documented module. @module */

/** Return a greeting. */
export function greet(): string {
  return "hello";
}
`;

describe("the TypeDoc gate", () => {
  test("passes a module and function that are both documented", () => {
    const { status } = runFixture(DOCUMENTED);
    expect(status).toBe(0);
  });

  test("fails an undocumented exported function", () => {
    const { status, output } = runFixture(`/** A documented module. @module */

export function greet(): string {
  return "hello";
}
`);
    expect(status).not.toBe(0);
    expect(output).toContain("does not have any documentation");
  });

  test("fails a module with no module comment", () => {
    const { status, output } = runFixture(`/** Return a greeting. */
export function greet(): string {
  return "hello";
}
`);
    expect(status).not.toBe(0);
    expect(output).toContain("does not have any documentation");
  });

  test("does not accept a plain block comment as documentation", () => {
    /* commentStyle is "jsdoc", so `/* ... *\/` is a comment and `/** ... *\/`
       is documentation. This is the trap worth having a test for: the browser
       scripts here are commented in the former style throughout. */
    const { status } = runFixture(`/* A module comment in the wrong style. @module */

/* Return a greeting. */
export function greet(): string {
  return "hello";
}
`);
    expect(status).not.toBe(0);
  });

  test("reports but tolerates the same fixture without treatValidationWarningsAsErrors", () => {
    const undocumented = `/** A documented module. @module */

export function greet(): string {
  return "hello";
}
`;
    const { status, output } = runFixture(undocumented, { treatWarningsAsErrors: false });
    expect(output).toContain("does not have any documentation");
    expect(status).toBe(0);
  });
});

describe("the repository's own configuration", () => {
  test("passes, so `make docs-check` gates rather than merely reports", () => {
    const result = spawnSync("bun", ["run", "docs:check"], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    });
    expect(`${result.stdout ?? ""}${result.stderr ?? ""}`).not.toContain(
      "does not have any documentation",
    );
    expect(result.status).toBe(0);
  });

  test("treats validation warnings as errors, which is what makes it a gate", () => {
    const config = spawnSync("bun", ["-e", "console.log(await Bun.file('typedoc.json').text())"], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    }).stdout;
    expect(config).toContain('"treatValidationWarningsAsErrors": true');
    expect(config).toContain('"notDocumented": true');
  });
});
