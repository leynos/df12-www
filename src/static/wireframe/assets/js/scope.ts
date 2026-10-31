/**
 * @file The beam: redraws the hero's scope scene as an X-Y vector display.
 *
 * The scene is complete without this script. `_scope.svg.jinja` is labelled
 * SVG, generated at build time, and it is what a reader sees with scripting
 * off, with reduced motion requested, or with more contrast requested. This
 * script only adds a canvas over it and redraws the SVG's strokes the way a
 * calligraphic display draws them: one beam visiting each path in turn.
 *
 * Four habits of real vector hardware carry the effect:
 *
 * - **Phosphor persistence.** The canvas is never cleared. Each frame erases
 *   a fraction of what is already lit, so anything that moves leaves a
 *   decaying trail, and the page behind the canvas shows through it.
 * - **Additive glow.** Strokes are drawn with the `lighter` operator, so
 *   where lines cross, and where the beam dwells at a vertex, the light adds
 *   up and the junction burns brighter than either line.
 * - **Imperfect blanking.** Between strokes the beam is meant to be off. A
 *   faint flyback line from the end of one path to the start of the next
 *   betrays where it travelled.
 * - **Analogue drift.** Deflection wanders by a fraction of a pixel and
 *   intensity breathes, and every few seconds a deflection glitch throws a
 *   ghost of the whole picture sideways for a few frames.
 *
 * Pulses travel the lit route at a steady rate, and the bit stream marches
 * into the funnel. None of it implies a throughput: the cadence is the
 * picture's, not the protocol's.
 *
 * The SVG's strokes are read from `path[data-beam]` elements whose `d` holds
 * only `M` and `L` commands, which the generator guarantees. The animation
 * runs only while the scene is on screen and the page is visible.
 *
 * `parsePath`, `cumulative`, `pointAt`, and `nextGlitchAt` are pure and
 * exported for the Bun tests; `init` at the bottom wires the real page.
 */
(() => {
  "use strict";

  type Point = [number, number];

  interface Stroke {
    role: string;
    points: Point[];
    lengths: number[];
    dashed: boolean;
    pulse: boolean;
  }

  interface Look {
    token: string;
    core: number;
    halo: number;
    nodes: boolean;
  }

  // How each beam role is drawn: the colour token, the core's opacity, the
  // halo's opacity (zero for none), and whether its vertices glow.
  const LOOKS: Record<string, Look> = {
    grid: { token: "--color-structure", core: 0.9, halo: 0, nodes: false },
    faint: { token: "--color-rule", core: 0.9, halo: 0, nodes: false },
    bits: { token: "--color-cyan", core: 0.8, halo: 0.12, nodes: false },
    cyan: { token: "--color-cyan", core: 0.85, halo: 0.14, nodes: true },
    mint: { token: "--color-mint", core: 0.95, halo: 0.16, nodes: true },
    amber: { token: "--color-amber", core: 0.95, halo: 0.18, nodes: true },
    route: { token: "--color-amber", core: 0.7, halo: 0.22, nodes: false },
    magenta: { token: "--color-magenta", core: 1, halo: 0.25, nodes: true },
    dim: { token: "--color-tick", core: 0.9, halo: 0, nodes: false },
    return: { token: "--color-tick", core: 1, halo: 0.06, nodes: false },
  };

  // Phosphor decay per frame: the fraction of the lit image erased before
  // the next frame is drawn. Higher clears faster; lower burns in.
  const PERSISTENCE = 0.24;
  // Pulse speed along the lit route, in viewBox units per second.
  const PULSE_SPEED = 150;
  const PULSE_COUNT = 3;
  const GLITCH_MS = 150;

  /** Parse an SVG path of `M` and `L` commands into its points. */
  function parsePath(d: string): Point[] {
    const numbers = d.match(/-?\d+(?:\.\d+)?/g) || [];
    const points: Point[] = [];
    for (let i = 0; i + 1 < numbers.length; i += 2) {
      points.push([Number(numbers[i]), Number(numbers[i + 1])]);
    }
    return points;
  }

  /** Return the running length of a polyline at each of its points. */
  function cumulative(points: Point[]): number[] {
    const lengths = [0];
    for (let i = 1; i < points.length; i++) {
      const dx = points[i][0] - points[i - 1][0];
      const dy = points[i][1] - points[i - 1][1];
      lengths.push(lengths[i - 1] + Math.hypot(dx, dy));
    }
    return lengths;
  }

  /** Return the point `distance` along a polyline, clamped to its ends. */
  function pointAt(points: Point[], lengths: number[], distance: number): Point {
    const total = lengths[lengths.length - 1];
    const d = Math.max(0, Math.min(total, distance));
    for (let i = 1; i < points.length; i++) {
      if (d <= lengths[i]) {
        const span = lengths[i] - lengths[i - 1] || 1;
        const t = (d - lengths[i - 1]) / span;
        return [
          points[i - 1][0] + (points[i][0] - points[i - 1][0]) * t,
          points[i - 1][1] + (points[i][1] - points[i - 1][1]) * t,
        ];
      }
    }
    return points[points.length - 1];
  }

  /** Schedule the next deflection glitch 6-10 seconds after `now` (ms). */
  function nextGlitchAt(now: number, random: () => number): number {
    return now + 6000 + random() * 4000;
  }

  function readStrokes(svg: SVGSVGElement): Stroke[] {
    const strokes: Stroke[] = [];
    for (const path of svg.querySelectorAll<SVGPathElement>("path[data-beam]")) {
      const points = parsePath(path.getAttribute("d") || "");
      if (points.length < 2) {
        continue;
      }
      strokes.push({
        role: path.dataset.beam || "faint",
        points: points,
        lengths: cumulative(points),
        dashed: path.dataset.dashed === "true",
        pulse: path.dataset.pulse === "true",
      });
    }
    return strokes;
  }

  function enhance(root: HTMLElement): void {
    const svg = root.querySelector<SVGSVGElement>("svg");
    const canvas = root.querySelector<HTMLCanvasElement>("canvas");
    const ctx = canvas ? canvas.getContext("2d") : null;
    if (!svg || !canvas || !ctx) {
      return;
    }
    const view = svg.viewBox.baseVal;
    const strokes = readStrokes(svg);
    const styles = getComputedStyle(document.documentElement);
    const colours: Record<string, string> = {};
    for (const role of Object.keys(LOOKS)) {
      colours[role] = styles.getPropertyValue(LOOKS[role].token).trim() || "#7cffb3";
    }
    const decay = `rgba(0,0,0,${PERSISTENCE})`;

    const g = ctx;
    const cvs = canvas;
    let scale = 1;
    let dpr = 1;
    let frame = 0;
    let running = false;
    let glitchAt = nextGlitchAt(performance.now(), Math.random);

    function resize(): void {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      const box = svg ? svg.getBoundingClientRect() : cvs.getBoundingClientRect();
      cvs.width = Math.max(1, Math.round(box.width * dpr));
      cvs.height = Math.max(1, Math.round(box.height * dpr));
      scale = cvs.width / view.width;
    }

    function trace(points: Point[], ox: number, oy: number): void {
      g.beginPath();
      g.moveTo(points[0][0] * scale + ox, points[0][1] * scale + oy);
      for (let i = 1; i < points.length; i++) {
        g.lineTo(points[i][0] * scale + ox, points[i][1] * scale + oy);
      }
    }

    function drawStroke(s: Stroke, ox: number, oy: number, gain: number, t: number): void {
      const look = LOOKS[s.role] || LOOKS.faint;
      g.strokeStyle = colours[s.role];
      if (s.dashed) {
        g.setLineDash([4 * scale, 4 * scale]);
      } else if (s.role === "bits") {
        g.setLineDash([2 * scale, 7 * scale]);
        g.lineDashOffset = -t * 0.05 * scale;
      } else {
        g.setLineDash([]);
      }
      trace(s.points, ox, oy);
      if (look.halo > 0) {
        g.globalAlpha = look.halo * gain;
        g.lineWidth = 6 * dpr;
        g.stroke();
      }
      g.globalAlpha = look.core * gain;
      g.lineWidth = 1.25 * dpr;
      g.stroke();
      g.lineDashOffset = 0;

      if (look.nodes) {
        // The beam dwells at each vertex, so each corner burns brighter.
        g.fillStyle = colours[s.role];
        for (const p of s.points) {
          g.globalAlpha = 0.18 * gain;
          g.beginPath();
          g.arc(p[0] * scale + ox, p[1] * scale + oy, 4 * dpr, 0, Math.PI * 2);
          g.fill();
          g.globalAlpha = 0.85 * gain;
          g.beginPath();
          g.arc(p[0] * scale + ox, p[1] * scale + oy, 1.3 * dpr, 0, Math.PI * 2);
          g.fill();
        }
      }
    }

    function drawPulses(s: Stroke, ox: number, oy: number, gain: number, t: number): void {
      const total = s.lengths[s.lengths.length - 1];
      g.fillStyle = colours.amber;
      for (let k = 0; k < PULSE_COUNT; k++) {
        const head = ((t / 1000) * PULSE_SPEED + (k * total) / PULSE_COUNT) % total;
        const p = pointAt(s.points, s.lengths, head);
        g.globalAlpha = 0.22 * gain;
        g.beginPath();
        g.arc(p[0] * scale + ox, p[1] * scale + oy, 7 * dpr, 0, Math.PI * 2);
        g.fill();
        g.globalAlpha = gain;
        g.beginPath();
        g.arc(p[0] * scale + ox, p[1] * scale + oy, 2 * dpr, 0, Math.PI * 2);
        g.fill();
      }
    }

    function paint(t: number, ox: number, oy: number, gain: number): void {
      let last: Point | null = null;
      for (const s of strokes) {
        if (last && s.role !== "grid") {
          // Imperfect blanking: a whisper of the beam's travel between paths.
          g.setLineDash([]);
          g.strokeStyle = colours.mint;
          g.globalAlpha = (0.03 + Math.random() * 0.04) * gain;
          g.lineWidth = 0.8 * dpr;
          g.beginPath();
          g.moveTo(last[0] * scale + ox, last[1] * scale + oy);
          g.lineTo(s.points[0][0] * scale + ox, s.points[0][1] * scale + oy);
          g.stroke();
        }
        drawStroke(s, ox, oy, gain, t);
        if (s.pulse) {
          drawPulses(s, ox, oy, gain, t);
        }
        if (s.role !== "grid") {
          last = s.points[s.points.length - 1];
        }
      }
    }

    function tick(now: number): void {
      if (!running) {
        return;
      }
      g.globalCompositeOperation = "destination-out";
      g.globalAlpha = 1;
      g.fillStyle = decay;
      g.fillRect(0, 0, cvs.width, cvs.height);
      g.globalCompositeOperation = "lighter";

      const s = now / 1000;
      let ox = (0.45 * Math.sin(s * 0.37) + 0.2 * Math.sin(s * 1.9)) * dpr;
      const oy = (0.35 * Math.sin(s * 0.53 + 1.3) + 0.15 * Math.sin(s * 2.7)) * dpr;
      const gain = 0.9 + 0.06 * Math.sin(s * 5.1) + Math.random() * 0.05;

      if (now >= glitchAt) {
        if (now < glitchAt + GLITCH_MS) {
          const throwX = (6 + Math.random() * 10) * dpr * (Math.random() < 0.5 ? -1 : 1);
          paint(now, ox + throwX, oy, gain * 0.35);
          ox += (Math.random() - 0.5) * 3 * dpr;
        } else {
          glitchAt = nextGlitchAt(now, Math.random);
        }
      }
      paint(now, ox, oy, gain);
      frame = requestAnimationFrame(tick);
    }

    function start(): void {
      if (!running) {
        running = true;
        frame = requestAnimationFrame(tick);
      }
    }

    function stop(): void {
      running = false;
      cancelAnimationFrame(frame);
    }

    resize();
    root.classList.add("is-lit");
    new ResizeObserver(resize).observe(root);

    let visible = false;
    function update(): void {
      if (visible && document.visibilityState === "visible") {
        start();
      } else {
        stop();
      }
    }
    new IntersectionObserver((entries) => {
      visible = entries.some((e) => e.isIntersecting);
      update();
    }).observe(root);
    document.addEventListener("visibilitychange", update);

    const quiet = window.matchMedia("(prefers-reduced-motion: reduce), (prefers-contrast: more)");
    quiet.addEventListener("change", () => {
      if (quiet.matches) {
        stop();
        root.classList.remove("is-lit");
      }
    });
  }

  function init(): void {
    const quiet = window.matchMedia("(prefers-reduced-motion: reduce), (prefers-contrast: more)");
    if (quiet.matches || typeof IntersectionObserver === "undefined") {
      return;
    }
    for (const root of document.querySelectorAll<HTMLElement>("[data-wf-scope]")) {
      enhance(root);
    }
  }

  if (typeof document !== "undefined" && typeof window !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      parsePath: parsePath,
      cumulative: cumulative,
      pointAt: pointAt,
      nextGlitchAt: nextGlitchAt,
      PERSISTENCE: PERSISTENCE,
    };
  }
})();
