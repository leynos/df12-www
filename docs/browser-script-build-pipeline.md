# Browser script build pipeline design

Status: Accepted. Scope: the compile and typecheck path for the classic scripts
under `src/static/<site>/assets/js/`. This document takes precedence over
informal descriptions elsewhere; the operating instructions for day-to-day work
remain in section 6 of the [Developer's Guide](developers-guide.md).

## 1. Context

Before this work, the sixteen classic browser scripts across the sub-sites were
hand-written JavaScript, copied to `public/` verbatim by
`scripts/copy-static.ts`. Nothing typechecked them. The two build scripts,
`scripts/copy-static.ts` and `scripts/generate-image-variants.ts`, were
TypeScript that Bun ran with their types stripped and never checked, and the
browser scripts had no types to check at all. GitHub issue #68 asked for these
scripts to be authored in TypeScript, typechecked, and compiled to the plain
JavaScript the templates already load.

## 2. Constraints

The migration had to fit the site's existing shape rather than change it:

- **Classic scripts stay classic.** Every browser script remains a plain
  immediately invoked function expression (IIFE), loaded with `<script defer>`.
  It is not converted to an ES module. Module scripts have different load
  semantics, different `file://` cross-origin resource sharing (CORS)
  behaviour, and implicit strict mode, any of which would be a runtime
  behaviour change disguised as a types-only migration.
- **Template and path contracts are unchanged.** Every `<script src="...">`
  path in `templates/<site>/` continues to resolve to the same published file;
  only the source of that file moves from hand-written JavaScript to compiled
  TypeScript.
- **The `module.exports` test hook stays.** Several scripts end with a
  guarded `if (typeof module !== "undefined" && module.exports) { ... }` block
  so the Bun test suite can `require` the pure decision functions they export.
  That hook has to survive compilation unchanged, because the tests `require`
  exactly what ships to the browser.
- **`public/` remains disposable build output.** It is git-ignored in its
  entirety (see [Repository Layout](repository-layout.md)); compiled JavaScript
  is written there and nowhere else.
- **Vendored code is out of scope.** Anything under a `vendor/` segment,
  such as the vendored MiniSearch build, is excluded from compilation,
  typechecking, and Biome alike. It ships as written.
- **This is a types-only migration.** The goal is static checking, not a
  rewrite. Runtime behaviour must not change as a side effect of adding types.

## 3. Decision: swc for compilation, `tsc` for the gate

`scripts/compile-browser-scripts.ts` compiles each browser script with
[`@swc/core`](https://swc.rs/), invoked through its `transform` application
programming interface (API), not through the TypeScript compiler. The options
that matter are:

- `isModule: false`, so swc treats the file as a plain script rather than
  wrapping it as a module. This is what keeps the top-level IIFE, the
  `"use strict"` directive, and the `module.exports` guard intact.
- `jsc.parser.syntax: "typescript"`, so the parser understands type
  annotations, interfaces, and generics.
- `jsc.preserveAllComments: true`, so the house-style comments described in
  section 6 of the Developer's Guide survive into the published file.
- `jsc.target: "es2022"`, matching the language level declared in
  `tsconfig.base.json`.
- `swcrc: false` and `configFile: false`, so the result depends only on the
  options passed in code, never on a `.swcrc` file that might exist on disk.

swc was chosen over `tsc` as the compiler because it strips types without
walking the type graph, which makes it fast enough to run on every build
without a caching layer of its own. That speed has a cost: swc does not check
anything it strips, so a wrongly typed module compiles cleanly and would ship
unnoticed if compilation were the only gate. `make typecheck` is therefore a
separate step from `build:js`, using `tsc --noEmit` over the same sources
(section 4). The build produces working output quickly; the gate decides
whether that output was type-safe. `tsgo` was named as an acceptable
alternative in the issue; it was not adopted because swc already does the
strip-only job the build needs, and the typecheck is `tsc` regardless, so the
compiler choice does not affect the gate.

Compiled output is written to `public/<site>/assets/js/<name>.js`, mirroring
the source path under `src/static/<site>/assets/js/` with the `.ts` extension
replaced by `.js`. A source is skipped when its compiled output is already
newer than it, so repeated builds stay cheap; nothing is pruned, because the
compile step cannot distinguish a deleted script from another build step's
output. This mirrors the incremental and non-pruning policy
`scripts/copy-static.ts` already uses for every other static asset. Removing
`public/` and rebuilding is the general remedy for either step's stale output;
see section 8.

## 4. TypeScript projects

Two kinds of TypeScript live in the repository, in different worlds. The
browser scripts under `src/static/<site>/assets/js/` are classic scripts that
see the DOM and nothing else; the build scripts under `scripts/` and the
Tailwind plugin under `src/styles/plugins/` are ES modules that Bun executes
with Node and Bun APIs at hand. They are typechecked as two projects sharing
one strict base.

| File                    | Covers                                                                                      |
| ----------------------- | ------------------------------------------------------------------------------------------- |
| `tsconfig.base.json`    | Shared strict options: `strict`, `noEmit`, ES2022, `isolatedModules`.                       |
| `tsconfig.browser.json` | `src/static/**/*.ts` with DOM libraries and `types: []`, so no Node or Bun global leaks in. |
| `tsconfig.scripts.json` | `scripts/**` and `src/styles/plugins/**` with Bun types; also what TypeDoc reads.           |
| `tsconfig.json`         | A solution file with no sources, pointing editors at both projects.                         |

_Table 1: The TypeScript projects and what each one covers._

`src/static/browser-globals.d.ts` declares everything a classic script can
reach beyond the DOM:

- The guarded `module` global the Bun tests `require` through, declared as
  a plain global rather than through `@types/node`, so the browser project
  stays free of Node's other globals.
- The vendored `MiniSearch` constructor, declared as `var` because the
  UMD (Universal Module Definition) build assigns it as a property of the
  global object, which is how the scripts reach it through `window` and
  `globalThis`. It is typed against `import("minisearch").default`, the same
  release pinned in `devDependencies`, so the ambient type cannot drift from
  the file actually shipped in `vendor/`.
- The cross-script telemetry contracts the Weaver and Episodic scripts
  install on `globalThis`: `WeaverTelemetryApi`, the fixed event shapes for
  Weaver navigation and clipboard telemetry, and the bounded Episodic
  search-index telemetry event. Every one of these globals is optional, because
  every reader tolerates its absence — the telemetry sinks are no-ops when
  nothing installed them.

Vendored files under `**/vendor/**` are excluded from both TypeScript projects,
as they are from Biome, for the same reason: they are third-party code, not
written to house conventions and not ours to typecheck.

```bash
bun run typecheck:js   # tsc -p tsconfig.browser.json && tsc -p tsconfig.scripts.json
make typecheck-js      # the same, in the gate
make typecheck         # ty over the Python, then typecheck-js
```

`tsc -b tsconfig.json` works as a solution build under TypeScript 6 even though
neither referenced project sets `composite` and both set `noEmit`; running it
only writes the git-ignored `.tsbuildinfo` files that make incremental builds
fast; it does not violate `noEmit` for program output. The gate does not use
it, though: `bun run typecheck:js` calls `tsc` on each project with `-p`
explicitly, so a failure names the project it came from rather than reporting
through the solution file.

### Strictness beyond the shared default

`tsconfig.base.json` turns on two options beyond `strict`:
`exactOptionalPropertyTypes`, so an optional property may be absent but not
explicitly set to `undefined`, and `noImplicitOverride`, so a class member that
overrides a base member must say so. Both were free for the code as written.

Two further strict flags were deliberately left off: `noUncheckedIndexedAccess`
and `noPropertyAccessFromIndexSignature`. The scripts read `element.dataset`
and index into arrays throughout; turning either flag on would force adding
`undefined` checks or non-null assertions at dozens of call sites for no
behavioural benefit. That rewrite is contrary to the types-only migration
described in section 2, so both flags are left off pending a decision to take
on that separate piece of work.

## 5. Build and gate order

`bun run build` composes, in a fixed order:

```plaintext
build:static -> build:js -> build:css -> build:images -> build:pages
             -> build:search -> build:static
```

`build:static` (`scripts/copy-static.ts`) copies every hand-crafted asset under
`src/static/` to its mirrored path under `public/`, skipping `.ts` files. It
runs first because `build:images` reads the source images it places, and it
runs a second time at the end so the committed Episodic search projection is
republished after `build:search` regenerates it. `build:js`
(`scripts/compile-browser-scripts.ts`) compiles the TypeScript under
`src/static/<site>/assets/js/` into the mirrored `.js` path.

`make typecheck` runs `ty` over the Python and then `typecheck-js`, which runs
`bun run typecheck:js` over both TypeScript projects. It is a completely
separate target from `build`, so a broken build never masks a type error and a
passing typecheck never certifies a build that has not happened.

`make test-js` runs `bun run build:static` and `bun run build:js` before
`bun run test:js`, because the suite `require`s the built copies under
`public/`, not the TypeScript sources. Running `bun test tests/js` directly
skips that step and will quietly test whatever was last built rather than the
current source.

`bun run dev` watches `src/**/*` — among other roots — and reruns the full
`bun run build` on any change, so editing a browser script under `src/static/`
triggers a recompile. See section 2 of the Developer's Guide for the full
watcher contract.

`make all` composes
`build check-fmt lint test test-js typecheck docs-check spelling`, run
sequentially so the build cache is used rather than contended by parallel
invocations.

## 6. Typing conventions adopted in the migration

The migration's guiding rule is that types are the only thing a module gains;
its runtime behaviour is unchanged. Several conventions recur across the
sixteen scripts:

- **Typed `querySelector` generics with early-return narrowing.** A
  `document.querySelector<HTMLElement>(...)` result is typed as the element its
  handler actually reads, and an early `if (!el) return;` both narrows the type
  for the rest of the function and preserves the existing behaviour of doing
  nothing when the root is absent.
- **Named interfaces for injected dependencies.** `copy-buttons.ts`,
  `config-keys.ts`, and `site-search.ts` each declare a `deps`-shaped interface
  for the loader, search, clipboard, or navigation functions they accept, so
  the production wiring and the test fakes are held to the same shape by the
  type checker rather than by convention alone.
- **Typed `data-*` vocabularies.** Where a module reads several `data-*`
  hooks, the attribute names are declared once — `config-keys.ts` keeps them in
  a `HOOKS` table its selectors and its label carry-over both read — and the
  values read from `dataset` are typed as the `string | undefined` a lookup can
  yield rather than assumed present.
- **Cast-at-guard, with a comment, where the checker cannot narrow.** A
  `var` or a hoisted `function` declaration that reads a root an earlier guard
  has already checked defeats ordinary narrowing, because the checker cannot
  see that the guard still holds by the time the hoisted code runs. In that
  specific situation the lookup is cast at the point of the guard, with a
  comment explaining why, rather than restructuring the module around the
  checker's control-flow analysis.
- **A runtime type guard on stored MiniSearch fields.**
  `src/static/episodic/assets/js/site-search.ts` filters returned search hits
  through `isSearchHit`, and `src/static/netsuke/assets/js/doc-search.ts`
  filters through `isDocSearchHit`, before rendering them, because MiniSearch
  types the stored fields under an index signature of `any`. Each guard
  requires the fields every list renders to be strings, accepts the optional
  ones (`sectionTitle`, `excerpt`, and for Episodic `pageTitle`) only when
  absent or a string, and drops a record that fails either check, so a
  malformed index file cannot make `escapeHtml` throw or become a navigation
  target.
- **`Array.from` instead of `Array.prototype.slice.call`.** Strict call
  checking rejects passing a `NodeList` as `this` to `Array.prototype.slice`,
  so call sites that need an array from a `NodeList` use `Array.from` instead,
  which is typed to accept an iterable directly.

## 7. Testing

Two test files exercise the pipeline itself, distinct from the suites that
exercise what any one compiled script does at runtime (section 6 of the
Developer's Guide):

- `tests/js/compile-browser-scripts.test.mjs` unit-tests
  `isBrowserScript`, `targetFor`, and `compileClassicScript` directly,
  including a fast-check property test that checks `isBrowserScript` against a
  hand-written specification over generated file trees — vendored paths,
  declaration files, and `.ts` files outside `assets/js` — rather than a fixed
  list of examples. It then runs `compile-browser-scripts.ts` and
  `copy-static.ts` as subprocesses against an isolated fixture tree, proving
  the two scripts agree about which files a `.ts` extension belongs to: the
  compile step emits exactly the browser scripts, and the copy step skips every
  `.ts` file, so nothing under `src/static` reaches `public/` in two forms.
- `tests/js/typecheck-gate.test.mjs` proves the gate actually gates, rather
  than merely asserting the tree is currently clean. It writes a deliberately
  wrong type into a fixture in each project in turn — a browser script under
  `src/static/netsuke/assets/js/` and a script under `scripts/` — and requires
  `make typecheck-js` to fail on each, then writes the same error under a
  `vendor/` directory and requires the gate to pass, proving the vendor
  exclusion holds rather than the fixture being accidentally valid.

## 8. Consequences and known limits

- **A stale compiled file can be skipped.** Because both `copy-static.ts`
  and `compile-browser-scripts.ts` skip a destination that is already newer
  than its source, a `public/*.js` file copied before this migration — when
  browser scripts were plain JavaScript copied verbatim — can remain newer than
  an unedited `.ts` source and never get recompiled. Removing `public/` and
  rebuilding from a clean tree is the general remedy, as it is for any other
  stale generated output described in section 3 of the Developer's Guide.
- **`@swc/core`'s postinstall step is blocked, and that is fine.** Bun's
  trusted-dependency default blocks the package's postinstall script; the
  native binding the package ships loads without it, which `make test-js`
  exercises on every run.
- **TypeDoc still excludes the browser scripts.** As described in section
  2.3 of the Developer's Guide, TypeDoc resolves the export object of a guarded
  `module.exports` as an anonymous type and asks for documentation on each
  synthetic member, which would mean writing comments addressed to the type
  checker rather than to a reader. The browser scripts remain outside
  `typedoc.json`'s entry points; they are typechecked by this pipeline instead,
  and commented to house style.

## 9. Alternatives considered

- **ES modules with `type="module"`.** Rejected outright: module scripts
  change load semantics (deferred by default, but with different ordering
  guarantees against classic scripts), have different `file://` CORS behaviour,
  and run in strict mode implicitly. Any of these would be an observable
  runtime change, which contradicts the types-only migration constraint in
  section 2.
- **`tsc` as the compiler.** `tsc` can emit JavaScript directly, which would
  have let one tool both typecheck and compile. It was rejected for the build
  role because it is markedly slower than swc for a strip-only job. `tsgo` was
  also named as an acceptable alternative in the issue, but swc already does
  the strip-only job the build needs, and the typecheck runs through `tsc`
  regardless, so the compiler choice would not have changed the gate. Using
  `tsc` to compile would also have coupled compilation to typechecking,
  undermining the separation of fast build from thorough gate described in
  section 3.
- **A second, module-based build for the test suite.** Rejected because it
  would test a different artefact from the one that ships. The Bun suite
  `require`s the same compiled output the templates load specifically so that a
  passing test proves something about the shipped file, not about a parallel
  build that exists only for tests.
