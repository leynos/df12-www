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
Plex, the lattice mark, and its authored SVG icons. Font licences accompany the
redistributed WOFF2 files. The concept mockups inform the cover, the
magnification series, the specimen notes, and the roadmap's exploratory
what-ifs.

The masthead is sticky, and its first navigation item is “← df12”, as on the
Cuprum and rstest-bdd sub-sites. The root's `scroll-padding-top` keeps anchor
targets clear of it. The shared legal pages follow the Netsuke layout: a
breadcrumb, then one raised panel with the eyebrow from `config/pages.yaml`,
the title, the summary, and the body. `legal.css` styles the generator's
contents list, sections, and badge cards. Legal pages carry no plates and no
page head.

### Survey plates

Every illustration is a *survey plate*: a fictional false-colour scanning
electron micrograph, lit from within by the amber record crates and the teal
crystal channels. `templates/femtologging/data/plates.jinja` is the single
catalogue. Each entry records the raster, its dimensions, plate number,
specimen ID, alt text, caption, illustrative scale, and any numbered callouts.
The same file holds the magnification series, the three specimens, and the
`page_plates` mapping that gives product pages a plate in their header. Task
guides, reference pages, and legal pages carry none.

The `plate` macro in `components.jinja` renders an entry. The raster carries no
text. The instrument strip (specimen ID, detector mode, and an illustrative
scale bar), the numbered markers, and the caption are HTML. A legend in the
caption repeats every marker in words, so the markers are hidden from assistive
technology. Every caption says “Fictional scientific illustration”. Specimen
IDs identify artwork, not test results. Scale values are fiction and always
render beside “illustrative scale”. The strip is a container query target and
drops detail as the plate narrows, rather than wrapping.

Callout coordinates are percentages of the uncropped raster. A plate with
callouts must therefore keep its aspect ratio; header plates crop to 3:2 and
carry no callouts. A marker's label appears beside it only on the cover at
desktop widths, where `side: 'left'` places the label left of the marker.

### Generation

The fifteen plates were generated with gpt-image-2 on 1 October 2026, using the
brand-pack anchors as character references and crops of the concept mockups as
lighting references. The cover plate was then used as the style reference for
the rest of the set. Each prompt asked for the same material grammar:
monochrome SEM greys with granular secondary-electron texture and edge-relief
halos; amber only on the record crates and their light; teal only on crystal
channels and instruments; carbon falloff and shallow depth of field. Every
prompt also excluded text, numbers, labels, scale bars, logos, plush, cartoon,
and glossy plastic.

The PNG originals are retained in `femtologging-reference/survey-plates/`. The
WebP files under `src/static/femtologging/assets/images/` were encoded at
quality 80 with Pillow. Each plate has a full-size file and a `-half` file at
half its linear size, which the macro offers through `srcset`. The sub-site's
images are outside the main site's `build:images` step, so re-encode both sizes
when replacing a plate.

The earlier brand-pack anchors and the record-transport survey are superseded
on the site. Their originals remain in the brand pack and the reference
directory.

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
