// Stilyagi roadmap page: the phase accordion.  Only one phase is open at a
// time, matching the source site.  Without scripting every phase renders in
// its server-side state and the content stays reachable.

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
   * Decide which phase is open after activating `clicked`.
   *
   * Activating the open phase closes it, which is why this returns -1 rather
   * than always echoing `clicked` back.
   */
  function nextOpenIndex(current: number, clicked: number): number {
    return current === clicked ? -1 : clicked;
  }

  function init(): void {
    const heads = [...document.querySelectorAll<HTMLElement>(".ph-head[aria-controls]")];
    if (!heads.length) return;

    const setOpen = (head: HTMLElement, open: boolean): void => {
      head.setAttribute("aria-expanded", String(open));
      const phase = head.closest(".phase");
      if (!phase) return;
      phase.classList.toggle("open", open);
      phase.classList.toggle("closed", !open);
    };

    const currentIndex = (): number =>
      heads.findIndex((head) => head.getAttribute("aria-expanded") === "true");

    const activate = (index: number): void => {
      const next = nextOpenIndex(currentIndex(), index);
      heads.forEach((head, i) => {
        setOpen(head, i === next);
      });
    };

    heads.forEach((head, index) => {
      head.addEventListener("click", () => activate(index));
      head.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        activate(index);
      });
    });
  }

  if (typeof document !== "undefined") {
    onReady(init);
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { nextOpenIndex: nextOpenIndex };
  }
})();
