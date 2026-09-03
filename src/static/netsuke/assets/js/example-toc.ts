/**
 * @file example-toc.ts — scroll behaviour for the Netsuke example pages' contents list.
 *
 * A plain script module in the shape described in section 6 of the
 * developers' guide: an IIFE loaded with `<script defer>` that addresses its
 * markup through a `data-` attribute and returns early when that markup is
 * absent, so the one script may be included on pages that have no contents
 * list. The list itself is rendered by `templates/netsuke/`; this file only
 * adds the smooth scrolling and the offset that keeps a target heading clear
 * of the fixed page header.
 *
 * Usage: `templates/netsuke/pages/examples-*.jinja` loads the compiled script with a plain
 * `<script defer src="/netsuke/assets/js/example-toc.js">` tag; `build:js` compiles that file
 * from this `.ts` source. There is no initialisation call — the IIFE runs on load and simply
 * waits for `DOMContentLoaded` before it looks for the contents-list markup.
 */
(() => {
  const HEADER_OFFSET = 120;

  /* A contents link paired with the section its fragment names. */
  interface Target {
    link: HTMLAnchorElement;
    section: HTMLElement;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const toc = document.querySelector<HTMLElement>("[data-page-toc]");

    if (!toc) {
      return;
    }

    const links = [...toc.querySelectorAll<HTMLAnchorElement>('a[href^="#"]')];
    const targets = links
      .map((link): Target | null => {
        const id = (link.getAttribute("href") ?? "").slice(1);
        const section = document.getElementById(id);
        return section ? { link, section } : null;
      })
      .filter((target): target is Target => target !== null);

    if (targets.length === 0) {
      return;
    }

    let ticking = false;

    /* Mark `current` as the active link and clear the mark from the rest. */
    function activate(current: HTMLAnchorElement): void {
      for (const { link } of targets) {
        link.classList.toggle("is-active", link === current);
      }
    }

    /* Pick the section being read and highlight its link.
       That is the last section whose heading has passed the header offset,
       or the final section once the page is scrolled to the bottom, so a
       short closing section can still activate. Reads layout, so it runs
       inside an animation frame rather than directly on scroll. */
    function update(): void {
      ticking = false;
      const threshold = HEADER_OFFSET;
      let current = targets[0];

      for (const target of targets) {
        if (target.section.getBoundingClientRect().top <= threshold) {
          current = target;
        }
      }

      const scrollBottom = window.innerHeight + window.scrollY;
      const pageHeight = document.documentElement.scrollHeight;
      if (pageHeight - scrollBottom < 2) {
        current = targets[targets.length - 1];
      }

      activate(current.link);
    }

    /* Schedule `update` for the next animation frame, coalescing the bursts
       of scroll and resize events into one layout read per frame. */
    function requestUpdate(): void {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(update);
      }
    }

    window.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate, { passive: true });
    update();
  });
})();
