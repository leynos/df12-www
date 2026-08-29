/* Tests for the Stilyagi roadmap accordion.
 *
 * `nextOpenIndex` decides which phase is open after a header is activated.
 * Only one phase is open at a time, and activating the open one closes it.
 * The DOM suite then checks that the decision actually lands in the markup:
 * `aria-expanded` on the heads, `.open`/`.closed` on the phases.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { createRequire } from "node:module";
import fc from "fast-check";
import { click, mount, pressKey, ROADMAP_FIXTURE, reset } from "./helpers/stilyagi.mjs";

const require = createRequire(import.meta.url);
const { nextOpenIndex } = require("../../public/stilyagi/assets/js/roadmap.js");

describe("nextOpenIndex", () => {
  test("activating a closed phase opens it", () => {
    expect(nextOpenIndex(2, 0)).toBe(0);
  });

  test("activating the open phase closes it", () => {
    expect(nextOpenIndex(2, 2)).toBe(-1);
  });

  test("opening a phase when none is open works", () => {
    expect(nextOpenIndex(-1, 3)).toBe(3);
  });

  test("opening one phase implicitly closes the other", () => {
    // The caller closes every head that is not the returned index, so a
    // single index is enough to express "only this one".
    expect(nextOpenIndex(0, 5)).toBe(5);
  });
});

describe("the accordion in the document", () => {
  afterEach(reset);

  const heads = () => [...document.querySelectorAll(".ph-head")];
  const phases = () => [...document.querySelectorAll(".phase")];

  /* Exactly the phase at `index` is open; every other one is closed. An
     index of -1 asserts that every phase is closed. */
  const expectOnlyOpen = (index) => {
    heads().forEach((head, i) => {
      expect(head.getAttribute("aria-expanded")).toBe(String(i === index));
    });
    phases().forEach((element, i) => {
      expect(element.classList.contains("open")).toBe(i === index);
      expect(element.classList.contains("closed")).toBe(i !== index);
    });
  };

  test("clicking a closed head leaves exactly that phase open", () => {
    mount(ROADMAP_FIXTURE, "roadmap");
    click(heads()[2]);
    expectOnlyOpen(2);
  });

  test("clicking the open head closes every phase", () => {
    // The fixture ships with phase 1 open, as the template does.
    mount(ROADMAP_FIXTURE, "roadmap");
    click(heads()[1]);
    expectOnlyOpen(-1);
  });

  test("Enter activates a head and takes over the keystroke", () => {
    mount(ROADMAP_FIXTURE, "roadmap");
    const event = pressKey(heads()[0], "Enter");
    expect(event.defaultPrevented).toBe(true);
    expectOnlyOpen(0);
  });

  test("Space activates a head and takes over the keystroke", () => {
    mount(ROADMAP_FIXTURE, "roadmap");
    const event = pressKey(heads()[2], " ");
    expect(event.defaultPrevented).toBe(true);
    expectOnlyOpen(2);
  });

  test("an unrelated key changes nothing and is left to the browser", () => {
    mount(ROADMAP_FIXTURE, "roadmap");
    const event = pressKey(heads()[0], "ArrowDown");
    expect(event.defaultPrevented).toBe(false);
    expectOnlyOpen(1);
  });

  test("any activation sequence stays in step with nextOpenIndex", () => {
    // The pure function is the oracle: after every click the markup must
    // show exactly the phase it names open, and never more than one.
    fc.assert(
      fc.property(fc.array(fc.integer({ min: 0, max: 2 }), { maxLength: 12 }), (activations) => {
        mount(ROADMAP_FIXTURE, "roadmap");
        let open = 1; // the fixture ships with phase 1 open
        for (const index of activations) {
          click(heads()[index]);
          open = nextOpenIndex(open, index);
          expectOnlyOpen(open);
        }
      }),
    );
  });
});
