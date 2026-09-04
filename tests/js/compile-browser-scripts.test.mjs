/**
 * @file Tests for the browser-script compile step and the copy step's `.ts` skip.
 *
 * `scripts/compile-browser-scripts.ts` decides which files under `src/static`
 * are browser scripts, where each one lands under `public/`, and what swc is
 * allowed to change on the way. The templates load the output as classic
 * scripts and the Bun suites `require` it for its guarded `module.exports`, so
 * the shape swc preserves is a contract, not an implementation detail. These
 * tests pin the three exported decisions directly, and then run the real
 * script and `copy-static.ts` as subprocesses against an isolated source tree
 * to prove the two steps agree about who owns a `.ts` file.
 *
 * The path properties are checked with fast-check over generated trees rather
 * than a handful of examples, because the classifier's job is to say no to
 * every path that is not a browser script — vendored code, declarations, a
 * `.ts` outside `assets/js` — and a list of examples only proves the ones it
 * happened to include.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  utimesSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import fc from "fast-check";

import {
  compileClassicScript,
  isBrowserScript,
  targetFor,
} from "../../scripts/compile-browser-scripts.ts";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

/* The roots the script derives from the working directory the suite runs in,
   which `make test-js` sets to the repository root. */
const SOURCE_ROOT = join(process.cwd(), "src", "static");
const TARGET_ROOT = join(process.cwd(), "public");

const source = (...parts) => join(SOURCE_ROOT, ...parts);

describe("isBrowserScript", () => {
  test("accepts a .ts file directly under a site's assets/js", () => {
    expect(isBrowserScript(source("netsuke", "assets", "js", "doc-search.ts"))).toBe(true);
  });

  test("accepts a .ts file in a subdirectory of assets/js", () => {
    expect(isBrowserScript(source("netsuke", "assets", "js", "lib", "util.ts"))).toBe(true);
  });

  test("rejects a declaration file, which has no runtime form", () => {
    expect(isBrowserScript(source("netsuke", "assets", "js", "globals.d.ts"))).toBe(false);
    expect(isBrowserScript(source("browser-globals.d.ts"))).toBe(false);
  });

  test("rejects vendored code anywhere on the path", () => {
    expect(isBrowserScript(source("netsuke", "assets", "js", "vendor", "lib.ts"))).toBe(false);
    expect(isBrowserScript(source("netsuke", "assets", "vendor", "js", "lib.ts"))).toBe(false);
  });

  test("rejects a .ts file outside assets/js", () => {
    expect(isBrowserScript(source("netsuke", "assets", "lib.ts"))).toBe(false);
    expect(isBrowserScript(source("netsuke", "js", "lib.ts"))).toBe(false);
    expect(isBrowserScript(source("netsuke", "assets", "styles", "js", "lib.ts"))).toBe(false);
  });

  test("rejects anything that is not TypeScript", () => {
    expect(isBrowserScript(source("netsuke", "assets", "js", "tailwind-config.js"))).toBe(false);
    expect(isBrowserScript(source("netsuke", "assets", "js", "notes.tsx"))).toBe(false);
    expect(isBrowserScript(source("netsuke", "assets", "js", "ts"))).toBe(false);
  });
});

/* A directory name that is neither of the two the classifier looks for, nor
   the vendor marker, so the generators can place those deliberately. */
const plainSegment = fc
  .stringMatching(/^[a-z][a-z0-9-]{0,7}$/)
  .filter((name) => !["assets", "js", "vendor"].includes(name));

const segment = fc.oneof(
  { weight: 3, arbitrary: plainSegment },
  fc.constant("assets"),
  fc.constant("js"),
  fc.constant("vendor"),
);

const extension = fc.constantFrom(".ts", ".d.ts", ".js", ".mjs", ".css", ".json", "");

const generatedPath = fc
  .record({
    dirs: fc.array(segment, { minLength: 1, maxLength: 6 }),
    stem: plainSegment,
    ext: extension,
  })
  .map(({ dirs, stem, ext }) => ({ dirs, name: `${stem}${ext}` }));

/* The classifier's specification, written from the rule rather than the code:
   a `.ts` that is not a declaration, with no `vendor` directory above it, in a
   directory tree that somewhere contains an `assets/js` pair. */
function specifiesBrowserScript({ dirs, name }) {
  const isTs = name.endsWith(".ts") && !name.endsWith(".d.ts");
  const vendored = dirs.includes("vendor");
  const underScripts = dirs.some((dir, i) => dir === "assets" && dirs[i + 1] === "js");
  return isTs && !vendored && underScripts;
}

describe("isBrowserScript over generated trees", () => {
  test("agrees with the specification for every generated path", () => {
    fc.assert(
      fc.property(generatedPath, (path) => {
        const absolute = source(...path.dirs, path.name);
        expect(isBrowserScript(absolute)).toBe(specifiesBrowserScript(path));
      }),
    );
  });
});

/* A path that is a browser script by construction: plain segments around an
   `assets/js` pair, no `vendor` anywhere, and a `.ts` name. Built directly
   rather than by filtering `generatedPath`, which qualifies well under one
   time in a hundred and would leave fast-check discarding most of its draws. */
const browserScriptPath = fc
  .record({
    before: fc.array(plainSegment, { maxLength: 2 }),
    after: fc.array(plainSegment, { maxLength: 2 }),
    stem: plainSegment,
  })
  .map(({ before, after, stem }) => ({
    dirs: [...before, "assets", "js", ...after],
    name: `${stem}.ts`,
  }));

describe("targetFor", () => {
  test("mirrors the source path under public/ with a .js extension", () => {
    expect(targetFor(source("netsuke", "assets", "js", "doc-search.ts"))).toBe(
      join(TARGET_ROOT, "netsuke", "assets", "js", "doc-search.js"),
    );
  });

  test("keeps every directory and the file stem for every generated script", () => {
    fc.assert(
      fc.property(browserScriptPath, (path) => {
        expect(specifiesBrowserScript(path)).toBe(true);
        expect(isBrowserScript(source(...path.dirs, path.name))).toBe(true);
        const target = targetFor(source(...path.dirs, path.name));
        const rel = relative(TARGET_ROOT, target).split(sep);
        expect(rel.slice(0, -1)).toEqual(path.dirs);
        expect(rel.at(-1)).toBe(path.name.replace(/\.ts$/, ".js"));
        expect(target.startsWith(TARGET_ROOT + sep)).toBe(true);
      }),
    );
  });
});

/* A classic script in the house shape: a leading comment, an IIFE with a
   directive, a typed function, an interface, a typed DOM lookup, and the
   guarded export hook the Bun tests rely on. */
const CLASSIC = `/* A classic script. */
(() => {
  "use strict";
  interface Pair {
    a: number;
    b: number;
  }
  /* Add the pair. */
  function add(pair: Pair): number {
    return pair.a + pair.b;
  }
  const root = document.querySelector<HTMLElement>("[data-root]");
  if (!root) return;
  root.textContent = String(add({ a: 1, b: 2 }));
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { add };
  }
})();
`;

describe("compileClassicScript", () => {
  test("removes the types and nothing else that matters", async () => {
    const js = await compileClassicScript(CLASSIC, "classic.ts");
    expect(js).not.toContain("interface");
    expect(js).not.toContain(": number");
    expect(js).not.toContain("<HTMLElement>");
    expect(js).toContain('"use strict"');
    expect(js).toContain("/* A classic script. */");
    expect(js).toContain("/* Add the pair. */");
    expect(js).toContain('typeof module !== "undefined"');
    expect(js).not.toContain("export ");
    expect(js).not.toContain("import ");
  });

  test("stays a classic script, so the output runs under new Function and exports", async () => {
    const js = await compileClassicScript(CLASSIC, "classic.ts");
    const fakeModule = { exports: {} };
    const root = { textContent: "" };
    const fakeDocument = { querySelector: () => root };
    const run = new Function("module", "document", js);
    run(fakeModule, fakeDocument);
    expect(root.textContent).toBe("3");
    expect(typeof fakeModule.exports.add).toBe("function");
    expect(fakeModule.exports.add({ a: 2, b: 3 })).toBe(5);
  });

  test("keeps the directive as the first statement of the IIFE", async () => {
    const js = await compileClassicScript(CLASSIC, "classic.ts");
    expect(js).toMatch(/\(\(\)\s*=>\s*\{\s*"use strict";/);
  });
});

/* ------------------------------------------------------------------------
 * What the compile step's own header claims about the output.
 * --------------------------------------------------------------------- */

/* The header comment of `scripts/compile-browser-scripts.ts`, stripped of its
   comment markers and rewrapped as one line, so a claim may be matched
   whatever width it happens to be wrapped at. */
function compilerHeader() {
  const source = readFileSync(join(REPO_ROOT, "scripts", "compile-browser-scripts.ts"), "utf8");
  const header = source.slice(0, source.indexOf("@module"));
  return header
    .replace(/^\s*\/?\*+\/?/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

describe("the compile step's header", () => {
  test("does not claim that every browser script is deferred", () => {
    /* It is not true of Weaver's two, and the header said so for a while.
       Any sentence tying `defer` to all, every, or each script fails here. */
    const header = compilerHeader();
    for (const claim of [
      /\ball\b[^.]{0,80}scripts?[^.]{0,80}defer/i,
      /\bevery\b[^.]{0,80}script[^.]{0,80}defer/i,
      /\beach\b[^.]{0,80}script[^.]{0,80}defer/i,
      /IIFE per file, loaded with a plain `<script defer>`/i,
    ]) {
      expect(header).not.toMatch(claim);
    }
  });

  test("names the two loading modes and where each is used", () => {
    const header = compilerHeader();
    expect(header).toContain("fourteen of the sixteen scripts are loaded with `<script defer>`");
    expect(header).toContain("Weaver's `telemetry.ts` and `mobile-nav.ts`");
    expect(header).toContain("end of `<body>`");
  });

  test("still explains the classic-script shape the compile preserves", () => {
    const header = compilerHeader();
    expect(header).toContain("classic scripts");
    expect(header).toContain("isModule: false");
    expect(header).toContain("module.exports");
    expect(header).toContain("no module or syntax transform is applied");
  });
});

/* ------------------------------------------------------------------------
 * The scripts as the build runs them, against an isolated tree.
 * --------------------------------------------------------------------- */

const created = [];

afterEach(() => {
  while (created.length) rmSync(created.pop(), { force: true, recursive: true });
});

/* Build a throwaway repository root holding one site with a browser script,
   a vendored script, a declaration file, a `.ts` outside `assets/js`, and two
   plain assets, and return its path. */
function fixtureTree() {
  const root = mkdtempSync(join(tmpdir(), "df12-compile-"));
  created.push(root);
  const site = join(root, "src", "static", "site", "assets");
  mkdirSync(join(site, "js", "vendor"), { recursive: true });
  mkdirSync(join(site, "styles"), { recursive: true });
  writeFileSync(join(site, "js", "widget.ts"), CLASSIC);
  writeFileSync(join(site, "js", "vendor", "lib.ts"), "const vendored: number = 1;\n");
  writeFileSync(join(site, "js", "globals.d.ts"), "declare const x: number;\n");
  writeFileSync(join(site, "js", "plain.js"), "// plain\n");
  writeFileSync(join(site, "styles", "helper.ts"), "export const a = 1;\n");
  writeFileSync(join(site, "styles", "site.css"), "body{}\n");
  return root;
}

/* Run one of the build scripts from the repository with `cwd` as its root. */
function runScript(name, cwd) {
  const result = spawnSync("bun", ["run", join(REPO_ROOT, "scripts", name)], {
    cwd,
    encoding: "utf8",
  });
  return { status: result.status, output: `${result.stdout ?? ""}${result.stderr ?? ""}` };
}

describe("compile-browser-scripts.ts as a build step", () => {
  test("compiles exactly the browser scripts, to their mirrored paths", () => {
    const root = fixtureTree();
    const { status, output } = runScript("compile-browser-scripts.ts", root);
    expect(status).toBe(0);
    expect(output).toContain("browser scripts: 1 compiled, 0 up to date");

    const out = join(root, "public", "site", "assets");
    expect(existsSync(join(out, "js", "widget.js"))).toBe(true);
    expect(existsSync(join(out, "js", "vendor", "lib.js"))).toBe(false);
    expect(existsSync(join(out, "js", "globals.js"))).toBe(false);
    expect(existsSync(join(out, "js", "globals.d.js"))).toBe(false);
    expect(existsSync(join(out, "styles", "helper.js"))).toBe(false);
    expect(existsSync(join(out, "js", "plain.js"))).toBe(false);

    const js = readFileSync(join(out, "js", "widget.js"), "utf8");
    expect(js).toContain('"use strict"');
    expect(js).not.toContain("interface Pair");
  });

  test("skips an output newer than its source and recompiles once the source moves", () => {
    const root = fixtureTree();
    expect(runScript("compile-browser-scripts.ts", root).status).toBe(0);
    const second = runScript("compile-browser-scripts.ts", root);
    expect(second.output).toContain("browser scripts: 0 compiled, 1 up to date");

    const sourcePath = join(root, "src", "static", "site", "assets", "js", "widget.ts");
    const later = new Date(Date.now() + 5_000);
    utimesSync(sourcePath, later, later);
    const third = runScript("compile-browser-scripts.ts", root);
    expect(third.output).toContain("browser scripts: 1 compiled, 0 up to date");
  });

  test("says so and exits cleanly when there is no src/static", () => {
    const root = mkdtempSync(join(tmpdir(), "df12-compile-empty-"));
    created.push(root);
    const { status, output } = runScript("compile-browser-scripts.ts", root);
    expect(status).toBe(0);
    expect(output).toContain("Skipping browser script compile");
  });

  test("fails when the source root cannot be read for any other reason", () => {
    /* `src` is a file here, so reading `src/static` fails with ENOTDIR rather
       than ENOENT. A source tree that cannot be read is a fault, not an
       absent directory, and must not pass as a quiet skip. */
    const root = mkdtempSync(join(tmpdir(), "df12-compile-broken-"));
    created.push(root);
    writeFileSync(join(root, "src"), "not a directory\n");
    const { status, output } = runScript("compile-browser-scripts.ts", root);
    expect(status).not.toBe(0);
    expect(output).not.toContain("Skipping browser script compile");
    expect(output).toContain("ENOTDIR");
  });
});

describe("copy-static.ts beside the compile step", () => {
  test("copies everything under src/static except TypeScript", () => {
    const root = fixtureTree();
    const { status } = runScript("copy-static.ts", root);
    expect(status).toBe(0);

    const out = join(root, "public", "site", "assets");
    expect(existsSync(join(out, "js", "plain.js"))).toBe(true);
    expect(existsSync(join(out, "styles", "site.css"))).toBe(true);
    /* The three `.ts` files stay behind: the compile step owns the script,
       and the declaration and the stray helper have no place in the output. */
    expect(existsSync(join(out, "js", "widget.ts"))).toBe(false);
    expect(existsSync(join(out, "js", "vendor", "lib.ts"))).toBe(false);
    expect(existsSync(join(out, "js", "globals.d.ts"))).toBe(false);
    expect(existsSync(join(out, "styles", "helper.ts"))).toBe(false);
  });

  test("leaves no source in two forms once both steps have run", () => {
    const root = fixtureTree();
    expect(runScript("copy-static.ts", root).status).toBe(0);
    expect(runScript("compile-browser-scripts.ts", root).status).toBe(0);
    const out = join(root, "public", "site", "assets", "js");
    expect(existsSync(join(out, "widget.js"))).toBe(true);
    expect(existsSync(join(out, "widget.ts"))).toBe(false);
  });
});
