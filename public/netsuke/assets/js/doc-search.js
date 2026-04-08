(function () {
  const SEARCH_MIN_LENGTH = 2;
  const RESULT_LIMIT = 6;

  document.addEventListener("DOMContentLoaded", () => {
    const searchRoots = document.querySelectorAll("[data-doc-search-root]");

    for (const root of searchRoots) {
      initializeDocSearch(root).catch((error) => {
        console.warn("Doc search initialization failed.", error);
      });
    }
  });

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

    const response = await fetch(searchIndexPath);
    if (!response.ok) {
      meta.textContent = "Search index is not available in this build.";
      showPanel(panel, input);
      return;
    }

    const payload = await response.json();
    const searchOptions = payload.indexOptions.searchOptions;
    const miniSearch = window.MiniSearch.loadJSON(payload.index, payload.indexOptions);

    let activeIndex = -1;
    let activeResults = [];

    input.setAttribute("autocomplete", "off");
    input.setAttribute("spellcheck", "false");
    input.setAttribute("aria-expanded", "false");

    document.addEventListener("keydown", (event) => {
      const wantsShortcut =
        (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";

      if (!wantsShortcut) {
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
          window.location.href = toAbsoluteSiteHref(selected.sitePath);
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
        const href = toAbsoluteSiteHref(result.sitePath);
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

  function toAbsoluteSiteHref(sitePath) {
    const docsMarker = "/docs/";
    const pathname = window.location.pathname;
    const markerIndex = pathname.indexOf(docsMarker);
    const siteRoot = markerIndex >= 0 ? pathname.slice(0, markerIndex + 1) : "/";
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
})();
