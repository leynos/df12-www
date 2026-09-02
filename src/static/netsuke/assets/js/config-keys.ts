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
(() => {
  "use strict";

  var WIDE = "(min-width: 768px)";
  var ACTIVE = "is-active";
  var PREVIEW = "is-preview";

  /* The `data-config-keys-*` hooks the template emits, named once so the
     selectors below and the makeButton carry-over agree. */
  var HOOKS = {
    labels: "data-config-keys-labels",
    panels: "data-config-keys-panels",
    key: "data-config-keys-key",
    panel: "data-config-keys-panel",
    label: "data-config-keys-label",
    note: "data-config-keys-note",
  };

  /* What `createConfigKeys` needs from its host. `matchMedia` is a function
     rather than a list so tests can hand back a fake whose `matches` they
     flip. */
  interface ConfigKeysDeps {
    document: Document;
    matchMedia(query: string): MediaQueryList;
  }

  /* One key group: the wrapper, the two label elements that alternate in it,
     the optional paragraph, and the extract the label describes. */
  interface Pair {
    key: HTMLElement;
    span: HTMLElement;
    button: HTMLButtonElement;
    note: HTMLElement | null;
    panel: HTMLElement;
  }

  /* The handle a mounted component returns, for tests to drive. */
  interface ConfigKeysController {
    applyMode(): void;
    select(index: number, focus: boolean): void;
  }

  /* Index of the tab an arrow/Home/End keypress should move to.
   *
   * Returns -1 when the key is not one this widget handles, so the
   * caller can leave the event alone. Arrow movement wraps.
   */
  function nextTabIndex(current: number, key: string, count: number): number {
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

  /* `querySelectorAll` as a real array, so the result can be mapped. */
  function list(root: ParentNode, selector: string): HTMLElement[] {
    return Array.from(root.querySelectorAll<HTMLElement>(selector));
  }

  /* The narrow-viewport tab that stands in for a label `span`, carrying over
     its id, classes, text, and data hook so the same selectors still find it. */
  function makeButton(doc: Document, span: HTMLElement): HTMLButtonElement {
    var button = doc.createElement("button");
    button.type = "button";
    button.id = span.id;
    button.className = span.className;
    button.textContent = span.textContent;
    button.setAttribute("role", "tab");
    // Keep the hook the span carried so the button is still findable
    // by the same selector once it has taken the span's place.
    button.setAttribute(HOOKS.label, span.getAttribute(HOOKS.label) ?? "");
    return button;
  }

  /* Wire one config-keys group and return its controller, or null when
       the markup does not satisfy the contract.
       `deps` supplies `document` and `matchMedia` so tests can drive the
       component with fakes; the browser wiring at the bottom passes the
       real ones. Every precondition is checked before anything is
       mutated: a half-upgraded group is worse than an unupgraded one,
       and a key without its label span used to throw part-way through. */
  function createConfigKeys(root: HTMLElement, deps: ConfigKeysDeps): ConfigKeysController | null {
    var doc = deps.document;
    /* Cast rather than narrowed: the functions below are hoisted
       declarations, which the checker does not narrow through, and the early
       return that follows is what makes the casts true at runtime. */
    var labelList = root.querySelector(`[${HOOKS.labels}]`) as HTMLElement;
    var panelList = root.querySelector(`[${HOOKS.panels}]`) as HTMLElement;
    var keys = list(root, `[${HOOKS.key}]`);
    var panels = list(root, `[${HOOKS.panel}]`);
    if (!labelList || !panelList || !keys.length || keys.length !== panels.length) {
      return null;
    }

    var found = keys.map((key) => key.querySelector<HTMLElement>(`[${HOOKS.label}]`));
    if (found.indexOf(null) !== -1) {
      return null;
    }
    // Every entry was just checked, which `indexOf` does not tell the checker.
    var spans = found as HTMLElement[];

    var wide = deps.matchMedia(WIDE);
    var selected = 0;
    var pairs: Pair[] = keys.map((key, index) => ({
      key: key,
      span: spans[index],
      button: makeButton(doc, spans[index]),
      note: key.querySelector<HTMLElement>(`[${HOOKS.note}]`),
      panel: panels[index],
    }));

    /* Whichever of the pair's two label elements is currently mounted: the
       span when wide, the tab button when narrow. */
    function label(pair: Pair): HTMLElement {
      return wide.matches ? pair.span : pair.button;
    }

    /* Put `className` on the key, panel, and label at `index`, and take it off
       every other one. Pass -1 to clear it everywhere. */
    function mark(className: string, index: number): void {
      pairs.forEach((pair, i) => {
        var on = i === index;
        label(pair).classList.toggle(className, on);
        pair.key.classList.toggle(className, on);
        pair.panel.classList.toggle(className, on);
      });
    }

    /* Draw the tablist state: exactly one tab selected, only its panel and
       note on screen, and the roving tabindex on the selected tab. */
    function renderNarrow(): void {
      // A tablist always has exactly one selected tab.
      if (selected < 0 || selected >= pairs.length) {
        selected = 0;
      }
      pairs.forEach((pair, index) => {
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

    /* Draw the wide state: every panel and note visible, and nothing marked,
       since there is no selection to indicate when all of it is on screen. */
    function renderWide(): void {
      pairs.forEach((pair) => {
        pair.panel.hidden = false;
        if (pair.note) {
          pair.note.hidden = false;
        }
      });
      // Nothing is pressed wide, so nothing stays marked; the
      // pointer supplies the only emphasis there is.
      mark(ACTIVE, -1);
    }

    /* Draw whichever state the current breakpoint calls for. */
    function render(): void {
      if (wide.matches) {
        renderWide();
      } else {
        renderNarrow();
      }
    }

    /* Select the tab at `index` and redraw, moving focus to it when `focus`
       is set — which distinguishes a keyboard move from a programmatic one. */
    function select(index: number, focus: boolean): void {
      selected = index;
      render();
      if (focus) {
        pairs[index].button.focus();
      }
    }

    /* Convert one pair to its tablist form: swap the span for the button,
       make the wrapper presentational so the tablist owns the tab directly,
       wire the ARIA relationships, and move the note above its panel. */
    function applyNarrow(pair: Pair): void {
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

    /* Convert one pair back to its wide form: restore the span, drop the tab
       ARIA, and return the note to the key it belongs with. */
    function applyWide(pair: Pair): void {
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

    /* Move the whole component to the current breakpoint's form and redraw.
       Idempotent, so a repeated breakpoint event costs nothing. */
    function applyMode(): void {
      var isWide = wide.matches;
      labelList.setAttribute("role", isWide ? "group" : "tablist");
      pairs.forEach(isWide ? applyWide : applyNarrow);
      render();
    }

    pairs.forEach((pair, index) => {
      pair.button.addEventListener("click", () => {
        select(index, false);
      });

      // The key wrapper covers the label and, wide, its paragraph.
      [pair.key, pair.panel].forEach((el) => {
        el.addEventListener("pointerenter", () => {
          if (wide.matches) {
            mark(PREVIEW, index);
          }
        });
        el.addEventListener("pointerleave", () => {
          if (wide.matches) {
            mark(PREVIEW, -1);
          }
        });
      });
    });

    labelList.addEventListener("keydown", (e) => {
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

    if (typeof wide.addEventListener === "function") {
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

  /* Mount every config-keys root on the page, injecting the real `document`
     and `matchMedia` that the tests replace with fakes. */
  function init(): void {
    var deps: ConfigKeysDeps = {
      document: document,
      matchMedia: (query) => window.matchMedia(query),
    };
    document.querySelectorAll<HTMLElement>("[data-config-keys]").forEach((root) => {
      createConfigKeys(root, deps);
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
      createConfigKeys: createConfigKeys,
      nextTabIndex: nextTabIndex,
    };
  }
})();
