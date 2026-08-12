/* Tests for the Stilyagi docs page's rules-catalogue filter.
 *
 * `matchesFilter` is the whole decision: given a row's namespace and its
 * precomputed searchable text, plus the selected chip and the search box
 * contents, it decides whether the row stays visible.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { matchesFilter } = require("../../public/stilyagi/assets/js/docs.js");

const HAYSTACK = "md201 heading depth headings must not skip levels";

describe("matchesFilter", () => {
  test('the "all" chip with no query keeps every row', () => {
    expect(matchesFilter("md", HAYSTACK, "all", "")).toBe(true);
    expect(matchesFilter("pydoc", "", "all", "")).toBe(true);
  });

  test("a namespace chip keeps only its own rows", () => {
    expect(matchesFilter("md", HAYSTACK, "md", "")).toBe(true);
    expect(matchesFilter("pydoc", HAYSTACK, "md", "")).toBe(false);
  });

  test("the query matches the rule id as well as its prose", () => {
    expect(matchesFilter("md", HAYSTACK, "all", "md201")).toBe(true);
    expect(matchesFilter("md", HAYSTACK, "all", "skip levels")).toBe(true);
  });

  test("the query is case-insensitive and ignores surrounding space", () => {
    expect(matchesFilter("md", HAYSTACK, "all", "  HEADING ")).toBe(true);
  });

  test("namespace and query must both hold", () => {
    // The row's text matches, but it belongs to another namespace.
    expect(matchesFilter("md", HAYSTACK, "pydoc", "heading")).toBe(false);
  });

  test("a query with no match hides the row", () => {
    expect(matchesFilter("md", HAYSTACK, "all", "oxford comma")).toBe(false);
  });

  test("a whitespace-only query is treated as empty", () => {
    expect(matchesFilter("md", HAYSTACK, "all", "   ")).toBe(true);
  });

  test("a row with no searchable text survives only an empty query", () => {
    expect(matchesFilter("md", undefined, "all", "")).toBe(true);
    expect(matchesFilter("md", undefined, "all", "heading")).toBe(false);
  });
});
