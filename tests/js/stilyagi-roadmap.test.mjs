/* Tests for the Stilyagi roadmap accordion's open-phase selection.
 *
 * `nextOpenIndex` decides which phase is open after a header is activated.
 * Only one phase is open at a time, and activating the open one closes it.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { nextOpenIndex } = require(
    "../../src/static/stilyagi/assets/js/roadmap.js"
);

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
