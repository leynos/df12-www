/* Client-side search over the Episodic subsite and its upstream documentation.
 *
 * Wires every `[data-search-root]` element to the MiniSearch index named by
 * its `data-search-index` attribute. The index is built by
 * scripts/build_search_index.mjs and covers three kinds of record: on-site
 * pages, on-site sections, and upstream documents.
 *
 * Progressive enhancement contract:
 *
 *   - the root ships with `hidden` set, and this script removes it only once
 *     MiniSearch has loaded, so a reader without JavaScript never meets an
 *     input that does nothing;
 *   - the index is fetched on first interaction rather than on page load, so
 *     the 56KB payload costs nothing to anyone who does not search; and
 *   - every indexed destination is reachable through the ordinary category
 *     listing below, which search never replaces.
 *
 * The script is safe when its root is absent, and it never throws into the
 * page: a failed index load degrades to a message inside the panel.
 */
(() => {
  const MIN_QUERY_LENGTH = 2;
  const RESULT_LIMIT = 8;

  const KIND_LABELS = {
    page: "Page",
    section: "Section",
    document: "Upstream document",
  };

  if (typeof document === "undefined") {
    return;
  }

  const initialiseAll = () => {
    for (const root of document.querySelectorAll("[data-search-root]")) {
      if (root.dataset.searchInitialised === "true") {
        continue;
      }
      root.dataset.searchInitialised = "true";
      try {
        initialise(root);
      } catch (error) {
        console.warn("Episodic search failed to initialise.", error);
      }
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiseAll);
  } else {
    initialiseAll();
  }

  function initialise(root) {
    const input = root.querySelector("[data-search-input]");
    const panel = root.querySelector("[data-search-panel]");
    const list = root.querySelector("[data-search-results]");
    const meta = root.querySelector("[data-search-meta]");
    const indexPath = root.getAttribute("data-search-index");

    if (!input || !panel || !list || !meta || !indexPath) {
      return;
    }

    // MiniSearch is what makes the control work, so its presence is the
    // condition for revealing the control at all.
    if (!window.MiniSearch) {
      return;
    }
    root.hidden = false;

    const listId = list.id || "search-results";
    list.id = listId;
    input.setAttribute("autocomplete", "off");
    input.setAttribute("spellcheck", "false");

    let engine = null;
    let loading = null;
    let results = [];
    let active = -1;

    const ensureIndex = () => {
      if (engine) {
        return Promise.resolve(engine);
      }
      if (!loading) {
        loading = fetch(indexPath)
          .then((response) => {
            if (!response.ok) {
              throw new Error(`Index request failed: ${response.status}`);
            }
            return response.json();
          })
          .then((payload) => {
            const options = payload.indexOptions || {};
            engine = {
              miniSearch: window.MiniSearch.loadJSON(payload.index, {
                fields: options.fields,
                storeFields: options.storeFields,
              }),
              searchOptions: options.searchOptions || {},
            };
            return engine;
          })
          .catch((error) => {
            console.warn("Episodic search index unavailable.", error);
            return null;
          });
      }
      return loading;
    };

    const render = () => {
      const query = input.value.trim();

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

      list.replaceChildren(...results.map((result, index) => buildOption(result, index, listId)));
      meta.textContent = `${results.length} result${results.length === 1 ? "" : "s"} for “${query}”.`;
      open();
      setActive(-1);
    };

    const runSearch = async () => {
      const query = input.value.trim();
      if (query.length < MIN_QUERY_LENGTH) {
        results = [];
        render();
        return;
      }

      const loaded = await ensureIndex();
      if (query !== input.value.trim()) {
        return;
      }
      if (!loaded) {
        list.replaceChildren();
        meta.textContent =
          "Search is unavailable in this build. Every document is listed by category below.";
        open();
        return;
      }

      results = search(loaded, query);
      render();
    };

    const open = () => {
      panel.hidden = false;
    };

    const close = () => {
      panel.hidden = true;
      active = -1;
    };

    const setActive = (index) => {
      active = index;
      const options = [...list.children];
      options.forEach((option, position) => {
        const selected = position === index;
        option.classList.toggle("is-active", selected);
      });
      if (index >= 0 && options[index]) {
        options[index].scrollIntoView({ block: "nearest" });
      }
    };

    const go = (index) => {
      const result = results[index];
      if (result) {
        window.location.href = result.sitePath;
      }
    };

    input.addEventListener("input", () => {
      void runSearch();
    });

    // Warm the index as soon as the reader shows intent, so the first
    // keystroke does not wait on a fetch.
    input.addEventListener("focus", () => {
      void ensureIndex();
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
      const option = event.target.closest("[data-result-index]");
      if (option) {
        event.preventDefault();
        go(Number(option.getAttribute("data-result-index")));
      }
    });

    document.addEventListener("click", (event) => {
      if (!root.contains(event.target)) {
        close();
      }
    });
  }

  function search(engine, query) {
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

  function buildOption(result, index, listId) {
    const item = document.createElement("li");
    item.className = "search-result";
    item.id = `${listId}-result-${index}`;
    item.setAttribute("data-result-index", String(index));

    const link = document.createElement("a");
    link.className = "search-result__link";
    link.href = result.sitePath;
    link.tabIndex = -1;

    const kind = document.createElement("span");
    kind.className = "search-result__kind";
    kind.textContent = KIND_LABELS[result.kind] || "Result";

    const title = document.createElement("span");
    title.className = "search-result__title";
    title.textContent = result.title;

    link.append(kind, title);

    const context = result.sectionTitle || result.pageTitle;
    if (context && context !== result.title) {
      const where = document.createElement("span");
      where.className = "search-result__context";
      where.textContent = context;
      link.append(where);
    }

    if (result.excerpt) {
      const excerpt = document.createElement("span");
      excerpt.className = "search-result__excerpt";
      excerpt.textContent = result.excerpt;
      link.append(excerpt);
    }

    item.append(link);
    return item;
  }
})();
