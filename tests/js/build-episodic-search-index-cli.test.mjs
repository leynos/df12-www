/**
 * @file End-to-end tests for the Episodic MiniSearch index-builder command.
 *
 * These tests run `scripts/build-episodic-search-index.mjs` against temporary
 * rendered-site fixtures and verify generation, drift, input failures, and
 * concurrent replacement behaviour.
 */

import { describe, expect, test } from "bun:test";
import { spawn, spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import MiniSearch from "minisearch";

const SCRIPT = fileURLToPath(
  new URL("../../scripts/build-episodic-search-index.mjs", import.meta.url),
);

async function fixtureRoot() {
  const root = await mkdtemp(path.join(tmpdir(), "episodic-index-"));
  await mkdir(path.join(root, "public/episodic/docs"), { recursive: true });
  await mkdir(path.join(root, "templates/episodic/data"), { recursive: true });
  await writeFile(
    path.join(root, "public/episodic/docs/index.html"),
    '<main><h1>Documentation</h1><section id="start"><h2>Start</h2><p>A long enough fixture paragraph for an excerpt.</p></section></main>',
  );
  await writeFile(
    path.join(root, "templates/episodic/data/docs_manifest.jinja"),
    '{% set doc_categories = [{"label":"Guides","type":"guide","audience":"operators","blurb":"Fixture documentation is searchable.","documents":[{"title":"Fixture document","path":"docs/fixture.md","summary":"A fixture upstream document."}]}] %}\n{% set doc_featured = [] %}\n',
  );
  return root;
}

function runIndex(root, ...args) {
  return spawnSync(process.execPath, [SCRIPT, ...args], {
    cwd: root,
    encoding: "utf8",
  });
}

function runIndexAsync(root, ...args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [SCRIPT, ...args], { cwd: root });
    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (status) => resolve({ status, stderr }));
  });
}

describe("Episodic search-index command", () => {
  test("writes deterministic output and detects drift in check mode", async () => {
    const root = await fixtureRoot();
    const outputPath = path.join(root, "src/static/episodic/assets/search/episodic-search.json");
    try {
      expect(runIndex(root).status).toBe(0);
      const generated = await readFile(outputPath, "utf8");
      const payload = JSON.parse(generated);
      expect(payload.index).toBeString();
      const index = MiniSearch.loadJSON(payload.index, {
        fields: payload.indexOptions.fields,
        storeFields: payload.indexOptions.storeFields,
      });
      expect(index.search("fixture").map((result) => result.sitePath)).toContain(
        "https://github.com/leynos/episodic/blob/main/docs/fixture.md",
      );
      expect(runIndex(root, "--check").status).toBe(0);

      await writeFile(outputPath, "stale\n");
      const drift = runIndex(root, "--check");
      expect(drift.status).not.toBe(0);
      expect(drift.stderr).toContain("is stale");
    } finally {
      await rm(root, { force: true, recursive: true });
    }
  });

  test("fails rather than publishing a partial index when rendered pages are absent", async () => {
    const root = await fixtureRoot();
    await rm(path.join(root, "public"), { force: true, recursive: true });
    try {
      const result = runIndex(root);
      expect(result.status).not.toBe(0);
      expect(result.stderr).toContain("ENOENT");
    } finally {
      await rm(root, { force: true, recursive: true });
    }
  });

  test("fails when the upstream documentation manifest is absent", async () => {
    const root = await fixtureRoot();
    await rm(path.join(root, "templates"), { force: true, recursive: true });
    try {
      const result = runIndex(root);
      expect(result.status).not.toBe(0);
      expect(result.stderr).toContain("ENOENT");
    } finally {
      await rm(root, { force: true, recursive: true });
    }
  });

  test("leaves a complete index when simultaneous builds replace the same output", async () => {
    const root = await fixtureRoot();
    const outputPath = path.join(root, "src/static/episodic/assets/search/episodic-search.json");
    try {
      const [first, second] = await Promise.all([runIndexAsync(root), runIndexAsync(root)]);
      expect(first.status).toBe(0);
      expect(second.status).toBe(0);
      expect(JSON.parse(await readFile(outputPath, "utf8")).index).toBeString();
    } finally {
      await rm(root, { force: true, recursive: true });
    }
  });
});
