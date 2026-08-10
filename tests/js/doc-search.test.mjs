/* Tests for the doc-search index cache and path helpers.
 *
 * `createIndexCache` is what lets a page's multiple search roots (the
 * desktop sidebar and the mobile docs bar) share one fetched and
 * deserialized index: the same path returns the same promise, concurrent
 * callers join the in-flight load, and failed or empty loads are evicted
 * so a later caller can retry.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const {
  createIndexCache,
  siteRootFromIndexPath,
} = require("../../public/netsuke/assets/js/doc-search.js");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("createIndexCache", () => {
  test("concurrent callers share one in-flight load per path", async () => {
    let calls = 0;
    const d = deferred();
    const load = createIndexCache(() => {
      calls += 1;
      return d.promise;
    });

    const first = load("/a.json");
    const second = load("/a.json");
    expect(first).toBe(second);
    await Promise.resolve(); // let the deferred loader call run
    expect(calls).toBe(1);

    d.resolve({ miniSearch: "instance" });
    expect((await first).miniSearch).toBe("instance");

    // A settled successful load stays cached.
    await load("/a.json");
    expect(calls).toBe(1);
  });

  test("distinct paths load independently", async () => {
    const seen = [];
    const load = createIndexCache(async (path) => {
      seen.push(path);
      return { path };
    });

    await load("/a.json");
    await load("/b.json");
    expect(seen).toEqual(["/a.json", "/b.json"]);
  });

  test("a failed load is evicted so the next caller retries", async () => {
    let calls = 0;
    const load = createIndexCache(async () => {
      calls += 1;
      if (calls === 1) {
        throw new Error("network down");
      }
      return { miniSearch: "recovered" };
    });

    let error = null;
    try {
      await load("/a.json");
    } catch (caught) {
      error = caught;
    }
    expect(error && error.message).toBe("network down");
    expect((await load("/a.json")).miniSearch).toBe("recovered");
    expect(calls).toBe(2);
  });

  test("an empty result (missing index) is not cached", async () => {
    let calls = 0;
    const load = createIndexCache(async () => {
      calls += 1;
      return calls === 1 ? null : { miniSearch: "present" };
    });

    expect(await load("/a.json")).toBeNull();
    expect((await load("/a.json")).miniSearch).toBe("present");
  });
});

describe("siteRootFromIndexPath", () => {
  test("derives the sub-site root from the index path", () => {
    expect(siteRootFromIndexPath("/netsuke/assets/search/docs-search.json")).toBe("/netsuke/");
  });

  test("falls back to the site root for unrecognized paths", () => {
    expect(siteRootFromIndexPath("/elsewhere/index.json")).toBe("/");
  });
});
