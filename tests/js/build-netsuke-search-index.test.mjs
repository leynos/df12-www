/**
 * @file Unit tests for the Netsuke MiniSearch builder's page list and
 * extraction logic.
 *
 * The page lists in `scripts/build-netsuke-search-index.mjs` are explicit
 * rather than globbed, so a new page joins the index only when someone adds
 * it. These tests pin the forthcoming-capability pages into the docs list
 * and check that a forthcoming page's sections extract with site paths under
 * `/netsuke/forthcoming/`.
 */

import { describe, expect, test } from "bun:test";

import { DOC_FILES, extractDocuments } from "../../scripts/build-netsuke-search-index.mjs";

/** Normalize a path from the page list to forward slashes for comparison. */
function normalized(filePath) {
  return filePath.replace(/\\/g, "/");
}

describe("Netsuke docs search page list", () => {
  test("indexes the forthcoming hub and both preview pages", () => {
    const files = DOC_FILES.map(normalized);
    expect(files).toContain("public/netsuke/forthcoming/index.html");
    expect(files).toContain("public/netsuke/forthcoming/linter/index.html");
    expect(files).toContain("public/netsuke/forthcoming/testing-framework/index.html");
  });

  test("still indexes every docs chain page", () => {
    const files = DOC_FILES.map(normalized);
    for (const slug of [
      "getting-started",
      "manifest-reference",
      "rules-and-targets",
      "templating",
      "standard-library",
      "cli",
      "configuration",
      "security",
    ]) {
      expect(files).toContain(`public/netsuke/docs/${slug}/index.html`);
    }
  });
});

describe("Netsuke search-index extraction", () => {
  test("derives forthcoming site paths and per-section documents", () => {
    const documents = extractDocuments(
      "public/netsuke/forthcoming/linter/index.html",
      `<main><h1>Netsukefile Linter</h1><section id="status"><h2>Status</h2><p>Not in the current release.</p></section><section id="rules"><h2>Rule catalogue</h2><p>Twenty-four rules across nine categories.</p></section></main>`,
    );

    expect(documents.map((document) => document.id)).toEqual([
      "forthcoming/linter/",
      "forthcoming/linter/#status",
      "forthcoming/linter/#rules",
    ]);
    const rules = documents.find((document) => document.id === "forthcoming/linter/#rules");
    expect(rules?.title).toBe("Rule catalogue - Netsukefile Linter");
    expect(rules?.body).toContain("Twenty-four rules");
  });
});
