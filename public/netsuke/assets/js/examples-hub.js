(function () {
  const TOAST_LINGER_MS = 2000;
  // Matches the .hm-toast fade-out duration in himotoshi.css.
  const TOAST_FADE_MS = 220;

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
    const buttons = [...document.querySelectorAll("[data-copy-snippet]")];

    if (buttons.length === 0) {
      return;
    }

    const toast = createToast();

    for (const button of buttons) {
      button.addEventListener("click", async () => {
        const card = button.closest("[data-example-card]");
        const snippet = card ? card.getAttribute("data-snippet") : null;

        if (!snippet || !navigator.clipboard) {
          flash(button, "Copy unavailable", "text-vermillion");
          toast.show("Copy unavailable", true);
          return;
        }

        try {
          await navigator.clipboard.writeText(snippet.trim() + "\n");
          flash(button, "Copied", "text-matcha");
          toast.show("Copied to clipboard", false);
        } catch {
          flash(button, "Copy failed", "text-vermillion");
          toast.show("Copy failed", true);
        }
      });
    }
  }

  // A single reusable ghost notification. It is created once and left in the
  // DOM so assistive tech treats it as a live region; repeat calls to show()
  // restart the timer rather than stacking further toasts.
  function createToast() {
    const element = document.createElement("div");
    element.className = "hm-toast";
    element.setAttribute("role", "status");
    element.setAttribute("aria-live", "polite");
    document.body.append(element);

    let lingerTimer = 0;
    let clearTimer = 0;

    function show(message, isError) {
      window.clearTimeout(lingerTimer);
      window.clearTimeout(clearTimer);

      if (element.textContent !== message) {
        element.textContent = message;
      }
      element.classList.toggle("hm-toast--error", isError);
      element.classList.add("hm-toast--visible");

      lingerTimer = window.setTimeout(() => {
        element.classList.remove("hm-toast--visible");
        // Wait for the fade to finish before emptying the live region, so the
        // text does not vanish mid-transition.
        clearTimer = window.setTimeout(() => {
          element.textContent = "";
        }, TOAST_FADE_MS);
      }, TOAST_LINGER_MS);
    }

    return { show };
  }

  function flash(button, message, colourClass) {
    const originalTitle = button.getAttribute("title");
    button.setAttribute("title", message);
    button.classList.add(colourClass);
    window.setTimeout(() => {
      button.setAttribute("title", originalTitle);
      button.classList.remove(colourClass);
    }, 1500);
  }
})();
