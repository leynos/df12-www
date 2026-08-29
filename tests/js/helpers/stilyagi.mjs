/* A DOM-level harness for the Stilyagi widgets.
 *
 * The widget modules are classic scripts: an IIFE that reads the document at
 * load time, wires listeners, and exports only its pure decision functions.
 * The wiring between those functions and the markup is where the bugs found
 * in review actually lived, so these helpers mount template-faithful markup
 * into the happy-dom `document` registered globally by `happydom.ts` and
 * evaluate the widget script against it.
 *
 * Scripts are read from `src/static/`, the hand-crafted source of truth, so
 * the DOM suites need no build step to run.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const SCRIPT_DIR = join("src", "static", "stilyagi", "assets", "js");

/* Evaluate a Stilyagi widget script (`design`, `docs`, or `roadmap`) against
   the global window, as a classic `<script>` tag would. The document is
   already loaded, so each module's `onReady` wiring runs synchronously. */
export function evaluateStilyagiScript(name) {
  const source = readFileSync(join(REPO_ROOT, SCRIPT_DIR, `${name}.js`), "utf8");
  /* The module under test is a classic browser script with no export
     surface, so running it is the only way to exercise it. The source is
     read from this repository, never from anything external. */
  const run = new Function("window", "document", "navigator", source);
  run(window, window.document, window.navigator);
}

/* Mount markup and evaluate the widget script that enhances it. `before`
   runs between the two, for tests that need to preset control state — a
   restored search string, a select left on a namespace — the way a reload
   or a back-navigation would. */
export function mount(html, script, { before } = {}) {
  document.body.innerHTML = html;
  if (before) before(document);
  if (script) evaluateStilyagiScript(script);
}

/* Put the document and any patched globals back. Call from `afterEach`:
   the widget scripts attach listeners only to elements inside `body`, so
   clearing it discards the wiring along with the markup. */
export function reset() {
  document.body.innerHTML = "";
  restoreIntersectionObserver();
}

/* Click `target`, bubbling so delegated handlers see it. */
export function click(target) {
  target.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
}

/* Press a key on `target`, returning the event so a test can assert on
   whether the handler took it over. */
export function pressKey(target, key) {
  const event = new window.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  target.dispatchEvent(event);
  return event;
}

/* Pointer enter/leave. These do not bubble in a browser, and the widgets
   listen directly on the element, so they are dispatched the same way. */
export function hover(target) {
  target.dispatchEvent(new window.MouseEvent("mouseenter"));
}

export function unhover(target) {
  target.dispatchEvent(new window.MouseEvent("mouseleave"));
}

let realIntersectionObserver = null;

/* Replace `IntersectionObserver` with a controllable stub. The returned
   handle captures the observer's callback and options, records what it was
   asked to observe, and can fire synthetic entries. `reset` restores the
   real constructor. */
export function installIntersectionObserver() {
  const handle = {
    callback: null,
    options: null,
    observed: [],
    /* Fire a synthetic entry, as the browser would when `target` crosses
       the observer's thresholds. */
    intersect(target, isIntersecting = true) {
      handle.callback([{ target, isIntersecting }]);
    },
  };
  if (realIntersectionObserver === null) {
    realIntersectionObserver = window.IntersectionObserver;
  }
  window.IntersectionObserver = class IntersectionObserverStub {
    constructor(callback, options) {
      handle.callback = callback;
      handle.options = options;
    }
    observe(target) {
      handle.observed.push(target);
    }
    unobserve() {}
    disconnect() {}
  };
  return handle;
}

function restoreIntersectionObserver() {
  if (realIntersectionObserver !== null) {
    window.IntersectionObserver = realIntersectionObserver;
    realIntersectionObserver = null;
  }
}

/* ------------------------------------------------------------------------
 * Fixtures.
 *
 * Each fixture mirrors the markup its widget is shipped against and must
 * stay in step with the template it names. They carry every selector and
 * attribute the script reads, with the prose trimmed to what the tests
 * assert on.
 * --------------------------------------------------------------------- */

function phase(index, { open = false, flavour = "later" } = {}) {
  return `
    <div class="phase ${flavour} ${open ? "open" : "closed"}">
      <div
        class="ph-head"
        role="button"
        tabindex="0"
        id="phase-head-${index}"
        aria-controls="phase-body-${index}"
        aria-expanded="${open}"
      >
        <div class="ph-num">0${index}</div>
        <div><h2 class="ph-title">Phase ${index}</h2></div>
        <div class="ph-toggle">+</div>
      </div>
      <div class="ph-body" id="phase-body-${index}" role="region" aria-labelledby="phase-head-${index}">
        <div class="ph-body-inner"><p>Body ${index}.</p></div>
      </div>
    </div>`;
}

/* Mirrors the phase accordion in `templates/stilyagi/pages/roadmap.jinja`:
   a timeline of `.phase` blocks whose `.ph-head` carries `aria-controls`
   and `aria-expanded`, with one phase shipped open. */
export const ROADMAP_FIXTURE = `
  <div class="timeline">
    ${phase(0, { flavour: "done" })}
    ${phase(1, { open: true, flavour: "current" })}
    ${phase(2)}
  </div>`;

function chip(ns, { active = false, label = ns } = {}) {
  return `<button
      type="button"
      data-ns="${ns}"
      data-ns-class="${ns === "all" ? "" : `ns-${ns}`}"
      aria-pressed="${active}"
      class="filter-chip${active ? " active" : ""}"
    >${label}</button>`;
}

function ruleRow(ns, id, text) {
  return `<tr role="row" data-ns="${ns}" data-search="${id.toLowerCase()} ${text}">
      <td role="cell" class="id">${id}</td>
      <td role="cell">${text}</td>
    </tr>`;
}

/* Mirrors the rules catalogue in `templates/stilyagi/pages/docs.jinja`:
   the chip row and its equivalent select, the search box, and a rules
   table led by a hidden `.empty-row`. */
export const CATALOGUE_FIXTURE = `
  <div class="filter-bar">
    <span class="lbl">Filter</span>
    ${chip("all", { active: true, label: "All" })}
    ${chip("md", { label: "Markdown" })}
    ${chip("pydoc", { label: "PyDoc" })}
    <label class="sr-only" for="ns-filter">Filter rules by namespace</label>
    <select id="ns-filter" class="filter-select">
      <option value="all" selected>All namespaces</option>
      <option value="md">Markdown</option>
      <option value="pydoc">PyDoc</option>
    </select>
    <label class="sr-only" for="rule-search">Search rules by name or ID</label>
    <input id="rule-search" type="search" class="search-box" value="" />
  </div>
  <table class="rules-table" role="table">
    <tbody role="rowgroup">
      <tr role="row" class="empty-row" hidden="">
        <td role="cell" colspan="2">No rules match that filter.</td>
      </tr>
      ${ruleRow("md", "MD201", "heading depth headings must not skip levels")}
      ${ruleRow("md", "MD401", "link hygiene reject bare urls and empty link text")}
      ${ruleRow("pydoc", "PYDOC101", "docstring summary must start with a single line")}
    </tbody>
  </table>`;

/* Mirrors the suppression examples in `templates/stilyagi/pages/docs.jinja`:
   a two-tab tablist whose panels are keyed by `data-panel`. */
export const TABS_FIXTURE = `
  <section class="suppress">
    <div class="tabs" role="tablist" aria-label="Suppression syntax">
      <button type="button" role="tab" id="suppress-tab-md" data-tab="md"
        aria-controls="suppress-panel-md" aria-selected="true" class="tab active">Markdown</button>
      <button type="button" role="tab" id="suppress-tab-py" data-tab="py"
        aria-controls="suppress-panel-py" aria-selected="false" class="tab">Python docstring</button>
    </div>
    <pre id="suppress-panel-md" role="tabpanel" aria-labelledby="suppress-tab-md"
      data-panel="md" tabindex="0">markdown example</pre>
    <pre id="suppress-panel-py" role="tabpanel" aria-labelledby="suppress-tab-py"
      data-panel="py" tabindex="0" hidden="">python example</pre>
  </section>`;

/* Mirrors the section rail in `templates/stilyagi/pages/docs.jinja`: a
   `.side-toc` of in-page links, each pointing at a section by id. */
export const RAIL_FIXTURE = `
  <div class="docs-layout">
    <aside class="side-toc">
      <a href="#catalogue" class="active">§ I. Rules</a><a href="#config" class="">§ II. Config</a
      ><a href="#suppress" class="">§ III. Suppressions</a>
    </aside>
    <div>
      <section id="catalogue" class="section-anchor"><h2>Rules</h2></section>
      <section id="config" class="section-anchor"><h2>Config</h2></section>
      <section id="suppress" class="section-anchor"><h2>Suppressions</h2></section>
    </div>
  </div>`;

function treeNode(region, label, range, { pressed = false } = {}) {
  return `<div
      role="button"
      tabindex="0"
      data-region="${region}"
      data-label="${label}"
      data-range="${range}"
      aria-pressed="${pressed}"
      class="tree-node${pressed ? " active" : ""}"
    >${label}</div>`;
}

/* Mirrors the IR inspector in `templates/stilyagi/pages/design.jinja`:
   highlighted source spans and IR tree nodes paired by `data-region`, and
   a footer reporting the active node's label and byte range. The markup
   ships with the link node pressed. */
export const INSPECTOR_FIXTURE = `
  <section id="ir-contract" class="ir-inspector section-anchor">
    <div class="pane">
      <div class="ir-src">
        <span data-region="h1-1" class="region type-heading"># Configuring Stilyagi</span>
        <span data-region="p-1" class="region type-paragraph">Rules are selected in </span>
        <span data-region="link-1" class="region type-link active">[the configuration guide]</span>
      </div>
      <div class="ir-foot">
        <span data-ir-label="true" aria-live="polite">Link</span
        ><span>range <code data-ir-range="true">[136,172]</code></span>
      </div>
    </div>
    <div class="pane">
      <div class="ir-tree">
        ${treeNode("h1-1", "Heading depth=1", "0,22")}
        ${treeNode("p-1", "Paragraph", "24,173")}
        ${treeNode("link-1", "Link", "136,172", { pressed: true })}
      </div>
    </div>
  </section>`;

function ruleToggle(code, caps, { checked = false } = {}) {
  return `<div
      role="switch"
      tabindex="0"
      data-code="${code}"
      data-caps="${caps}"
      aria-checked="${checked}"
      class="rule-toggle${checked ? " on" : ""}"
    >
      <span class="check"></span><span class="code">${code}</span>
    </div>`;
}

function provider(name, label, { loaded = false } = {}) {
  return `<div data-provider="${name}" class="provider ${loaded ? "loaded" : "skipped"}">
      <div class="pname">${label}</div>
      <span class="ptag" data-provider-tag="true">${loaded ? "Loaded" : "Skipped"}</span>
    </div>`;
}

/* Mirrors the capability planner in `templates/stilyagi/pages/design.jinja`:
   rule toggles declaring their capabilities, provider cards, and the
   summary counters. The provider count ships with a leading space, as the
   template writes it. */
export const PLANNER_FIXTURE = `
  <section class="planner">
    <div class="plan-left">
      ${ruleToggle("MD201", "", { checked: true })}
      ${ruleToggle("GRAM301", "grammar")}
      ${ruleToggle("SPELL101", "spell")}
      ${ruleToggle("TERM201", "terminology")}
    </div>
    <div class="plan-right">
      <div class="providers">
        ${provider("core", "Core extractor", { loaded: true })}
        ${provider("grammar", "Grammar · spaCy")}
        ${provider("spell", "Spellchecker")}
        ${provider("terminology", "Terminology")}
      </div>
      <div class="plan-sum" aria-live="polite">
        <b data-plan-rules="true">1</b> rules enabled ·<b data-plan-providers="true"> 0</b>
        linguistic providers required · estimated cold start <b data-plan-coldstart="true">40 ms</b>
      </div>
    </div>
  </section>`;
