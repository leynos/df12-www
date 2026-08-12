/* Category filtering for the examples hub.
 *
 * The filter pills (`[data-example-filter]`, rendered by the
 * filter_buttons macro in templates/netsuke/examples_data.jinja) toggle
 * which example cards (`[data-example-card]`) are visible by matching
 * each card's `data-category`. Copy-to-clipboard behaviour for the
 * cards lives in copy-buttons.js.
 */
(() => {
  document.addEventListener("DOMContentLoaded", () => {
    initFilters();
  });

  /* Wire the example-card filter chips, returning early when the page has no
     chips or no cards. Each chip presses itself, unpresses its siblings, and
     shows the cards matching its filter. */
  function initFilters() {
    const buttons = [...document.querySelectorAll("[data-example-filter]")];
    const cards = [...document.querySelectorAll("[data-example-card]")];

    if (buttons.length === 0 || cards.length === 0) {
      return;
    }

    for (const button of buttons) {
      button.addEventListener("click", () => {
        const filter = button.getAttribute("data-example-filter");

        for (const other of buttons) {
          const active = other === button;
          other.classList.toggle("hm-chip--active", active);
          other.setAttribute("aria-pressed", String(active));
        }

        for (const card of cards) {
          const matches = filter === "all" || card.getAttribute("data-category") === filter;
          card.classList.toggle("hidden", !matches);
        }
      });
    }
  }
})();
