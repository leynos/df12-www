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
        "paper-xl": "0 20px 25px -5px rgba(46, 42, 37, 0.1), 0 10px 10px -5px rgba(46, 42, 37, 0.04)",
      },
    },
  },
};
