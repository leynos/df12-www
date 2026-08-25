/**
 * @file Behavioural tests for the Episodic documentation search.
 *
 * These tests load the shipped classic script into happy-dom, inject its
 * loader and navigation dependencies, and exercise index loading, result
 * ranking, and keyboard interaction without live network requests.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";
import { Window } from "happy-dom";

const require = createRequire(import.meta.url);
const {
  createIndexCache,
  fetchEpisodicSearchIndex,
  initialiseAllEpisodicSearch,
  initialiseEpisodicSearch,
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
});

describe("network-free search", () => {
  test("puts strict matches first, removes duplicates, and bounds the result set", () => {
    const strict = Array.from({ length: 9 }, (_, index) => result(`strict-${index}`));
    const loose = [strict[0], result("loose")];
    const found = searchEpisodicIndex(engine({ needle: { loose, strict } }), "needle");

    expect(found).toHaveLength(8);
    expect(found.map(({ id }) => id)).toEqual(strict.slice(0, 8).map(({ id }) => id));
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
