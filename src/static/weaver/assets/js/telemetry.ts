/**
 * @file Optional, privacy-preserving telemetry for the Weaver sub-site's chrome.
 *
 * Modelled on the Episodic search hook in
 * `src/static/episodic/assets/js/site-search.ts`: a host may install a
 * function at `globalThis.df12WeaverNavTelemetry` before the deferred scripts
 * run. Without it every call here is a no-op, and nothing is collected.
 *
 * What an event may contain is fixed, and deliberately dull. Every field is
 * drawn from a closed vocabulary declared below, so a reader of this file can
 * see the whole of what leaves the page. There is no URL, no page path, no
 * navigation label, no copied text, and nothing that identifies a person or
 * persists between visits — not because they are stripped, but because there
 * is nowhere in the schema to put them.
 *
 * This file is separate from `mobile-nav.ts` because that script returns
 * early on a page without the drawer's markup, and the copy controls on the
 * install page need the seam whether or not the drawer is there.
 */
(() => {
  "use strict";

  /* Which surface an event came from. The drawer and the copy controls are
     separate things in separate places — the controls sit on the install and
     home pages, not inside the navigation — so labelling a copy event
     `weaver-mobile-nav` would tell a reader it happened somewhere it cannot. */
  const COMPONENTS = {
    drawer: "weaver-mobile-nav",
    clipboard: "weaver-copy-button",
  };

  /* What was being done. Each operation belongs to exactly one component, so
     the component is derived rather than passed and cannot disagree with it. */
  const OPERATIONS = {
    drawer: "drawer",
    clipboard: "clipboard",
  };

  const COMPONENT_FOR: Record<string, string> = {
    [OPERATIONS.drawer]: COMPONENTS.drawer,
    [OPERATIONS.clipboard]: COMPONENTS.clipboard,
  };

  /* How it turned out. */
  const OUTCOMES = {
    initialized: "initialized",
    opened: "opened",
    closed: "closed",
    focusRestored: "focus-restored",
    copied: "copied",
    failed: "failed",
  };

  /* Why, where a single outcome has more than one cause worth separating.
     Closes are attributed to the thing that caused them; a focus restore says
     whether it returned focus to where it came from or fell back to the
     toggle; a clipboard failure says whether the API was absent or refused. */
  const REASONS = {
    toggle: "toggle",
    backdrop: "backdrop",
    navLink: "nav-link",
    escape: "escape",
    breakpoint: "breakpoint",
    savedElement: "saved-element",
    toggleFallback: "toggle-fallback",
    unavailable: "unavailable",
    rejected: "rejected",
  };

  const OPERATION_VALUES = new Set(Object.values(OPERATIONS));
  const OUTCOME_VALUES = new Set(Object.values(OUTCOMES));
  const REASON_VALUES = new Set(Object.values(REASONS));

  /**
   * Emit one fixed-schema event, if a host has installed a sink.
   *
   * @param operation One of `OPERATIONS`.
   * @param outcome One of `OUTCOMES`.
   * @param reason One of `REASONS`, where the outcome has causes.
   */
  function emit(operation: string, outcome: string, reason?: string): void {
    const sink = globalThis.df12WeaverNavTelemetry;
    if (typeof sink !== "function") {
      return;
    }
    /* A caller passing something outside the vocabulary is a bug here, not a
       reason to widen the schema at runtime: dropping the event keeps the
       promise this file makes about what can leave the page. */
    if (!OPERATION_VALUES.has(operation) || !OUTCOME_VALUES.has(outcome)) {
      return;
    }
    if (reason !== undefined && !REASON_VALUES.has(reason)) {
      return;
    }
    const event: WeaverTelemetryEvent = {
      component: COMPONENT_FOR[operation],
      operation,
      outcome,
      ...(reason === undefined ? {} : { reason }),
    };
    try {
      sink(event);
    } catch {
      /* Observability is optional: a sink that throws must not break the
         drawer or the copy button it was watching. */
    }
  }

  /**
   * Copy text to the clipboard, reporting the outcome but never the text.
   *
   * The copy controls are inline `onclick` handlers in the templates, so this
   * is the seam they call: `onclick="df12WeaverCopy('cargo install weaver')"`.
   *
   * @param text What to copy. Never included in an event.
   * @returns Whether the write resolved.
   */
  async function copy(text: string): Promise<boolean> {
    const clipboard = globalThis.navigator?.clipboard;
    if (!clipboard || typeof clipboard.writeText !== "function") {
      emit(OPERATIONS.clipboard, OUTCOMES.failed, REASONS.unavailable);
      return false;
    }
    try {
      await clipboard.writeText(text);
    } catch {
      /* Refused permission, or an insecure context. */
      emit(OPERATIONS.clipboard, OUTCOMES.failed, REASONS.rejected);
      return false;
    }
    emit(OPERATIONS.clipboard, OUTCOMES.copied);
    return true;
  }

  globalThis.df12WeaverTelemetry = { emit, COMPONENTS, OPERATIONS, OUTCOMES, REASONS };
  globalThis.df12WeaverCopy = copy;

  /* Exported for the Bun tests, which require the built copy under public/. */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { emit, copy, COMPONENTS, OPERATIONS, OUTCOMES, REASONS };
  }
})();
