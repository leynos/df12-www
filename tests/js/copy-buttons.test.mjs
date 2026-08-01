/* Tests for the copy-button toast's concurrency and timer behaviour.
 *
 * The production file injects its document, clock, and clipboard, so
 * these tests drive it with a minimal fake DOM, a manually advanced
 * clock, and deferred clipboard promises whose settlement order the
 * tests control explicitly.
 */
import { describe, expect, test } from "bun:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const {
    createCopyController,
    TOAST_LINGER_MS,
    TOAST_FADE_MS,
    ANNOUNCE_DELAY_MS,
} = require("../../public/netsuke/assets/js/copy-buttons.js");

function fakeElement() {
    const classes = new Set();
    const attrs = new Map();
    return {
        textContent: "",
        className: "",
        setAttribute(name, value) {
            attrs.set(name, String(value));
        },
        getAttribute(name) {
            return attrs.has(name) ? attrs.get(name) : null;
        },
        classList: {
            add(name) {
                classes.add(name);
            },
            remove(name) {
                classes.delete(name);
            },
            toggle(name, force) {
                if (force) {
                    classes.add(name);
                } else {
                    classes.delete(name);
                }
            },
            contains(name) {
                return classes.has(name);
            },
        },
    };
}

function fakeDocument() {
    return {
        body: {
            children: [],
            append(el) {
                this.children.push(el);
            },
        },
        createElement() {
            return fakeElement();
        },
    };
}

function fakeClock() {
    let now = 0;
    let nextId = 1;
    const timers = new Map();
    return {
        setTimeout(fn, ms) {
            const id = nextId++;
            timers.set(id, { at: now + ms, fn });
            return id;
        },
        clearTimeout(id) {
            timers.delete(id);
        },
        advance(ms) {
            now += ms;
            const due = [...timers.entries()]
                .filter(([, t]) => t.at <= now)
                .sort((a, b) => a[1].at - b[1].at);
            for (const [id, t] of due) {
                if (timers.delete(id)) {
                    t.fn();
                }
            }
        },
    };
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
}

function harness({ clipboardQueue = [], hasClipboard = true } = {}) {
    const clock = fakeClock();
    const writes = [];
    const clipboard = hasClipboard
        ? {
              writeText(text) {
                  const d = clipboardQueue.shift() ?? deferred();
                  writes.push({ text, d });
                  return d.promise;
              },
          }
        : null;
    const controller = createCopyController({
        document: fakeDocument(),
        clock,
        getClipboard: () => clipboard,
    });
    return { clock, controller, writes };
}

const flush = () => Promise.resolve().then(() => Promise.resolve());

describe("last-click-wins under reordered settlement", () => {
    test("a stale failure cannot overwrite a newer success", async () => {
        const first = deferred();
        const second = deferred();
        const { controller } = harness({ clipboardQueue: [first, second] });
        const { element } = controller.toast;

        const p1 = controller.handleCopy("alpha");
        const p2 = controller.handleCopy("beta");

        second.resolve();
        await flush();
        expect(element.textContent).toBe("Copied to clipboard");

        first.reject(new Error("denied"));
        await Promise.allSettled([p1, p2]);
        expect(element.textContent).toBe("Copied to clipboard");
        expect(element.classList.contains("hm-toast--error")).toBe(false);
    });

    test("a stale success cannot overwrite a newer failure", async () => {
        const first = deferred();
        const second = deferred();
        const { controller } = harness({ clipboardQueue: [first, second] });
        const { element } = controller.toast;

        const p1 = controller.handleCopy("alpha");
        const p2 = controller.handleCopy("beta");

        second.reject(new Error("denied"));
        await flush();
        expect(element.textContent).toBe("Copy failed");
        expect(element.classList.contains("hm-toast--error")).toBe(true);

        first.resolve();
        await Promise.allSettled([p1, p2]);
        expect(element.textContent).toBe("Copy failed");
        expect(element.classList.contains("hm-toast--error")).toBe(true);
    });

    test("missing clipboard reports unavailable and still claims the attempt", async () => {
        const { controller } = harness({ hasClipboard: false });
        const { element } = controller.toast;

        await controller.handleCopy("alpha");
        expect(element.textContent).toBe("Copy unavailable");
        expect(element.classList.contains("hm-toast--error")).toBe(true);
    });
});

describe("timer resets with an injectable clock", () => {
    test("a second copy restarts the linger window", async () => {
        const first = deferred();
        const second = deferred();
        const { clock, controller } = harness({ clipboardQueue: [first, second] });
        const { element } = controller.toast;

        controller.handleCopy("alpha");
        first.resolve();
        await flush();
        expect(element.classList.contains("hm-toast--visible")).toBe(true);

        clock.advance(TOAST_LINGER_MS - 100);
        expect(element.classList.contains("hm-toast--visible")).toBe(true);

        controller.handleCopy("beta");
        second.resolve();
        await flush();

        // The old linger timer was cancelled: advancing past its original
        // deadline keeps the toast visible.
        clock.advance(TOAST_LINGER_MS - 100);
        expect(element.classList.contains("hm-toast--visible")).toBe(true);

        clock.advance(100);
        expect(element.classList.contains("hm-toast--visible")).toBe(false);

        clock.advance(TOAST_FADE_MS);
        expect(element.textContent).toBe("");
    });

    test("each copy empties then refills the live region", async () => {
        const first = deferred();
        const second = deferred();
        const { clock, controller } = harness({ clipboardQueue: [first, second] });
        const { announcer } = controller.toast;

        controller.handleCopy("alpha");
        first.resolve();
        await flush();
        expect(announcer.textContent).toBe("");
        clock.advance(ANNOUNCE_DELAY_MS);
        expect(announcer.textContent).toBe("Copied to clipboard");

        controller.handleCopy("beta");
        second.resolve();
        await flush();
        expect(announcer.textContent).toBe("");
        clock.advance(ANNOUNCE_DELAY_MS);
        expect(announcer.textContent).toBe("Copied to clipboard");
    });

    test("a superseded announcement never fires late", async () => {
        const first = deferred();
        const second = deferred();
        const { clock, controller } = harness({ clipboardQueue: [first, second] });
        const { announcer } = controller.toast;

        controller.handleCopy("alpha");
        const p2 = controller.handleCopy("beta");
        second.reject(new Error("denied"));
        await flush();

        // The first write settles after the second already showed its
        // outcome; its announcement must not be scheduled at all.
        first.resolve();
        await flush();
        clock.advance(ANNOUNCE_DELAY_MS);
        expect(announcer.textContent).toBe("Copy failed");
        await Promise.allSettled([p2]);
    });
});
