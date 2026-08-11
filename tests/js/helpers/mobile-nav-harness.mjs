/* A browser-level harness for the two mobile-navigation modules.
 *
 * Both modules are classic scripts: an IIFE that reads the document at load
 * time, wires listeners, and exports nothing. There is no factory to call and
 * no pure function to isolate, so the fake DOM that drives `config-keys` and
 * `copy-buttons` has nothing to take hold of. Section 6 of the developers'
 * guide documents this harness and records both `mobile-nav.js` modules as
 * covered by it. The decision each one gets wrong is not a calculation but an
 * interaction — which element holds focus after a keypress — so a fake DOM
 * with hand-written focus bookkeeping would largely be testing itself.
 *
 * happy-dom supplies the real thing: genuine event dispatch and bubbling,
 * a real `activeElement`, and `closest`/`contains`/`getComputedStyle`. The
 * script is read from `public/`, the copy the browser is actually served, in
 * keeping with the convention the other tests here follow.
 *
 * The script is evaluated through `new Function` rather than a `<script>`
 * tag: happy-dom does not execute markup-injected script by default, and the
 * wrapper hands the module the same three globals a classic script would
 * find on the window it was loaded into.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

/* Load a shipped script into a window, as a classic `<script>` would. */
export function evaluateScript(window, relativePath) {
  const source = readFileSync(join(REPO_ROOT, relativePath), "utf8");
  /* The module under test is a classic browser script with no export
     surface, so running it is the only way to exercise it. The source comes
     from the repository's own build output, never from anything external. */
  const run = new Function("window", "document", "navigator", source);
  run(window, window.document, window.navigator);
}

/* Press a key on `target`, returning the event so a test can assert on
   whether the handler took it over. Bubbles, because both modules listen
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

/* A matchMedia stand-in whose `matches` the test controls, so a breakpoint
   crossing can be driven without resizing anything. happy-dom's own
   implementation has no way to fire a change. */
export function installMatchMedia(window, { matches = false } = {}) {
  const listeners = [];
  const list = {
    matches,
    media: "",
    addEventListener: (_type, fn) => listeners.push(fn),
    removeEventListener: (_type, fn) => {
      const i = listeners.indexOf(fn);
      if (i !== -1) listeners.splice(i, 1);
    },
    /* Cross the breakpoint and notify, as the browser would. */
    cross(nowMatches) {
      list.matches = nowMatches;
      for (const fn of listeners.slice()) fn({ matches: nowMatches });
    },
  };
  window.matchMedia = () => list;
  return list;
}

/* Give every element a non-zero box. `isToggleVisible` in the Netsuke module
   asks for one, and happy-dom lays nothing out. */
export function stubLayout(window, { width = 40, height = 40 } = {}) {
  window.Element.prototype.getBoundingClientRect = function getBoundingClientRect() {
    return { width, height, top: 0, left: 0, right: width, bottom: height, x: 0, y: 0 };
  };
}
