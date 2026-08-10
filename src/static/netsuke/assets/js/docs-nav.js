/* Navigation for the mobile docs sub-menu dropdown.
 *
 * The floating docs bar (templates/netsuke/docs_nav.jinja) renders the
 * docs pages as a native <select> marked `data-docs-nav-select`, with
 * the current page pre-selected. This module navigates to the chosen
 * page's URL on change, skipping no-op selections of the current path.
 */
(function () {
  "use strict";

  function init() {
    var selects = document.querySelectorAll("[data-docs-nav-select]");
    selects.forEach(function (select) {
      select.addEventListener("change", function () {
        if (select.value && select.value !== window.location.pathname) {
          window.location.assign(select.value);
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
