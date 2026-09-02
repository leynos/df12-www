/**
 * compile-browser-scripts.ts — the `build:js` step of the site build.
 *
 * Walks the TypeScript sources under `src/static/<site>/assets/js/` and
 * writes a plain JavaScript file for each at the mirrored path under
 * `public/`, so `src/static/netsuke/assets/js/doc-search.ts` is published
 * as `/netsuke/assets/js/doc-search.js`. swc does the compiling.
 *
 * Only types are removed. The sources are classic scripts — an IIFE per
 * file, loaded with a plain `<script defer>` — and they must stay that way,
 * because the templates load them without `type="module"` and the Bun tests
 * `require` the output for its guarded `module.exports`. So each file is
 * compiled with `isModule: false`, which tells swc to leave the top level
 * alone rather than wrap it as a module, and no module or syntax transform
 * is applied beyond the target. Typechecking is not swc's job: it strips
 * without checking, and `bun run typecheck:js` is the gate that catches a
 * wrongly typed module.
 *
 * Ordering matters: this runs after the first `build:static`, alongside the
 * other steps that write into `public/`. A file is skipped when its output is
 * already newer than its source, so repeated builds stay cheap; nothing is
 * pruned, because this step cannot tell a deleted script from another step's
 * output. Remove `public/` and rebuild to clear stale files.
 *
 * @module
 */
import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import { basename, dirname, join, relative, sep } from "node:path";
import { transform } from "@swc/core";

const SOURCE_ROOT = join(process.cwd(), "src", "static");
const TARGET_ROOT = join(process.cwd(), "public");

/** The directory, under a site's `assets/`, that holds its scripts. */
const SCRIPT_DIR = "js";

/** Third-party code, shipped as written and never compiled. */
const VENDOR_DIR = "vendor";

/**
 * Whether `path` is a browser script this step compiles.
 *
 * A source qualifies when it is a `.ts` file, is not a declaration file, and
 * sits under an `assets/js/` directory with no `vendor/` segment anywhere in
 * its path. Ambient declarations such as `src/static/browser-globals.d.ts`
 * inform the typecheck but have no runtime form to emit.
 */
export function isBrowserScript(path: string): boolean {
  const segments = relative(SOURCE_ROOT, path).split(sep);
  const name = basename(path);
  if (!name.endsWith(".ts") || name.endsWith(".d.ts")) {
    return false;
  }
  if (segments.includes(VENDOR_DIR)) {
    return false;
  }
  const assets = segments.indexOf("assets");
  return assets !== -1 && segments[assets + 1] === SCRIPT_DIR;
}

/**
 * Collect every file beneath `dir`, recursing into subdirectories.
 *
 * `results` is the accumulator the recursion threads through; callers pass
 * nothing. Returns absolute paths. Reads the filesystem but writes nothing.
 */
async function findFiles(dir: string, results: string[] = []): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const entryPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      await findFiles(entryPath, results);
    } else if (entry.isFile()) {
      results.push(entryPath);
    }
  }
  return results;
}

/**
 * Whether `targetPath` is missing or older than `sourcePath`.
 *
 * Any error reading either file counts as "needs compiling": a missing
 * output is the common case, and an unreadable source will fail loudly in
 * the compile step rather than be silently skipped here.
 */
async function needsCompile(sourcePath: string, targetPath: string): Promise<boolean> {
  try {
    const [source, target] = await Promise.all([stat(sourcePath), stat(targetPath)]);
    return source.mtimeMs > target.mtimeMs;
  } catch {
    return true;
  }
}

/**
 * The published path for a browser script: the mirrored location under
 * `public/`, with the `.ts` extension replaced by `.js`.
 */
export function targetFor(sourcePath: string): string {
  const rel = relative(SOURCE_ROOT, sourcePath);
  return join(TARGET_ROOT, `${rel.slice(0, -".ts".length)}.js`);
}

/**
 * Strip the types from one classic script and return the JavaScript.
 *
 * The output keeps the file's comments, its `"use strict"` directive, and
 * its top-level shape. `swcrc` and `configFile` are off so the result
 * depends only on the options here, not on anything found on disk.
 */
export async function compileClassicScript(source: string, filename: string): Promise<string> {
  const { code } = await transform(source, {
    filename,
    isModule: false,
    swcrc: false,
    configFile: false,
    minify: false,
    jsc: {
      parser: { syntax: "typescript" },
      target: "es2022",
      preserveAllComments: true,
    },
  });
  return code;
}

/**
 * Compile every browser script whose output is missing or stale.
 *
 * Skips the step with a message when `src/static` is absent, so a partial
 * checkout does not fail the build.
 */
async function main(): Promise<void> {
  try {
    await stat(SOURCE_ROOT);
  } catch {
    console.log("Skipping browser script compile. Directory src/static does not exist.");
    return;
  }

  const sources = (await findFiles(SOURCE_ROOT)).filter(isBrowserScript);
  if (sources.length === 0) {
    console.log("No browser scripts found under src/static. Skipping compile.");
    return;
  }

  let compiled = 0;
  for (const sourcePath of sources) {
    const targetPath = targetFor(sourcePath);
    if (!(await needsCompile(sourcePath, targetPath))) {
      continue;
    }
    const source = await readFile(sourcePath, "utf8");
    const code = await compileClassicScript(source, relative(process.cwd(), sourcePath));
    await mkdir(dirname(targetPath), { recursive: true });
    await writeFile(targetPath, code);
    compiled += 1;
    const rel = relative(process.cwd(), targetPath).split(sep).join("/");
    console.log(`compiled ${rel}`);
  }

  const skipped = sources.length - compiled;
  console.log(`browser scripts: ${compiled} compiled, ${skipped} up to date`);
}

if (import.meta.main) {
  await main();
}
