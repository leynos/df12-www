/**
 * @file Tests for wireframe's plate playback.
 *
 * The Common Signal identity (v0.4, section 10) fixes how a plate behaves in
 * each motion mode, and these tests hold the script to that table. The
 * `presentation` suite checks the pure decision for every state. The
 * controller suite mounts figures shaped like the `plate` macro in
 * `templates/wireframe/components.jinja` and drives them through fake media
 * queries, a fake intersection observer, and a runtime loader the test
 * resolves, rejects, or counts. The live `<wireframe-plate>` element is the
 * vendored runtime's business and is checked in a browser; here it is an
 * undefined element whose attributes and presence are the observable result.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const SCRIPT = join("public", "wireframe", "assets", "js", "plates.js");
const { presentation, createPlateController, MAX_LIVE } = require(`../../${SCRIPT}`);

const RUNTIME = "/wireframe/assets/vendor/plates/wireframe-plate.js";

/* One figure as the macro renders it, reduced to what the script reads. */
function figure(id, { eager = false } = {}) {
  return `
    <figure class="wf-plate" data-wf-plate="${id}" data-wf-plate-runtime="${RUNTIME}"${eager ? " data-wf-plate-eager" : ""}>
      <div class="wf-plate__stage" data-wf-plate-stage>
        <img class="wf-plate__poster" data-wf-plate-poster src="/p/${id}.webp" alt="Plate ${id}" width="929" height="494">
      </div>
      <div class="wf-plate__controls" data-wf-plate-controls hidden>
        <button type="button" data-wf-plate-toggle>Play illustration</button>
        <button type="button" data-wf-plate-still hidden>Show still</button>
        <button type="button" data-wf-plate-glow hidden>Reduce glow</button>
        <span data-wf-plate-status></span>
      </div>
      <figcaption>Plate ${id}</figcaption>
    </figure>`;
}

/* A media query whose answer the test changes, firing `change` as a browser
   does. */
function mediaQuery(matches) {
  const listeners = [];
  return {
    matches,
    addEventListener(_type, listener) {
      listeners.push(listener);
    },
    set(value) {
      this.matches = value;
      for (const listener of listeners) listener();
    },
  };
}

/* Wait for the loader's promise chain to settle. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

/* Mount `ids` and wire them with fakes; returns the handles a test drives. */
function setup(ids, { reduced = false, contrast = false, webgl = true, load } = {}) {
  document.body.innerHTML = ids.map((id, i) => figure(id, { eager: i === 0 })).join("");
  let notify = () => undefined;
  const loads = [];
  const deps = {
    document,
    reducedMotion: mediaQuery(reduced),
    moreContrast: mediaQuery(contrast),
    observe(callback) {
      notify = callback;
      return { observe() {} };
    },
    loadRuntime(url) {
      loads.push(url);
      return load ? load() : Promise.resolve();
    },
    webgl,
  };
  const controller = createPlateController(deps);
  const fig = (id) => document.querySelector(`[data-wf-plate="${id}"]`);
  return {
    deps,
    loads,
    controller,
    fig,
    live: (id) => fig(id).querySelector("wireframe-plate"),
    toggle: (id) => fig(id).querySelector("[data-wf-plate-toggle]"),
    still: (id) => fig(id).querySelector("[data-wf-plate-still]"),
    glow: (id) => fig(id).querySelector("[data-wf-plate-glow]"),
    status: (id) => fig(id).querySelector("[data-wf-plate-status]").textContent,
    async see(id, inView = true) {
      notify([{ target: fig(id), isIntersecting: inView }]);
      await settle();
    },
  };
}

afterEach(() => {
  document.body.innerHTML = "";
});

const base = { userPaused: false, optIn: false, visible: true, failed: false, lowGlow: false };

describe("presentation", () => {
  test("ordinary motion plays without a Play gate and offers Pause", () => {
    const shown = presentation("normal", base);
    expect(shown.live).toBe(true);
    expect(shown.paused).toBe(false);
    expect(shown.allowMotion).toBe(false);
    expect(shown.toggleLabel).toBe("Pause illustration");
    expect(shown.showStill).toBe(false);
  });

  test("a pause under ordinary motion is offered back as Play", () => {
    const shown = presentation("normal", { ...base, userPaused: true });
    expect(shown.paused).toBe(true);
    expect(shown.toggleLabel).toBe("Play illustration");
  });

  test("reduced motion is a still with a Play button until the visitor opts in", () => {
    const shown = presentation("reduced", base);
    expect(shown.live).toBe(false);
    expect(shown.toggleLabel).toBe("Play illustration");
    expect(shown.showToggle).toBe(true);
    expect(shown.showGlow).toBe(false);
  });

  test("an opt-in under reduced motion plays that plate and offers Pause and Show still", () => {
    const shown = presentation("reduced", { ...base, optIn: true });
    expect(shown.live).toBe(true);
    expect(shown.allowMotion).toBe(true);
    expect(shown.toggleLabel).toBe("Pause illustration");
    expect(shown.showStill).toBe(true);
  });

  test("a failed plate offers no control that could not work and says why", () => {
    for (const mode of ["normal", "reduced"]) {
      const shown = presentation(mode, { ...base, failed: true, optIn: true });
      expect(shown.live).toBe(false);
      expect(shown.showToggle).toBe(false);
      expect(shown.showStill).toBe(false);
      expect(shown.status).toContain("unavailable");
    }
  });
});

describe("ordinary motion", () => {
  test("controls appear, and a plate mounts unpaused once it is in view", async () => {
    const page = setup(["27"]);
    expect(page.fig("27").querySelector("[data-wf-plate-controls]").hidden).toBe(false);
    expect(page.live("27")).toBeNull();
    await page.see("27");
    const live = page.live("27");
    expect(live).not.toBeNull();
    expect(live.getAttribute("plate")).toBe("27");
    expect(live.getAttribute("aria-hidden")).toBe("true");
    expect(live.hasAttribute("paused")).toBe(false);
    expect(live.hasAttribute("allow-motion")).toBe(false);
    expect(page.toggle("27").textContent).toBe("Pause illustration");
  });

  test("the hero loads the runtime at once; other plates wait for their turn", async () => {
    const page = setup(["27", "29"]);
    expect(page.loads).toEqual([RUNTIME]);
  });

  test("the live element carries a poster copy that is not announced twice", async () => {
    const page = setup(["27"]);
    await page.see("27");
    const copy = page.live("27").querySelector("img");
    expect(copy.getAttribute("alt")).toBe("");
    expect(page.fig("27").querySelector("[data-wf-plate-poster]").alt).toBe("Plate 27");
  });

  test("Pause holds across leaving and re-entering the viewport", async () => {
    const page = setup(["27"]);
    await page.see("27");
    page.toggle("27").click();
    await settle();
    expect(page.live("27").hasAttribute("paused")).toBe(true);
    expect(page.toggle("27").textContent).toBe("Play illustration");
    await page.see("27", false);
    await page.see("27");
    expect(page.live("27").hasAttribute("paused")).toBe(true);
    page.toggle("27").click();
    await settle();
    expect(page.live("27").hasAttribute("paused")).toBe(false);
  });

  test("the status reports what the element says it is doing", async () => {
    const page = setup(["27"]);
    await page.see("27");
    expect(page.status("27")).toBe("Loading");
    const live = page.live("27");
    live.dataset.state = "scanning";
    live.dispatchEvent(new CustomEvent("plate-state", { detail: "scanning" }));
    expect(page.status("27")).toBe("Playing");
  });
});

describe("reduced motion", () => {
  test("no renderer and no runtime until the visitor presses Play", async () => {
    const page = setup(["27"], { reduced: true });
    await page.see("27");
    expect(page.live("27")).toBeNull();
    expect(page.loads).toEqual([]);
    expect(page.toggle("27").textContent).toBe("Play illustration");
    expect(page.toggle("27").hidden).toBe(false);
  });

  test("Play opts that one plate in; Show still returns it to the poster", async () => {
    const page = setup(["27", "28"], { reduced: true });
    await page.see("27");
    await page.see("28");
    page.toggle("27").click();
    await settle();
    expect(page.live("27").hasAttribute("allow-motion")).toBe(true);
    expect(page.live("28")).toBeNull();
    expect(page.toggle("27").textContent).toBe("Pause illustration");
    expect(page.still("27").hidden).toBe(false);
    page.still("27").click();
    await settle();
    expect(page.live("27")).toBeNull();
    expect(page.still("27").hidden).toBe(true);
    expect(document.activeElement).toBe(page.toggle("27"));
  });

  test("Pause under an opt-in freezes the scene rather than removing it", async () => {
    const page = setup(["27"], { reduced: true });
    await page.see("27");
    page.toggle("27").click();
    await settle();
    page.toggle("27").click();
    await settle();
    expect(page.live("27").hasAttribute("paused")).toBe(true);
    expect(page.toggle("27").textContent).toBe("Play illustration");
  });
});

describe("a change of motion preference", () => {
  test("to reduce stops every plate and forgets every opt-in", async () => {
    const page = setup(["27", "29"], { reduced: true });
    await page.see("27");
    page.toggle("27").click();
    await settle();
    page.deps.reducedMotion.set(false);
    await page.see("29");
    expect(page.live("29")).not.toBeNull();
    page.deps.reducedMotion.set(true);
    await settle();
    expect(page.live("27")).toBeNull();
    expect(page.live("29")).toBeNull();
    expect(page.toggle("27").textContent).toBe("Play illustration");
    await page.see("27");
    expect(page.live("27")).toBeNull();
  });

  test("back to ordinary motion resumes unpaused plates and leaves paused ones paused", async () => {
    const page = setup(["27", "29"]);
    await page.see("27");
    await page.see("29");
    page.toggle("29").click();
    await settle();
    page.deps.reducedMotion.set(true);
    await settle();
    page.deps.reducedMotion.set(false);
    await settle();
    expect(page.live("27")).not.toBeNull();
    expect(page.live("29")).toBeNull();
    expect(page.toggle("29").textContent).toBe("Play illustration");
  });
});

describe("fallback", () => {
  test("a runtime that cannot load leaves the poster and withdraws Play", async () => {
    const page = setup(["27"], { reduced: true, load: () => Promise.reject(new Error("offline")) });
    await page.see("27");
    page.toggle("27").click();
    await settle();
    await settle();
    expect(page.live("27")).toBeNull();
    expect(page.toggle("27").hidden).toBe(true);
    expect(page.status("27")).toContain("unavailable");
    expect(page.fig("27").dataset.wfPlateState).toBe("fallback");
  });

  test("a runtime that cannot load withdraws Play from every plate on the page", async () => {
    const page = setup(["27", "29"], { load: () => Promise.reject(new Error("offline")) });
    await settle();
    for (const id of ["27", "29"]) {
      expect(page.toggle(id).hidden).toBe(true);
      expect(page.status(id)).toContain("unavailable");
    }
  });

  test("without WebGL 2 the plate is a still from the start", async () => {
    const page = setup(["27"], { webgl: false });
    await page.see("27");
    expect(page.live("27")).toBeNull();
    expect(page.toggle("27").hidden).toBe(true);
    expect(page.status("27")).toContain("unavailable");
  });

  test("a lost context returns the plate to its poster", async () => {
    const page = setup(["27"]);
    await page.see("27");
    page.live("27").dispatchEvent(new CustomEvent("plate-state", { detail: "fallback" }));
    await settle();
    expect(page.live("27")).toBeNull();
    expect(page.status("27")).toContain("unavailable");
  });
});

describe("glow", () => {
  test("a contrast preference starts plates with low glow, and the button restores it", async () => {
    const page = setup(["27"], { contrast: true });
    await page.see("27");
    expect(page.live("27").hasAttribute("low-glow")).toBe(true);
    expect(page.glow("27").textContent).toBe("Restore glow");
    page.glow("27").click();
    await settle();
    expect(page.live("27").hasAttribute("low-glow")).toBe(false);
  });

  test("the glow control only shows while a live scene can honour it", async () => {
    const page = setup(["27"], { reduced: true });
    await page.see("27");
    expect(page.glow("27").hidden).toBe(true);
  });
});

describe("the renderer cap", () => {
  test(`keeps at most ${MAX_LIVE} renderers, releasing one out of view first`, async () => {
    const ids = ["06", "15", "21", "26", "27"];
    const page = setup(ids);
    for (const id of ids.slice(0, 4)) await page.see(id);
    await page.see("06", false);
    await page.see("27");
    expect(page.live("06")).toBeNull();
    for (const id of ids.slice(1)) expect(page.live(id)).not.toBeNull();
  });

  test("never releases a plate that is in view", async () => {
    const ids = ["06", "15", "21", "26", "27"];
    const page = setup(ids);
    for (const id of ids) await page.see(id);
    for (const id of ids) expect(page.live(id)).not.toBeNull();
  });
});
