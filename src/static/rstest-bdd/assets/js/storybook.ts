/* The lantern picnic storybook on the rstest-bdd home page.
 *
 * The markup is complete without this script: all eight chapters sit in a
 * horizontally scrolling, keyboard-reachable strip (`[data-rb-storybook]`),
 * and the chapter tabs above it are fragment links to each chapter's id.
 * The script adds three things:
 *
 * - The tab for the chapter in view carries `aria-current="true"`, updated
 *   as the strip scrolls.
 * - Choosing a tab scrolls the strip to that chapter without jumping the
 *   page, and moves focus to the chapter so reading continues there.
 * - The previous and next buttons in `[data-rb-story-paging]`, hidden in
 *   the markup because they do nothing without script, are shown and wired,
 *   with a counter naming the chapter in view.
 *
 * Smooth scrolling is dropped when the reader prefers reduced motion.
 *
 * `nearestIndex` and `counterText` are pure queries. The controller takes
 * its dependencies (document, animation frame, motion preference) as
 * arguments so tests can drive it with fakes; `init` at the bottom supplies
 * the real ones. All of them are exported for the Bun tests.
 */
(() => {
  "use strict";

  /* What `createStorybook` needs from its host. */
  interface StorybookDeps {
    document: Document;
    requestFrame(callback: () => void): void;
    prefersReducedMotion(): boolean;
  }

  /* The index of the chapter whose left edge is nearest the strip's scroll
     position. `offsets` are each chapter's left edge relative to the strip's
     scroll origin, in order. An empty list yields -1. */
  function nearestIndex(offsets: number[], scrollLeft: number): number {
    var best = -1;
    var bestDistance = Number.POSITIVE_INFINITY;
    offsets.forEach((offset, index) => {
      var distance = Math.abs(offset - scrollLeft);
      if (distance < bestDistance) {
        best = index;
        bestDistance = distance;
      }
    });
    return best;
  }

  /* The counter's words for chapter `index` (zero-based) of `total`. */
  function counterText(index: number, total: number): string {
    var pad = (n: number) => String(n).padStart(2, "0");
    return `Chapter ${pad(index + 1)} of ${pad(total)}`;
  }

  /* Wire the storybook in `deps.document`. Returns the controller, or null,
     changing nothing, when the page has no storybook or no chapters. */
  function createStorybook(deps: StorybookDeps) {
    var doc = deps.document;
    var track = doc.querySelector<HTMLElement>("[data-rb-storybook]");
    if (!track) {
      return null;
    }
    var strip: HTMLElement = track;
    var chapters = Array.from(strip.querySelectorAll<HTMLElement>("[data-rb-chapter]"));
    if (chapters.length === 0) {
      return null;
    }
    var tabs = Array.from(doc.querySelectorAll<HTMLAnchorElement>("[data-rb-chapter-tab]"));
    var paging = doc.querySelector<HTMLElement>("[data-rb-story-paging]");
    var prev = paging?.querySelector<HTMLButtonElement>("[data-rb-story-prev]");
    var next = paging?.querySelector<HTMLButtonElement>("[data-rb-story-next]");
    var counter = paging?.querySelector<HTMLElement>("[data-rb-story-count]");
    var current = -1;
    var pending = false;

    /* Each chapter's left edge within the strip's scroll area, measured
       from the first chapter's, which sits at scroll position zero. */
    function offsets(): number[] {
      var origin = chapters[0].offsetLeft;
      return chapters.map((chapter) => chapter.offsetLeft - origin);
    }

    /* Mark chapter `index` as the one in view. */
    function mark(index: number): void {
      if (index === current || index < 0) {
        return;
      }
      current = index;
      tabs.forEach((tab, i) => {
        if (i === index) {
          tab.setAttribute("aria-current", "true");
        } else {
          tab.removeAttribute("aria-current");
        }
      });
      if (counter) {
        counter.textContent = counterText(index, chapters.length);
      }
      if (prev) {
        prev.disabled = index === 0;
      }
      if (next) {
        next.disabled = index === chapters.length - 1;
      }
    }

    /* Scroll the strip to chapter `index` and hand it focus. */
    function show(index: number): void {
      var target = chapters[index];
      if (!target) {
        return;
      }
      strip.scrollTo({
        left: offsets()[index],
        behavior: deps.prefersReducedMotion() ? "auto" : "smooth",
      });
      target.focus({ preventScroll: true });
      mark(index);
    }

    /* Recompute the chapter in view, at most once per frame. */
    function onScroll(): void {
      if (pending) {
        return;
      }
      pending = true;
      deps.requestFrame(() => {
        pending = false;
        mark(nearestIndex(offsets(), strip.scrollLeft));
      });
    }

    for (const chapter of chapters) {
      chapter.tabIndex = -1;
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", (event) => {
        event.preventDefault();
        show(index);
      });
    });
    strip.addEventListener("scroll", onScroll, { passive: true });
    if (paging) {
      paging.hidden = false;
      prev?.addEventListener("click", () => show(Math.max(current - 1, 0)));
      next?.addEventListener("click", () => show(Math.min(current + 1, chapters.length - 1)));
    }
    mark(nearestIndex(offsets(), strip.scrollLeft));

    return {
      show: show,
      current: () => current,
    };
  }

  /* Wire the page's storybook, supplying the real document, animation
     frame, and motion preference. */
  function init(): void {
    createStorybook({
      document: document,
      requestFrame: (callback) => {
        window.requestAnimationFrame(callback);
      },
      prefersReducedMotion: () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    });
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      nearestIndex: nearestIndex,
      counterText: counterText,
      createStorybook: createStorybook,
    };
  }
})();
