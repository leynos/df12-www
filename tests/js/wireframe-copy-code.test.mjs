/**
 * @file Tests for the wireframe copy-control enhancement.
 *
 * The identity specification asks every code panel for a labelled copy
 * control. The DOM suite mounts a command panel and a working-example panel
 * shaped like the `command` and `code` macros in
 * `templates/wireframe/_code.jinja`, evaluates the compiled script against
 * the global happy-dom document, and checks each button lands in its slot,
 * names what it copies, and copies the right text. The controller suite
 * drives `createCopyController` through a manually advanced clock and fake
 * clipboards, so every outcome and the reset are observed when they fall due.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const SCRIPT = join("public", "wireframe", "assets", "js", "copy-code.js");
const { stripPrompts, copyLabel, panelText, createCopyController, RESET_MS, ANNOUNCE_DELAY_MS } =
  require(`../../${SCRIPT}`);

/* The panels the macros render, reduced to the attributes the script reads.
   The command panel's prompt is drawn in CSS, so its text has none. */
const FIXTURE = `
  <figure class="wf-code wf-code--command" data-wf-copy="console" data-wf-copy-label="Pin tokio-util">
    <figcaption class="wf-code__bar"><span class="wf-code__name">Pin tokio-util</span><span class="wf-code__slot" data-wf-copy-slot></span></figcaption>
    <div class="wf-code__scroll" tabindex="0" role="region" aria-label="Pin tokio-util"><pre><code>cargo update -p tokio-util --precise 0.7.19</code></pre></div>
  </figure>
  <figure class="wf-code" data-wf-sample="tests/first_server.rs" data-wf-copy="code" data-wf-copy-label="The application">
    <figcaption class="wf-code__bar"><span class="wf-code__name">The application</span><span class="wf-code__kind">Working example</span><span class="wf-code__slot" data-wf-copy-slot></span></figcaption>
    <div class="wf-code__scroll" tabindex="0" role="region" aria-label="The application, working example">
      <div class="wf-syntax"><pre><code>WireframeApp::new()?.route(PING, handler)?.wrap(AnswerPings)
</code></pre></div>
    </div>
  </figure>
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

/* A controllable stand-in for setTimeout and clearTimeout. */
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
        .filter(([, timer]) => timer.at <= now)
        .sort((a, b) => a[1].at - b[1].at);
      for (const [id, timer] of due) {
        if (timers.delete(id)) {
          timer.fn();
        }
      }
    },
  };
}

/* A clipboard whose writes resolve or reject, recording what they were given. */
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

/* Build the controller over the fixture, a fake clock, and `clipboard`,
   which may be undefined to model an insecure context. */
function harness(clipboard) {
  document.body.innerHTML = FIXTURE;
  const clock = fakeClock();
  const controller = createCopyController({ document, clock, getClipboard: () => clipboard });
  return { clock, controller };
}

describe("the pure helpers", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("stripPrompts removes a typed prompt from each command line only", () => {
    expect(stripPrompts("$ cargo test\noutput\n$ cargo run")).toBe("cargo test\noutput\ncargo run");
    expect(stripPrompts("echo $ HOME")).toBe("echo $ HOME");
  });

  test("copyLabel names every outcome in words", () => {
    expect(copyLabel("idle")).toBe("Copy");
    expect(copyLabel("copied")).toBe("Copied");
    expect(copyLabel("failed")).toBe("Copy failed");
    expect(copyLabel("unavailable")).toBe("Copy unavailable");
  });

  test("panelText drops trailing newlines and reads nothing from an empty panel", () => {
    document.body.innerHTML = `
      <div id="text" data-wf-copy="code"><pre>let x = 1;\n\n</pre></div>
      <div id="empty" data-wf-copy="code"><span data-wf-copy-slot></span></div>`;
    expect(panelText(document.getElementById("text"))).toBe("let x = 1;");
    expect(panelText(document.getElementById("empty"))).toBe("");
  });
});

describe("the copy controls in the document", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("each marked panel gets one labelled button in its slot", () => {
    mountWithClipboard();
    const buttons = document.querySelectorAll("[data-wf-copy-slot] > button.wf-copy");
    expect(buttons.length).toBe(2);
    expect(buttons[0].getAttribute("aria-label")).toBe("Copy Pin tokio-util");
    expect(buttons[1].getAttribute("aria-label")).toBe("Copy The application");
    expect(buttons[0].type).toBe("button");
  });

  test("a command panel copies the command alone", async () => {
    const written = mountWithClipboard();
    document.querySelectorAll("button.wf-copy")[0].click();
    await settle();
    expect(written).toEqual(["cargo update -p tokio-util --precise 0.7.19"]);
    expect(document.querySelectorAll("button.wf-copy")[0].textContent).toBe("Copied");
  });

  test("a working example copies its code as shown", async () => {
    const written = mountWithClipboard();
    document.querySelectorAll("button.wf-copy")[1].click();
    await settle();
    expect(written).toEqual(["WireframeApp::new()?.route(PING, handler)?.wrap(AnswerPings)"]);
  });
});

describe("the copy controller", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("a document without marked panels gets no live region", () => {
    document.body.innerHTML = "<pre>plain</pre>";
    const controller = createCopyController({
      document,
      clock: fakeClock(),
      getClipboard: () => undefined,
    });
    expect(controller).toBeNull();
    expect(document.querySelector("[role='status']")).toBeNull();
  });

  test("an absent clipboard says copying is unavailable, then resets", async () => {
    const { clock, controller } = harness(undefined);
    const [first] = controller.buttons;
    await first.copy();
    expect(first.button.textContent).toBe("Copy unavailable");
    clock.advance(ANNOUNCE_DELAY_MS);
    expect(controller.announcer.textContent).toBe("Copy unavailable");
    clock.advance(RESET_MS);
    expect(first.button.textContent).toBe("Copy");
  });

  test("a refused write says the copy failed", async () => {
    const clipboard = fakeClipboard("reject");
    const { controller } = harness(clipboard);
    const [, second] = controller.buttons;
    await second.copy();
    expect(clipboard.written).toHaveLength(1);
    expect(second.button.textContent).toBe("Copy failed");
  });

  test("a second copy restarts the reset pause", async () => {
    const { clock, controller } = harness(fakeClipboard("resolve"));
    const [first] = controller.buttons;
    await first.copy();
    clock.advance(RESET_MS - 1);
    await first.copy();
    clock.advance(RESET_MS - 1);
    expect(first.button.textContent).toBe("Copied");
    clock.advance(1);
    expect(first.button.textContent).toBe("Copy");
  });
});
