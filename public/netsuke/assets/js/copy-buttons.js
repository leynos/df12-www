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

    // A single reusable ghost notification. It is created once and left in
    // the DOM so assistive tech treats it as a live region; repeat calls to
    // show() restart the timer rather than stacking further toasts.
    function createToast() {
        var element = document.createElement("div");
        element.className = "hm-toast";
        element.setAttribute("role", "status");
        element.setAttribute("aria-live", "polite");
        document.body.append(element);

        var lingerTimer = 0;
        var clearTimer = 0;

        function show(message, isError) {
            window.clearTimeout(lingerTimer);
            window.clearTimeout(clearTimer);

            if (element.textContent !== message) {
                element.textContent = message;
            }
            element.classList.toggle("hm-toast--error", isError);
            element.classList.add("hm-toast--visible");

            lingerTimer = window.setTimeout(function () {
                element.classList.remove("hm-toast--visible");
                // Wait for the fade to finish before emptying the live
                // region, so the text does not vanish mid-transition.
                clearTimer = window.setTimeout(function () {
                    element.textContent = "";
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
