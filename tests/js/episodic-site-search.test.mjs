/**
 * @file Behavioural tests for the Episodic documentation search.
 *
 * These tests load the shipped classic script into happy-dom, inject its
 * loader and navigation dependencies, and exercise index loading, result
 * ranking, and keyboard interaction without live network requests.
 */
import { describe, expect, mock, test } from "bun:test";
import { createRequire } from "node:module";
import fc from "fast-check";
import { Window } from "happy-dom";

const require = createRequire(import.meta.url);
const {
  createIndexCache,
  fetchEpisodicSearchIndex,
  initialiseAllEpisodicSearch,
  initialiseEpisodicSearch,
  isIndexPayload,
  isSearchHit,
  searchEpisodicIndex,
} = require("../../public/episodic/assets/js/site-search.js");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, reject, resolve };
}

async function settle() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

function result(id, title = `Result ${id}`) {
  return {
    id,
    kind: "document",
    sitePath: `/episodic/docs/${id}/`,
    title,
    pageTitle: "Documentation",
  };
}

function engine(resultsByQuery) {
  return {
    miniSearch: {
      search(query, options) {
        const { loose = [], strict = loose } = resultsByQuery[query] || {};
        return options.combineWith === "AND" ? strict : loose;
      },
    },
    searchOptions: { prefix: true },
  };
}

function dispatchInput(window, input, value) {
  input.value = value;
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
}

function dispatchKey(window, input, key) {
  const event = new window.KeyboardEvent("keydown", {
    bubbles: true,
    cancelable: true,
    key,
  });
  input.dispatchEvent(event);
  return event;
}

function setUp({ loadIndex, loaded = engine({}), navigate = () => {} } = {}) {
  const window = new Window({ url: "https://episodic.example/docs/" });
  const { document } = window;
  window.HTMLElement.prototype.scrollIntoView = () => {};
  document.body.innerHTML = `
    <div data-search-root data-search-index="/episodic/assets/search/index.json" hidden>
      <input data-search-input type="search" />
      <div data-search-panel hidden>
        <ul data-search-results></ul>
        <p data-search-meta></p>
      </div>
    </div>
    <button id="outside" type="button">Outside</button>`;

  const root = document.querySelector("[data-search-root]");
  const input = root.querySelector("[data-search-input]");
  const panel = root.querySelector("[data-search-panel]");
  const list = root.querySelector("[data-search-results]");
  const meta = root.querySelector("[data-search-meta]");
  const initialised = initialiseEpisodicSearch(root, {
    loadIndex: loadIndex || (async () => loaded),
    miniSearch: {},
    navigate,
  });

  return { document, initialised, input, list, loaded, meta, panel, root, window };
}

describe("index loading", () => {
  test("fetches and deserializes the index with its recorded fields", async () => {
    const seen = [];
    const miniSearch = {
      loadJSON(index, options) {
        seen.push({ index, options });
        return { restored: true };
      },
    };
    const loaded = await fetchEpisodicSearchIndex("/index.json", {
      MiniSearch: miniSearch,
      fetchImpl: async (path) => ({
        json: async () => ({
          index: "serialized-index",
          indexOptions: {
            fields: ["title"],
            searchOptions: { prefix: true },
            storeFields: ["sitePath"],
          },
        }),
        ok: true,
        path,
      }),
    });

    expect(loaded.miniSearch).toEqual({ restored: true });
    expect(loaded.searchOptions).toEqual({ prefix: true });
    expect(seen).toEqual([
      {
        index: "serialized-index",
        options: { fields: ["title"], storeFields: ["sitePath"] },
      },
    ]);
  });

  test("rejects a malformed payload before handing it to MiniSearch", async () => {
    const loadJSON = mock(() => ({}));
    for (const body of [{}, { index: 5, indexOptions: { fields: ["title"] } }, { index: "{}" }]) {
      await expect(
        fetchEpisodicSearchIndex("/index.json", {
          MiniSearch: { loadJSON },
          fetchImpl: async () => ({ ok: true, json: async () => body }),
        }),
      ).rejects.toThrow("Episodic search index payload is malformed.");
    }
    expect(loadJSON).not.toHaveBeenCalled();
  });

  test("rejects unsuccessful index requests", async () => {
    await expect(
      fetchEpisodicSearchIndex("/index.json", {
        MiniSearch: { loadJSON: () => null },
        fetchImpl: async () => ({ ok: false, status: 503 }),
      }),
    ).rejects.toThrow("Index request failed: 503");
  });

  test("shares a pending load and retries after its failure", async () => {
    let calls = 0;
    const pending = deferred();
    const load = createIndexCache(() => {
      calls += 1;
      return calls === 1 ? pending.promise : Promise.resolve({ miniSearch: {} });
    });

    const first = load("/index.json");
    const second = load("/index.json");
    expect(first).toBe(second);
    await settle();
    expect(calls).toBe(1);

    pending.reject(new Error("offline"));
    await expect(first).rejects.toThrow("offline");
    await expect(load("/index.json")).resolves.toEqual({ miniSearch: {} });
    expect(calls).toBe(2);
  });

  test("emits bounded cache lifecycle telemetry without index paths", async () => {
    const events = [];
    let time = 0;
    let calls = 0;
    const load = createIndexCache(
      async () => {
        calls += 1;
        if (calls === 1) {
          throw new Error("offline");
        }
        return { miniSearch: {} };
      },
      {
        now: () => {
          time += 40;
          return time;
        },
        telemetry: (event) => events.push(event),
      },
    );

    const failed = load("/private/index.json");
    expect(load("/private/index.json")).toBe(failed);
    await expect(failed).rejects.toThrow("offline");
    await expect(load("/private/index.json")).resolves.toEqual({ miniSearch: {} });

    expect(events).toEqual([
      {
        attempt: "initial",
        cache_state: "miss",
        operation: "episodic-search-index",
        outcome: "requested",
      },
      {
        attempt: "initial",
        cache_state: "hit",
        operation: "episodic-search-index",
        outcome: "requested",
      },
      {
        attempt: "initial",
        cache_state: "miss",
        duration_bucket: "under-50ms",
        operation: "episodic-search-index",
        outcome: "failure",
      },
      {
        attempt: "initial",
        cache_state: "evicted",
        operation: "episodic-search-index",
        outcome: "evicted",
      },
      {
        attempt: "retry",
        cache_state: "miss",
        operation: "episodic-search-index",
        outcome: "requested",
      },
      {
        attempt: "retry",
        cache_state: "miss",
        duration_bucket: "under-50ms",
        operation: "episodic-search-index",
        outcome: "success",
      },
    ]);
    for (const event of events) {
      expect(Object.keys(event).sort()).toEqual(
        ["attempt", "cache_state", "duration_bucket", "operation", "outcome"]
          .filter((key) => key in event)
          .sort(),
      );
      expect(JSON.stringify(event)).not.toContain("/private/index.json");
    }
  });
});

describe("network-free search", () => {
  test("puts strict matches first, removes duplicates, and bounds the result set", () => {
    const strict = Array.from({ length: 9 }, (_, index) => result(`strict-${index}`));
    const loose = [strict[0], result("loose")];
    const found = searchEpisodicIndex(engine({ needle: { loose, strict } }), "needle");

    expect(found).toHaveLength(8);
    expect(found.map(({ id }) => id)).toEqual(strict.slice(0, 8).map(({ id }) => id));
  });

  test("keeps strict-first unique bounded results for arbitrary duplicate inputs", () => {
    const resultArbitrary = fc.record({
      id: fc.string({ minLength: 1, maxLength: 8 }),
      kind: fc.constant("document"),
      pageTitle: fc.constant("Documentation"),
      sitePath: fc.webPath(),
      title: fc.string({ minLength: 1, maxLength: 24 }),
    });

    fc.assert(
      fc.property(
        fc.array(resultArbitrary, { maxLength: 20 }),
        fc.array(resultArbitrary, { maxLength: 20 }),
        (strict, loose) => {
          const found = searchEpisodicIndex(engine({ query: { loose, strict } }), "query");
          const expected = [];
          const ids = new Set();
          for (const candidate of [...strict, ...loose]) {
            if (!ids.has(candidate.id)) {
              ids.add(candidate.id);
              expected.push(candidate.id);
            }
          }

          return (
            found.length <= 8 &&
            new Set(found.map(({ id }) => id)).size === found.length &&
            JSON.stringify(found.map(({ id }) => id)) === JSON.stringify(expected.slice(0, 8))
          );
        },
      ),
      { numRuns: 100 },
    );
  });
});

describe("root event state", () => {
  test("starts loading at initialization, never from focus or input, and renders results", async () => {
    let calls = 0;
    const loaded = engine({ film: { loose: [result("film", "Film design")] } });
    const dom = setUp({
      loadIndex: async () => {
        calls += 1;
        return loaded;
      },
      loaded,
    });

    expect(dom.initialised).toBe(true);
    expect(dom.root.hidden).toBe(false);
    expect(calls).toBe(1);
    dom.input.dispatchEvent(new dom.window.Event("focus"));
    await settle();
    expect(calls).toBe(1);

    dispatchInput(dom.window, dom.input, "film");
    await settle();
    expect(dom.list.children).toHaveLength(1);
    expect(dom.list.querySelector("a").tabIndex).toBe(0);
    expect(dom.input.getAttribute("role")).toBe("combobox");
    expect(dom.input.getAttribute("aria-controls")).toBe(dom.list.id);
    expect(dom.list.getAttribute("role")).toBe("listbox");
    expect(dom.meta.textContent).toBe("1 result for “film”.");
    expect(dom.panel.hidden).toBe(false);
    expect(calls).toBe(1);
  });

  test("snapshots populated, empty, unavailable, and keyboard-active result states", async () => {
    const populated = setUp({
      loaded: engine({ film: { loose: [result("film", "Film design")] } }),
    });
    dispatchInput(populated.window, populated.input, "film");
    await settle();
    expect({ meta: populated.meta.textContent, results: populated.list.innerHTML }).toMatchSnapshot(
      "populated results",
    );

    const empty = setUp({ loaded: engine({ none: { loose: [] } }) });
    dispatchInput(empty.window, empty.input, "none");
    await settle();
    expect({ meta: empty.meta.textContent, results: empty.list.innerHTML }).toMatchSnapshot(
      "empty results",
    );

    const unavailable = setUp({ loadIndex: async () => Promise.reject(new Error("offline")) });
    const warning = console.warn;
    console.warn = () => {};
    try {
      dispatchInput(unavailable.window, unavailable.input, "docs");
      await settle();
    } finally {
      console.warn = warning;
    }
    expect({
      meta: unavailable.meta.textContent,
      results: unavailable.list.innerHTML,
    }).toMatchSnapshot("unavailable results");

    const active = setUp({ loaded: engine({ docs: { loose: [result("one"), result("two")] } }) });
    dispatchInput(active.window, active.input, "docs");
    await settle();
    dispatchKey(active.window, active.input, "ArrowDown");
    expect({
      active: active.input.getAttribute("aria-activedescendant"),
      results: active.list.innerHTML,
    }).toMatchSnapshot("keyboard active results");
  });

  test("does not let an older request overwrite a newer query", async () => {
    const pending = deferred();
    const loaded = engine({
      old: { loose: [result("old", "Old result")] },
      new: { loose: [result("new", "New result")] },
    });
    const dom = setUp({
      loadIndex: () => pending.promise,
      loaded,
    });

    dispatchInput(dom.window, dom.input, "old");
    dispatchInput(dom.window, dom.input, "new");
    pending.resolve(dom.loaded);
    await settle();

    expect(dom.meta.textContent).toBe("1 result for “new”.");
    expect(dom.list.textContent).toContain("New result");
    expect(dom.list.textContent).not.toContain("Old result");
  });

  test("reports a current loading failure without input retrying the loader", async () => {
    let calls = 0;
    const dom = setUp({
      loadIndex: async () => {
        calls += 1;
        throw new Error("offline");
      },
    });
    const warning = console.warn;
    console.warn = () => {};

    try {
      dispatchInput(dom.window, dom.input, "retry");
      await settle();
      expect(dom.meta.textContent).toContain("Search is unavailable");

      dispatchInput(dom.window, dom.input, "retry");
      await settle();
      expect(calls).toBe(1);
    } finally {
      console.warn = warning;
    }
  });

  test("keeps keyboard selection, escape, and outside clicks in bounded states", async () => {
    const navigated = [];
    const loaded = engine({ docs: { loose: [result("first"), result("second")] } });
    const dom = setUp({
      navigate: (href) => navigated.push(href),
      loaded,
    });
    dispatchInput(dom.window, dom.input, "docs");
    await settle();

    const firstDown = dispatchKey(dom.window, dom.input, "ArrowDown");
    const secondDown = dispatchKey(dom.window, dom.input, "ArrowDown");
    const boundedDown = dispatchKey(dom.window, dom.input, "ArrowDown");
    expect(firstDown.defaultPrevented).toBe(true);
    expect(secondDown.defaultPrevented).toBe(true);
    expect(boundedDown.defaultPrevented).toBe(true);
    expect(dom.list.children[1].classList.contains("is-active")).toBe(true);
    expect(dom.list.querySelectorAll('[role="option"]')[1].getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(dom.input.getAttribute("aria-activedescendant")).toBe(
      dom.list.querySelectorAll('[role="option"]')[1].id,
    );

    const enter = dispatchKey(dom.window, dom.input, "Enter");
    expect(enter.defaultPrevented).toBe(true);
    expect(navigated).toEqual(["/episodic/docs/second/"]);

    dispatchKey(dom.window, dom.input, "Escape");
    expect(dom.panel.hidden).toBe(true);
    expect(dom.input.getAttribute("aria-expanded")).toBe("false");
    expect(dom.input.hasAttribute("aria-activedescendant")).toBe(false);
    dom.input.dispatchEvent(new dom.window.Event("focus"));
    expect(dom.panel.hidden).toBe(false);
    dom.document
      .getElementById("outside")
      .dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    expect(dom.panel.hidden).toBe(true);
  });

  test("marks automatically initialised roots exactly once", () => {
    const window = new Window();
    const { document } = window;
    document.body.innerHTML = `
      <div data-search-root data-search-index="/index.json">
        <input data-search-input />
        <div data-search-panel><ul data-search-results></ul><p data-search-meta></p></div>
      </div>`;
    const root = document.querySelector("[data-search-root]");
    initialiseAllEpisodicSearch(document, {
      loadIndex: async () => engine({}),
      miniSearch: {},
    });
    expect(root.dataset.searchInitialised).toBe("true");
    initialiseAllEpisodicSearch(document, { miniSearch: {} });
    expect(root.dataset.searchInitialised).toBe("true");
  });
});

describe("isSearchHit", () => {
  const hit = { id: "a", sitePath: "/docs/a/", title: "A", kind: "document" };

  test("accepts a record with the stored fields as strings", () => {
    expect(isSearchHit(hit)).toBe(true);
    expect(isSearchHit({ ...hit, pageTitle: "A", sectionTitle: "S", excerpt: "…" })).toBe(true);
  });

  test("rejects a record whose navigation target or labels are not strings", () => {
    expect(isSearchHit({ ...hit, sitePath: undefined })).toBe(false);
    expect(isSearchHit({ ...hit, title: 1 })).toBe(false);
    expect(isSearchHit({ ...hit, excerpt: ["no"] })).toBe(false);
    expect(isSearchHit(null)).toBe(false);
  });

  test("keeps a malformed record out of the ranked results", () => {
    const good = { id: "g", sitePath: "/docs/g/", title: "G", kind: "document" };
    const bad = { id: "b", sitePath: 42, title: "B", kind: "document" };
    const miniSearch = { search: () => [bad, good] };
    const dropped = [];
    const engine = { miniSearch, searchOptions: {} };
    expect(searchEpisodicIndex(engine, "g", (count) => dropped.push(count))).toEqual([good]);
    /* The query stays pure: it reports the count and leaves the warning to
       the root that owns the UI. */
    expect(dropped).toEqual([1]);
    expect(searchEpisodicIndex(engine, "g")).toEqual([good]);
  });
});

describe("isIndexPayload", () => {
  test("accepts the shape the index builder writes, with optional stored fields", () => {
    expect(isIndexPayload({ index: "{}", indexOptions: { fields: ["title"] } })).toBe(true);
    expect(
      isIndexPayload({
        index: "{}",
        indexOptions: { fields: ["title"], storeFields: ["sitePath"], searchOptions: {} },
      }),
    ).toBe(true);
  });

  test("rejects a payload without a serialized index or its fields", () => {
    expect(isIndexPayload({})).toBe(false);
    expect(isIndexPayload({ index: "{}" })).toBe(false);
    expect(isIndexPayload({ index: "{}", indexOptions: {} })).toBe(false);
    expect(isIndexPayload({ index: "{}", indexOptions: { fields: "title" } })).toBe(false);
    expect(
      isIndexPayload({ index: "{}", indexOptions: { fields: ["title"], storeFields: 1 } }),
    ).toBe(false);
  });
});
