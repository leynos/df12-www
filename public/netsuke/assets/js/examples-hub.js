(function () {
  document.addEventListener("DOMContentLoaded", () => {
    initFilters();
  });

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
          const matches =
            filter === "all" || card.getAttribute("data-category") === filter;
          card.classList.toggle("hidden", !matches);
        }
      });
    }
  }

})();
