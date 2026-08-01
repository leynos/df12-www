/* Tests for the docs scrollspy's active-section selection logic.
 *
 * `pickActiveIndex` is the pure decision at the heart of the scrollspy:
 * given each section heading's viewport-relative top, the activation
 * offset, and whether the page is scrolled to the bottom, it chooses
 * which sidebar link should light up.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { pickActiveIndex } = require(
    "../../public/netsuke/assets/js/docs-scrollspy.js"
);

const OFFSET = 96;

describe("pickActiveIndex", () => {
    test("nothing is active above the first section", () => {
        expect(pickActiveIndex([200, 900, 1600], OFFSET, false)).toBe(-1);
    });

    test("the last heading past the offset wins", () => {
        expect(pickActiveIndex([-500, 40, 700], OFFSET, false)).toBe(1);
    });

    test("a heading exactly on the offset counts as reached", () => {
        expect(pickActiveIndex([-500, OFFSET, 700], OFFSET, false)).toBe(1);
    });

    test("scrolling past every heading activates the last section", () => {
        expect(pickActiveIndex([-900, -400, -100], OFFSET, false)).toBe(2);
    });

    test("the bottom of the page forces the final section", () => {
        // A short closing section whose heading never crosses the offset
        // must still activate once the page cannot scroll further.
        expect(pickActiveIndex([-900, -400, 300], OFFSET, true)).toBe(2);
    });

    test("an empty target list stays inactive even at the bottom", () => {
        expect(pickActiveIndex([], OFFSET, true)).toBe(-1);
    });
});
