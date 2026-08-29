/* Shared DOM primitives for the browser-level harnesses.
 *
 * Both `mobile-nav-harness.mjs` and `stilyagi.mjs` drive shipped classic
 * scripts against a happy-dom window; the mechanics of loading a script and
 * dispatching the basic events are the same in each, so they live here once.
 * Every helper takes the window explicitly: the mobile-nav suites build an
 * isolated `Window` per test, while the Stilyagi harness passes the global
 * one registered by `happydom.ts`.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

/* Load a shipped script into a window, as a classic `<script>` would. */
export function evaluateScript(window, relativePath) {
  const source = readFileSync(join(REPO_ROOT, relativePath), "utf8");
  /* The module under test is a classic browser script with no export
     surface, so running it is the only way to exercise it. The source comes
     from this repository, never from anything external. */
  const run = new Function("window", "document", "navigator", source);
  run(window, window.document, window.navigator);
}

/* Press a key on `target`, returning the event so a test can assert on
   whether the handler took it over. Bubbles, because some modules listen
   above the element that receives the keystroke. */
export function pressKey(window, target, key, { shiftKey = false } = {}) {
  const event = new window.KeyboardEvent("keydown", {
    key,
    shiftKey,
    bubbles: true,
    cancelable: true,
  });
  target.dispatchEvent(event);
  return event;
}

/* Click `target`, bubbling so document-level handlers see it. */
export function click(window, target) {
  target.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
}
