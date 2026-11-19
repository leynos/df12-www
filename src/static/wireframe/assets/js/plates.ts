/**
 * @file Playback for wireframe's Three.js plates.
 *
 * Every plate is server-rendered as a complete poster with an HTML caption,
 * so the page is whole without this script, without WebGL, and in print. The
 * script adds the live scene and its controls, following section 10 of the
 * Common Signal identity (v0.4):
 *
 * - Under ordinary motion settings a plate plays without being asked: the
 *   hero as the page loads, the others as they scroll into view. Its control
 *   reads "Pause illustration", and a pause holds until the visitor plays it
 *   again, whatever scrolling, resizing, or a hidden tab does.
 * - When the browser asks for reduced motion, every plate is a poster with a
 *   "Play illustration" button, and no renderer or WebGL context exists until
 *   that button is pressed. Pressing it plays that one plate, through the
 *   vendored element's `allow-motion` attribute, and offers "Show still".
 * - If the preference changes to reduce, every live plate stops at once and
 *   every opt-in is forgotten. If it changes back, unpaused visible plates
 *   resume and paused ones stay paused.
 * - If the runtime cannot load or a plate loses WebGL, the poster stays and
 *   says so; no control is offered that could not work.
 *
 * The scene itself is `<wireframe-plate>`, loaded on demand as an ES module
 * by dynamic `import()`; this file stays a classic script. The element owns
 * its canvas inside a shadow root and is hidden from assistive technology:
 * the poster's `alt` and the caption are the plate's one accessible
 * description, and the buttons stay in the light DOM beside them.
 *
 * At most `MAX_LIVE` plates keep a renderer. Mounting one more evicts the
 * least recently seen plate that is out of view, which remounts when it
 * returns; a plate in view is never evicted, so the cap cannot turn a
 * visible plate into a poster.
 *
 * `presentation` is a pure query over a plate's state, exported with the
 * controller for the Bun tests; `init` supplies the browser's dependencies.
 */
(() => {
  "use strict";

  /* No page shows more than four plates; the cap only bounds contexts kept
     by plates that have scrolled away. */
  const MAX_LIVE = 4;

  /* The words for each state the element reports, so the status says what
     the scene is actually doing rather than what was asked of it. */
  const ELEMENT_STATUS: Record<string, string> = {
    scanning: "Playing",
    stable: "Playing",
    paused: "Paused",
    still: "Still",
  };

  type Mode = "normal" | "reduced";

  /* What the controller remembers about one plate between events. */
  interface PlateState {
    /** The visitor pressed Pause and has not pressed Play since. */
    userPaused: boolean;
    /** Under reduced motion, the visitor pressed Play for this plate. */
    optIn: boolean;
    /** The plate is in or near the viewport. */
    visible: boolean;
    /** The runtime or WebGL is unavailable for this plate. */
    failed: boolean;
    /** The visitor, or a contrast preference, asked for less glow. */
    lowGlow: boolean;
  }

  /* What a plate should look like for a state: whether a live scene may be
     mounted, how it is set, and which controls show what. */
  interface Presentation {
    live: boolean;
    paused: boolean;
    allowMotion: boolean;
    toggleLabel: "Pause illustration" | "Play illustration";
    showToggle: boolean;
    showStill: boolean;
    showGlow: boolean;
    status: string;
  }

  /* Media queries the controller reads and listens to. */
  interface MediaQuery {
    matches: boolean;
    addEventListener(type: "change", listener: () => void): void;
  }

  /* The observer the controller uses to learn when a plate is in view. */
  type ObserverFactory = (
    callback: (entries: Array<{ target: Element; isIntersecting: boolean }>) => void,
  ) => { observe(target: Element): void };

  /* What `createPlateController` needs from its host. */
  interface PlateDeps {
    document: Document;
    reducedMotion: MediaQuery;
    moreContrast: MediaQuery;
    observe: ObserverFactory;
    /** Resolves once `<wireframe-plate>` is defined; rejects if it cannot be. */
    loadRuntime(url: string): Promise<void>;
    /** Whether the browser can create the WebGL 2 context the runtime needs. */
    webgl: boolean;
  }

  /* One wired figure and its live element, if mounted. */
  interface Plate {
    figure: HTMLElement;
    stage: HTMLElement;
    poster: HTMLImageElement;
    toggle: HTMLButtonElement;
    still: HTMLButtonElement;
    glow: HTMLButtonElement;
    status: HTMLElement;
    state: PlateState;
    element: HTMLElement | null;
    seen: number;
  }

  /* Decide how a plate presents. A failed plate is a poster with a note;
     under reduced motion only an explicit opt-in mounts a scene; otherwise
     a plate is live unless it has failed, and a pause freezes it. */
  function presentation(mode: Mode, state: PlateState): Presentation {
    if (state.failed) {
      return {
        live: false,
        paused: false,
        allowMotion: false,
        toggleLabel: "Play illustration",
        showToggle: false,
        showStill: false,
        showGlow: false,
        status: "Live illustration unavailable; showing the still.",
      };
    }
    const live = mode === "normal" || state.optIn;
    const playing = live && !state.userPaused;
    let status = "Still";
    if (playing) status = "Playing";
    else if (live) status = "Paused";
    return {
      live,
      paused: state.userPaused,
      allowMotion: mode === "reduced" && state.optIn,
      toggleLabel: playing ? "Pause illustration" : "Play illustration",
      showToggle: true,
      showStill: mode === "reduced" && state.optIn,
      showGlow: mode === "normal" || state.optIn,
      status,
    };
  }

  /* Wire every `[data-wf-plate]` figure in the document. Returns the plates
     and a `sync` hook for tests. */
  function createPlateController(deps: PlateDeps) {
    const doc = deps.document;
    const figures = Array.from(doc.querySelectorAll<HTMLElement>("[data-wf-plate]"));
    const plates: Plate[] = [];
    let clock = 0;
    let runtime: Promise<void> | null = null;

    const mode = (): Mode => (deps.reducedMotion.matches ? "reduced" : "normal");

    /* Load the runtime once. If it cannot load, no plate on the page can
       play, so every plate says so at once rather than when it is reached. */
    function load(url: string): Promise<void> {
      if (!runtime) {
        runtime = deps.loadRuntime(url);
        runtime.catch(() => {
          for (const plate of plates) plate.state.failed = true;
          renderAll();
        });
      }
      return runtime;
    }

    function unmount(plate: Plate): void {
      if (!plate.element) return;
      plate.element.remove();
      plate.element = null;
      plate.figure.dataset.wfPlateLive = "false";
    }

    /* Make room for one more renderer by releasing the least recently seen
       plate that is out of view. */
    function evict(except: Plate): void {
      const mounted = plates.filter((p) => p.element);
      if (mounted.length < MAX_LIVE) return;
      const idle = mounted
        .filter((p) => p !== except && !p.state.visible)
        .sort((a, b) => a.seen - b.seen)[0];
      if (idle) unmount(idle);
    }

    function mount(plate: Plate): void {
      if (plate.element) return;
      evict(plate);
      const element = doc.createElement("wireframe-plate");
      element.setAttribute("plate", plate.figure.dataset.wfPlate ?? "");
      element.setAttribute("aria-hidden", "true");
      element.className = "wf-plate__live";
      const still = plate.poster.cloneNode(false) as HTMLImageElement;
      still.alt = "";
      still.removeAttribute("class");
      still.removeAttribute("id");
      element.append(still);
      // `plate-state` does not bubble, so it is heard on the element itself.
      element.addEventListener("plate-state", (event) => {
        const detail = (event as CustomEvent<string>).detail;
        if (detail === "fallback") plate.state.failed = true;
        render(plate);
      });
      plate.element = element;
      plate.stage.append(element);
      plate.figure.dataset.wfPlateLive = "true";
    }

    /* Apply a plate's presentation: mount or unmount the scene, set its
       attributes, and label the controls to match. */
    function render(plate: Plate): void {
      const shown = presentation(mode(), plate.state);
      // A paused plate that is not already drawn stays a poster: a fresh
      // element frozen at once would hold an almost empty first frame.
      const wantMount =
        shown.live && (plate.element !== null || (plate.state.visible && !shown.paused));
      if (!wantMount) unmount(plate);
      plate.toggle.textContent = shown.toggleLabel;
      plate.toggle.hidden = !shown.showToggle;
      plate.still.hidden = !shown.showStill;
      plate.glow.hidden = !(shown.showGlow && wantMount);
      plate.glow.textContent = plate.state.lowGlow ? "Restore glow" : "Reduce glow";
      const reported = plate.element
        ? ELEMENT_STATUS[plate.element.dataset.state ?? ""]
        : undefined;
      // A plate waiting to scroll into view is neither playing nor still yet,
      // so it reports nothing rather than a state it is not in.
      const waiting = !plate.element && !wantMount && shown.live && !shown.paused;
      let words = reported ?? shown.status;
      if (!reported && wantMount) words = "Loading";
      if (waiting) words = "";
      plate.status.textContent = words;
      plate.figure.dataset.wfPlateState = plate.state.failed
        ? "fallback"
        : (words || "waiting").toLowerCase();
      if (!wantMount) return;
      const url = plate.figure.dataset.wfPlateRuntime ?? "";
      load(url).then(
        () => {
          const now = presentation(mode(), plate.state);
          if (!now.live) return;
          if (!plate.element && (now.paused || !plate.state.visible)) return;
          mount(plate);
          const element = plate.element as HTMLElement | null;
          if (!element) return;
          element.toggleAttribute("paused", now.paused);
          element.toggleAttribute("allow-motion", now.allowMotion);
          element.toggleAttribute("low-glow", plate.state.lowGlow);
        },
        () => {
          plate.state.failed = true;
          render(plate);
        },
      );
    }

    function renderAll(): void {
      for (const plate of plates) render(plate);
    }

    function onToggle(plate: Plate): void {
      const shown = presentation(mode(), plate.state);
      if (shown.toggleLabel === "Pause illustration") {
        plate.state.userPaused = true;
      } else {
        plate.state.userPaused = false;
        if (mode() === "reduced") plate.state.optIn = true;
        plate.state.visible = true;
      }
      render(plate);
    }

    function onStill(plate: Plate): void {
      plate.state.optIn = false;
      plate.state.userPaused = false;
      unmount(plate);
      render(plate);
      plate.toggle.focus();
    }

    function onGlow(plate: Plate): void {
      plate.state.lowGlow = !plate.state.lowGlow;
      render(plate);
    }

    for (const figure of figures) {
      const stage = figure.querySelector<HTMLElement>("[data-wf-plate-stage]");
      const poster = figure.querySelector<HTMLImageElement>("[data-wf-plate-poster]");
      const controls = figure.querySelector<HTMLElement>("[data-wf-plate-controls]");
      const toggle = figure.querySelector<HTMLButtonElement>("[data-wf-plate-toggle]");
      const still = figure.querySelector<HTMLButtonElement>("[data-wf-plate-still]");
      const glow = figure.querySelector<HTMLButtonElement>("[data-wf-plate-glow]");
      const status = figure.querySelector<HTMLElement>("[data-wf-plate-status]");
      if (!stage || !poster || !controls || !toggle || !still || !glow || !status) continue;
      const plate: Plate = {
        figure,
        stage,
        poster,
        toggle,
        still,
        glow,
        status,
        element: null,
        seen: 0,
        state: {
          userPaused: false,
          optIn: false,
          visible: false,
          failed: !deps.webgl,
          lowGlow: deps.moreContrast.matches,
        },
      };
      plates.push(plate);
      controls.hidden = false;
      toggle.addEventListener("click", () => onToggle(plate));
      still.addEventListener("click", () => onStill(plate));
      glow.addEventListener("click", () => onGlow(plate));
    }

    const observer = deps.observe((entries) => {
      for (const entry of entries) {
        const plate = plates.find((p) => p.figure === entry.target);
        if (!plate) continue;
        plate.state.visible = entry.isIntersecting;
        if (entry.isIntersecting) plate.seen = ++clock;
        render(plate);
      }
    });
    for (const plate of plates) observer.observe(plate.figure);

    /* A change to reduce stops everything and forgets every opt-in; a change
       back lets unpaused plates in view play again. */
    deps.reducedMotion.addEventListener("change", () => {
      if (mode() === "reduced") {
        for (const plate of plates) {
          plate.state.optIn = false;
          unmount(plate);
        }
      }
      renderAll();
    });

    /* The hero starts loading the runtime at once rather than at first
       intersection, so its scene is ready as soon as it can be drawn. */
    const eager = plates.find((p) => p.figure.hasAttribute("data-wf-plate-eager"));
    if (eager && mode() === "normal" && !eager.state.failed) {
      load(eager.figure.dataset.wfPlateRuntime ?? "").catch(() => undefined);
    }

    renderAll();
    return { plates, sync: renderAll };
  }

  /* Wire the page's plates with the browser's own dependencies. */
  function init(): void {
    createPlateController({
      document,
      reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)"),
      moreContrast: window.matchMedia("(prefers-contrast: more), (forced-colors: active)"),
      observe: (callback) => new IntersectionObserver(callback, { rootMargin: "200px 0px" }),
      loadRuntime: (url) =>
        import(url).then(() => customElements.whenDefined("wireframe-plate")).then(() => undefined),
      webgl: typeof window.WebGL2RenderingContext === "function",
    });
  }

  if (
    typeof document !== "undefined" &&
    typeof window !== "undefined" &&
    typeof window.IntersectionObserver === "function"
  ) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      presentation,
      createPlateController,
      MAX_LIVE,
    };
  }
})();
