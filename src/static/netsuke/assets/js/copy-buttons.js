/* Shared copy-to-clipboard wiring.
 *
 * Any button carrying a `data-copy-text` attribute copies that text on
 * click and reports the outcome through a single ghost toast (styled by
 * .hm-toast in himotoshi.css). Pages without such buttons pay nothing:
 * init bails before creating the toast.
 *
 * Concurrency policy: last click wins. Each click takes a monotonically
 * increasing attempt token; when a clipboard write settles, its outcome
 * is shown only if no later click has occurred. Rapid clicks whose
 * promises settle out of order therefore cannot paint a stale outcome
 * over a newer one, and show() cancels all pending toast timers
 * (linger, clear, and announce), so a superseded message is never
 * announced late.
 *
 * The factories take their dependencies (document, clock, clipboard) as
 * arguments so tests can drive them with fakes; the browser wiring at
 * the bottom supplies the real ones.
 */
(() => {
  "use strict";

  var TOAST_LINGER_MS = 2000;
  // Matches the .hm-toast fade-out duration in himotoshi.css.
  var TOAST_FADE_MS = 220;
  // Gap between emptying the live region and refilling it.
  var ANNOUNCE_DELAY_MS = 100;

  // A single reusable ghost notification. The visible pill is hidden
  // from assistive tech and paired with an off-screen live region
  // created once and left in the DOM; repeat calls to show() restart
  // the timers rather than stacking further toasts.
  function createToast(doc, clock) {
    var element = doc.createElement("div");
    element.className = "hm-toast";
    element.setAttribute("aria-hidden", "true");
    doc.body.append(element);

    var announcer = doc.createElement("div");
    announcer.className = "visually-hidden";
    announcer.setAttribute("role", "status");
    announcer.setAttribute("aria-live", "polite");
    doc.body.append(announcer);

    var lingerTimer = 0;
    var clearTimer = 0;
    var announceTimer = 0;

    function show(message, isError) {
      clock.clearTimeout(lingerTimer);
      clock.clearTimeout(clearTimer);
      clock.clearTimeout(announceTimer);

      element.textContent = message;
      element.classList.toggle("hm-toast--error", isError);
      element.classList.add("hm-toast--visible");

      // Empty the region and refill it on a later task. Reassigning
      // an identical string in one go can settle back to the same
      // text before assistive tech reads it, leaving a repeat copy
      // silent. The region is off-screen, so the gap costs nothing
      // visually.
      announcer.textContent = "";
      announceTimer = clock.setTimeout(() => {
        announcer.textContent = message;
      }, ANNOUNCE_DELAY_MS);

      lingerTimer = clock.setTimeout(() => {
        element.classList.remove("hm-toast--visible");
        // Wait for the fade to finish before emptying the toast,
        // so the text does not vanish mid-transition.
        clearTimer = clock.setTimeout(() => {
          element.textContent = "";
          announcer.textContent = "";
        }, TOAST_FADE_MS);
      }, TOAST_LINGER_MS);
    }

    return { show: show, element: element, announcer: announcer };
  }

  function createCopyController(deps) {
    var toast = createToast(deps.document, deps.clock);
    var attempt = 0;

    // Returns a promise so tests can await settlement; the browser
    // wiring ignores it.
    function handleCopy(text) {
      var id = ++attempt;
      var clipboard = deps.getClipboard();

      if (!text || !clipboard) {
        toast.show("Copy unavailable", true);
        return Promise.resolve();
      }

      return clipboard.writeText(text).then(
        () => {
          if (id === attempt) {
            toast.show("Copied to clipboard", false);
          }
        },
        () => {
          if (id === attempt) {
            toast.show("Copy failed", true);
          }
        },
      );
    }

    return { handleCopy: handleCopy, toast: toast };
  }

  function init() {
    var buttons = document.querySelectorAll("[data-copy-text]");
    if (buttons.length === 0) {
      return;
    }

    var controller = createCopyController({
      document: document,
      clock: {
        setTimeout: window.setTimeout.bind(window),
        clearTimeout: window.clearTimeout.bind(window),
      },
      getClipboard: () => navigator.clipboard,
    });

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        controller.handleCopy(button.getAttribute("data-copy-text"));
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
    module.exports = {
      createToast: createToast,
      createCopyController: createCopyController,
      TOAST_LINGER_MS: TOAST_LINGER_MS,
      TOAST_FADE_MS: TOAST_FADE_MS,
      ANNOUNCE_DELAY_MS: ANNOUNCE_DELAY_MS,
    };
  }
})();
