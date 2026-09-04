/**
 * @file DOM-level tests for the Netsuke doc-search boundary.
 *
 * `doc-search.test.mjs` covers the pure helpers the module exports. What it
 * cannot reach is the wiring: the fetch of the index file, the shape check
 * on what comes back, and the way a bad result is kept out of the list a
 * reader sees. Those live inside `initializeDocSearch`, which is not
 * exported, so this suite drives the compiled script against the global
 * happy-dom document with the markup `templates/netsuke/pages/docs.jinja`
 * renders and stubs `fetch` and `MiniSearch` at the window.
 *
 * Each test builds its own happy-dom `Window` rather than using the global
 * document. The script waits for `DOMContentLoaded` rather than checking
 * `document.readyState`, so the test dispatches that event by hand after
 * mounting — and on the shared document that would also wake the listener
 * the unit suite's `require` of the same script installed, initializing each
 * root twice. An isolated window has exactly one listener: this one.
 */
import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";
import { Window } from "happy-dom";
import { evaluateScript } from "./helpers/dom.mjs";

const SCRIPT = "public/netsuke/assets/js/doc-search.js";
const INDEX = "/netsuke/assets/search/docs-search.json";

/* Mirrors the search box in `templates/netsuke/pages/docs.jinja`, reduced to
   the `data-doc-search-*` contract the script reads. */
const ROOT = `
  <div data-doc-search-root data-doc-search-index="${INDEX}">
    <input data-doc-search-input type="search" value="" />
    <div data-doc-search-panel class="hidden">
      <p data-doc-search-meta></p>
      <ul data-doc-search-results></ul>
    </div>
  </div>`;

/* A well-formed index payload, as `scripts/build-netsuke-search-index.mjs`
   writes it. The serialized index is opaque to the script. */
const PAYLOAD = {
  index: "{}",
  indexOptions: { fields: ["title"], storeFields: ["title"], searchOptions: { prefix: true } },
};

const saved = {};
let page = null;

beforeEach(() => {
  saved.fetch = globalThis.fetch;
  saved.warn = console.warn;
  /* The script builds each result's href against `window.location.origin`,
     so the window needs a real URL rather than `about:blank`. */
  page = new Window({ url: "http://localhost/netsuke/docs/" });
});

afterEach(async () => {
  globalThis.fetch = saved.fetch;
  console.warn = saved.warn;
  await page.happyDOM.close();
  page = null;
});

/* Mount the search root, evaluate the script against this test's window,
   let it initialize, and give the async load a few turns to settle. */
async function mount({ response, miniSearch }) {
  const { document } = page;
  document.body.innerHTML = ROOT;
  globalThis.fetch = mock(async () => response);
  page.MiniSearch = miniSearch;
  evaluateScript(page, SCRIPT);
  document.dispatchEvent(new page.Event("DOMContentLoaded"));
  for (let i = 0; i < 5; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  return {
    input: document.querySelector("[data-doc-search-input]"),
    meta: document.querySelector("[data-doc-search-meta]"),
    list: document.querySelector("[data-doc-search-results]"),
  };
}

/* Capture `console.warn` calls as their joined text. */
function captureWarnings() {
  const warnings = [];
  console.warn = (...args) => warnings.push(args.map(String).join(" "));
  return warnings;
}

describe("loading the index", () => {
  test("a malformed payload never reaches MiniSearch and the box says so", async () => {
    const warnings = captureWarnings();
    const loadJSON = mock(() => ({}));
    const { meta } = await mount({
      response: { ok: true, status: 200, json: async () => ({ index: 5 }) },
      miniSearch: { loadJSON },
    });
    expect(loadJSON).not.toHaveBeenCalled();
    expect(meta.textContent).toBe("Search index is not available in this build.");
    expect(warnings).toEqual(["doc-search-index: invalid-payload"]);
  });

  test("a failed request is reported by status, with nothing else", async () => {
    const warnings = captureWarnings();
    const { meta } = await mount({
      response: { ok: false, status: 503, json: async () => ({}) },
      miniSearch: { loadJSON: mock(() => ({})) },
    });
    expect(meta.textContent).toBe("Search index is not available in this build.");
    expect(warnings).toEqual(["doc-search-index: http 503"]);
  });

  test("a loader that throws is reported as a load failure", async () => {
    const warnings = captureWarnings();
    const { meta } = await mount({
      response: {
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError("Unexpected token");
        },
      },
      miniSearch: { loadJSON: mock(() => ({})) },
    });
    expect(meta.textContent).toBe("Search index is not available in this build.");
    expect(warnings).toEqual(["doc-search-index: load-failed"]);
  });
});

describe("searching", () => {
  const good = { id: 1, sitePath: "/docs/a/", title: "Alpha", kind: "page", pageTitle: "Alpha" };
  const bad = { id: 2, sitePath: "/docs/b/", title: 3, kind: "page", pageTitle: "Beta" };

  /* A MiniSearch stand-in whose `search` returns whatever the test says. */
  function fakeMiniSearch(results) {
    return { loadJSON: () => ({ search: () => results }) };
  }

  test("a malformed hit is kept out of the list and reported once", async () => {
    const warnings = captureWarnings();
    const { input, list } = await mount({
      response: { ok: true, status: 200, json: async () => PAYLOAD },
      miniSearch: fakeMiniSearch([bad, good]),
    });
    input.value = "al";
    input.dispatchEvent(new page.Event("input"));
    input.dispatchEvent(new page.Event("input"));

    const options = [...list.querySelectorAll("[data-doc-search-option]")];
    expect(options.map((option) => option.textContent.includes("Alpha"))).toEqual([true]);
    expect(warnings).toEqual(["Doc search dropped 1 malformed result(s) from the index."]);
  });

  test("well-formed hits render without a warning", async () => {
    const warnings = captureWarnings();
    const { input, list } = await mount({
      response: { ok: true, status: 200, json: async () => PAYLOAD },
      miniSearch: fakeMiniSearch([good]),
    });
    input.value = "al";
    input.dispatchEvent(new page.Event("input"));
    expect(list.querySelectorAll("[data-doc-search-option]").length).toBe(1);
    expect(warnings).toEqual([]);
  });
});
