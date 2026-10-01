# femtologging sub-site

The site at `/femtologging/` uses the native df12 generator. Its 28 routes
follow the proposed sitemap in the sibling `femtologging-reference` directory.
The parent homepage includes a library link to the sub-site.

## Sources and release status

`config/pages.yaml` contains the sub-site routes, navigation, and version
variables. Templates live in `templates/femtologging/`; assets live in
`src/static/femtologging/`. `src/styles/femtologging.css` imports the font,
base, chrome, content, and generated syntax partials into the appropriate
Tailwind layers. The shared build compiles its stylesheet.

The target is 0.2.0, with 0.2.0-beta1 assumed to be the next release. This is
prospective copy: installation instructions label the package-index command as
forthcoming and provide a pinned source build for use now.

The documented source revision is `f5bcaa8257f4c59a361dc4f41585b9ecccb9f345`.
Its package metadata still says 0.1.0, although its source includes the
structured logging changes documented for 0.2.0. Do not change the website
status to “released” merely by changing its version variable. Verify
distributions, source, and examples together.

`templates/femtologging/data/pages.jinja` supplies article metadata and local
navigation from one catalogue. Article copy remains in the page templates.
`data/api.jinja` is a transcription of public exports and declarations from
that revision. It groups the supported API, identifies formatter placeholders,
and lists internal/test exports separately. When updating the revision,
reconcile every `__all__` export and public stub declaration with that
inventory. The reference describes source, rather than claiming an unpublished
wheel has been verified.

## Design and asset provenance

The primary direction is the supplied brand pack: carbon/alumina surfaces, IBM
Plex, the lattice mark, its authored SVG icons, and the three anchor
illustrations. Font licences accompany the redistributed WOFF2 files. The
concepts inform the roadmap’s explicitly exploratory what-ifs.

Prospective copy and visual direction were written before implementation to
`femtologging-reference/prospective-site-copy.md` and `visual-direction.md`.
The new illustration was generated with the built-in imagegen tool before
building the site, using the pipeline and habitat anchors as style references.
The PNG is retained as `femtologging-reference/record-transport-survey.png`.
The original WebP and PNG are retained. The site uses the subsequent
`assets/images/record-transport-survey-sem.webp` variant, encoded at quality

1. The original brand-pack WebP anchors are preserved.

The final generation prompt was:

> Use case: stylized-concept. Asset type: wide 3:2 editorial website
> illustration
> for femtologging, a Rust logging extension for Python. Input images are style
> reference only: preserve the engineering and animal anatomy of the supplied
> femtofauna brand plates. Create a new scene: an oblique cutaway specimen tray
> in a severe materials science laboratory. In the foreground an ivory ceramic
> articulated robot panda with black sensor patches carries a translucent amber
> cubic log-record crate along a crystalline teal transport trench; a low
> blunt-muzzled robotic capybara sits beside a circular buffer cavity mid-right;
> a small long-neck segmented ceramic sauropod inspects an interface bridge in
> the distant upper-left. Machinery dominates, animals discovered in it. Carbon
> #12171B machined metal, alumina #F2EEE6 ceramic, teal #63D6CF channels, amber
> #E1A64B crates, tiny gold bond wires, rivets, oxide and grain boundaries, fine
> SEM-inspired texture. Strong diagonal layers, intricate credible modelmaking,
> largely grey with restrained false colour, crisp foreground detail. Calm
> institutional observer, quietly delightful. Fictional scientific illustration,
> not actual microscopy. No text, labels, logos, numbers, scale bars, UI,
> watermarks, rainbow neon, plushies, generic cube robots, or glossy plastic.

A subsequent imagegen edit used the transport plate as its composition
reference and the three user-supplied SEM images as material references. It
preserves the fauna and transport machinery, adds granular etched surfaces,
bright secondary-electron edge relief, muted teal/amber false colour, and a
“SIMULATED MICROGRAPH” instrument strip. No numerical measurement is asserted.
The edit target and the references were passed as separate image inputs; their
watermarks, logos, and original subjects were excluded from the prompt. The
resulting PNG is retained as
`femtologging-reference/record-transport-survey-sem.png`.

Captions are HTML. Every meaningful plate identifies its fictional context;
legal pages contain no survey art. No image represents benchmark evidence.

## Code panels and verification

The complete Python programs under `templates/femtologging/samples/` are
included verbatim and highlighted at build time. Downloadable copies under
`src/static/femtologging/assets/samples/` must remain byte-identical. The build
tests compare both against the rendered code panels.

`FemtoStyle` in `df12_pages/femtologging_highlighting.py` owns syntax colours.
Regenerate the syntax partial after changing that style:

```bash
uv run python scripts/generate_femtologging_pygments_css.py
make fmt
```

Never edit generated token rules by hand. Code-panel structure and overflow
behaviour live in `content.css`, outside the generated partial.

Run the examples with an interpreter that has the documented femtologging
source installed. The website environment intentionally excludes these
upstream-dependent downloadable programs from its own typecheck:

```bash
FEMTOLOGGING_PYTHON=/path/to/source-environment/bin/python
"$FEMTOLOGGING_PYTHON" templates/femtologging/samples/first-record.py
"$FEMTOLOGGING_PYTHON" templates/femtologging/samples/console-and-file.py
"$FEMTOLOGGING_PYTHON" templates/femtologging/samples/request-context.py
"$FEMTOLOGGING_PYTHON" templates/femtologging/samples/stdlib-handler.py
```

On 1 October 2026, all four programs passed with a freshly built source wheel
in a separate CPython 3.13 Linux environment. JSON output normalized request ID
42 to the string `"42"`. Immediate flushing of queued Python handlers could
time out while the worker awaited the GIL. The examples use delivery Events
before flushing, and the Operations guide records that limitation.

For site changes, run the contributor guide’s formatting, lint, typecheck,
Python, JavaScript, and Markdown gates. Rebuild through `bun run build`.
Inspect all 28 pages at 1440, 1280, 1024, 768, 390, and 320px, check horizontal
overflow, and audit WCAG A/AA. The build tests also check local assets, route
links, heading anchors, release status, and legal-page boundaries.
