/** @file Poster-first, user-controlled enhancement for Common Signal illustrations. */
(() => {
  const runtime = document.currentScript?.getAttribute("data-runtime");
  if (!runtime) return;
  // Creating the element allocates a renderer. Keep at most one pending or live.
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const contrast = matchMedia("(prefers-contrast: more), (forced-colors: active)");
  let stopActive: (() => void) | undefined;

  for (const figure of document.querySelectorAll<HTMLElement>("[data-wf-plate]")) {
    const scene = figure.querySelector<HTMLElement>(".wf-scene");
    const controls = figure.querySelector<HTMLElement>(".wf-controls");
    const play = controls?.querySelector<HTMLButtonElement>("[data-play]");
    const glow = controls?.querySelector<HTMLButtonElement>("[data-glow]");
    const status = controls?.querySelector<HTMLElement>("[role=status]");
    const plateId = figure.dataset.wfPlate;
    if (!scene || !controls || !play || !glow || !status || !plateId) continue;
    let element: HTMLElement | undefined;
    let reduceGlow = false;

    const stop = () => {
      if (stopActive === stop) stopActive = undefined;
      if (document.activeElement === glow) play.focus();
      element?.remove();
      element = undefined;
      play.textContent = "Play illustration";
      glow.hidden = true;
    };

    const preference = () => {
      if (motion.matches) stop();
      if (motion.matches && document.activeElement === play) status.focus();
      play.hidden = motion.matches;
      status.textContent = motion.matches ? "Still illustration · reduced motion" : "";
      updateGlow();
    };

    const updateGlow = () => {
      element?.toggleAttribute("low-glow", reduceGlow || contrast.matches);
      glow.setAttribute("aria-pressed", String(reduceGlow || contrast.matches));
      glow.hidden = !element || contrast.matches;
    };

    play.addEventListener("click", async () => {
      if (stopActive === stop) {
        stop();
        return;
      }
      stopActive?.();
      stopActive = stop;
      status.textContent = "";
      play.textContent = "Pause illustration";
      try {
        await import(runtime);
        if (stopActive !== stop || motion.matches || element) return;
        element = document.createElement("wireframe-plate");
        element.setAttribute("plate", plateId);
        element.setAttribute("aria-hidden", "true");
        element.addEventListener("plate-state", (event) => {
          if (event instanceof CustomEvent && event.detail === "fallback") {
            stop();
            status.textContent = "Playback unavailable. Showing the still illustration.";
          }
        });
        updateGlow();
        scene.append(element);
      } catch {
        if (stopActive === stop) {
          stop();
          status.textContent = "Playback unavailable. Showing the still illustration.";
        }
      }
    });
    glow.addEventListener("click", () => {
      reduceGlow = !reduceGlow;
      updateGlow();
    });
    motion.addEventListener("change", preference);
    contrast.addEventListener("change", updateGlow);
    window.addEventListener("pagehide", stop);
    preference();
    controls.hidden = false;
  }
})();
