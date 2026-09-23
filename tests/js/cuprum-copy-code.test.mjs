/**
 * @file Tests for the Cuprum copy-button enhancement.
 *
 * `stripPrompts` decides what a shell transcript puts on the clipboard, and
 * `copyLabel` what the button says after a copy. The DOM suite mounts a code
 * panel and an install slip shaped like the `code_panel` and `install_slip`
 * macros in `templates/cuprum/components.jinja`, evaluates the compiled
 * script against the global happy-dom document, and checks the button lands
 * in the panel's slot and copies the right text.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const SCRIPT = join("public", "cuprum", "assets", "js", "copy-code.js");
const { stripPrompts, copyLabel } = require(`../../${SCRIPT}`);

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
