/**
 * doc-inline-code.js — a Tailwind plugin for inline code in documentation prose.
 *
 * Registered from the main site's entrypoint, `src/styles/site.css`, and run
 * by Tailwind during `build:css`. `@tailwindcss/typography` styles `code`
 * inside `.prose` with a scheme that suits body copy but not the doc pages,
 * where inline code carries identifiers the reader is expected to match
 * against a code block. This plugin restates those declarations under
 * `.doc-prose`, excluding `code` inside `pre` so highlighted blocks keep the
 * colours the Pygments generators emit.
 *
 * It is a component rather than a utility so that the typography plugin's own
 * rules, which are components too, do not win on ordering alone.
 *
 * @module
 */
/**
 * Register the `.doc-prose` inline-code component.
 *
 * @param {object} api - The plugin API Tailwind supplies.
 * @param {Function} api.addComponents - Registers rules in the components
 *   layer, so the typography plugin's own component rules cannot win on
 *   ordering alone.
 * @returns {void}
 */
export default function docInlineCodePlugin({ addComponents }) {
  addComponents({
    ":root .doc-prose :where(code):not(:where(pre code))": {
      backgroundColor: "rgb(229 231 235)",
      borderRadius: "0.25rem",
      borderColor: "rgb(229 231 235)",
      borderStyle: "solid",
      borderWidth: "0px",
      boxSizing: "border-box",
      color: "rgb(75 85 99)",
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-sm)",
      fontWeight: "400",
      letterSpacing: "-0.4px",
      lineHeight: "var(--text-sm--line-height)",
      paddingBlock: "0.125rem",
      paddingInline: "0.25rem",
      tabSize: "4",
    },
  });
}
