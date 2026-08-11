/* Navigation for the mobile docs sub-menu dropdown.
 *
 * The floating docs bar (templates/netsuke/docs_nav.jinja) renders the
 * docs pages as a native <select> marked `data-docs-nav-select`, with
 * the current page pre-selected. This module navigates to the chosen
 * page's URL on change, skipping no-op selections of the current path.
 */
(() => {
  "use strict";

  /* Wire every docs `<select>` on the page to navigate on change, skipping a
     selection that names the path already open. */
  function init() {
    var selects = document.querySelectorAll("[data-docs-nav-select]");
    selects.forEach((select) => {
      select.addEventListener("change", () => {
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
