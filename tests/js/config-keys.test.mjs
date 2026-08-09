/* Tests for the config-keys tab strip's keyboard navigation.
 *
 * `nextTabIndex` is the pure decision behind the narrow-viewport
 * tablist: given the selected tab, the key pressed, and how many tabs
 * there are, it returns the tab to move to, or -1 for a key the widget
 * should leave to the browser.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { nextTabIndex } = require(
    "../../public/netsuke/assets/js/config-keys.js"
);

const COUNT = 3;

describe("nextTabIndex", () => {
    test("Right and Down both advance", () => {
        expect(nextTabIndex(0, "ArrowRight", COUNT)).toBe(1);
        expect(nextTabIndex(0, "ArrowDown", COUNT)).toBe(1);
    });

    test("Left and Up both retreat", () => {
        expect(nextTabIndex(2, "ArrowLeft", COUNT)).toBe(1);
        expect(nextTabIndex(2, "ArrowUp", COUNT)).toBe(1);
    });

    test("advancing past the last tab wraps to the first", () => {
        expect(nextTabIndex(COUNT - 1, "ArrowRight", COUNT)).toBe(0);
    });

    test("retreating from the first tab wraps to the last", () => {
        expect(nextTabIndex(0, "ArrowLeft", COUNT)).toBe(COUNT - 1);
    });

    test("Home and End jump to the ends", () => {
        expect(nextTabIndex(1, "Home", COUNT)).toBe(0);
        expect(nextTabIndex(1, "End", COUNT)).toBe(COUNT - 1);
    });

    test("keys the widget does not own are left alone", () => {
        // -1 tells the handler not to preventDefault, so Tab still moves
        // focus out of the strip and typing still reaches the page.
        expect(nextTabIndex(0, "Tab", COUNT)).toBe(-1);
        expect(nextTabIndex(0, "Enter", COUNT)).toBe(-1);
        expect(nextTabIndex(0, "a", COUNT)).toBe(-1);
    });

    test("an empty strip has nowhere to move", () => {
        expect(nextTabIndex(0, "ArrowRight", 0)).toBe(-1);
        expect(nextTabIndex(0, "Home", 0)).toBe(-1);
    });

    test("a single tab always resolves to itself", () => {
        expect(nextTabIndex(0, "ArrowRight", 1)).toBe(0);
        expect(nextTabIndex(0, "ArrowLeft", 1)).toBe(0);
    });

    test("an unmarked wide-mode state still advances into range", () => {
        // Wide mode can clear the mark (selected = -1); crossing to narrow
        // must not leave the arrow keys computing a negative index.
        expect(nextTabIndex(-1, "ArrowRight", COUNT)).toBe(0);
        expect(nextTabIndex(-1, "ArrowLeft", COUNT)).toBe(COUNT - 1);
    });
});
