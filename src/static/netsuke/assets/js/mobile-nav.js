/* mobile-nav.js — the Netsuke navbar's narrow-viewport menu.
 *
 * A plain script module in the shape described in section 6 of the
 * developers' guide: an IIFE loaded with `<script defer>` that finds its
 * markup by id, returns early when that markup is absent, and enhances what
 * the server already rendered. `templates/netsuke/` emits the toggle button
 * and the menu pane; this file supplies the behaviour and nothing else, so a
 * page that fails to load it still renders a usable navbar.
 *
 * The menu is a dropdown rather than a modal: it does not dim the page or
 * lock scrolling, and a click outside it closes it. Focus is still cycled
 * between the toggle and the menu's items while it is open, because a menu
 * that has taken focus should give it back predictably.
 *
 * The toggle starts hidden and is revealed here, so a viewport wide enough
 * for the full navbar never shows a control that does nothing.
 */
(() => {
  "use strict";

  var SELECTORS = {
    toggle: "#navbar-mobile-toggle",
    menu: "#navbar-mobile-menu",
    navbar: "#navbar",
  };

  var CLASSES = { open: "is-open", hidden: "hidden" };

  /* Find the navbar, toggle, and menu pane, returning early when any is
     absent, then reveal the toggle and wire the menu's behaviour. */
  function init() {
    var toggle = document.querySelector(SELECTORS.toggle);
    var menu = document.querySelector(SELECTORS.menu);
    var navbar = document.querySelector(SELECTORS.navbar);
    if (!toggle || !menu || !navbar) return;

    toggle.classList.remove(CLASSES.hidden);

    var openIcon = toggle.querySelector(".hm-hamburger__open");
    var closeIcon = toggle.querySelector(".hm-hamburger__close");

    /* Whether the menu pane is currently expanded. */
    function isOpen() {
      return menu.classList.contains(CLASSES.open);
    }

    /* The menu's tab stops, in document order. */
    function getFocusableMenuItems() {
      return menu.querySelectorAll('a[href], button, [tabindex]:not([tabindex="-1"])');
    }

    /* Whether the toggle is on screen. Focus is only restored to it when it
       is, since a breakpoint change can hide it while the menu is open. */
    function isToggleVisible() {
      var style = window.getComputedStyle(toggle);
      var rect = toggle.getBoundingClientRect();

      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        rect.width > 0 &&
        rect.height > 0
      );
    }

    /* Expand the menu and move focus to its first item. */
    function openMenu() {
      menu.classList.remove(CLASSES.hidden);
      // Force a reflow so the transition triggers from max-height:0
      void menu.offsetHeight;
      menu.classList.add(CLASSES.open);
      toggle.setAttribute("aria-expanded", "true");
      toggle.setAttribute("aria-label", "Close menu");
      if (openIcon) openIcon.style.display = "none";
      if (closeIcon) closeIcon.style.display = "";
      var first = menu.querySelector("a, button");
      if (first) {
        first.focus();
      } else {
        /* An empty menu still has to take focus, or the Tab handling below
           has no anchor to cycle from and focus stays outside a pane the
           user has just opened. */
        menu.setAttribute("tabindex", "-1");
        menu.focus();
      }
    }

    /* Collapse the menu. `restoreFocus` returns focus to the toggle when the
       toggle is still on screen; `hideImmediately` skips the transition and
       hides the pane at once, which is what the initial no-JS collapse and a
       breakpoint change both want. */
    function closeMenu(options) {
      var opts = options || {};
      var restoreFocus = !!opts.restoreFocus;
      var hideImmediately = !!opts.hideImmediately;

      menu.classList.remove(CLASSES.open);
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open menu");
      if (openIcon) openIcon.style.display = "";
      if (closeIcon) closeIcon.style.display = "none";
      if (restoreFocus && isToggleVisible()) toggle.focus();
      if (hideImmediately) {
        menu.classList.add(CLASSES.hidden);
        return;
      }
      menu.addEventListener("transitionend", function hide(e) {
        if (e.propertyName !== "max-height") return;
        if (!isOpen()) menu.classList.add(CLASSES.hidden);
        menu.removeEventListener("transitionend", hide);
      });
    }

    /* Whether a link targets a fragment of the page already on screen, which
       navigates nothing and so needs the menu closed by hand. */
    function isSamePageAnchor(link) {
      if (!link?.hash) return false;

      return (
        link.origin === window.location.origin &&
        link.pathname === window.location.pathname &&
        link.search === window.location.search
      );
    }

    // Collapse any markup that renders the menu open as a no-JS fallback.
    closeMenu({ hideImmediately: true });

    // Toggle on click
    toggle.addEventListener("click", () => {
      if (isOpen()) closeMenu({ restoreFocus: true });
      else openMenu();
    });

    // Close on Escape
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && isOpen()) {
        closeMenu({ restoreFocus: true });
      }
    });

    // Close on click outside both the navbar shell and the mobile menu pane.
    document.addEventListener("click", (e) => {
      if (isOpen() && !navbar.contains(e.target) && !menu.contains(e.target)) {
        closeMenu();
      }
    });

    // Close after selecting an in-page link from the mobile menu.
    menu.addEventListener("click", (e) => {
      var link = e.target.closest("a[href]");
      if (!link || !menu.contains(link) || !isOpen()) return;
      if (isSamePageAnchor(link)) closeMenu();
    });

    // Close when viewport crosses md breakpoint
    var mql = window.matchMedia("(min-width: 768px)");
    /* Collapse the menu once the viewport is wide enough for the full navbar,
       so a hidden toggle cannot leave an open menu behind it. */
    function onBreakpoint() {
      if (mql.matches && isOpen()) closeMenu({ hideImmediately: true });
    }
    if (mql.addEventListener) mql.addEventListener("change", onBreakpoint);
    else mql.addListener(onBreakpoint);

    // Focus trap: Tab cycles through the toggle and menu items in both
    // directions while the menu is open.
    menu.addEventListener("keydown", (e) => {
      if (e.key !== "Tab" || !isOpen()) return;
      var focusable = getFocusableMenuItems();
      if (!focusable.length) {
        /* Nothing to cycle through, so hand focus back to the toggle rather
           than letting Tab walk out of a menu that is still open. */
        e.preventDefault();
        toggle.focus();
        return;
      }
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });

    // When focus leaves toggle while menu is open, wrap to the matching edge.
    toggle.addEventListener("keydown", (e) => {
      if (e.key !== "Tab" || !isOpen()) return;
      var focusable = getFocusableMenuItems();
      if (focusable.length) {
        e.preventDefault();
        if (e.shiftKey) focusable[focusable.length - 1].focus();
        else focusable[0].focus();
      } else {
        /* Empty menu: the pane itself took focus when it opened, so send
           Tab there instead of out of the open menu entirely. */
        e.preventDefault();
        menu.focus();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
