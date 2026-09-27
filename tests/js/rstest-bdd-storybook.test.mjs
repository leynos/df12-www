/**
 * @file Tests for the rstest-bdd home page's storybook enhancement.
 *
 * `nearestIndex` decides which chapter the strip is showing, and
 * `counterText` what the counter says about it; both are pure and checked
 * directly, `nearestIndex` also as a property. The controller suite mounts a
 * storybook shaped like the markup in `templates/rstest-bdd/home_page.jinja`
 * into the global happy-dom document and drives `createStorybook` through a
 * fake animation frame, so the tabs, focus, paging, and counter are observed
 * without layout: happy-dom reports every offset as zero, so the scroll
 * position is asserted through the call the strip receives rather than
 * through geometry.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { createRequire } from "node:module";
import { join } from "node:path";
import fc from "fast-check";

const require = createRequire(import.meta.url);
const SCRIPT = join("public", "rstest-bdd", "assets", "js", "storybook.js");
const { nearestIndex, counterText, createStorybook } = require(`../../${SCRIPT}`);

/* The storybook the home page renders, reduced to what the script reads. */
function fixture(chapters) {
  const tabs = Array.from(
    { length: chapters },
    (_, i) => `<li><a href="#chapter-0${i + 1}" data-rb-chapter-tab>Chapter ${i + 1}</a></li>`,
  ).join("");
  const articles = Array.from(
    { length: chapters },
    (_, i) => `<article id="chapter-0${i + 1}" data-rb-chapter>Chapter ${i + 1}</article>`,
  ).join("");
  return `
    <nav><ol>${tabs}</ol></nav>
    <div class="rb-story__track" data-rb-storybook>${articles}</div>
    <div data-rb-story-paging hidden>
      <button type="button" data-rb-story-prev>Previous chapter</button>
      <p data-rb-story-count></p>
      <button type="button" data-rb-story-next>Next chapter</button>
    </div>`;
}

/* Mount `markup`, record the strip's scroll calls, and build the controller
   over a frame queue the test flushes itself. */
function harness(markup, reducedMotion = false) {
  document.body.innerHTML = markup;
  const scrolls = [];
  const track = document.querySelector("[data-rb-storybook]");
  if (track) {
    track.scrollTo = (options) => scrolls.push(options);
  }
  const frames = [];
  const controller = createStorybook({
    document,
    requestFrame: (callback) => frames.push(callback),
    prefersReducedMotion: () => reducedMotion,
  });
  return { controller, frames, scrolls, track };
}

/* Which tab carries aria-current, as an index, or -1. */
function currentTab() {
  return [...document.querySelectorAll("[data-rb-chapter-tab]")].findIndex(
    (tab) => tab.getAttribute("aria-current") === "true",
  );
}

describe("nearestIndex", () => {
  test("picks the chapter whose edge is closest to the scroll position", () => {
    expect(nearestIndex([0, 100, 200], 0)).toBe(0);
    expect(nearestIndex([0, 100, 200], 140)).toBe(1);
    expect(nearestIndex([0, 100, 200], 180)).toBe(2);
  });

  test("an empty strip has no chapter", () => {
    expect(nearestIndex([], 50)).toBe(-1);
  });

  test("the chosen edge is never further than any other", () => {
    fc.assert(
      fc.property(
        fc.array(fc.integer({ min: 0, max: 10_000 }), { minLength: 1, maxLength: 12 }),
        fc.integer({ min: 0, max: 10_000 }),
        (offsets, position) => {
          const chosen = nearestIndex(offsets, position);
          const distance = Math.abs(offsets[chosen] - position);
          expect(offsets.every((offset) => distance <= Math.abs(offset - position))).toBe(true);
        },
      ),
    );
  });
});

describe("counterText", () => {
  test("names the chapter and the total, zero-padded", () => {
    expect(counterText(0, 8)).toBe("Chapter 01 of 08");
    expect(counterText(7, 8)).toBe("Chapter 08 of 08");
  });
});

describe("the storybook controller", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("a page without a storybook is left alone", () => {
    const { controller } = harness("<p>No story here.</p>");
    expect(controller).toBeNull();
  });

  test("a storybook without chapters is left alone", () => {
    const { controller } = harness(
      "<div data-rb-storybook></div><div data-rb-story-paging hidden></div>",
    );
    expect(controller).toBeNull();
    expect(document.querySelector("[data-rb-story-paging]").hidden).toBe(true);
  });

  test("the first chapter is marked and the paging is shown", () => {
    harness(fixture(3));
    expect(currentTab()).toBe(0);
    expect(document.querySelector("[data-rb-story-paging]").hidden).toBe(false);
    expect(document.querySelector("[data-rb-story-count]").textContent).toBe("Chapter 01 of 03");
    expect(document.querySelector("[data-rb-story-prev]").disabled).toBe(true);
    expect(document.querySelector("[data-rb-story-next]").disabled).toBe(false);
  });

  test("choosing a tab scrolls the strip, marks the tab, and moves focus", () => {
    const { scrolls } = harness(fixture(3));
    const event = new window.MouseEvent("click", { bubbles: true, cancelable: true });
    document.querySelectorAll("[data-rb-chapter-tab]")[2].dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(scrolls).toEqual([{ left: 0, behavior: "smooth" }]);
    expect(currentTab()).toBe(2);
    expect(document.activeElement.id).toBe("chapter-03");
    expect(document.querySelector("[data-rb-story-next]").disabled).toBe(true);
  });

  test("reduced motion scrolls without animation", () => {
    const { controller, scrolls } = harness(fixture(2), true);
    controller.show(1);
    expect(scrolls).toEqual([{ left: 0, behavior: "auto" }]);
  });

  test("the paging buttons step through the chapters and stop at the ends", () => {
    const { controller } = harness(fixture(3));
    const next = document.querySelector("[data-rb-story-next]");
    const prev = document.querySelector("[data-rb-story-prev]");
    next.click();
    next.click();
    next.click();
    expect(controller.current()).toBe(2);
    prev.click();
    expect(controller.current()).toBe(1);
    expect(document.querySelector("[data-rb-story-count]").textContent).toBe("Chapter 02 of 03");
  });

  test("scrolling re-marks the chapter at most once per frame", () => {
    const { controller, frames, track } = harness(fixture(3));
    controller.show(2);
    track.dispatchEvent(new window.Event("scroll"));
    track.dispatchEvent(new window.Event("scroll"));
    expect(frames.length).toBe(1);
    frames.shift()();
    // Every offset is zero under happy-dom, so the nearest chapter is the
    // first; what matters is that the frame recomputed it.
    expect(controller.current()).toBe(0);
    expect(currentTab()).toBe(0);
  });
});
