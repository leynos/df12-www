/* Client-side documentation search.
 *
 * Wires every `[data-doc-search-root]` element (the desktop sidebar box
 * and the mobile docs bar both declare one) to a MiniSearch index named
 * by its `data-doc-search-index` attribute. Each root keeps its own
 * input, results panel, and keyboard handling, while index loads are
 * fetched, parsed, and deserialized once per index path and shared. The
 * indexes are built by scripts/build-netsuke-search-index.mjs; the
 * markup contract lives in the sidebar blocks of the docs page
 * templates and in templates/netsuke/docs_nav.jinja.
 */
(() => {
  const SEARCH_MIN_LENGTH = 2;
  const RESULT_LIMIT = 6;

  type Index = import("minisearch").default;
  type IndexOptions = import("minisearch").Options;
  type SearchOptions = import("minisearch").SearchOptions;
  type SearchResult = import("minisearch").SearchResult;

  /* The JSON `scripts/build-netsuke-search-index.mjs` writes: a serialized
     index and the options it was built with, including the query-time
     options every search should use. */
  interface IndexPayload {
    index: string;
    indexOptions: IndexOptions & { searchOptions: SearchOptions };
  }

  /* A deserialized index and the query options that go with it. */
  interface LoadedIndex {
    miniSearch: Index;
    searchOptions: SearchOptions;
  }

  /* One result, as the index stores it: MiniSearch's own fields plus the
     stored page fields the results list renders. */
  interface DocSearchHit {
    id: unknown;
    sitePath: string;
    title: string;
    kind: string;
    pageTitle: string;
    sectionTitle?: string;
    excerpt?: string;
  }

  /* Whether `value` is absent or a string, which is what an optional stored
     field may be. */
  function isOptionalString(value: unknown): value is string | undefined {
    return value === undefined || typeof value === "string";
  }

  /* Whether a deserialized result carries the stored fields the list renders,
     each as a string. The index builder always writes them that way, but the
     index arrives as JSON at runtime, and `escapeHtml` throws on anything
     else — so a malformed record is dropped here rather than taking every
     result down with it. */
  function isDocSearchHit(value: unknown): value is DocSearchHit {
    if (typeof value !== "object" || value === null) {
      return false;
    }
    const hit = value as Record<string, unknown>;
    return (
      typeof hit.sitePath === "string" &&
      typeof hit.title === "string" &&
      typeof hit.kind === "string" &&
      typeof hit.pageTitle === "string" &&
      isOptionalString(hit.sectionTitle) &&
      isOptionalString(hit.excerpt)
    );
  }

  /* Whether `value` is the index payload the build script writes: a
     serialized index and the options MiniSearch needs to read it back, with
     `fields` present. The file is fetched at runtime, so its shape is checked
     rather than assumed; a payload that fails is treated as no index. */
  function isIndexPayload(value: unknown): value is IndexPayload {
    if (typeof value !== "object" || value === null) {
      return false;
    }
    const payload = value as Record<string, unknown>;
    if (typeof payload.index !== "string") {
      return false;
    }
    const options = payload.indexOptions;
    if (typeof options !== "object" || options === null) {
      return false;
    }
    const { fields, searchOptions } = options as Record<string, unknown>;
    return (
      Array.isArray(fields) &&
      fields.every((field) => typeof field === "string") &&
      typeof searchOptions === "object" &&
      searchOptions !== null
    );
  }

  /* Why an index could not be loaded, as the one word a maintainer needs. */
  type IndexFailure = "http" | "invalid-payload" | "load-failed";

  /* Report an index failure with a stable operation name and a category, and
     nothing else: no path, no payload, no error text. */
  function reportIndexFailure(category: IndexFailure, detail?: number): void {
    console.warn(`doc-search-index: ${category}${detail === undefined ? "" : ` ${detail}`}`);
  }

  /* What a query returns: the hits to show, and how many records the
     stored-field guard dropped, for the caller to report as it sees fit. */
  interface SearchOutcome {
    hits: DocSearchHit[];
    dropped: number;
  }

  /* Called with how many results a query dropped for failing `isDocSearchHit`. */
  type DropReporter = (count: number) => void;

  /* A reporter that says so once, for one root, so a malformed index cannot
     shrink the results list silently and cannot flood the console either. */
  function onceDropReporter(): DropReporter {
    let reported = false;
    return (count) => {
      if (count > 0 && !reported) {
        reported = true;
        console.warn(`Doc search dropped ${count} malformed result(s) from the index.`);
      }
    };
  }

  /* Everything `renderResults` needs to redraw one root. */
  interface RenderState {
    activeIndex: number;
    activeResults: DocSearchHit[];
    input: HTMLInputElement;
    meta: HTMLElement;
    panel: HTMLElement;
    resultsList: HTMLElement;
    siteRoot: string;
  }

  if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", () => {
      const searchRoots = document.querySelectorAll<HTMLElement>("[data-doc-search-root]");

      for (const root of searchRoots) {
        initializeDocSearch(root).catch((error) => {
          console.warn("Doc search initialization failed.", error);
        });
      }
    });
  }

  /* Wire one search root: its input, results panel, and list. Loads the index
     lazily through the shared cache, so a page carrying several roots for the
     same index fetches it once. */
  async function initializeDocSearch(root: HTMLElement): Promise<void> {
    const input = root.querySelector<HTMLInputElement>("[data-doc-search-input]");
    const panel = root.querySelector<HTMLElement>("[data-doc-search-panel]");
    const resultsList = root.querySelector<HTMLElement>("[data-doc-search-results]");
    const meta = root.querySelector<HTMLElement>("[data-doc-search-meta]");
    const searchIndexPath = root.getAttribute("data-doc-search-index");

    if (!input || !panel || !resultsList || !meta || !searchIndexPath) {
      return;
    }

    if (!window.MiniSearch) {
      meta.textContent = "Search is unavailable because MiniSearch did not load.";
      showPanel(panel, input);
      return;
    }

    let loaded: LoadedIndex | null;
    try {
      loaded = await loadSearchIndex(searchIndexPath);
    } catch {
      reportIndexFailure("load-failed");
      loaded = null;
    }
    if (!loaded) {
      meta.textContent = "Search index is not available in this build.";
      showPanel(panel, input);
      return;
    }

    const { miniSearch, searchOptions } = loaded;
    const siteRoot = siteRootFromIndexPath(searchIndexPath);

    let activeIndex = -1;
    let activeResults: DocSearchHit[] = [];
    const reportDropped = onceDropReporter();

    input.setAttribute("autocomplete", "off");
    input.setAttribute("spellcheck", "false");
    input.setAttribute("aria-expanded", "false");

    document.addEventListener("keydown", (event) => {
      const wantsShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";

      if (!wantsShortcut) {
        return;
      }

      // Pages can carry more than one search root (desktop sidebar and the
      // mobile docs bar); each installs this handler, so only the root that
      // is visible at the current breakpoint may claim the shortcut.
      if (input.offsetParent === null) {
        return;
      }

      event.preventDefault();
      input.focus();
      input.select();
    });

    input.addEventListener("input", () => {
      activeIndex = -1;
      const outcome = search(miniSearch, searchOptions, input.value);
      activeResults = outcome.hits;
      reportDropped(outcome.dropped);
      renderResults({
        activeIndex,
        activeResults,
        input,
        meta,
        panel,
        resultsList,
        siteRoot,
      });
    });

    input.addEventListener("keydown", (event) => {
      if (panel.classList.contains("hidden")) {
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        activeIndex = Math.min(activeIndex + 1, activeResults.length - 1);
        updateActiveResult(resultsList, activeIndex);
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        activeIndex = Math.max(activeIndex - 1, -1);
        updateActiveResult(resultsList, activeIndex);
        return;
      }

      if (event.key === "Enter" && activeIndex >= 0) {
        event.preventDefault();
        const selected = activeResults[activeIndex];
        if (selected) {
          window.location.href = toAbsoluteSiteHref(siteRoot, selected.sitePath);
        }
        return;
      }

      if (event.key === "Escape") {
        hidePanel(panel, input);
      }
    });

    document.addEventListener("click", (event) => {
      if (!root.contains(event.target as Node)) {
        hidePanel(panel, input);
      }
    });

    input.addEventListener("focus", () => {
      if (input.value.trim().length >= SEARCH_MIN_LENGTH) {
        showPanel(panel, input);
      }
    });
  }

  /* Run `rawQuery` against the index and return at most RESULT_LIMIT results,
     or nothing at all for a query below the minimum length. Results are merged
     so a page and its sections do not both appear for the same match. A pure
     query: the count of records dropped for failing `isDocSearchHit` comes
     back with the hits, and the caller decides what to do with it. */
  function search(
    miniSearch: Index,
    searchOptions: SearchOptions,
    rawQuery: string,
  ): SearchOutcome {
    const query = rawQuery.trim();
    if (query.length < SEARCH_MIN_LENGTH) {
      return { hits: [], dropped: 0 };
    }

    const exactResults = miniSearch.search(query, {
      ...searchOptions,
      combineWith: "AND",
    });
    const fuzzyResults = miniSearch.search(query, searchOptions);

    const merged = new Map<unknown, SearchResult>();
    for (const result of [...exactResults, ...fuzzyResults]) {
      if (!merged.has(result.id)) {
        merged.set(result.id, result);
      }
    }

    // The stored fields ride along on each result under an index signature,
    // so each one is checked before it is trusted.
    const hits = [...merged.values()].filter((result): result is SearchResult & DocSearchHit =>
      isDocSearchHit(result),
    );
    return { hits: hits.slice(0, RESULT_LIMIT), dropped: merged.size - hits.length };
  }

  /* Draw the results list and its count, then show the panel and mark the
     active option. Takes its collaborators as one options object because the
     list, meta, input, and panel all have to move together. */
  function renderResults({
    activeIndex,
    activeResults,
    input,
    meta,
    panel,
    resultsList,
    siteRoot,
  }: RenderState): void {
    const query = input.value.trim();

    if (query.length < SEARCH_MIN_LENGTH) {
      resultsList.innerHTML = "";
      meta.textContent = "Type at least 2 characters to search the docs.";
      hidePanel(panel, input);
      return;
    }

    if (activeResults.length === 0) {
      resultsList.innerHTML = "";
      meta.textContent = `No docs matched “${query}”.`;
      showPanel(panel, input);
      return;
    }

    resultsList.innerHTML = activeResults
      .map((result, index) => {
        const href = toAbsoluteSiteHref(siteRoot, result.sitePath);
        const subtitle = result.sectionTitle || result.pageTitle;
        const excerpt = escapeHtml(result.excerpt || "");

        return `
          <li>
            <a
              href="${href}"
              data-doc-search-option
              data-doc-search-index="${index}"
              class="doc-search-option block px-4 py-3 transition-colors hover:bg-boxwood-pale focus:bg-boxwood-pale focus:outline-none"
            >
              <div class="flex items-center justify-between gap-3">
                <span class="text-sm font-semibold text-charcoal">${escapeHtml(result.title)}</span>
                <span class="shrink-0 rounded-full border border-stone bg-white px-2 py-0.5 text-[11px] font-mono uppercase tracking-wide text-charcoal-light">${escapeHtml(result.kind)}</span>
              </div>
              <div class="mt-1 text-xs font-mono text-indigo">${escapeHtml(subtitle)}</div>
              <p class="mt-2 text-sm leading-relaxed text-charcoal-mid">${excerpt}</p>
            </a>
          </li>
        `;
      })
      .join("");

    meta.textContent = `${activeResults.length} result${activeResults.length === 1 ? "" : "s"} ready. Use ↑ and ↓ to move, Enter to open.`;
    showPanel(panel, input);
    updateActiveResult(resultsList, activeIndex);
  }

  /* Move the highlight to the option at `activeIndex`, clearing it from the
     rest. Pass an index no option holds to clear it entirely. */
  function updateActiveResult(resultsList: HTMLElement, activeIndex: number): void {
    const options = resultsList.querySelectorAll("[data-doc-search-option]");

    for (const option of options) {
      const optionIndex = Number(option.getAttribute("data-doc-search-index"));
      const isActive = optionIndex === activeIndex;
      option.classList.toggle("bg-boxwood-pale", isActive);
      option.classList.toggle("border-l-4", isActive);
      option.classList.toggle("border-vermillion", isActive);
    }
  }

  /* Reveal the results panel and record it as expanded on the combobox. */
  function showPanel(panel: HTMLElement, input: HTMLInputElement): void {
    panel.classList.remove("hidden");
    input.setAttribute("aria-expanded", "true");
  }

  /* Hide the results panel and record it as collapsed on the combobox. */
  function hidePanel(panel: HTMLElement, input: HTMLInputElement): void {
    panel.classList.add("hidden");
    input.setAttribute("aria-expanded", "false");
  }

  // Pages can carry more than one search root for the same index (desktop
  // sidebar plus the mobile docs bar). Fetch, parse, and deserialize each
  // index once, sharing the MiniSearch instance across roots; UI state and
  // listeners stay per-root. The cache stores promises so concurrent roots
  // reuse the in-flight load, and a failed or empty load is evicted so a
  // later root can retry. `load` is injectable for tests.
  function createIndexCache<T>(
    load: (path: string) => Promise<T | null>,
  ): (path: string) => Promise<T | null> {
    const cache = new Map<string, Promise<T | null>>();
    return function loadCached(path: string): Promise<T | null> {
      if (!cache.has(path)) {
        const pending = Promise.resolve()
          .then(() => load(path))
          .then(
            (loaded) => {
              if (!loaded) {
                cache.delete(path);
              }
              return loaded;
            },
            (error) => {
              cache.delete(path);
              throw error;
            },
          );
        cache.set(path, pending);
      }
      // Set on the branch above when absent, which `has` does not tell the
      // checker.
      return cache.get(path) as Promise<T | null>;
    };
  }

  /* Fetch and deserialize one MiniSearch index, returning the index and the
     search options it was built with, or null when the request fails — a
     search box that cannot load its index simply stays inert. */
  async function fetchSearchIndex(searchIndexPath: string): Promise<LoadedIndex | null> {
    const response = await fetch(searchIndexPath);
    if (!response.ok) {
      reportIndexFailure("http", response.status);
      return null;
    }
    const payload: unknown = await response.json();
    if (!isIndexPayload(payload)) {
      reportIndexFailure("invalid-payload");
      return null;
    }
    return {
      miniSearch: window.MiniSearch.loadJSON(payload.index, payload.indexOptions),
      searchOptions: payload.indexOptions.searchOptions,
    };
  }

  const loadSearchIndex = createIndexCache(fetchSearchIndex);

  /* The sub-site root a set of results belongs to, recovered from the index
     path. Falls back to "/" when the expected marker is absent. */
  function siteRootFromIndexPath(indexPath: string): string {
    // Index files live at "<siteRoot>assets/search/<name>.json", so the
    // prefix before that marker is the sub-site root the results belong to.
    const marker = "assets/search/";
    const markerIndex = indexPath.indexOf(marker);
    return markerIndex >= 0 ? indexPath.slice(0, markerIndex) : "/";
  }

  /* Join a site root and an indexed path into an absolute same-origin href,
     preserving the fragment that takes the reader to the right section. */
  function toAbsoluteSiteHref(siteRoot: string, sitePath: string): string {
    const url = new URL(siteRoot + sitePath, window.location.origin);
    return `${url.pathname}${url.hash}`;
  }

  /* Escape `text` for interpolation into result markup. Indexed content is
     built from the site's own pages, but it still reaches innerHTML. */
  function escapeHtml(text: string): string {
    return text
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { createIndexCache, isDocSearchHit, isIndexPayload, siteRootFromIndexPath };
  }
})();
