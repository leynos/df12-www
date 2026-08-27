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

  const KIND_LABELS = {
    page: "Page",
    section: "Section",
    document: "Upstream document",
  };

  /**
   * Map a load duration to a bounded telemetry label.
   *
   * @param {number} duration Milliseconds elapsed while loading an index.
   * @returns {string} One of the fixed duration buckets.
   */
  function durationBucket(duration) {
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
   * @param {((event: object) => void) | undefined} telemetry Optional event sink.
   * @param {string} outcome Fixed event outcome.
   * @param {string} cacheState Fixed cache-state label.
   * @param {string} attempt Fixed initial or retry label.
   * @param {number | undefined} duration Load duration when one exists.
   * @returns {void}
   */
  function emitSearchTelemetry(telemetry, outcome, cacheState, attempt, duration) {
    if (typeof telemetry !== "function") {
      return;
    }
    const event = {
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
   * @param {(path: string) => Promise<object | undefined>} load Index loader.
   * @param {{now?: () => number, telemetry?: (event: object) => void}} [options]
   *     Injectable clock and privacy-preserving telemetry sink.
   * @returns {(path: string) => Promise<object | undefined>} Cached index loader.
   */
  function createIndexCache(
    load,
    { now = () => globalThis.performance?.now?.() ?? Date.now(), telemetry } = {},
  ) {
    const cache = new Map();
    const retries = new Set();

    return function loadCached(path) {
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
      return cache.get(path);
    };
  }

  // Fetching and MiniSearch deserialization are intentionally outside the UI
  // query path. Supplying the dependencies keeps this boundary testable.
  async function fetchEpisodicSearchIndex(
    indexPath,
    { fetchImpl = globalThis.fetch, MiniSearch = globalThis.MiniSearch } = {},
  ) {
    if (!fetchImpl || !MiniSearch) {
      throw new Error("Episodic search dependencies are unavailable.");
    }

    const response = await fetchImpl(indexPath);
    if (!response.ok) {
      throw new Error(`Index request failed: ${response.status}`);
    }

    const payload = await response.json();
    const options = payload.indexOptions || {};
    return {
      miniSearch: MiniSearch.loadJSON(payload.index, {
        fields: options.fields,
        storeFields: options.storeFields,
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
  function searchEpisodicIndex(engine, query) {
    const { miniSearch, searchOptions } = engine;
    const strict = miniSearch.search(query, {
      ...searchOptions,
      combineWith: "AND",
    });
    const loose = miniSearch.search(query, searchOptions);

    const merged = new Map();
    for (const result of [...strict, ...loose]) {
      if (!merged.has(result.id)) {
        merged.set(result.id, result);
      }
    }
    return [...merged.values()].slice(0, RESULT_LIMIT);
  }

  /* Wire one rendered search root. `loadIndex`, `searchIndex`, and `navigate`
     are injected at this boundary so event behaviour can be tested without a
     network or real location change. Returns false when the markup or the
     MiniSearch dependency is absent. */
  function initialiseEpisodicSearch(
    root,
    {
      loadIndex = loadEpisodicSearchIndex,
      miniSearch = globalThis.MiniSearch,
      searchIndex = searchEpisodicIndex,
      navigate = (href) => {
        globalThis.window.location.href = href;
      },
    } = {},
  ) {
    const input = root.querySelector("[data-search-input]");
    const panel = root.querySelector("[data-search-panel]");
    const list = root.querySelector("[data-search-results]");
    const meta = root.querySelector("[data-search-meta]");
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

    let results = [];
    let active = -1;
    let request = 0;

    // This is the one explicit loading boundary for a root. Recording both
    // outcomes makes a failed eager load safe while leaving queries entirely
    // free of loader and network work.
    let loading;
    try {
      loading = Promise.resolve(loadIndex(indexPath));
    } catch (error) {
      loading = Promise.reject(error);
    }
    const indexReady = loading.then(
      (engine) => ({ engine }),
      (error) => ({ engine: null, error }),
    );

    const open = () => {
      panel.hidden = false;
      input.setAttribute("aria-expanded", "true");
    };

    const close = () => {
      panel.hidden = true;
      input.setAttribute("aria-expanded", "false");
      setActive(-1);
    };

    const setActive = (index) => {
      active = index;
      const options = [...list.querySelectorAll('[role="option"]')];
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

    const render = (query) => {
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

    const showUnavailable = () => {
      list.replaceChildren();
      meta.textContent =
        "Search is unavailable in this build. Every document is listed by category below.";
      open();
    };

    const runSearch = async () => {
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

      results = searchIndex(engine, query);
      render(query);
    };

    const go = (index) => {
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
      const option = event.target.closest?.("[data-result-index]");
      if (option) {
        event.preventDefault();
        go(Number(option.getAttribute("data-result-index")));
      }
    });

    pageDocument.addEventListener("click", (event) => {
      if (!root.contains(event.target)) {
        close();
      }
    });

    return true;
  }

  function initialiseAllEpisodicSearch(pageDocument = globalThis.document, options) {
    if (!pageDocument) {
      return;
    }

    for (const root of pageDocument.querySelectorAll("[data-search-root]")) {
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

  function buildOption(pageDocument, result, index, listId) {
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
      searchEpisodicIndex,
    };
  }
})();
