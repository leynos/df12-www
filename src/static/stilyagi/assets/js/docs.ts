// Stilyagi docs page: rules-catalogue filtering, the suppression tab pair, and
// the section rail.  Every widget enhances markup that is already complete and
// correct without scripting — filters start at "all", both tab panels exist,
// and the rail is a list of ordinary in-page links.

(() => {
  "use strict";

  const onReady = (fn: () => void): void => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  };

  /**
   * Decide whether a rule row survives the current filter.
   *
   * `namespace` is the selected chip ("all" matches every row) and `query` is
   * the raw contents of the search box.  `haystack` is the row's precomputed
   * lowercase "id title description" string.
   */
  function matchesFilter(
    rowNamespace: string | undefined,
    haystack: string | undefined,
    namespace: string,
    query: string,
  ): boolean {
    if (namespace !== "all" && rowNamespace !== namespace) return false;
    const needle = (query || "").trim().toLowerCase();
    if (!needle) return true;
    return (haystack || "").includes(needle);
  }

  /** Filter the rules table by namespace chip and free-text search. */
  function initCatalogue(): void {
    const bar = document.querySelector<HTMLElement>(".filter-bar");
    const table = document.querySelector<HTMLTableElement>(".rules-table");
    if (!bar || !table) return;

    const chips = [...bar.querySelectorAll<HTMLElement>(".filter-chip[data-ns]")];
    const select = bar.querySelector<HTMLSelectElement>(".filter-select");
    const search = bar.querySelector<HTMLInputElement>("#rule-search");
    const rows = [...table.querySelectorAll<HTMLTableRowElement>("tbody tr[data-ns]")];
    const emptyRow = table.querySelector<HTMLTableRowElement>("tbody .empty-row");
    if (!chips.length || !rows.length) return;

    let namespace = "all";

    const apply = (): void => {
      const query = search ? search.value : "";
      let visible = 0;
      for (const row of rows) {
        const show = matchesFilter(row.dataset.ns, row.dataset.search, namespace, query);
        row.hidden = !show;
        if (show) visible += 1;
      }
      if (emptyRow) emptyRow.hidden = visible !== 0;
    };

    // The chip row and the select are the same control at different widths,
    // so a change to either has to leave the other showing the same answer.
    const choose = (next: string): void => {
      namespace = next;
      for (const chip of chips) {
        const active = chip.dataset.ns === next;
        chip.classList.toggle("active", active);
        // The namespace tint is only worn while the chip is selected.
        const tint = chip.dataset.nsClass;
        if (tint) chip.classList.toggle(tint, active);
        chip.setAttribute("aria-pressed", String(active));
      }
      if (select && select.value !== next) select.value = next;
      apply();
    };

    for (const chip of chips) {
      chip.addEventListener("click", () => choose(chip.dataset.ns ?? ""));
    }

    if (select) {
      select.addEventListener("change", () => choose(select.value));
    }

    if (search) {
      search.addEventListener("input", apply);
    }

    // A reload or a back-navigation restores the search text and the select's
    // value, but not the table they describe.  Settle the rows against
    // whatever the controls are actually showing.
    if (select?.value && select.value !== namespace) {
      choose(select.value);
    } else {
      apply();
    }
  }

  /** Swap the Markdown and Python suppression examples. */
  function initSuppressionTabs(): void {
    const tablist = document.querySelector<HTMLElement>('.suppress .syntax-tabs[role="tablist"]');
    if (!tablist) return;

    const tabs = [...tablist.querySelectorAll<HTMLElement>('[role="tab"][data-tab]')];
    const panels = new Map(
      [...document.querySelectorAll<HTMLElement>(".suppress [data-panel]")].map((panel) => [
        panel.dataset.panel,
        panel,
      ]),
    );
    if (tabs.length < 2 || panels.size < 2) return;

    const select = (tab: HTMLElement): void => {
      for (const other of tabs) {
        const active = other === tab;
        other.classList.toggle("active", active);
        other.setAttribute("aria-selected", String(active));
        // Only the selected tab stays in the tab order; the arrow keys move
        // between them, which is what a tablist is expected to do.
        other.tabIndex = active ? 0 : -1;
        const panel = panels.get(other.dataset.tab);
        if (panel) panel.hidden = !active;
      }
    };

    tablist.addEventListener("click", (event) => {
      const tab = (event.target as Element).closest<HTMLElement>('[role="tab"][data-tab]');
      if (tab) select(tab);
    });

    const STEPS: Record<string, number> = {
      ArrowRight: 1,
      ArrowLeft: -1,
      ArrowDown: 1,
      ArrowUp: -1,
    };
    tablist.addEventListener("keydown", (event) => {
      const step = STEPS[event.key];
      if (!step) return;
      const index = tabs.indexOf(document.activeElement as HTMLElement);
      if (index === -1) return;
      event.preventDefault();
      const next = tabs[(index + step + tabs.length) % tabs.length];
      select(next);
      next.focus();
    });

    select(tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0]);
  }

  /** Mark the rail entry for whichever section is in view. */
  function initSectionRail(): void {
    const rail = document.querySelector<HTMLElement>(".side-toc");
    if (!rail || !("IntersectionObserver" in window)) return;

    const links = new Map(
      [...rail.querySelectorAll<HTMLAnchorElement>('a[href^="#"]')].map((link) => [
        (link.getAttribute("href") ?? "").slice(1),
        link,
      ]),
    );
    const sections = [...links.keys()]
      .map((id) => document.getElementById(id))
      .filter((section): section is HTMLElement => section !== null);
    if (!sections.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          for (const link of links.values()) link.classList.remove("active");
          const link = links.get(entry.target.id);
          if (link) link.classList.add("active");
        }
      },
      // Treats the middle band of the viewport as "the section being read".
      { rootMargin: "-40% 0px -55% 0px" },
    );
    for (const section of sections) observer.observe(section);
  }

  if (typeof document !== "undefined") {
    onReady(() => {
      initCatalogue();
      initSuppressionTabs();
      initSectionRail();
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { matchesFilter: matchesFilter };
  }
})();
