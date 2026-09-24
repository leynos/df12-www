/* Copy buttons for Cuprum's code panels and install slips.
 *
 * The markup is complete without this script: every command and code block
 * is selectable text in a keyboard-reachable scroll region. The script only
 * adds a Copy button to each element carrying `data-cu-copy`, in the panel's
 * bar (`[data-cu-copy-slot]`), and copies the panel's text on click.
 *
 * `data-cu-copy="console"` marks a shell transcript: the `$ ` prompts are
 * stripped, so what lands on the clipboard can be pasted and run. Any other
 * value copies the text as shown.
 *
 * The confirmation changes the button's words, not only its colour, and is
 * announced through one polite live region per page. The button returns to
 * "Copy" after a short pause; a second click restarts the pause.
 *
 * `stripPrompts`, `copyLabel`, and `panelText` are pure queries. The
 * controller takes its dependencies (document, clock, clipboard) as
 * arguments so tests can drive it with fakes; `init` at the bottom supplies
 * the real ones. All of them are exported for the Bun tests.
 */
(() => {
  "use strict";

  var RESET_MS = 2000;
  // Gap between emptying the live region and refilling it.
  var ANNOUNCE_DELAY_MS = 50;

  type CopyOutcome = "idle" | "copied" | "failed" | "unavailable";

  /* The timer pair the buttons schedule against; the browser wiring passes
     `window`'s, and the tests a manually advanced fake. */
  interface Clock {
    setTimeout(fn: () => void, ms: number): number;
    clearTimeout(id: number): void;
  }

  /* What `createCopyController` needs from its host. `getClipboard` is a
     getter rather than a value because `navigator.clipboard` is absent in an
     insecure context, and the outcome has to be checked on each click. */
  interface CopyDeps {
    document: Document;
    clock: Clock;
    getClipboard(): Clipboard | undefined;
  }

  /* One wired panel: the button it gained, and the copy its click runs. */
  interface CopyButton {
    panel: HTMLElement;
    button: HTMLButtonElement;
    copy(): Promise<void>;
  }

  /* Remove a leading `$ ` prompt from every line that has one, leaving
     output lines and blank lines as they are. */
  function stripPrompts(text: string): string {
    return text
      .split("\n")
      .map((line) => (line.startsWith("$ ") ? line.slice(2) : line))
      .join("\n");
  }

  /* The button's visible words for each outcome. */
  function copyLabel(outcome: CopyOutcome): string {
    switch (outcome) {
      case "copied":
        return "Copied";
      case "failed":
        return "Copy failed";
      case "unavailable":
        return "Copy unavailable";
      default:
        return "Copy";
    }
  }

  /* The text a panel carries: its highlighted block, or a slip's command. */
  function panelText(panel: HTMLElement): string {
    var source = panel.querySelector<HTMLElement>("pre, .cu-slip__command");
    var text = source ? (source.textContent ?? "") : "";
    text = text.replace(/\n+$/, "");
    return panel.dataset.cuCopy === "console" ? stripPrompts(text) : text;
  }

  /* The page's one polite live region, appended to `doc`'s body. */
  function createAnnouncer(doc: Document): HTMLElement {
    var announcer = doc.createElement("div");
    announcer.className = "sr-only";
    announcer.setAttribute("role", "status");
    announcer.setAttribute("aria-live", "polite");
    doc.body.append(announcer);
    return announcer;
  }

  /* Add a Copy button to `panel`'s slot and wire it to the clipboard and
     `announcer`. Returns null, adding nothing, when the panel has no slot. */
  function attachButton(
    panel: HTMLElement,
    announcer: HTMLElement,
    deps: CopyDeps,
  ): CopyButton | null {
    var slot = panel.querySelector<HTMLElement>("[data-cu-copy-slot]");
    if (!slot) {
      return null;
    }

    var button = deps.document.createElement("button");
    button.type = "button";
    button.className = "cu-copy";
    var label = panel.dataset.cuCopyLabel;
    if (label) {
      button.setAttribute("aria-label", `Copy ${label}`);
    }
    button.textContent = copyLabel("idle");
    slot.append(button);

    var resetTimer = 0;

    /* Show and announce an outcome, then restore "Copy" after a pause. */
    function report(outcome: CopyOutcome): void {
      var words = copyLabel(outcome);
      button.textContent = words;
      announcer.textContent = "";
      deps.clock.setTimeout(() => {
        announcer.textContent = words;
      }, ANNOUNCE_DELAY_MS);
      deps.clock.clearTimeout(resetTimer);
      resetTimer = deps.clock.setTimeout(() => {
        button.textContent = copyLabel("idle");
      }, RESET_MS);
    }

    /* Copy the panel's text and report the outcome. Returns a promise so
       tests can await settlement; the click listener ignores it. */
    function copy(): Promise<void> {
      var clipboard = deps.getClipboard();
      if (!clipboard) {
        report("unavailable");
        return Promise.resolve();
      }
      return clipboard.writeText(panelText(panel)).then(
        () => report("copied"),
        () => report("failed"),
      );
    }

    button.addEventListener("click", () => {
      copy();
    });

    return { panel: panel, button: button, copy: copy };
  }

  /* The component proper. Adds a copy button to every marked panel in
     `deps.document` and returns the live region and the wired buttons, or
     null, creating nothing, when the document has no marked panel. */
  function createCopyController(deps: CopyDeps) {
    var panels = deps.document.querySelectorAll<HTMLElement>("[data-cu-copy]");
    if (panels.length === 0) {
      return null;
    }

    var announcer = createAnnouncer(deps.document);
    var buttons: CopyButton[] = [];
    for (const panel of panels) {
      const wired = attachButton(panel, announcer, deps);
      if (wired) {
        buttons.push(wired);
      }
    }
    return { announcer: announcer, buttons: buttons };
  }

  /* Wire the page's panels, supplying the real document, timers, and
     clipboard. */
  function init(): void {
    createCopyController({
      document: document,
      clock: {
        setTimeout: window.setTimeout.bind(window),
        clearTimeout: window.clearTimeout.bind(window),
      },
      getClipboard: () => navigator.clipboard,
    });
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      stripPrompts: stripPrompts,
      copyLabel: copyLabel,
      panelText: panelText,
      createCopyController: createCopyController,
      RESET_MS: RESET_MS,
      ANNOUNCE_DELAY_MS: ANNOUNCE_DELAY_MS,
    };
  }
})();
