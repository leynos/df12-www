/**
 * Ambient declarations for the globals the browser scripts rely on.
 *
 * The scripts under `src/static/<site>/assets/js/` are classic scripts: each
 * is an IIFE loaded with `<script defer>`, with no imports and no exports.
 * The values they reach for that are neither theirs nor the DOM's arrive in
 * one of two ways, and both are declared here so `tsconfig.browser.json`
 * can typecheck the scripts with `types: []` and no other ambient input.
 *
 * - **Vendored libraries** are loaded by an earlier `<script>` tag and
 *   attach themselves to `window`. MiniSearch is the only one; its vendored
 *   copy is the same release as the `minisearch` development dependency, so
 *   the global is typed against that package's own declarations rather than
 *   a stub that could drift from the file actually shipped.
 * - **Cross-script contracts** are properties one deferred script installs
 *   on `globalThis` for a later one, or for a host page, to read. They are
 *   optional throughout because every reader tolerates their absence: the
 *   telemetry sinks are no-ops when nothing installed them.
 *
 * `module` is the CommonJS hook the Bun tests use. Seven scripts end with
 * `if (typeof module !== "undefined" && module.exports) { module.exports =
 * {...}; }`, which the browser skips and `require` honours. It is declared as
 * a plain global rather than through `@types/node` so the browser project
 * stays free of Node's other globals.
 */

/** The CommonJS module record, present only when a script is `require`d. */
declare const module: { exports: Record<string, unknown> };

/**
 * The vendored MiniSearch constructor; see `src/static/<site>/assets/vendor/`.
 * A `var`, because the UMD build assigns it as a property of the global
 * object, which is how the scripts reach it through `window` and
 * `globalThis`.
 */
declare var MiniSearch: typeof import("minisearch").default;

/** A Weaver telemetry event, as handed to the host's sink by `telemetry.ts`. */
interface WeaverTelemetryEvent {
  component: string;
  operation: string;
  outcome: string;
  reason?: string;
}

/**
 * The API `weaver/assets/js/telemetry.ts` installs for the drawer script.
 * Each vocabulary is a closed map from a camelCase name to the string that
 * leaves the page; `emit` drops anything outside them.
 */
interface WeaverTelemetryApi {
  emit(operation: string, outcome: string, reason?: string): void;
  COMPONENTS: Readonly<Record<string, string>>;
  OPERATIONS: Readonly<Record<string, string>>;
  OUTCOMES: Readonly<Record<string, string>>;
  REASONS: Readonly<Record<string, string>>;
}

/**
 * An Episodic search-index lifecycle event, as `site-search.ts` hands it to
 * the host's sink. The schema is fixed and has nowhere to put a query, a
 * path, or anything that identifies a person.
 */
interface EpisodicSearchTelemetryEvent {
  attempt: string;
  cache_state: string;
  operation: string;
  outcome: string;
  duration_bucket?: string;
}

/** The Tailwind Play CDN's configuration hook, read once when the CDN script runs. */
interface TailwindPlayCdn {
  config?: Record<string, unknown>;
}

declare var df12WeaverTelemetry: WeaverTelemetryApi | undefined;
declare var df12WeaverNavTelemetry: ((event: WeaverTelemetryEvent) => void) | undefined;
declare var df12WeaverCopy: ((text: string) => Promise<boolean>) | undefined;
declare var df12EpisodicSearchTelemetry:
  | ((event: EpisodicSearchTelemetryEvent) => void)
  | undefined;

interface Window {
  tailwind?: TailwindPlayCdn;
}
