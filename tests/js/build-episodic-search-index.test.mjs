import { describe, expect, test } from "bun:test";

import { extractDocuments } from "../../scripts/build-episodic-search-index.mjs";

describe("Episodic search-index section extraction", () => {
  test("retains nested content and indexes every identified section", () => {
    const documents = extractDocuments(
      "public/episodic/docs/index.html",
      `<main><h1>Documentation</h1><section id="outer"><h2>Outer</h2><p>Outer context before nested content.</p><section id="inner"><h3>Inner</h3><p>Nested content remains searchable.</p></section><p>Outer context after nested content.</p></section></main>`,
    );

    const outer = documents.find((document) => document.id === "/episodic/docs/#outer");
    const inner = documents.find((document) => document.id === "/episodic/docs/#inner");
    expect(outer?.body).toContain("Nested content remains searchable.");
    expect(inner?.body).toContain("Nested content remains searchable.");
    expect(documents.map((document) => document.id)).toEqual([
      "/episodic/docs/",
      "/episodic/docs/#outer",
      "/episodic/docs/#inner",
    ]);
  });
});
