/* mobile-nav.js — the Weaver sidebar's narrow-viewport drawer (<1024px).
 *
 * A plain script module in the shape described in section 6 of the
 * developers' guide: an IIFE loaded with `<script defer>` that finds its
 * markup, returns early when any part of it is absent, and enhances what the
 * server already rendered. `templates/weaver/` emits the sidebar, its header,
 * and the nav; this file builds the hamburger button and the backdrop, which
 * only make sense once script is running, and adds `has-mobile-nav` to the
 * root element so the stylesheet may hide the nav in the knowledge that
 * something can reopen it.
 *
 * Unlike the Netsuke menu, this drawer is modal: it dims the page behind a
 * backdrop and locks body scrolling, so focus is trapped inside it until it
 * closes and is then restored to wherever it came from.
 */
(() => {
  "use strict";

  var sidebar = document.getElementById("sidebar");
  if (!sidebar) return;

  var nav = sidebar.querySelector("nav");
  if (!nav) return;

  var header = sidebar.querySelector("[data-mobile-nav-header]");
  if (!header) return;

  /* Signal that JS is available so CSS can safely hide the nav */
  document.documentElement.classList.add("has-mobile-nav");

  /* Optional telemetry, from `telemetry.js`. Absent on a page that did not
     load it, and a no-op there unless a host installed a sink; either way the
     drawer behaves the same. See that file for the whole event schema. */
  var telemetry = globalThis.df12WeaverTelemetry;
  function report(outcome, reason) {
    telemetry?.emit(telemetry.OPERATIONS.drawer, outcome, reason);
  }

  /* ---- hamburger button ---- */
  var btn = document.createElement("button");
  btn.id = "mobile-nav-toggle";
  btn.setAttribute("aria-expanded", "false");
  btn.setAttribute("aria-controls", nav.id || "sidebar-nav");
  btn.setAttribute("aria-label", "Open navigation menu");
  if (!nav.id) nav.id = "sidebar-nav";
  /* The button *is* the brand mark: the glyph and the block of indigo
     both come from `.weaver-brand-mark` in weaver/chrome.css, so this
     file carries no markup of its own. `aria-label` above says what the
     button does, and is kept in step with its state below. */
  btn.className = "weaver-brand-mark";
  header.style.position = "relative";
  header.appendChild(btn);

  /* ---- backdrop ---- */
  var backdrop = document.createElement("div");
  backdrop.id = "mobile-nav-backdrop";
  sidebar.parentNode.insertBefore(backdrop, sidebar.nextSibling);

  /* Publish the header's height as a custom property, so the drawer can sit
     below a header whose height depends on the rendered text. */
  function setHeaderHeight() {
    var h = header.getBoundingClientRect().height;
    sidebar.style.setProperty("--mobile-header-height", `${h}px`);
  }

  var previousBodyOverflowY = "";
  var savedFocus = null;
  var focusTrapHandler = null;

  /* The drawer's tab stops, in document order. Requeried on each keypress
     rather than cached, since the nav's contents are not fixed. */
  function getFocusableElements() {
    return nav.querySelectorAll(
      "a[href], button:not([disabled]), input:not([disabled]), " +
        'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
  }

  /* Open the drawer: lock the page behind it, move focus inside, and install
     the trap that keeps focus there. */
  function open() {
    sidebar.classList.add("mobile-nav-open");
    btn.setAttribute("aria-expanded", "true");
    btn.setAttribute("aria-label", "Close navigation menu");
    /* Lock the vertical axis only.
     *
     * `style.overflow` would set both axes, momentarily replacing the
     * `overflow-x: hidden` the body carries as a class — the clip that
     * keeps the page from scrolling sideways — and then removing both on
     * close. The horizontal clip should never be disturbed: the drawer
     * only ever needed to stop the page scrolling underneath it. */
    previousBodyOverflowY = document.body.style.overflowY;
    document.body.style.overflowY = "hidden";
    setHeaderHeight();

    /* Save focus and move it into the nav */
    savedFocus = document.activeElement;
    var focusables = getFocusableElements();
    if (focusables.length) {
      focusables[0].focus();
    } else {
      /* Nothing focusable inside: make the nav itself a focus target. */
      nav.setAttribute("tabindex", "-1");
      nav.focus();
    }

    /* Install focus trap */
    focusTrapHandler = (e) => {
      if (e.key !== "Tab") return;
      var els = getFocusableElements();
      if (!els.length) {
        /* The drawer is modal — backdrop plus `overflow: hidden` — so Tab
           must not reach the obscured page behind it. With nothing focusable
           inside, the container and the toggle are the only two stops worth
           having, so cycle between them. */
        e.preventDefault();
        if (document.activeElement === btn) nav.focus();
        else btn.focus();
        return;
      }
      var first = els[0];
      var last = els[els.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first || document.activeElement === btn) {
          e.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last) {
        e.preventDefault();
        btn.focus();
      } else if (document.activeElement === btn) {
        /* Document order already sends Tab from the toggle into the nav,
           since the header precedes it. Say so explicitly so the cycle does
           not depend on the templates keeping that order. */
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", focusTrapHandler);
    report(telemetry?.OUTCOMES.opened);
  }

  /* Close the drawer, unlock the page, remove the trap, and return focus to
     whatever held it before the drawer opened. */
  function close(reason) {
    sidebar.classList.remove("mobile-nav-open");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", "Open navigation menu");
    document.body.style.overflowY = previousBodyOverflowY;

    /* Remove focus trap */
    if (focusTrapHandler) {
      document.removeEventListener("keydown", focusTrapHandler);
      focusTrapHandler = null;
    }

    /* Restore focus.
     *
     * `<body>` is not a focus holder worth returning to. It is what
     * `document.activeElement` reports when nothing is focused, which is the
     * usual case for someone who opened the drawer by tapping it: the saved
     * element is the body, `body.focus()` does nothing, and focus is left on
     * a nav link inside a drawer that has just been hidden. Falling back to
     * the toggle puts it somewhere the reader can see and use. */
    var restoreTo =
      savedFocus &&
      savedFocus !== document.body &&
      savedFocus.isConnected &&
      typeof savedFocus.focus === "function"
        ? savedFocus
        : btn;
    restoreTo.focus();
    report(telemetry?.OUTCOMES.closed, reason);
    report(
      telemetry?.OUTCOMES.focusRestored,
      restoreTo === btn ? telemetry?.REASONS.toggleFallback : telemetry?.REASONS.savedElement,
    );
    savedFocus = null;
  }

  /* Whether the drawer is currently open. */
  function isOpen() {
    return sidebar.classList.contains("mobile-nav-open");
  }

  /* ---- event listeners ---- */
  btn.addEventListener("click", () => {
    if (isOpen()) close(telemetry?.REASONS.toggle);
    else open();
  });

  backdrop.addEventListener("click", () => close(telemetry?.REASONS.backdrop));

  /* Close drawer when a nav link is clicked (same-page anchors, etc.) */
  var navLinks = nav.querySelectorAll("a");
  for (const navLink of navLinks) {
    navLink.addEventListener("click", () => {
      if (isOpen()) close(telemetry?.REASONS.navLink);
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isOpen()) close(telemetry?.REASONS.escape);
  });

  var mql = window.matchMedia("(min-width: 1024px)");

  /* Close the drawer once the viewport is wide enough for the full sidebar,
     so the page is never left scroll-locked behind an invisible drawer. */
  function onBreakpoint() {
    if (mql.matches && isOpen()) close(telemetry?.REASONS.breakpoint);
  }
  if (mql.addEventListener) mql.addEventListener("change", onBreakpoint);
  else mql.addListener(onBreakpoint); /* Safari <14 */

  report(telemetry?.OUTCOMES.initialized);
})();
