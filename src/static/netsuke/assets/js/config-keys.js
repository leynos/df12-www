/* Config-keys browser: pairs each key group's label with its extract.
 *
 * The component ships as plain text labels, each with a paragraph saying
 * what the group is for, beside always-visible extracts. Every extract is
 * a `role="group"` labelled by its heading. That is the no-JavaScript
 * reading: three labelled, described listings, nothing hidden.
 *
 * What JavaScript adds depends on how much room there is:
 *
 * - Wide, every extract is already on screen beside its label, so there
 *   is nothing to reveal and nothing to operate. Pointing at either half
 *   of a pair marks both, and that is all. The labels stay inert text.
 * - Narrow (< 768px) there is no room for three listings, so the labels
 *   become buttons in a tablist and only the selected extract shows, with
 *   that group's paragraph moved above it. Full tab semantics: arrow
 *   keys, Home/End, roving tabindex.
 *
 * The labels really are spans in one mode and buttons in the other. A
 * control that does nothing is worse than no control, and a tab whose
 * panel is always visible is a lie to a screen reader, so neither is
 * declared unless the layout has made it true.
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
            return forward ? 0 : count - 1;
        }
        return (current + (forward ? 1 : -1) + count) % count;
    }

    function list(root, selector) {
        return Array.prototype.slice.call(root.querySelectorAll(selector));
    }

    function makeButton(doc, span) {
        var button = doc.createElement("button");
        button.type = "button";
        button.id = span.id;
        button.className = span.className;
        button.textContent = span.textContent;
        button.setAttribute("role", "tab");
        // Keep the hook the span carried so the button is still findable
        // by the same selector once it has taken the span's place.
        button.setAttribute(
            "data-config-keys-label",
            span.getAttribute("data-config-keys-label")
        );
        return button;
    }

    /* Wire one config-keys group and return its controller, or null when
       the markup does not satisfy the contract.
       `deps` supplies `document` and `matchMedia` so tests can drive the
       component with fakes; the browser wiring at the bottom passes the
       real ones. Every precondition is checked before anything is
       mutated: a half-upgraded group is worse than an unupgraded one,
       and a key without its label span used to throw part-way through. */
    function createConfigKeys(root, deps) {
        var doc = deps.document;
        var labelList = root.querySelector("[data-config-keys-labels]");
        var panelList = root.querySelector("[data-config-keys-panels]");
        var keys = list(root, "[data-config-keys-key]");
        var panels = list(root, "[data-config-keys-panel]");
        if (!labelList || !panelList || !keys.length || keys.length !== panels.length) {
            return null;
        }

        var spans = keys.map(function (key) {
            return key.querySelector("[data-config-keys-label]");
        });
        if (spans.indexOf(null) !== -1) {
            return null;
        }

        var wide = deps.matchMedia(WIDE);
        var selected = 0;
        var pairs = keys.map(function (key, index) {
            return {
                key: key,
                span: spans[index],
                button: makeButton(doc, spans[index]),
                note: key.querySelector("[data-config-keys-note]"),
                panel: panels[index]
            };
        });

        function label(pair) {
            return wide.matches ? pair.span : pair.button;
        }

        function mark(className, index) {
            pairs.forEach(function (pair, i) {
                var on = i === index;
                label(pair).classList.toggle(className, on);
                pair.key.classList.toggle(className, on);
                pair.panel.classList.toggle(className, on);
            });
        }

        function renderNarrow() {
            // A tablist always has exactly one selected tab.
            if (selected < 0 || selected >= pairs.length) {
                selected = 0;
            }
            pairs.forEach(function (pair, index) {
                var on = index === selected;
                pair.button.setAttribute("aria-selected", on ? "true" : "false");
                pair.button.tabIndex = on ? 0 : -1;
                pair.panel.hidden = !on;
                if (pair.note) {
                    pair.note.hidden = !on;
                }
            });
            mark(ACTIVE, selected);
        }

        function renderWide() {
            pairs.forEach(function (pair) {
                pair.panel.hidden = false;
                if (pair.note) {
                    pair.note.hidden = false;
                }
            });
            // Nothing is pressed wide, so nothing stays marked; the
            // pointer supplies the only emphasis there is.
            mark(ACTIVE, -1);
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

        function applyNarrow(pair) {
            if (pair.button.parentNode !== pair.key) {
                pair.key.replaceChild(pair.button, pair.span);
            }
            // The wrapper is transparent to assistive technology so the
            // tablist owns the tabs directly, as `li` does in the APG's
            // list-based tabs.
            pair.key.setAttribute("role", "presentation");
            pair.button.setAttribute("aria-controls", pair.panel.id);
            pair.panel.setAttribute("role", "tabpanel");
            if (pair.note) {
                // The paragraph belongs with the extract once only one is
                // on screen, and describes the panel it now sits above.
                panelList.insertBefore(pair.note, pair.panel);
                pair.panel.setAttribute("aria-describedby", pair.note.id);
            }
        }

        function applyWide(pair) {
            if (pair.span.parentNode !== pair.key) {
                pair.key.replaceChild(pair.span, pair.button);
            }
            pair.key.removeAttribute("role");
            pair.panel.setAttribute("role", "group");
            pair.panel.removeAttribute("aria-describedby");
            if (pair.note) {
                pair.key.appendChild(pair.note);
            }
        }

        function applyMode() {
            var isWide = wide.matches;
            labelList.setAttribute("role", isWide ? "group" : "tablist");
            pairs.forEach(isWide ? applyWide : applyNarrow);
            render();
        }

        pairs.forEach(function (pair, index) {
            pair.button.addEventListener("click", function () {
                select(index, false);
            });

            // The key wrapper covers the label and, wide, its paragraph.
            [pair.key, pair.panel].forEach(function (el) {
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
        // Marks the component as enhanced only once the DOM has actually
        // been rearranged. The narrow tab strip is gated on this class: it
        // assumes the paragraphs have moved out of the key groups, which
        // is something only applyMode can have done.
        root.classList.add("is-enhanced");

        // Exposed so tests can drive a breakpoint crossing without
        // synthesising a MediaQueryList change event.
        return { applyMode: applyMode, select: select };
    }

    function init() {
        var deps = {
            document: document,
            matchMedia: function (query) {
                return window.matchMedia(query);
            }
        };
        Array.prototype.forEach.call(
            document.querySelectorAll("[data-config-keys]"),
            function (root) {
                createConfigKeys(root, deps);
            }
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
        module.exports = {
            createConfigKeys: createConfigKeys,
            nextTabIndex: nextTabIndex
        };
    }
})();
