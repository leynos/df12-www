/* Scroll-spy and drop-down behaviour for Cuprum's route map.
 *
 * The route map (`[data-cu-routemap]`, rendered by the `routemap` macro in
 * templates/cuprum/components.jinja) lists a page's sections twice: as a
 * strip on wide screens and as a <details> drop-down on narrow ones. Both
 * work without this script — the links are plain fragment links, and the
 * drop-down opens and closes natively.
 *
 * The script marks the link of the section being read with
 * `aria-current="location"` in both lists, and copies that link's number and
 * label into the drop-down's summary, so a closed menu still says where the
 * reader is. It also closes the menu once a section is chosen, on Escape
 * (returning focus to the summary), and on a click outside it.
 *
 * A section counts as being read once its top has passed the bottom of the
 * sticky route map, with a little room to spare; at the foot of the page the
 * last section is current, so a short closing section can still be marked.
 *
 * `pickActiveIndex` is a pure decision and `collectTargets` a query over the
 * route map's links. The controller takes its dependencies (document,
 * viewport, animation-frame scheduler) as arguments so tests can drive it
 * with fakes; `init` at the bottom supplies the real ones. All of them are
 * exported for the Bun tests.
 */
(() => {
  "use strict";

  var SLACK = 24; // px below the route map at which a section counts as reached

  /* Decide which section is being read: the last whose top has passed
     `offset`, or the final one once the page is scrolled to the bottom.
     Returns an index into `tops`, or -1 when no section has been reached. */
  function pickActiveIndex(tops: number[], offset: number, atBottom: boolean): number {
    if (atBottom && tops.length > 0) {
      return tops.length - 1;
    }
    var active = -1;
    for (let i = 0; i < tops.length; i += 1) {
      if (tops[i] <= offset) {
        active = i;
      }
    }
    return active;
  }

  /* One section: the element a fragment names, and every link to it. */
  interface Target {
    id: string;
    el: HTMLElement;
    links: HTMLAnchorElement[];
  }

  /* The page geometry the scroll-spy reads, and the events that move it. The
     browser wiring reads `window` and the root element; the tests a fake. */
  interface Viewport {
    scrollY(): number;
    innerHeight(): number;
    scrollHeight(): number;
    listen(type: "scroll" | "resize", listener: () => void): void;
  }

  /* What `createRouteMapController` needs from its host. `requestFrame` runs
     a callback before the next paint, as `window.requestAnimationFrame`
     does. */
  interface RouteMapDeps {
    document: Document;
    viewport: Viewport;
    requestFrame(callback: () => void): void;
  }

  /* Pair each distinct fragment in the route map with its section in `doc`,
     in the order the strip lists them. Links to a missing section are
     ignored; later links to a section already found join its links. */
  function collectTargets(doc: Document, nav: HTMLElement): Target[] {
    var byId = new Map<string, Target>();
    var links = nav.querySelectorAll<HTMLAnchorElement>("a[data-cu-routemap-link]");
    for (const link of links) {
      const id = decodeURIComponent((link.getAttribute("href") ?? "").replace(/^#/, ""));
      const existing = byId.get(id);
      if (existing) {
        existing.links.push(link);
        continue;
      }
      const el = id ? doc.getElementById(id) : null;
      if (el) {
        byId.set(id, { id: id, el: el, links: [link] });
      }
    }
    return Array.from(byId.values());
  }

  /* The component proper. Wires one route map and returns its targets and
     its update and schedule steps, or null, wiring nothing, when it names
     no section in `deps.document`. */
  function createRouteMapController(nav: HTMLElement, deps: RouteMapDeps) {
    var targets = collectTargets(deps.document, nav);
    if (!targets.length) {
      return null;
    }
    var menu = nav.querySelector<HTMLDetailsElement>("details");
    var summary = menu ? menu.querySelector<HTMLElement>("summary") : null;
    var current = nav.querySelector<HTMLElement>("[data-cu-routemap-current]");
    var fallback = current ? current.textContent : "";
    var active: Target | null = null;

    /* Move the mark to `target`, or clear it; does nothing when the target
       is already current, so scrolling within a section touches nothing. */
    function setActive(target: Target | null): void {
      if (target === active) {
        return;
      }
      if (active) {
        for (const link of active.links) {
          link.removeAttribute("aria-current");
        }
      }
      if (target) {
        for (const link of target.links) {
          link.setAttribute("aria-current", "location");
        }
      }
      if (current) {
        if (target) {
          current.replaceChildren(...Array.from(target.links[0].cloneNode(true).childNodes));
        } else {
          current.textContent = fallback;
        }
      }
      active = target;
    }

    /* Recompute the section being read. Reads layout, so it runs in an
       animation frame rather than directly from an event. */
    function update(): void {
      var offset = nav.getBoundingClientRect().bottom + SLACK;
      var viewport = deps.viewport;
      var atBottom = viewport.innerHeight() + viewport.scrollY() >= viewport.scrollHeight() - 2;
      var tops = targets.map((target) => target.el.getBoundingClientRect().top);
      var index = pickActiveIndex(tops, offset, atBottom);
      setActive(index >= 0 ? targets[index] : null);
    }

    var ticking = false;
    /* Coalesce a burst of scroll or resize events into one layout read. */
    function schedule(): void {
      if (!ticking) {
        ticking = true;
        deps.requestFrame(() => {
          ticking = false;
          update();
        });
      }
    }

    deps.viewport.listen("scroll", schedule);
    deps.viewport.listen("resize", schedule);
    update();

    var controller = {
      targets: targets,
      update: update,
      schedule: schedule,
      /* The section currently marked, or null. */
      active: (): Target | null => active,
    };

    if (!menu) {
      return controller;
    }
    var details = menu;
    details.addEventListener("click", (event) => {
      if (event.target instanceof Element && event.target.closest("a[data-cu-routemap-link]")) {
        details.open = false;
      }
    });
    details.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && details.open) {
        details.open = false;
        if (summary) {
          summary.focus();
        }
      }
    });
    deps.document.addEventListener("click", (event) => {
      if (details.open && event.target instanceof Node && !details.contains(event.target)) {
        details.open = false;
      }
    });
    return controller;
  }

  /* Wire every route map on the page; most pages have one, some none.
     Supplies the real document, viewport, and animation frames. */
  function init(): void {
    var deps: RouteMapDeps = {
      document: document,
      viewport: {
        scrollY: () => window.scrollY,
        innerHeight: () => window.innerHeight,
        scrollHeight: () => document.documentElement.scrollHeight,
        listen: (type, listener) => {
          window.addEventListener(type, listener, { passive: true });
        },
      },
      requestFrame: (callback) => {
        window.requestAnimationFrame(() => callback());
      },
    };
    for (const nav of document.querySelectorAll<HTMLElement>("[data-cu-routemap]")) {
      createRouteMapController(nav, deps);
    }
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
      pickActiveIndex: pickActiveIndex,
      collectTargets: collectTargets,
      createRouteMapController: createRouteMapController,
      SLACK: SLACK,
    };
  }
})();
