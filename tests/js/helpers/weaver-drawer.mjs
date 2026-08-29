/* The happy-dom harness both Weaver drawer suites drive.
 *
 * Builds a page with the sidebar markup `templates/weaver/` renders, loads the
 * shipped scripts into it, and hands back the parts a test needs. Shared so
 * the behavioural suite and the telemetry one describe the same drawer.
 */
import { Window } from "happy-dom";

import { evaluateScript, installMatchMedia, stubLayout } from "./mobile-nav-harness.mjs";

const SCRIPT = "public/weaver/assets/js/mobile-nav.js";
const TELEMETRY = "public/weaver/assets/js/telemetry.js";

/* What the touched globals held before the first `setUp` of the current
   test. `evaluateScript` runs the shipped scripts against this process's
   `globalThis`, so whatever `setUp` installs there outlives the test — and
   the test file — unless something puts the old values back. */
let saved = null;

/* Restore every global `setUp` touches to its pre-setup value. Register this
   with `afterEach` in every file that imports `setUp`, or the file's sinks
   and telemetry API leak into whichever test file the runner loads next. */
export function tearDown() {
  if (saved === null) {
    return;
  }
  globalThis.df12WeaverNavTelemetry = saved.nav;
  globalThis.df12WeaverTelemetry = saved.telemetry;
  globalThis.df12WeaverCopy = saved.copy;
  saved = null;
}

/* Build a page with the sidebar markup `templates/weaver/` renders, load the
   drawer into it, and hand back the parts a test needs to drive. */
export function setUp({ links = ["/install", "/docs"], telemetry = false } = {}) {
  if (saved === null) {
    saved = {
      nav: globalThis.df12WeaverNavTelemetry,
      telemetry: globalThis.df12WeaverTelemetry,
      copy: globalThis.df12WeaverCopy,
    };
  }
  const window = new Window({ url: "https://weaver.example/docs/" });
  const { document } = window;
  document.body.innerHTML = `
    <a href="/elsewhere" id="outside">Outside</a>
    <aside id="sidebar">
      <div data-mobile-nav-header><h1>WEAVER</h1></div>
      <nav>${links.map((href) => `<a href="${href}">${href}</a>`).join("")}</nav>
    </aside>`;
  stubLayout(window);
  const media = installMatchMedia(window);
  /* The drawer reports through `telemetry.js` when the page loaded it, and
     works the same when it did not. Both are worth exercising, so the script
     is only present when a test asks for it. */
  /* The sink is installed either way, so a test asserting the drawer stays
     silent has something that would catch it if it did not. Only the script
     that reports through it is conditional. `evaluateScript` runs a script
     through `new Function`, so its `globalThis` is this process's rather than
     the happy-dom window's; in a browser the two are the same object, and
     here `afterEach` takes the sink away again. */
  const events = [];
  globalThis.df12WeaverNavTelemetry = (event) => events.push(event);
  if (telemetry) {
    evaluateScript(window, TELEMETRY);
  } else {
    /* `telemetry.js` installs its API on the process global, and another test
       file in the same run may have required it already. A page that did not
       load it must not find it, or "says nothing at all" is asserted against
       a drawer that had somewhere to report to after all. */
    globalThis.df12WeaverTelemetry = undefined;
  }
  evaluateScript(window, SCRIPT);

  const sidebar = document.getElementById("sidebar");
  return {
    window,
    document,
    media,
    sidebar,
    nav: sidebar.querySelector("nav"),
    toggle: document.getElementById("mobile-nav-toggle"),
    backdrop: document.getElementById("mobile-nav-backdrop"),
    isOpen: () => sidebar.classList.contains("mobile-nav-open"),
    events,
  };
}
