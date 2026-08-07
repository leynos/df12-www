/* mobile-nav.js — hamburger toggle for sidebar navigation (<1024px) */
(function () {
  "use strict";

  var sidebar = document.getElementById("sidebar");
  if (!sidebar) return;

  var nav = sidebar.querySelector("nav");
  if (!nav) return;

  var header = sidebar.querySelector("[data-mobile-nav-header]");
  if (!header) return;

  /* Signal that JS is available so CSS can safely hide the nav */
  document.documentElement.classList.add("has-mobile-nav");

  /* ---- hamburger button ---- */
  var btn = document.createElement("button");
  btn.id = "mobile-nav-toggle";
  btn.setAttribute("aria-expanded", "false");
  btn.setAttribute("aria-controls", nav.id || "sidebar-nav");
  btn.setAttribute("aria-label", "Open navigation menu");
  if (!nav.id) nav.id = "sidebar-nav";
  btn.innerHTML = '<i class="fa-solid fa-bars"></i>';
  header.style.position = "relative";
  header.appendChild(btn);

  /* ---- backdrop ---- */
  var backdrop = document.createElement("div");
  backdrop.id = "mobile-nav-backdrop";
  sidebar.parentNode.insertBefore(backdrop, sidebar.nextSibling);

  /* ---- measure header height for fixed-nav offset ---- */
  function setHeaderHeight() {
    var h = header.getBoundingClientRect().height;
    sidebar.style.setProperty("--mobile-header-height", h + "px");
  }

  var previousBodyOverflow = "";
  var savedFocus = null;
  var focusTrapHandler = null;

  /* ---- focus-trap helper ---- */
  function getFocusableElements() {
    return nav.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), ' +
      'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
  }

  /* ---- open / close helpers ---- */
  function open() {
    sidebar.classList.add("mobile-nav-open");
    btn.setAttribute("aria-expanded", "true");
    btn.setAttribute("aria-label", "Close navigation menu");
    btn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    setHeaderHeight();

    /* Save focus and move it into the nav */
    savedFocus = document.activeElement;
    var focusables = getFocusableElements();
    if (focusables.length) focusables[0].focus();
    else nav.setAttribute("tabindex", "-1"), nav.focus();

    /* Install focus trap */
    focusTrapHandler = function (e) {
      if (e.key !== "Tab") return;
      var els = getFocusableElements();
      if (!els.length) return;
      var first = els[0];
      var last = els[els.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first || document.activeElement === btn) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          btn.focus();
        }
      }
    };
    document.addEventListener("keydown", focusTrapHandler);
  }

  function close() {
    sidebar.classList.remove("mobile-nav-open");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", "Open navigation menu");
    btn.innerHTML = '<i class="fa-solid fa-bars"></i>';
    document.body.style.overflow = previousBodyOverflow;

    /* Remove focus trap */
    if (focusTrapHandler) {
      document.removeEventListener("keydown", focusTrapHandler);
      focusTrapHandler = null;
    }

    /* Restore focus */
    if (savedFocus && typeof savedFocus.focus === "function") {
      savedFocus.focus();
    } else {
      btn.focus();
    }
    savedFocus = null;
  }

  function isOpen() {
    return sidebar.classList.contains("mobile-nav-open");
  }

  /* ---- event listeners ---- */
  btn.addEventListener("click", function () {
    if (isOpen()) close();
    else open();
  });

  backdrop.addEventListener("click", close);

  /* Close drawer when a nav link is clicked (same-page anchors, etc.) */
  var navLinks = nav.querySelectorAll("a");
  for (var i = 0; i < navLinks.length; i++) {
    navLinks[i].addEventListener("click", function () {
      if (isOpen()) close();
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && isOpen()) close();
  });

  /* close menu if viewport crosses the 1024px breakpoint */
  var mql = window.matchMedia("(min-width: 1024px)");
  function onBreakpoint() {
    if (mql.matches && isOpen()) close();
  }
  if (mql.addEventListener) mql.addEventListener("change", onBreakpoint);
  else mql.addListener(onBreakpoint); /* Safari <14 */
})();
