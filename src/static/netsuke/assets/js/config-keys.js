/* Config-keys browser: pairs each key group's label with its extract.
 *
 * The component ships as plain text labels and always-visible extracts,
 * each extract a `role="group"` labelled by its heading. That is the
 * no-JavaScript reading: three labelled listings, nothing hidden.
 *
 * With JavaScript the labels become buttons, and what those buttons mean
 * depends on how much room there is:
 *
 * - Narrow (< 768px) there is no room for three listings, so the labels
 *   are a tablist and only the selected extract is shown. Full tab
 *   semantics: arrow keys, Home/End, roving tabindex.
 * - Wide, every extract stays on screen beside its label, so a button
 *   cannot "reveal" anything. It emphasises instead: pressing one marks
 *   its pair, and `aria-pressed` says so. Pointer and keyboard focus
 *   preview the same emphasis without committing to it.
 *
 * Roles are swapped on the breakpoint rather than declared once, because
 * a tab whose panel is always visible is a lie to a screen reader.
 */
(function () {
    "use strict";

    var WIDE = "(min-width: 768px)";
    var ACTIVE = "is-active";
    var PREVIEW = "is-preview";

    /* Index of the tab an arrow/Home/End keypress should move to.
     *
     * Returns -1 when the key is not one this widget handles, so the
     * caller can leave the event alone. Arrow movement wraps.
     */
    function nextTabIndex(current, key, count) {
        if (count <= 0) {
            return -1;
        }
        if (key === "Home") {
            return 0;
        }
        if (key === "End") {
            return count - 1;
        }
        var forward = key === "ArrowRight" || key === "ArrowDown";
        var back = key === "ArrowLeft" || key === "ArrowUp";
        if (!forward && !back) {
            return -1;
        }
        if (current < 0) {
            // Nothing is marked — wide mode allows that — so step in from
            // whichever end the reader is heading towards.
            return forward ? 0 : count - 1;
        }
        return (current + (forward ? 1 : -1) + count) % count;
    }

    function toButton(label) {
        var button = document.createElement("button");
        button.type = "button";
        button.id = label.id;
        button.className = label.className;
        button.textContent = label.textContent;
        button.setAttribute(
            "data-config-keys-label",
            label.getAttribute("data-config-keys-label")
        );
        label.parentNode.replaceChild(button, label);
        return button;
    }

    function initGroup(root) {
        var labelList = root.querySelector("[data-config-keys-labels]");
        var labels = Array.prototype.slice.call(
            root.querySelectorAll("[data-config-keys-label]")
        );
        var panels = Array.prototype.slice.call(
            root.querySelectorAll("[data-config-keys-panel]")
        );
        if (!labelList || labels.length === 0 || labels.length !== panels.length) {
            return;
        }

        var pairs = labels.map(function (label, index) {
            return { button: toButton(label), panel: panels[index] };
        });
        var wide = window.matchMedia(WIDE);
        // Wide, every extract is already on screen, so nothing is marked
        // until the reader asks for it. Narrow, a tablist must start with
        // one tab selected.
        var selected = wide.matches ? -1 : 0;

        function mark(className, index) {
            pairs.forEach(function (pair, i) {
                var on = i === index;
                pair.button.classList.toggle(className, on);
                pair.panel.classList.toggle(className, on);
            });
        }

        function renderNarrow() {
            // A tablist always has exactly one selected tab, so an
            // unmarked wide-mode state resolves to the first group.
            if (selected < 0) {
                selected = 0;
            }
            pairs.forEach(function (pair, index) {
                var on = index === selected;
                pair.button.setAttribute("aria-selected", on ? "true" : "false");
                pair.button.tabIndex = on ? 0 : -1;
                pair.panel.hidden = !on;
            });
            mark(ACTIVE, selected);
            mark(PREVIEW, -1);
        }

        function renderWide() {
            pairs.forEach(function (pair, index) {
                pair.button.setAttribute(
                    "aria-pressed",
                    index === selected ? "true" : "false"
                );
                pair.button.tabIndex = 0;
                pair.panel.hidden = false;
            });
            mark(ACTIVE, selected);
        }

        function render() {
            if (wide.matches) {
                renderWide();
            } else {
                renderNarrow();
            }
        }

        function select(index, focus) {
            selected = index;
            render();
            if (focus) {
                pairs[index].button.focus();
            }
        }

        function applyMode() {
            var isWide = wide.matches;
            labelList.setAttribute("role", isWide ? "group" : "tablist");
            pairs.forEach(function (pair) {
                if (isWide) {
                    pair.button.removeAttribute("role");
                    pair.button.removeAttribute("aria-selected");
                    pair.button.removeAttribute("aria-controls");
                    pair.panel.setAttribute("role", "group");
                } else {
                    pair.button.setAttribute("role", "tab");
                    pair.button.removeAttribute("aria-pressed");
                    pair.button.setAttribute("aria-controls", pair.panel.id);
                    pair.panel.setAttribute("role", "tabpanel");
                }
                // The panel keeps the tabindex the markup gave it in both
                // modes: it is the scroll container, so it must stay
                // reachable whether or not it is also a tabpanel.
            });
            render();
        }

        pairs.forEach(function (pair, index) {
            pair.button.addEventListener("click", function () {
                // Wide: pressing the marked pair again clears the mark, so
                // the control is a genuine toggle rather than a one-way trap.
                if (wide.matches && selected === index) {
                    select(-1, false);
                    return;
                }
                select(index, false);
                if (wide.matches) {
                    // Emphasis alone is no use to a reader who cannot see
                    // it, so pressing also brings the extract into view.
                    // 'nearest' is a no-op when it already is.
                    pair.panel.scrollIntoView({ block: "nearest" });
                }
            });

            [pair.button, pair.panel].forEach(function (el) {
                el.addEventListener("pointerenter", function () {
                    if (wide.matches) {
                        mark(PREVIEW, index);
                    }
                });
                el.addEventListener("pointerleave", function () {
                    if (wide.matches) {
                        mark(PREVIEW, -1);
                    }
                });
            });

            pair.button.addEventListener("focus", function () {
                if (wide.matches) {
                    mark(PREVIEW, index);
                }
            });
            pair.button.addEventListener("blur", function () {
                if (wide.matches) {
                    mark(PREVIEW, -1);
                }
            });
        });

        labelList.addEventListener("keydown", function (e) {
            if (wide.matches) {
                return;
            }
            var next = nextTabIndex(selected, e.key, pairs.length);
            if (next === -1) {
                return;
            }
            e.preventDefault();
            select(next, true);
        });

        if (wide.addEventListener) {
            wide.addEventListener("change", applyMode);
        } else {
            wide.addListener(applyMode);
        }
        applyMode();
    }

    function init() {
        Array.prototype.forEach.call(
            document.querySelectorAll("[data-config-keys]"),
            initGroup
        );
    }

    if (typeof document !== "undefined") {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", init);
        } else {
            init();
        }
    }

    if (typeof module !== "undefined" && module.exports) {
        module.exports = { nextTabIndex: nextTabIndex };
    }
})();
