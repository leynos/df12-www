/* Shared copy-to-clipboard wiring.
 *
 * Any button carrying a `data-copy-text` attribute copies that text on
 * click and reports the outcome through a single ghost toast (styled by
 * .hm-toast in himotoshi.css). Pages without such buttons pay nothing:
 * init bails before creating the toast.
 */
(function () {
    "use strict";

    var TOAST_LINGER_MS = 2000;
    // Matches the .hm-toast fade-out duration in himotoshi.css.
    var TOAST_FADE_MS = 220;
    // Gap between emptying the live region and refilling it.
    var ANNOUNCE_DELAY_MS = 100;

    // A single reusable ghost notification. The visible pill is hidden from
    // assistive tech and paired with an off-screen live region created once
    // and left in the DOM; repeat calls to show() restart the timers rather
    // than stacking further toasts.
    function createToast() {
        var element = document.createElement("div");
        element.className = "hm-toast";
        element.setAttribute("aria-hidden", "true");
        document.body.append(element);

        var announcer = document.createElement("div");
        announcer.className = "visually-hidden";
        announcer.setAttribute("role", "status");
        announcer.setAttribute("aria-live", "polite");
        document.body.append(announcer);

        var lingerTimer = 0;
        var clearTimer = 0;
        var announceTimer = 0;

        function show(message, isError) {
            window.clearTimeout(lingerTimer);
            window.clearTimeout(clearTimer);
            window.clearTimeout(announceTimer);

            element.textContent = message;
            element.classList.toggle("hm-toast--error", isError);
            element.classList.add("hm-toast--visible");

            // Empty the region and refill it on a later task. Reassigning an
            // identical string in one go can settle back to the same text
            // before assistive tech reads it, leaving a repeat copy silent.
            // The region is off-screen, so the gap costs nothing visually.
            announcer.textContent = "";
            announceTimer = window.setTimeout(function () {
                announcer.textContent = message;
            }, ANNOUNCE_DELAY_MS);

            lingerTimer = window.setTimeout(function () {
                element.classList.remove("hm-toast--visible");
                // Wait for the fade to finish before emptying the toast, so
                // the text does not vanish mid-transition.
                clearTimer = window.setTimeout(function () {
                    element.textContent = "";
                    announcer.textContent = "";
                }, TOAST_FADE_MS);
            }, TOAST_LINGER_MS);
        }

        return { show: show };
    }

    function init() {
        var buttons = document.querySelectorAll("[data-copy-text]");
        if (buttons.length === 0) {
            return;
        }

        var toast = createToast();

        buttons.forEach(function (button) {
            button.addEventListener("click", function () {
                var text = button.getAttribute("data-copy-text");

                if (!text || !navigator.clipboard) {
                    toast.show("Copy unavailable", true);
                    return;
                }

                navigator.clipboard.writeText(text).then(
                    function () {
                        toast.show("Copied to clipboard", false);
                    },
                    function () {
                        toast.show("Copy failed", true);
                    }
                );
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
