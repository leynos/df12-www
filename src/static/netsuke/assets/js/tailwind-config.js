/* tailwind-config.js — theme extensions for the Netsuke sub-site.
 *
 * Netsuke loads the Tailwind Play CDN at runtime rather than compiling an
 * entrypoint, so its theme cannot live in CSS the way the main site's and
 * mxd's do. The CDN reads `window.tailwind.config` when it initialises, which
 * is what this file sets; it must therefore be loaded before the CDN script,
 * and it is plain assignment rather than a module for that reason.
 *
 * This is configuration, not behaviour: the palette and family names here are
 * the source of the utilities the Netsuke templates use. See the "Styling"
 * section of AGENTS.md for why colour belongs in a theme rather than in
 * arbitrary values in the markup.
 */
window.tailwind = window.tailwind || {};

window.tailwind.config = {
  theme: {
    extend: {
      colors: {
        charcoal: {
          DEFAULT: "#2E2A25",
          mid: "#5C554D",
          light: "#8A8279",
        },
        indigo: {
          DEFAULT: "#2B4162",
          light: "#3A5A7C",
        },
        vermillion: {
          DEFAULT: "#C23B22",
          dim: "#9E3020",
        },
        boxwood: {
          DEFAULT: "#E8D5B5",
          light: "#F5EDE0",
          pale: "#FAF6F0",
        },
        stone: {
          DEFAULT: "#D1C7B8",
          light: "#E5DDD0",
        },
        matcha: "#4A7C59",
        amber: "#C48B2C",
      },
      fontFamily: {
        sans: ['"Source Sans 3"', "sans-serif"],
        serif: ['"Fraunces"', "serif"],
        mono: ['"JetBrains Mono"', "monospace"],
      },
      spacing: {
        128: "32rem",
      },
      boxShadow: {
        paper: "0 4px 6px -1px rgba(46, 42, 37, 0.1), 0 2px 4px -1px rgba(46, 42, 37, 0.06)",
        "paper-lg": "0 10px 15px -3px rgba(46, 42, 37, 0.1), 0 4px 6px -2px rgba(46, 42, 37, 0.05)",
        "paper-xl":
          "0 20px 25px -5px rgba(46, 42, 37, 0.1), 0 10px 10px -5px rgba(46, 42, 37, 0.04)",
      },
    },
  },
};
