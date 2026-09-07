/**
 * @file Stylelint configuration for the hand-written and Tailwind CSS.
 *
 * Formatting is Biome's job (`biome check` covers `.css`), so this is a
 * lint-only pass over `src/**` built on `stylelint-config-standard`. Every
 * departure from the preset is recorded beside the rule with its reason.
 * Where a rule genuinely should not apply to one block, disable it there with
 * `stylelint-disable-next-line <rule> -- why` rather than loosening it here.
 */

/**
 * The at-rules Tailwind v4 adds to CSS. Stylelint knows none of them, and
 * the two kinds of entrypoint under `src/styles/` are where the theme tokens
 * live, so excluding those files would lint the least valuable half.
 */
const tailwindAtRules = [
  "apply",
  "config",
  "custom-variant",
  "plugin",
  "reference",
  "source",
  "tailwind",
  "theme",
  "utility",
  "variant",
];

/** A kebab-case word: `foo`, `foo-bar`, `text-3xs`. */
const kebab = "[a-z][a-z0-9]*(?:-[a-z0-9]+)*";
/** A BEM modifier may be bare number, as in `track--2`. */
const modifier = "[a-z0-9]+(?:-[a-z0-9]+)*";

export default {
  extends: ["stylelint-config-standard"],
  rules: {
    "at-rule-no-unknown": [true, { ignoreAtRules: tailwindAtRules }],
    // `@apply` takes a list of utility classes, which the CSS grammar has no
    // production for.
    "at-rule-prelude-no-invalid": [true, { ignoreAtRules: ["apply"] }],
    // The stylesheets use BEM: block, `block__element`, `block--modifier`.
    "selector-class-pattern": [
      `^${kebab}(?:__${kebab})?(?:--${modifier})?$`,
      {
        resolveNestedSelectors: true,
        message: (selector) => `Expected class selector "${selector}" to be kebab-case BEM`,
      },
    ],
    // Tailwind's theme namespace joins a token to its sub-property with a
    // double hyphen: `--text-xs--line-height` is the line-height paired with
    // the `text-xs` size.
    "custom-property-pattern": [
      `^${kebab}(?:--${kebab})?$`,
      {
        message: (property) =>
          `Expected custom property name "${property}" to be kebab-case, ` +
          "with at most one double-hyphen namespace join",
      },
    ],
    // Tailwind v4 resolves `@import` itself at build time and documents the
    // string form, so the entrypoints follow the upstream convention rather
    // than the preset's `url()` form.
    "import-notation": "string",
    // The sub-site stylesheets are grouped by component, and this rule
    // compares selectors across components that share only a type element
    // (`.camp h3` against `.weakness-panel h3`). Reordering to satisfy it
    // would scatter each component's rules across the file, and the
    // cascade it guards against does not arise between unrelated blocks.
    "no-descending-specificity": null,
  },
  overrides: [
    {
      // The stylesheets under src/static/ are copied to the published tree
      // verbatim; only src/styles/ goes through Tailwind, whose Lightning CSS
      // pass lowers newer syntax for older browsers. Range media queries
      // (`width <= 900px`) need Safari 16.4, so the copied files keep the
      // prefix form (`max-width: 900px`) that every browser reads.
      files: ["src/static/**/*.css"],
      rules: {
        "media-feature-range-notation": "prefix",
      },
    },
  ],
};
