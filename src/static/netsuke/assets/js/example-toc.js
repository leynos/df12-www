(function () {
  const HEADER_OFFSET = 120;

  document.addEventListener("DOMContentLoaded", () => {
    const toc = document.querySelector("[data-page-toc]");

    if (!toc) {
      return;
    }

    const links = [...toc.querySelectorAll('a[href^="#"]')];
    const targets = links
      .map((link) => {
        const id = link.getAttribute("href").slice(1);
        const section = document.getElementById(id);
        return section ? { link, section } : null;
      })
      .filter(Boolean);

    if (targets.length === 0) {
      return;
    }

    let ticking = false;

    function activate(current) {
      for (const { link } of targets) {
        link.classList.toggle("is-active", link === current);
      }
    }

    function update() {
      ticking = false;
      const threshold = HEADER_OFFSET;
      let current = targets[0];

      for (const target of targets) {
        if (target.section.getBoundingClientRect().top <= threshold) {
          current = target;
        }
      }

      const scrollBottom = window.innerHeight + window.scrollY;
      const pageHeight = document.documentElement.scrollHeight;
      if (pageHeight - scrollBottom < 2) {
        current = targets[targets.length - 1];
      }

      activate(current.link);
    }

    function requestUpdate() {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(update);
      }
    }

    window.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate, { passive: true });
    update();
  });
})();
