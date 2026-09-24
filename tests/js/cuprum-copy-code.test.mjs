/**
 * @file Tests for the Cuprum copy-button enhancement.
 *
 * `stripPrompts` decides what a shell transcript puts on the clipboard, and
 * `copyLabel` what the button says after a copy. The DOM suite mounts a code
 * panel and an install slip shaped like the `code_panel` and `install_slip`
 * macros in `templates/cuprum/components.jinja`, evaluates the compiled
 * script against the global happy-dom document, and checks the button lands
 * in the panel's slot and copies the right text.
 *
 * The controller suite drives `createCopyController` through injected fakes
 * — a manually advanced clock and a clipboard whose write resolves, rejects,
 * or is missing — so every outcome, the delayed announcement, and the reset
 * are observed at the moment they are due rather than waited out. The
 * `DOMContentLoaded` path runs in an isolated happy-dom `Window`, because
 * dispatching that event on the shared document would wake every other
 * suite's waiting listener as well.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import fc from "fast-check";
import { Window } from "happy-dom";
import { evaluateScript } from "./helpers/dom.mjs";

const require = createRequire(import.meta.url);
const SCRIPT = join("public", "cuprum", "assets", "js", "copy-code.js");
const {
  stripPrompts,
  copyLabel,
  panelText,
  createCopyController,
  RESET_MS,
  ANNOUNCE_DELAY_MS,
} = require(`../../${SCRIPT}`);

/* The panels the macros render, reduced to the attributes the script reads. */
const FIXTURE = `
  <div class="cu-code" data-cu-copy="console" data-cu-copy-label="shell">
    <div class="cu-code__bar"><span>shell</span><span data-cu-copy-slot></span></div>
    <div class="code-scroll" tabindex="0" role="region" aria-label="shell">
      <div class="cuprum-syntax"><pre><code>$ CUPRUM_STREAM_BACKEND=python python a.py
$ CUPRUM_STREAM_BACKEND=rust python a.py
</code></pre></div>
    </div>
  </div>
  <div class="cu-slip" data-cu-copy="text" data-cu-copy-label="pip command">
    <span class="cu-slip__label" data-cu-copy-slot>pip</span>
    <div class="cu-slip__body"><code class="cu-slip__command">pip install "cuprum @ git+https://example/x@abc"</code></div>
  </div>
`;

/* Mount the fixture, install a recording clipboard, and run the script. */
function mountWithClipboard() {
  document.body.innerHTML = FIXTURE;
  const written = [];
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: (text) => {
        written.push(text);
        return Promise.resolve();
      },
    },
  });
  // The compiled script is a classic IIFE; evaluating it runs `init`
  // immediately because the document has finished loading.
  new Function("module", readFileSync(SCRIPT, "utf8"))(undefined);
  return written;
}

/* Let the clipboard promise settle and the button report. */
function settle() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/* A controllable stand-in for setTimeout/clearTimeout, so the button's
   timings can be advanced deliberately rather than waited out. */
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

/* A clipboard whose every write settles as `outcome` says — "resolve" or
   "reject" — recording the text it was handed. */
function fakeClipboard(outcome) {
  const written = [];
  return {
    written,
    writeText(text) {
      written.push(text);
      return outcome === "resolve" ? Promise.resolve() : Promise.reject(new Error("denied"));
    },
  };
}

/* Mount `markup` into the global document and build the controller over a
   fake clock and `clipboard`, which may be undefined to model an insecure
   context. Returns the controller with the clock that drives it. */
function harness(markup, clipboard) {
  document.body.innerHTML = markup;
  const clock = fakeClock();
  const controller = createCopyController({
    document,
    clock,
    getClipboard: () => clipboard,
  });
  return { clock, controller };
}

/* A reference for one line: drop a single leading `$ ` prompt, if any. */
function stripOnePrompt(line) {
  return /^\$ /.test(line) ? line.slice(2) : line;
}

/* A line of text without a newline, biased toward prompt-like prefixes so
   the property exercises `$ `, `$$ `, ` $ `, and a bare `$`. */
const lineArb = fc
  .tuple(fc.constantFrom("", "$ ", "$", "$$ ", " $ ", "$ $ "), fc.string())
  .map(([prefix, body]) => `${prefix}${body}`.replaceAll("\n", ""));

describe("stripPrompts", () => {
  test("removes a leading prompt from each command line", () => {
    expect(stripPrompts("$ echo one\n$ echo two")).toBe("echo one\necho two");
  });

  test("leaves output lines and blank lines alone", () => {
    expect(stripPrompts("$ ls\nfile.txt\n\n$ pwd")).toBe("ls\nfile.txt\n\npwd");
  });

  test("only strips a prompt at the start of a line", () => {
    expect(stripPrompts("echo $ HOME")).toBe("echo $ HOME");
  });

  test("treats every line independently of its neighbours", () => {
    fc.assert(
      fc.property(fc.array(lineArb, { minLength: 1, maxLength: 12 }), (lines) => {
        expect(stripPrompts(lines.join("\n"))).toBe(lines.map(stripOnePrompt).join("\n"));
      }),
    );
  });
});

describe("panelText", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("drops trailing newlines and gives nothing for a panel with no source", () => {
    document.body.innerHTML = `
      <div id="text" data-cu-copy="text"><pre>$ keep\n\n</pre></div>
      <div id="empty" data-cu-copy="text"><span data-cu-copy-slot></span></div>`;
    expect(panelText(document.getElementById("text"))).toBe("$ keep");
    expect(panelText(document.getElementById("empty"))).toBe("");
  });
});

describe("copyLabel", () => {
  test("names every outcome in words", () => {
    expect(copyLabel("idle")).toBe("Copy");
    expect(copyLabel("copied")).toBe("Copied");
    expect(copyLabel("failed")).toBe("Copy failed");
    expect(copyLabel("unavailable")).toBe("Copy unavailable");
  });
});

describe("the copy buttons in the document", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("each marked panel gets one labelled button in its slot", () => {
    mountWithClipboard();
    const buttons = document.querySelectorAll("[data-cu-copy-slot] > button.cu-copy");
    expect(buttons.length).toBe(2);
    expect(buttons[0].getAttribute("aria-label")).toBe("Copy shell");
    expect(buttons[0].type).toBe("button");
  });

  test("a console panel copies commands without their prompts", async () => {
    const written = mountWithClipboard();
    document.querySelector(".cu-code button.cu-copy").click();
    await settle();
    expect(written).toEqual([
      "CUPRUM_STREAM_BACKEND=python python a.py\nCUPRUM_STREAM_BACKEND=rust python a.py",
    ]);
    expect(document.querySelector(".cu-code button.cu-copy").textContent).toBe("Copied");
  });

  test("an install slip copies the command as shown", async () => {
    const written = mountWithClipboard();
    document.querySelector(".cu-slip button.cu-copy").click();
    await settle();
    expect(written).toEqual(['pip install "cuprum @ git+https://example/x@abc"']);
  });
});

describe("the copy controller", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("a document without marked panels gets no live region and no controller", () => {
    const { controller } = harness("<pre>$ plain</pre>", fakeClipboard("resolve"));
    expect(controller).toBeNull();
    expect(document.querySelector("[role='status']")).toBeNull();
    expect(document.querySelector("button")).toBeNull();
  });

  test("a panel without a slot is skipped while the others are wired", () => {
    const markup = `
      <div id="bare" data-cu-copy="text"><pre>unslotted</pre></div>
      ${FIXTURE}`;
    const { controller } = harness(markup, fakeClipboard("resolve"));
    expect(controller.buttons.map((wired) => wired.panel.className)).toEqual([
      "cu-code",
      "cu-slip",
    ]);
    expect(document.querySelector("#bare button")).toBeNull();
    expect(document.querySelectorAll("[role='status'][aria-live='polite']").length).toBe(1);
  });

  test("an absent clipboard reports that copying is unavailable", async () => {
    const { clock, controller } = harness(FIXTURE, undefined);
    const [wired] = controller.buttons;
    await wired.copy();
    expect(wired.button.textContent).toBe("Copy unavailable");
    clock.advance(ANNOUNCE_DELAY_MS);
    expect(controller.announcer.textContent).toBe("Copy unavailable");
  });

  test("a rejected write reports that the copy failed", async () => {
    const clipboard = fakeClipboard("reject");
    const { clock, controller } = harness(FIXTURE, clipboard);
    const [, slip] = controller.buttons;
    await slip.copy();
    expect(clipboard.written).toEqual(['pip install "cuprum @ git+https://example/x@abc"']);
    expect(slip.button.textContent).toBe("Copy failed");
    clock.advance(ANNOUNCE_DELAY_MS);
    expect(controller.announcer.textContent).toBe("Copy failed");
  });

  test("a click copies through the injected clipboard", async () => {
    const clipboard = fakeClipboard("resolve");
    const { controller } = harness(FIXTURE, clipboard);
    controller.buttons[0].button.click();
    await settle();
    expect(clipboard.written).toEqual([
      "CUPRUM_STREAM_BACKEND=python python a.py\nCUPRUM_STREAM_BACKEND=rust python a.py",
    ]);
    expect(controller.buttons[0].button.textContent).toBe("Copied");
  });

  test("the live region is emptied at once and refilled after its delay", async () => {
    const { clock, controller } = harness(FIXTURE, fakeClipboard("resolve"));
    const { announcer } = controller;
    await controller.buttons[0].copy();
    clock.advance(ANNOUNCE_DELAY_MS);
    expect(announcer.textContent).toBe("Copied");

    // A repeat copy empties the region first, so the same words are
    // announced again rather than settling back unread.
    await controller.buttons[0].copy();
    expect(announcer.textContent).toBe("");
    clock.advance(ANNOUNCE_DELAY_MS - 1);
    expect(announcer.textContent).toBe("");
    clock.advance(1);
    expect(announcer.textContent).toBe("Copied");
  });

  test("the button returns to Copy once the pause has passed", async () => {
    const { clock, controller } = harness(FIXTURE, fakeClipboard("resolve"));
    const [wired] = controller.buttons;
    await wired.copy();
    clock.advance(RESET_MS - 1);
    expect(wired.button.textContent).toBe("Copied");
    clock.advance(1);
    expect(wired.button.textContent).toBe("Copy");
  });

  test("a second click restarts the pause", async () => {
    const { clock, controller } = harness(FIXTURE, fakeClipboard("resolve"));
    const [wired] = controller.buttons;
    await wired.copy();
    clock.advance(RESET_MS - 500);
    await wired.copy();
    // The first pause would have ended here; the second has 500ms to go.
    clock.advance(500);
    expect(wired.button.textContent).toBe("Copied");
    clock.advance(RESET_MS - 500);
    expect(wired.button.textContent).toBe("Copy");
  });
});

describe("initialisation while the document is loading", () => {
  let page = null;

  afterEach(async () => {
    await page.happyDOM.close();
    page = null;
  });

  test("waits for DOMContentLoaded before adding the buttons", () => {
    page = new Window({ url: "http://localhost/cuprum/" });
    const { document: doc } = page;
    doc.body.innerHTML = FIXTURE;
    Object.defineProperty(doc, "readyState", { configurable: true, value: "loading" });
    evaluateScript(page, SCRIPT);
    expect(doc.querySelectorAll("button.cu-copy").length).toBe(0);

    doc.dispatchEvent(new page.Event("DOMContentLoaded"));
    expect(doc.querySelectorAll("[data-cu-copy-slot] > button.cu-copy").length).toBe(2);
  });
});
