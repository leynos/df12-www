/* Scroll-spy for the docs sidebar.
 *
 * Docs pages list their in-page sub-headings in the desktop sidebar as
 * `a.sidebar-link--sub` anchors. As the reader scrolls, mark the link
 * whose section contains the current reading position with the same
 * `active` class the stylesheet already uses (red left border). Pages
 * without sub-links are left alone.
 */
(() => {
  "use strict";

  var OFFSET = 96; // sticky navbar (4rem) plus breathing room

  /* Wire the sidebar sub-links to the headings they point at, returning early
     when none of them target a heading on this page. Sub-links may carry a
     bare fragment or a full same-page URL, so both are resolved. */
  function init() {
    var links = Array.prototype.slice.call(
      document.querySelectorAll('#sidebar a.sidebar-link--sub[href*="#"]'),
    );
    var targets = links
      .map((link) => {
        // Sub-links may use bare fragments or absolute same-page
        // URLs such as /netsuke/docs/getting-started/#installation.
        var url = new URL(link.getAttribute("href"), window.location.href);
        if (url.pathname !== window.location.pathname || !url.hash) {
          return null;
        }
        var el = document.getElementById(decodeURIComponent(url.hash.slice(1)));
        return el ? { link: link, el: el } : null;
      })
      .filter(Boolean);
    if (!targets.length) {
      return;
    }

    var current = null;

    /* Move the active marker to `entry`, or clear it when passed null. Does
       nothing when the entry is already current, so scrolling within one
       section touches no attributes. */
    function setActive(entry) {
      if (entry === current) {
        return;
      }
      if (current) {
        current.link.classList.remove("active");
        current.link.removeAttribute("aria-current");
      }
      if (entry) {
        entry.link.classList.add("active");
        entry.link.setAttribute("aria-current", "location");
      }
      current = entry;
    }

    /* Recompute which heading is being read and mark its link. Reads layout,
       so it is called from an animation frame rather than directly. */
    function update() {
      var atBottom =
        window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      var tops = targets.map((target) => target.el.getBoundingClientRect().top);
      var index = pickActiveIndex(tops, OFFSET, atBottom);
      setActive(index >= 0 ? targets[index] : null);
    }

    var ticking = false;
    /* Coalesce a burst of scroll or resize events into one layout read per
       animation frame. */
    function onScroll() {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(() => {
          ticking = false;
          update();
        });
      }
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    update();
  }

  // Decide which section is being read: the last one whose heading has
  // passed `offset`, or the final section once the page is scrolled to
  // the bottom (so short closing sections can still activate). Returns
  // an index into `tops`, or -1 when nothing has been reached.
  function pickActiveIndex(tops, offset, atBottom) {
    if (atBottom && tops.length > 0) {
      return tops.length - 1;
    }
    var active = -1;
    for (let i = 0; i < tops.length; i += 1) {
      if (tops[i] <= offset) {
        active = i;
      }
    }
    return active;
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { pickActiveIndex: pickActiveIndex };
  }
})();
