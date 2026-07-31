(function () {
  document.addEventListener("DOMContentLoaded", () => {
    initFilters();
    initCopyButtons();
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

  function initCopyButtons() {
    for (const button of document.querySelectorAll("[data-copy-snippet]")) {
      button.addEventListener("click", async () => {
        const card = button.closest("[data-example-card]");
        const snippet = card ? card.getAttribute("data-snippet") : null;

        if (!snippet || !navigator.clipboard) {
          flash(button, "Copy unavailable", "text-vermillion");
          return;
        }

        try {
          await navigator.clipboard.writeText(snippet.trim() + "\n");
          flash(button, "Copied", "text-matcha");
        } catch {
          flash(button, "Copy failed", "text-vermillion");
        }
      });
    }
  }

  function flash(button, message, colourClass) {
    const originalTitle = button.getAttribute("title");
    const originalAriaLabel = button.getAttribute("aria-label");
    button.setAttribute("title", message);
    button.setAttribute("aria-label", message);
    button.classList.add(colourClass);
    window.setTimeout(() => {
      button.setAttribute("title", originalTitle);
      if (originalAriaLabel === null) {
        button.removeAttribute("aria-label");
      } else {
        button.setAttribute("aria-label", originalAriaLabel);
      }
      button.classList.remove(colourClass);
    }, 1500);
  }
})();
