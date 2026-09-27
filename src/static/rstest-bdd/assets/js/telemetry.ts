/**
 * @file Optional, privacy-preserving telemetry for rstest-bdd's copy buttons
 * and storybook.
 *
 * Modelled on Weaver's hook in `src/static/weaver/assets/js/telemetry.ts`: a
 * host may install a function at `globalThis.df12RstestBddTelemetrySink`
 * before this script runs, which happens immediately, at the end of
 * `<body>`, with no `defer` and no `DOMContentLoaded` gate, so the deferred
 * scripts that report through it find the API already in place. Without a
 * sink every call here is a no-op, and nothing is collected.
 *
 * What an event may contain is fixed, and deliberately dull. Every field is
 * drawn from a closed vocabulary declared below, so a reader of this file can
 * see the whole of what leaves the page. There is no URL, no page path, no
 * chapter title, no copied text, and nothing that identifies a person or
 * persists between visits — not because they are stripped, but because there
 * is nowhere in the schema to put them.
 *
 * This file is separate from `copy-code.ts` and `storybook.ts` because each
 * of those returns early on a page without its markup, and the other still
 * needs the seam.
 */
(() => {
  "use strict";

  /* Which surface an event came from. */
  const COMPONENTS = Object.freeze({
    clipboard: "rstest-bdd-copy-button",
    storybook: "rstest-bdd-storybook",
  });

  /* What was being done. Each operation belongs to exactly one component, so
     the component is derived rather than passed and cannot disagree with it. */
  const OPERATIONS = Object.freeze({
    clipboard: "clipboard",
    storybook: "storybook",
  });

  const COMPONENT_FOR: Record<string, string> = {
    [OPERATIONS.clipboard]: COMPONENTS.clipboard,
    [OPERATIONS.storybook]: COMPONENTS.storybook,
  };

  /* How it turned out. */
  const OUTCOMES = Object.freeze({
    copied: "copied",
    failed: "failed",
    initialized: "initialized",
    navigated: "navigated",
  });

  /* Why, where a single outcome has more than one cause worth separating.
     A clipboard failure says whether the API was absent or refused; a
     storybook navigation says whether the reader chose a tab, paged, or
     scrolled the strip. Never which chapter: the index would be harmless,
     but the schema stays one that cannot carry it. */
  const REASONS = Object.freeze({
    unavailable: "unavailable",
    rejected: "rejected",
    tab: "tab",
    previous: "previous",
    next: "next",
    scroll: "scroll",
  });

  const OPERATION_VALUES = new Set<string>(Object.values(OPERATIONS));
  const OUTCOME_VALUES = new Set<string>(Object.values(OUTCOMES));
  const REASON_VALUES = new Set<string>(Object.values(REASONS));

  /**
   * Emit one fixed-schema event, if a host has installed a sink.
   *
   * @param operation One of `OPERATIONS`.
   * @param outcome One of `OUTCOMES`.
   * @param reason One of `REASONS`, where the outcome has causes.
   */
  function emit(operation: string, outcome: string, reason?: string): void {
    const sink = globalThis.df12RstestBddTelemetrySink;
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
    const event: RstestBddTelemetryEvent = {
      component: COMPONENT_FOR[operation],
      operation,
      outcome,
      ...(reason === undefined ? {} : { reason }),
    };
    try {
      sink(event);
    } catch {
      /* Observability is optional: a sink that throws must not break the
         copy button or the storybook it was watching. */
    }
  }

  globalThis.df12RstestBddTelemetry = { emit, COMPONENTS, OPERATIONS, OUTCOMES, REASONS };

  /* Exported for the Bun tests, which require the built copy under public/. */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { emit, COMPONENTS, OPERATIONS, OUTCOMES, REASONS };
  }
})();
