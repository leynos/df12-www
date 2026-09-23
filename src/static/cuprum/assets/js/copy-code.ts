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
 * `stripPrompts` and `copyLabel` are pure and exported for the Bun tests.
 */
(() => {
  "use strict";

  var RESET_MS = 2000;

  type CopyOutcome = "idle" | "copied" | "failed" | "unavailable";

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

  /* Add a copy button to every marked panel, returning early when there are
     none, and wire it to the clipboard and the shared live region. */
  function init(): void {
    var panels = document.querySelectorAll<HTMLElement>("[data-cu-copy]");
    if (panels.length === 0) {
      return;
    }

    var announcer = document.createElement("div");
    announcer.className = "sr-only";
    announcer.setAttribute("role", "status");
    announcer.setAttribute("aria-live", "polite");
    document.body.append(announcer);

    panels.forEach((panel) => {
      var slot = panel.querySelector<HTMLElement>("[data-cu-copy-slot]");
      if (!slot) {
        return;
      }

      var button = document.createElement("button");
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
        window.setTimeout(() => {
          announcer.textContent = words;
        }, 50);
        window.clearTimeout(resetTimer);
        resetTimer = window.setTimeout(() => {
          button.textContent = copyLabel("idle");
        }, RESET_MS);
      }

      button.addEventListener("click", () => {
        var clipboard = navigator.clipboard;
        if (!clipboard) {
          report("unavailable");
          return;
        }
        clipboard.writeText(panelText(panel)).then(
          () => report("copied"),
          () => report("failed"),
        );
      });
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
    module.exports = { stripPrompts: stripPrompts, copyLabel: copyLabel };
  }
})();
