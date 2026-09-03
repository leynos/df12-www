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
import { pressKey } from "./dom.mjs";

/* The DOM primitives shared with the Stilyagi harness live in `dom.mjs`;
   they are re-exported here so this module remains the single import the
   mobile-nav suites reach for. */
export { click, evaluateScript, pressKey } from "./dom.mjs";

export const TRANSITIONS = ["toggle", "tab", "shift-tab", "escape", "wide", "narrow"];

/* Enumerate *every* transition trace up to `depth`, which for a state machine
   this small is worth more than a property-testing package would be.

   The drawer has six transitions and a handful of states, so the reachable
   space is finite and small. Sampling it randomly — which is what a generator
   library does — leaves the result depending on a seed, and says nothing about
   the traces it happened not to draw. Enumerating instead turns the test from
   "these traces held" into "no trace of this length breaks the invariants",
   which is the claim actually wanted, and it removes the seed entirely.

   Growth is 6^depth, so the depth is the budget: 258 traces at depth 4 and
   1554 at depth 5, each of which builds a fresh DOM. Every trace opens the
   drawer first, since a closed drawer ignores almost everything and those
   traces prove little about the trap. */
export function exhaustiveTransitionSequences({ depth = 4 } = {}) {
  const sequences = [];
  const walk = (prefix) => {
    if (prefix.length > 1) sequences.push(prefix);
    if (prefix.length >= depth) return;
    for (const transition of TRANSITIONS) walk([...prefix, transition]);
  };
  walk(["toggle"]);
  return sequences;
}

/* Dispatch Tab, then emulate the browser's default focus movement when the
   script under test did not prevent it. happy-dom dispatches the event but
   deliberately does not implement keyboard navigation. */
export function pressTab(window, orderedStops, { shiftKey = false } = {}) {
  const { document } = window;
  const event = pressKey(window, document.activeElement, "Tab", { shiftKey });
  if (event.defaultPrevented) return event;

  const currentIndex = orderedStops.indexOf(document.activeElement);
  const direction = shiftKey ? -1 : 1;
  const nextIndex = (currentIndex + direction + orderedStops.length) % orderedStops.length;
  orderedStops[nextIndex].focus();
  return event;
}

/* A matchMedia stand-in whose `matches` the test controls, so a breakpoint
   crossing can be driven without resizing anything. happy-dom's own
   implementation has no way to fire a change.

   `legacy` models Safari before 14, whose `MediaQueryList` had only
   `addListener`/`removeListener` and no `addEventListener`; the modules keep
   a fallback for it, and this is the only way to reach that branch. */
export function installMatchMedia(window, { matches = false, legacy = false } = {}) {
  const listeners = [];
  const subscribe = (fn) => listeners.push(fn);
  const unsubscribe = (fn) => {
    const i = listeners.indexOf(fn);
    if (i !== -1) listeners.splice(i, 1);
  };
  const list = {
    matches,
    media: "",
    /* Cross the breakpoint and notify, as the browser would. */
    cross(nowMatches) {
      list.matches = nowMatches;
      for (const fn of listeners.slice()) fn({ matches: nowMatches });
    },
  };
  if (legacy) {
    list.addListener = subscribe;
    list.removeListener = unsubscribe;
  } else {
    list.addEventListener = (_type, fn) => subscribe(fn);
    list.removeEventListener = (_type, fn) => unsubscribe(fn);
  }
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
