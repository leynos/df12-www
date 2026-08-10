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

  if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", () => {
      const searchRoots = document.querySelectorAll("[data-doc-search-root]");

      for (const root of searchRoots) {
        initializeDocSearch(root).catch((error) => {
          console.warn("Doc search initialization failed.", error);
        });
      }
    });
  }

  async function initializeDocSearch(root) {
    const input = root.querySelector("[data-doc-search-input]");
    const panel = root.querySelector("[data-doc-search-panel]");
    const resultsList = root.querySelector("[data-doc-search-results]");
    const meta = root.querySelector("[data-doc-search-meta]");
    const searchIndexPath = root.getAttribute("data-doc-search-index");

    if (!input || !panel || !resultsList || !meta || !searchIndexPath) {
      return;
    }

    if (!window.MiniSearch) {
      meta.textContent = "Search is unavailable because MiniSearch did not load.";
      showPanel(panel, input);
      return;
    }

    let loaded;
    try {
      loaded = await loadSearchIndex(searchIndexPath);
    } catch {
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
    let activeResults = [];

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
      activeResults = search(miniSearch, searchOptions, input.value);
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
      if (!root.contains(event.target)) {
        hidePanel(panel, input);
      }
    });

    input.addEventListener("focus", () => {
      if (input.value.trim().length >= SEARCH_MIN_LENGTH) {
        showPanel(panel, input);
      }
    });
  }

  function search(miniSearch, searchOptions, rawQuery) {
    const query = rawQuery.trim();
    if (query.length < SEARCH_MIN_LENGTH) {
      return [];
    }

    const exactResults = miniSearch.search(query, {
      ...searchOptions,
      combineWith: "AND",
    });
    const fuzzyResults = miniSearch.search(query, searchOptions);

    const merged = new Map();
    for (const result of [...exactResults, ...fuzzyResults]) {
      if (!merged.has(result.id)) {
        merged.set(result.id, result);
      }
    }

    return [...merged.values()].slice(0, RESULT_LIMIT);
  }

  function renderResults({
    activeIndex,
    activeResults,
    input,
    meta,
    panel,
    resultsList,
    siteRoot,
  }) {
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

  function updateActiveResult(resultsList, activeIndex) {
    const options = resultsList.querySelectorAll("[data-doc-search-option]");

    for (const option of options) {
      const optionIndex = Number(option.getAttribute("data-doc-search-index"));
      const isActive = optionIndex === activeIndex;
      option.classList.toggle("bg-boxwood-pale", isActive);
      option.classList.toggle("border-l-4", isActive);
      option.classList.toggle("border-vermillion", isActive);
    }
  }

  function showPanel(panel, input) {
    panel.classList.remove("hidden");
    input.setAttribute("aria-expanded", "true");
  }

  function hidePanel(panel, input) {
    panel.classList.add("hidden");
    input.setAttribute("aria-expanded", "false");
  }

  // Pages can carry more than one search root for the same index (desktop
  // sidebar plus the mobile docs bar). Fetch, parse, and deserialize each
  // index once, sharing the MiniSearch instance across roots; UI state and
  // listeners stay per-root. The cache stores promises so concurrent roots
  // reuse the in-flight load, and a failed or empty load is evicted so a
  // later root can retry. `load` is injectable for tests.
  function createIndexCache(load) {
    const cache = new Map();
    return function loadCached(path) {
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
      return cache.get(path);
    };
  }

  async function fetchSearchIndex(searchIndexPath) {
    const response = await fetch(searchIndexPath);
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    return {
      miniSearch: window.MiniSearch.loadJSON(payload.index, payload.indexOptions),
      searchOptions: payload.indexOptions.searchOptions,
    };
  }

  const loadSearchIndex = createIndexCache(fetchSearchIndex);

  function siteRootFromIndexPath(indexPath) {
    // Index files live at "<siteRoot>assets/search/<name>.json", so the
    // prefix before that marker is the sub-site root the results belong to.
    const marker = "assets/search/";
    const markerIndex = indexPath.indexOf(marker);
    return markerIndex >= 0 ? indexPath.slice(0, markerIndex) : "/";
  }

  function toAbsoluteSiteHref(siteRoot, sitePath) {
    const url = new URL(siteRoot + sitePath, window.location.origin);
    return `${url.pathname}${url.hash}`;
  }

  function escapeHtml(text) {
    return text
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { createIndexCache, siteRootFromIndexPath };
  }
})();
