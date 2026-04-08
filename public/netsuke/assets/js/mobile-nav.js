(function () {
  "use strict";

  var SELECTORS = {
    toggle: "#navbar-mobile-toggle",
    menu: "#navbar-mobile-menu",
    navbar: "#navbar"
  };

  var CLASSES = { open: "is-open", hidden: "hidden" };

  function init() {
    var toggle = document.querySelector(SELECTORS.toggle);
    var menu = document.querySelector(SELECTORS.menu);
    var navbar = document.querySelector(SELECTORS.navbar);
    if (!toggle || !menu || !navbar) return;

    toggle.classList.remove(CLASSES.hidden);

    var openIcon = toggle.querySelector(".hm-hamburger__open");
    var closeIcon = toggle.querySelector(".hm-hamburger__close");

    function isOpen() {
      return menu.classList.contains(CLASSES.open);
    }

    function getFocusableMenuItems() {
      return menu.querySelectorAll(
        'a[href], button, [tabindex]:not([tabindex="-1"])'
      );
    }

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
      if (first) first.focus();
    }

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
      menu.addEventListener(
        "transitionend",
        function hide(e) {
          if (e.propertyName !== "max-height") return;
          if (!isOpen()) menu.classList.add(CLASSES.hidden);
          menu.removeEventListener("transitionend", hide);
        }
      );
    }

    function isSamePageAnchor(link) {
      if (!link || !link.hash) return false;

      return (
        link.origin === window.location.origin &&
        link.pathname === window.location.pathname &&
        link.search === window.location.search
      );
    }

    // Collapse any markup that renders the menu open as a no-JS fallback.
    closeMenu({ hideImmediately: true });

    // Toggle on click
    toggle.addEventListener("click", function () {
      if (isOpen()) closeMenu({ restoreFocus: true });
      else openMenu();
    });

    // Close on Escape
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && isOpen()) {
        closeMenu({ restoreFocus: true });
      }
    });

    // Close on click outside both the navbar shell and the mobile menu pane.
    document.addEventListener("click", function (e) {
      if (isOpen() && !navbar.contains(e.target) && !menu.contains(e.target)) {
        closeMenu();
      }
    });

    // Close after selecting an in-page link from the mobile menu.
    menu.addEventListener("click", function (e) {
      var link = e.target.closest('a[href]');
      if (!link || !menu.contains(link) || !isOpen()) return;
      if (isSamePageAnchor(link)) closeMenu();
    });

    // Close when viewport crosses md breakpoint
    var mql = window.matchMedia("(min-width: 768px)");
    function onBreakpoint() {
      if (mql.matches && isOpen()) closeMenu({ hideImmediately: true });
    }
    if (mql.addEventListener) mql.addEventListener("change", onBreakpoint);
    else mql.addListener(onBreakpoint);

    // Focus trap: Tab cycles through the toggle and menu items in both
    // directions while the menu is open.
    menu.addEventListener("keydown", function (e) {
      if (e.key !== "Tab" || !isOpen()) return;
      var focusable = getFocusableMenuItems();
      if (!focusable.length) return;
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
    toggle.addEventListener("keydown", function (e) {
      if (e.key !== "Tab" || !isOpen()) return;
      var focusable = getFocusableMenuItems();
      if (focusable.length) {
        e.preventDefault();
        if (e.shiftKey) focusable[focusable.length - 1].focus();
        else focusable[0].focus();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
