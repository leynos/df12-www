/**
 * Client-side category filter for the Netsuke blog index.
 *
 * Reads `data-category` from each `<button>` filter control and each
 * `<article>` in the feed. Clicking a button shows only articles whose
 * `data-category` matches (or all articles when "all" is selected).
 * `aria-pressed` is kept in sync with the active filter.
 */
(() => {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    var buttons = Array.from(document.querySelectorAll("button[data-category]"));
    var articles = Array.from(document.querySelectorAll("article[data-category]"));

    if (buttons.length === 0 || articles.length === 0) {
      return;
    }

    function applyFilter(category) {
      buttons.forEach((btn) => {
        btn.setAttribute("aria-pressed", btn.dataset.category === category ? "true" : "false");
      });

      articles.forEach((article) => {
        var visible = category === "all" || article.dataset.category === category;
        article.hidden = !visible;
      });
    }

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        applyFilter(btn.dataset.category);
      });
    });
  });
})();
