/**
 * @file Client-side search over the Episodic subsite and upstream documentation.
 *
 * Responsibilities: initialize each `[data-search-root]`, load the shared
 * MiniSearch index at that explicit boundary, rank query-time results, and
 * preserve keyboard-accessible listbox state. Load this classic deferred
 * script after MiniSearch; the category listing remains the no-JavaScript
 * path to every document.
 */
(() => {
  const MIN_QUERY_LENGTH = 2;
  const RESULT_LIMIT = 8;
  const TELEMETRY_OPERATION = "episodic-search-index";

  const KIND_LABELS: Record<string, string> = {
    page: "Page",
    section: "Section",
    document: "Upstream document",
  };

  type Index = import("minisearch").default;
  type SearchOptions = import("minisearch").SearchOptions;
  type SearchResult = import("minisearch").SearchResult;

  /** A host-installed sink for the fixed-schema lifecycle events. */
  type TelemetrySink = (event: EpisodicSearchTelemetryEvent) => void;

  /** A deserialized index and the query-time options recorded with it. */
  interface Engine {
    miniSearch: Index;
    searchOptions: SearchOptions;
  }

  /** One result, as the index stores it and the listbox renders it. */
  interface SearchHit {
    id?: unknown;
    sitePath: string;
    title: string;
    kind: string;
    pageTitle?: string;
    sectionTitle?: string;
    excerpt?: string;
  }

  /** Whether `value` is absent or a string, as an optional stored field may be. */
  function isOptionalString(value: unknown): value is string | undefined {
    return value === undefined || typeof value === "string";
  }

  /**
   * Whether a deserialized result carries the stored fields the listbox
   * renders and navigates to, each as a string. The index builder always
   * writes them so, but the index arrives as JSON at runtime; a record that
   * fails this is dropped rather than rendered or navigated to.
   */
  function isSearchHit(value: unknown): value is SearchHit {
    if (typeof value !== "object" || value === null) {
      return false;
    }
    const hit = value as Record<string, unknown>;
    return (
      typeof hit.sitePath === "string" &&
      typeof hit.title === "string" &&
      typeof hit.kind === "string" &&
      isOptionalString(hit.pageTitle) &&
      isOptionalString(hit.sectionTitle) &&
      isOptionalString(hit.excerpt)
    );
  }

  /** The JSON `scripts/build-episodic-search-index.mjs` writes. */
  interface IndexPayload {
    index: string;
    indexOptions?: {
      fields?: string[];
      storeFields?: string[];
      searchOptions?: SearchOptions;
    };
  }

  /** Whether `value` is a list of strings. */
  function isStringArray(value: unknown): value is string[] {
    return Array.isArray(value) && value.every((item) => typeof item === "string");
  }

  /**
   * Whether `value` is the index payload the build script writes: a
   * serialized index, and options carrying the `fields` MiniSearch needs to
   * read it back. The file is fetched at runtime, so its shape is checked
   * rather than assumed.
   */
  function isIndexPayload(value: unknown): value is IndexPayload & {
    indexOptions: { fields: string[] };
  } {
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
    const { fields, storeFields, searchOptions } = options as Record<string, unknown>;
    return (
      isStringArray(fields) &&
      (storeFields === undefined || isStringArray(storeFields)) &&
      (searchOptions === undefined || (typeof searchOptions === "object" && searchOptions !== null))
    );
  }

  /** What `fetchEpisodicSearchIndex` takes from its host; tests pass fakes. */
  interface FetchDeps {
    fetchImpl?: typeof fetch;
    MiniSearch?: typeof globalThis.MiniSearch;
  }

  /**
   * What a query returns: the hits to show, and how many records the
   * stored-field guard dropped, for the caller to report as it sees fit.
   */
  interface SearchOutcome {
    hits: SearchHit[];
    dropped: number;
  }

  /** Called with how many results a query dropped for failing `isSearchHit`. */
  type DropReporter = (count: number) => void;

  /**
   * A reporter that says so once, for one root, so a malformed index cannot
   * shrink the results list silently and cannot flood the console either.
   */
  function onceDropReporter(): DropReporter {
    let reported = false;
    return (count) => {
      if (count > 0 && !reported) {
        reported = true;
        console.warn(`Episodic search dropped ${count} malformed result(s) from the index.`);
      }
    };
  }

  /** The seams `initialiseEpisodicSearch` exposes for testing one root. */
  interface InitOptions {
    loadIndex?: (path: string) => Promise<Engine | undefined> | Engine;
    miniSearch?: unknown;
    searchIndex?: (engine: Engine, query: string) => SearchOutcome;
    navigate?: (href: string) => void;
  }

  /** The settled state of a root's one index load. */
  interface IndexOutcome {
    engine: Engine | null | undefined;
    error?: unknown;
  }

  /**
   * Map a load duration to a bounded telemetry label.
   *
   * @param duration Milliseconds elapsed while loading an index.
   * @returns One of the fixed duration buckets.
   */
  function durationBucket(duration: number): string {
    if (duration < 50) {
      return "under-50ms";
    }
    if (duration < 250) {
      return "50ms-to-249ms";
    }
    if (duration < 1000) {
      return "250ms-to-999ms";
    }
    return "1s-or-more";
  }

  /**
   * Emit one fixed-schema, privacy-preserving search-index lifecycle event.
   *
   * @param telemetry Optional event sink.
   * @param outcome Fixed event outcome.
   * @param cacheState Fixed cache-state label.
   * @param attempt Fixed initial or retry label.
   * @param duration Load duration when one exists.
   */
  function emitSearchTelemetry(
    telemetry: TelemetrySink | undefined,
    outcome: string,
    cacheState: string,
    attempt: string,
    duration?: number,
  ): void {
    if (typeof telemetry !== "function") {
      return;
    }
    const event: EpisodicSearchTelemetryEvent = {
      attempt,
      cache_state: cacheState,
      operation: TELEMETRY_OPERATION,
      outcome,
      ...(duration === undefined ? {} : { duration_bucket: durationBucket(duration) }),
    };
    try {
      telemetry(event);
    } catch {
      // Observability is optional: an unavailable sink must not disable search.
    }
  }

  /**
   * Cache index-loader promises and report bounded lifecycle telemetry.
   *
   * @param load Index loader.
   * @param options Injectable clock and privacy-preserving telemetry sink.
   * @returns Cached index loader.
   */
  function createIndexCache<T>(
    load: (path: string) => Promise<T | undefined>,
    {
      now = () => globalThis.performance?.now?.() ?? Date.now(),
      telemetry,
    }: { now?: () => number; telemetry?: TelemetrySink | undefined } = {},
  ): (path: string) => Promise<T | undefined> {
    const cache = new Map<string, Promise<T | undefined>>();
    const retries = new Set<string>();

    return function loadCached(path: string): Promise<T | undefined> {
      if (cache.has(path)) {
        emitSearchTelemetry(telemetry, "requested", "hit", retries.has(path) ? "retry" : "initial");
      } else {
        const attempt = retries.has(path) ? "retry" : "initial";
        const started = now();
        emitSearchTelemetry(telemetry, "requested", "miss", attempt);
        const pending = Promise.resolve()
          .then(() => load(path))
          .then(
            (loaded) => {
              if (!loaded) {
                cache.delete(path);
                retries.add(path);
                emitSearchTelemetry(telemetry, "failure", "miss", attempt, now() - started);
                emitSearchTelemetry(telemetry, "evicted", "evicted", attempt);
              } else {
                retries.delete(path);
                emitSearchTelemetry(telemetry, "success", "miss", attempt, now() - started);
              }
              return loaded;
            },
            (error) => {
              cache.delete(path);
              retries.add(path);
              emitSearchTelemetry(telemetry, "failure", "miss", attempt, now() - started);
              emitSearchTelemetry(telemetry, "evicted", "evicted", attempt);
              throw error;
            },
          );
        cache.set(path, pending);
      }
      // Set on the branch above when absent, which `has` does not tell the
      // checker.
      return cache.get(path) as Promise<T | undefined>;
    };
  }

  // Fetching and MiniSearch deserialization are intentionally outside the UI
  // query path. Supplying the dependencies keeps this boundary testable.
  async function fetchEpisodicSearchIndex(
    indexPath: string,
    { fetchImpl = globalThis.fetch, MiniSearch = globalThis.MiniSearch }: FetchDeps = {},
  ): Promise<Engine> {
    if (!fetchImpl || !MiniSearch) {
      throw new Error("Episodic search dependencies are unavailable.");
    }

    const response = await fetchImpl(indexPath);
    if (!response.ok) {
      throw new Error(`Index request failed: ${response.status}`);
    }

    const payload: unknown = await response.json();
    if (!isIndexPayload(payload)) {
      throw new Error("Episodic search index payload is malformed.");
    }
    const options = payload.indexOptions;
    return {
      miniSearch: MiniSearch.loadJSON(payload.index, {
        fields: options.fields,
        ...(options.storeFields === undefined ? {} : { storeFields: options.storeFields }),
      }),
      searchOptions: options.searchOptions || {},
    };
  }

  // A host may install this optional function before the deferred script runs.
  // Without it telemetry is a no-op; no query, path, content, or identifier is
  // ever included in the fixed event schema.
  const loadEpisodicSearchIndex = createIndexCache((path) => fetchEpisodicSearchIndex(path), {
    telemetry: globalThis.df12EpisodicSearchTelemetry,
  });

  // Search only consults the already-loaded index. The strict pass gives
  // precise multi-word matches first; the loose pass fills useful fallbacks.
  // A pure query: the count of records dropped for failing `isSearchHit`
  // comes back with the hits, and the caller decides what to do with it.
  function searchEpisodicIndex(engine: Engine, query: string): SearchOutcome {
    const { miniSearch, searchOptions } = engine;
    const strict = miniSearch.search(query, {
      ...searchOptions,
      combineWith: "AND",
    });
    const loose = miniSearch.search(query, searchOptions);

    const merged = new Map<unknown, SearchResult>();
    for (const result of [...strict, ...loose]) {
      if (!merged.has(result.id)) {
        merged.set(result.id, result);
      }
    }
    // The stored fields ride along on each result under an index signature,
    // so each one is checked before it is trusted.
    const hits = [...merged.values()].filter((result): result is SearchResult & SearchHit =>
      isSearchHit(result),
    );
    return { hits: hits.slice(0, RESULT_LIMIT), dropped: merged.size - hits.length };
  }

  /* Wire one rendered search root. `loadIndex`, `searchIndex`, and `navigate`
     are injected at this boundary so event behaviour can be tested without a
     network or real location change. Returns false when the markup or the
     MiniSearch dependency is absent. */
  function initialiseEpisodicSearch(
    root: HTMLElement,
    {
      loadIndex = loadEpisodicSearchIndex,
      miniSearch = globalThis.MiniSearch,
      searchIndex = searchEpisodicIndex,
      navigate = (href: string) => {
        globalThis.window.location.href = href;
      },
    }: InitOptions = {},
  ): boolean {
    const input = root.querySelector<HTMLInputElement>("[data-search-input]");
    const panel = root.querySelector<HTMLElement>("[data-search-panel]");
    const list = root.querySelector<HTMLElement>("[data-search-results]");
    const meta = root.querySelector<HTMLElement>("[data-search-meta]");
    const indexPath = root.getAttribute("data-search-index");
    const pageDocument = root.ownerDocument;

    if (!input || !panel || !list || !meta || !indexPath || !miniSearch || !pageDocument) {
      return false;
    }

    root.hidden = false;
    const listId = list.id || "search-results";
    list.id = listId;
    input.setAttribute("autocomplete", "off");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", listId);
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("role", "combobox");
    input.setAttribute("spellcheck", "false");
    list.setAttribute("role", "listbox");

    let results: SearchHit[] = [];
    let active = -1;
    let request = 0;
    const reportDropped = onceDropReporter();

    // This is the one explicit loading boundary for a root. Recording both
    // outcomes makes a failed eager load safe while leaving queries entirely
    // free of loader and network work.
    let loading: Promise<Engine | undefined>;
    try {
      loading = Promise.resolve(loadIndex(indexPath));
    } catch (error) {
      loading = Promise.reject(error);
    }
    const indexReady: Promise<IndexOutcome> = loading.then(
      (engine) => ({ engine }),
      (error: unknown) => ({ engine: null, error }),
    );

    const open = (): void => {
      panel.hidden = false;
      input.setAttribute("aria-expanded", "true");
    };

    const close = (): void => {
      panel.hidden = true;
      input.setAttribute("aria-expanded", "false");
      setActive(-1);
    };

    const setActive = (index: number): void => {
      active = index;
      const options = [...list.querySelectorAll<HTMLElement>('[role="option"]')];
      options.forEach((option, position) => {
        option.classList.toggle("is-active", position === index);
        option.closest(".search-result")?.classList.toggle("is-active", position === index);
        option.setAttribute("aria-selected", String(position === index));
      });
      if (index >= 0 && options[index]) {
        input.setAttribute("aria-activedescendant", options[index].id);
        options[index].scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    };

    const render = (query: string): void => {
      if (query.length < MIN_QUERY_LENGTH) {
        list.replaceChildren();
        meta.textContent = `Type at least ${MIN_QUERY_LENGTH} characters.`;
        close();
        return;
      }

      if (results.length === 0) {
        list.replaceChildren();
        meta.textContent = `Nothing matched “${query}”. Every document is still listed by category below.`;
        open();
        return;
      }

      list.replaceChildren(
        ...results.map((result, index) => buildOption(pageDocument, result, index, listId)),
      );
      meta.textContent = `${results.length} result${results.length === 1 ? "" : "s"} for “${query}”.`;
      open();
      setActive(-1);
    };

    const showUnavailable = (): void => {
      list.replaceChildren();
      meta.textContent =
        "Search is unavailable in this build. Every document is listed by category below.";
      open();
    };

    const runSearch = async (): Promise<void> => {
      const query = input.value.trim();
      const currentRequest = ++request;
      if (query.length < MIN_QUERY_LENGTH) {
        results = [];
        render(query);
        return;
      }

      const { engine, error } = await indexReady;

      // An older request must not overwrite the result of a newer keystroke,
      // including when both waited on the same cached promise.
      if (currentRequest !== request || query !== input.value.trim()) {
        return;
      }
      if (error) {
        console.warn("Episodic search index unavailable.", error);
        showUnavailable();
        return;
      }
      if (!engine) {
        showUnavailable();
        return;
      }

      const outcome = searchIndex(engine, query);
      results = outcome.hits;
      reportDropped(outcome.dropped);
      render(query);
    };

    const go = (index: number): void => {
      const result = results[index];
      if (result) {
        navigate(result.sitePath);
      }
    };

    input.addEventListener("input", () => {
      void runSearch();
    });

    input.addEventListener("focus", () => {
      if (input.value.trim().length >= MIN_QUERY_LENGTH) {
        open();
      }
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        close();
        return;
      }
      if (panel.hidden || results.length === 0) {
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActive(Math.min(active + 1, results.length - 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActive(Math.max(active - 1, -1));
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        go(active);
      }
    });

    list.addEventListener("mousedown", (event) => {
      const option = (event.target as Element).closest?.<HTMLElement>("[data-result-index]");
      if (option) {
        event.preventDefault();
        go(Number(option.getAttribute("data-result-index")));
      }
    });

    pageDocument.addEventListener("click", (event) => {
      /* A click can be reported against a target that is not a node at all,
         so check before asking the root whether it contains it. */
      const target = event.target;
      if (!(target instanceof Node) || !root.contains(target)) {
        close();
      }
    });

    return true;
  }

  function initialiseAllEpisodicSearch(
    pageDocument: Document | undefined = globalThis.document,
    options?: InitOptions,
  ): void {
    if (!pageDocument) {
      return;
    }

    for (const root of pageDocument.querySelectorAll<HTMLElement>("[data-search-root]")) {
      if (root.dataset.searchInitialised === "true") {
        continue;
      }
      try {
        if (initialiseEpisodicSearch(root, options)) {
          root.dataset.searchInitialised = "true";
        }
      } catch (error) {
        console.warn("Episodic search failed to initialise.", error);
      }
    }
  }

  function buildOption(
    pageDocument: Document,
    result: SearchHit,
    index: number,
    listId: string,
  ): HTMLLIElement {
    const item = pageDocument.createElement("li");
    item.className = "search-result";
    item.setAttribute("role", "presentation");
    item.setAttribute("data-result-index", String(index));

    const link = pageDocument.createElement("a");
    link.className = "search-result__link";
    link.href = result.sitePath;
    link.id = `${listId}-option-${index}`;
    link.setAttribute("aria-selected", "false");
    link.setAttribute("role", "option");

    const kind = pageDocument.createElement("span");
    kind.className = "search-result__kind";
    kind.textContent = KIND_LABELS[result.kind] || "Result";

    const title = pageDocument.createElement("span");
    title.className = "search-result__title";
    title.textContent = result.title;

    link.append(kind, title);

    const context = result.sectionTitle || result.pageTitle;
    if (context && context !== result.title) {
      const where = pageDocument.createElement("span");
      where.className = "search-result__context";
      where.textContent = context;
      link.append(where);
    }

    if (result.excerpt) {
      const excerpt = pageDocument.createElement("span");
      excerpt.className = "search-result__excerpt";
      excerpt.textContent = result.excerpt;
      link.append(excerpt);
    }

    item.append(link);
    return item;
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => initialiseAllEpisodicSearch());
    } else {
      initialiseAllEpisodicSearch();
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      createIndexCache,
      durationBucket,
      emitSearchTelemetry,
      fetchEpisodicSearchIndex,
      initialiseAllEpisodicSearch,
      initialiseEpisodicSearch,
      isIndexPayload,
      isSearchHit,
      searchEpisodicIndex,
    };
  }
})();
