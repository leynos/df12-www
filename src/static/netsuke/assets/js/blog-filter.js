/**
 * Client-side category filter for the Netsuke blog index.
 *
 * Reads `data-category` from each `<button>` filter control and each
 * `<article>` in the feed. Clicking a button shows only articles whose
 * `data-category` matches (or all articles when "all" is selected).
 * `aria-pressed` is kept in sync with the active filter.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var buttons = Array.from(
      document.querySelectorAll("button[data-category]"),
    );
    var articles = Array.from(document.querySelectorAll("article[data-category]"));

    if (buttons.length === 0 || articles.length === 0) {
      return;
    }

    function applyFilter(category) {
      buttons.forEach(function (btn) {
        btn.setAttribute(
          "aria-pressed",
          btn.dataset.category === category ? "true" : "false",
        );
      });

      articles.forEach(function (article) {
        var visible =
          category === "all" || article.dataset.category === category;
        article.hidden = !visible;
      });
    }

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        applyFilter(btn.dataset.category);
      });
    });
  });
})();
