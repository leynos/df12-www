// Stilyagi home page: split the typewriter annotation into one span per
// character so the line can be typed onto the paper on load.  The annotation
// already renders in its finished state, so with scripting disabled — or under
// prefers-reduced-motion — the page is left exactly as the server sent it.

(() => {
  "use strict";

  // The line finishes within TOTAL_MS of the first strike; each character
  // takes LETTER_MS to fade in and shed its bold weight, so the stagger is
  // whatever is left over, divided between the gaps.
  const TOTAL_MS = 750;
  const LETTER_MS = 260;

  const onReady = (fn: () => void): void => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  };

  /**
   * Replace a text node with one indexed span per character.
   *
   * The index drives the stagger in CSS.  Spaces get a span of their own so
   * the rhythm matches the visible line rather than running the words
   * together, and inline layout is unaffected because opacity does not change
   * a character's advance width.
   */
  function splitTextNode(node: Text, firstIndex: number): number {
    const fragment = document.createDocumentFragment();
    let index = firstIndex;
    for (const character of node.textContent ?? "") {
      const letter = document.createElement("span");
      letter.className = "typed-letter";
      letter.style.setProperty("--typed-index", String(index));
      letter.textContent = character;
      fragment.append(letter);
      index += 1;
    }
    node.replaceWith(fragment);
    return index;
  }

  /** Split every text node beneath `root`, leaving nested markup in place. */
  function splitDescendantText(root: Node, firstIndex: number): number {
    let index = firstIndex;
    for (const node of [...root.childNodes]) {
      if (node.nodeType === Node.TEXT_NODE) {
        index = splitTextNode(node as Text, index);
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        index = splitDescendantText(node, index);
      }
    }
    return index;
  }

  /**
   * Prepare `element` for the typing animation.
   *
   * The original text is kept as a visually hidden label and the split copy is
   * hidden from assistive technology, so the reading experience is unchanged
   * however far through the animation a screen reader arrives.
   */
  function prepareTypewriter(element: HTMLElement): void {
    const text = element.textContent;
    // Splitting the line into one text run per character shifts a glyph or two
    // off their kerned positions, so the served markup is put back once the
    // last character has settled and the rendered result is identical again.
    const original = [...element.childNodes].map((node) => node.cloneNode(true));
    const typed = document.createElement("span");
    typed.className = "typed-line";
    typed.setAttribute("aria-hidden", "true");
    typed.append(...element.childNodes);

    const label = document.createElement("span");
    label.className = "sr-only";
    label.textContent = text;

    element.append(label, typed);

    const count = splitDescendantText(typed, 0);
    const letters = typed.querySelectorAll<HTMLElement>(".typed-letter");
    if (letters.length === 0) {
      element.replaceChildren(...original);
      return;
    }

    const stagger = count > 1 ? (TOTAL_MS - LETTER_MS) / (count - 1) : 0;
    element.style.setProperty("--typed-duration", `${LETTER_MS}ms`);
    element.style.setProperty("--typed-stagger", `${stagger}ms`);
    element.classList.add("is-typing");

    // The last character starts last and so finishes last.
    letters[letters.length - 1].addEventListener(
      "animationend",
      () => {
        element.classList.remove("is-typing");
        element.style.removeProperty("--typed-duration");
        element.style.removeProperty("--typed-stagger");
        element.replaceChildren(...original);
      },
      { once: true },
    );
  }

  onReady(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    for (const element of document.querySelectorAll<HTMLElement>(".poster-annotation")) {
      prepareTypewriter(element);
    }
  });
})();
