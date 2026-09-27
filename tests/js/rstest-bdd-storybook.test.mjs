/**
 * @file Tests for the rstest-bdd home page's storybook enhancement.
 *
 * `nearestIndex` decides which chapter the strip is showing, and
 * `counterText` what the counter says about it; both are pure and checked
 * directly, `nearestIndex` also as a property. The controller suite mounts a
 * storybook shaped like the markup in `templates/rstest-bdd/home_page.jinja`
 * into the global happy-dom document and drives `createStorybook` through a
 * fake animation frame, so the tabs, focus, paging, and counter are observed
 * without layout. happy-dom lays nothing out and reports every `offsetLeft`
 * as zero, so the harness gives each chapter its own distinct offset —
 * starting away from zero, so the script's subtraction of the first
 * chapter's origin is exercised — and the scroll destination is asserted
 * exactly through the call the strip receives.
 *
 * A model-based property drives random traces of tab choices, paging, and
 * scrolling against a few lines of pure bookkeeping, and checks after every
 * step that the markup, the scroll destination, and the telemetry agree
 * with it. The telemetry suite hands the controller the compiled hook from
 * `telemetry.js` and a recording sink.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { createRequire } from "node:module";
import { join } from "node:path";
import fc from "fast-check";

const require = createRequire(import.meta.url);
const SCRIPT = join("public", "rstest-bdd", "assets", "js", "storybook.js");
const { nearestIndex, counterText, createStorybook } = require(`../../${SCRIPT}`);
const telemetry = require("../../public/rstest-bdd/assets/js/telemetry.js");

/* Where the harness places chapter `i`'s left edge. The first chapter sits
   away from zero, as it does behind the strip's padding, so the script has
   to measure from it rather than from the strip. */
const ORIGIN = 24;
const WIDTH = 320;
const offsetOf = (i) => ORIGIN + WIDTH * i;
/* The scroll position that brings chapter `i` into view. */
const destinationOf = (i) => offsetOf(i) - offsetOf(0);

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

/* Mount `markup`, give each chapter a distinct offset, record the strip's
   scroll calls, and build the controller over a frame queue the test flushes
   itself, with the telemetry hook if given. The fake `scrollTo` moves the
   strip at once, as a finished smooth scroll would, without firing a scroll
   event. */
function harness(markup, reducedMotion = false, hook = undefined) {
  document.body.innerHTML = markup;
  document.querySelectorAll("[data-rb-chapter]").forEach((chapter, i) => {
    // happy-dom's offsetLeft is a prototype getter; shadow it per element.
    Object.defineProperty(chapter, "offsetLeft", { value: offsetOf(i), configurable: true });
  });
  const scrolls = [];
  const track = document.querySelector("[data-rb-storybook]");
  if (track) {
    track.scrollTo = (options) => {
      scrolls.push(options);
      track.scrollLeft = options.left;
    };
  }
  const frames = [];
  const controller = createStorybook({
    document,
    requestFrame: (callback) => frames.push(callback),
    prefersReducedMotion: () => reducedMotion,
    telemetry: hook,
  });
  return { controller, frames, scrolls, track };
}

/* Move the strip to `left` as the reader would, and run the frame the scroll
   event asked for. */
function scrollStripTo(track, frames, left) {
  track.scrollLeft = left;
  track.dispatchEvent(new window.Event("scroll"));
  while (frames.length > 0) {
    frames.shift()();
  }
}

/* Install a sink that records every telemetry event, and return the list. */
function recordTelemetry() {
  const events = [];
  globalThis.df12RstestBddTelemetrySink = (event) => events.push(event);
  return events;
}

/* The storybook event the telemetry hook emits for `outcome` and `reason`. */
function storyEvent(outcome, reason) {
  return {
    component: "rstest-bdd-storybook",
    operation: "storybook",
    outcome,
    ...(reason === undefined ? {} : { reason }),
  };
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
    globalThis.df12RstestBddTelemetrySink = undefined;
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
    expect(scrolls).toEqual([{ left: destinationOf(2), behavior: "smooth" }]);
    expect(currentTab()).toBe(2);
    expect(document.activeElement.id).toBe("chapter-03");
    expect(document.querySelector("[data-rb-story-next]").disabled).toBe(true);
  });

  test("reduced motion scrolls without animation, to the same place", () => {
    const { controller, scrolls } = harness(fixture(2), true);
    controller.show(1);
    expect(scrolls).toEqual([{ left: destinationOf(1), behavior: "auto" }]);
  });

  test("a reduced-motion tab click scrolls to its chapter without animation", () => {
    const { scrolls } = harness(fixture(4), true);
    document.querySelectorAll("[data-rb-chapter-tab]")[3].click();
    expect(scrolls).toEqual([{ left: destinationOf(3), behavior: "auto" }]);
  });

  test("the paging buttons step through the chapters and stop at the ends", () => {
    const { controller, scrolls } = harness(fixture(3));
    const next = document.querySelector("[data-rb-story-next]");
    const prev = document.querySelector("[data-rb-story-prev]");
    next.click();
    next.click();
    next.click();
    expect(controller.current()).toBe(2);
    prev.click();
    expect(controller.current()).toBe(1);
    expect(document.querySelector("[data-rb-story-count]").textContent).toBe("Chapter 02 of 03");
    // The third click met a disabled button, so there are three scrolls.
    expect(scrolls).toEqual([
      { left: destinationOf(1), behavior: "smooth" },
      { left: destinationOf(2), behavior: "smooth" },
      { left: destinationOf(1), behavior: "smooth" },
    ]);
  });

  test("the paging buttons honour reduced motion", () => {
    const { scrolls } = harness(fixture(3), true);
    document.querySelector("[data-rb-story-next]").click();
    document.querySelector("[data-rb-story-prev]").click();
    expect(scrolls).toEqual([
      { left: destinationOf(1), behavior: "auto" },
      { left: destinationOf(0), behavior: "auto" },
    ]);
  });

  test("scrolling re-marks the chapter at most once per frame", () => {
    const { controller, frames, track } = harness(fixture(3));
    // Just short of the third chapter, nearer it than the second.
    track.scrollLeft = destinationOf(2) - WIDTH / 4;
    track.dispatchEvent(new window.Event("scroll"));
    track.dispatchEvent(new window.Event("scroll"));
    expect(frames.length).toBe(1);
    expect(controller.current()).toBe(0);
    frames.shift()();
    expect(controller.current()).toBe(2);
    expect(currentTab()).toBe(2);
    expect(document.querySelector("[data-rb-story-count]").textContent).toBe("Chapter 03 of 03");
  });

  test("any trace of tabs, paging, and scrolling stays in step with a model", () => {
    const action = (count) =>
      fc.oneof(
        fc.record({ kind: fc.constant("tab"), index: fc.nat({ max: count - 1 }) }),
        fc.record({ kind: fc.constant("previous") }),
        fc.record({ kind: fc.constant("next") }),
        fc.record({ kind: fc.constant("scroll"), index: fc.nat({ max: count - 1 }) }),
      );
    const scenario = fc
      .integer({ min: 1, max: 10 })
      .chain((count) => fc.tuple(fc.constant(count), fc.array(action(count), { maxLength: 25 })));

    fc.assert(
      fc.property(scenario, fc.boolean(), ([count, trace], reducedMotion) => {
        const events = recordTelemetry();
        const { controller, frames, scrolls, track } = harness(
          fixture(count),
          reducedMotion,
          telemetry,
        );
        const tabs = document.querySelectorAll("[data-rb-chapter-tab]");
        const prev = document.querySelector("[data-rb-story-prev]");
        const next = document.querySelector("[data-rb-story-next]");
        const counter = document.querySelector("[data-rb-story-count]");
        const behavior = reducedMotion ? "auto" : "smooth";
        // The model: the chapter in view, and the events it implies.
        let current = 0;
        const expected = [storyEvent("initialized")];

        for (const step of trace) {
          const before = scrolls.length;
          if (step.kind === "tab") {
            tabs[step.index].click();
            current = step.index;
            expected.push(storyEvent("navigated", "tab"));
          } else if (step.kind === "previous") {
            // A disabled button does nothing, so paging past an end is
            // not a navigation.
            prev.click();
            if (current > 0) {
              current -= 1;
              expected.push(storyEvent("navigated", "previous"));
            }
          } else if (step.kind === "next") {
            next.click();
            if (current < count - 1) {
              current += 1;
              expected.push(storyEvent("navigated", "next"));
            }
          } else {
            scrollStripTo(track, frames, destinationOf(step.index));
            if (step.index !== current) {
              current = step.index;
              expected.push(storyEvent("navigated", "scroll"));
            }
          }

          expect(current >= 0 && current < count).toBe(true);
          expect(controller.current()).toBe(current);
          const marked = [...tabs].filter((tab) => tab.getAttribute("aria-current") === "true");
          expect(marked).toEqual([tabs[current]]);
          expect(counter.textContent).toBe(counterText(current, count));
          expect(prev.disabled).toBe(current === 0);
          expect(next.disabled).toBe(current === count - 1);
          if (scrolls.length > before) {
            expect(scrolls.at(-1)).toEqual({ left: destinationOf(current), behavior });
          }
          // Every scroll the strip received, and every reader scroll, left
          // it at the model's chapter.
          expect(track.scrollLeft).toBe(destinationOf(current));
          expect(events).toEqual(expected);
        }
      }),
    );
  });
});

describe("the storybook telemetry", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    globalThis.df12RstestBddTelemetrySink = undefined;
  });

  test("reports once that the storybook was wired", () => {
    const events = recordTelemetry();
    harness(fixture(3), false, telemetry);
    expect(events).toEqual([storyEvent("initialized")]);
  });

  test("reports each chosen chapter with its cause, never the chapter", () => {
    const events = recordTelemetry();
    harness(fixture(3), false, telemetry);
    document.querySelectorAll("[data-rb-chapter-tab]")[2].click();
    document.querySelector("[data-rb-story-prev]").click();
    document.querySelector("[data-rb-story-next]").click();
    expect(events).toEqual([
      storyEvent("initialized"),
      storyEvent("navigated", "tab"),
      storyEvent("navigated", "previous"),
      storyEvent("navigated", "next"),
    ]);
    const reported = JSON.stringify(events);
    expect(reported).not.toContain("chapter-0");
    expect(reported).not.toContain("Chapter");
    expect(reported).not.toContain("#");
  });

  test("reports a scroll only when it changes the chapter in view", () => {
    const events = recordTelemetry();
    const { frames, track } = harness(fixture(3), false, telemetry);
    scrollStripTo(track, frames, 5);
    expect(events).toEqual([storyEvent("initialized")]);
    scrollStripTo(track, frames, destinationOf(1));
    scrollStripTo(track, frames, destinationOf(1) + 5);
    expect(events).toEqual([storyEvent("initialized"), storyEvent("navigated", "scroll")]);
  });

  test("says nothing, and still works, when the page did not load the hook", () => {
    const events = recordTelemetry();
    const { controller } = harness(fixture(3));
    document.querySelector("[data-rb-story-next]").click();
    expect(controller.current()).toBe(1);
    expect(events).toEqual([]);
  });
});
