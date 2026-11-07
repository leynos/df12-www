# wireframe sub-site

The sub-site at `/wireframe/` documents wireframe, the Rust router for
frame-based binary protocols that mxd runs on. It publishes 18 routes: the home
page, 14 content pages, and the three shared legal pages. The parent homepage
links it from its libraries group.

This document records where the site's facts come from, what the release
taught, how the identity was applied, and how the code and art were made.

## Sources and release status

Every claim describes wireframe 0.4.0-alpha1, targeted for 15 November 2026,
unless the page labels it as history. The sources are, in order of authority:

1. The library's source, which settles any disagreement.
2. The sample crate under `templates/wireframe/samples/`, which compiles and
   runs every working example.
3. The library's `docs/users-guide.md` and `docs/v0-4-0-migration-guide.md`,
   which are audited and carry tested examples.

If the library and its documents disagree, tell the library's maintainers.

`config/pages.yaml` holds the release facts in the sub-site's `template_vars`:
`wireframe_version`, `wireframe_tag`, `wireframe_published`,
`wireframe_released`, `samples_verified_against`, `rust_minimum`,
`rust_verified`, `samples_verified_on`, and `mxd_wireframe_version`. mxd has
its own variable because it moves on its own schedule, and it still pins 0.3.0.
The API reference is docs.rs (`docs_url`) rather than a transcription, because
rustdoc is generated from the release and cannot drift from it.

### Before the release is published

The site was updated ahead of publication. On 7 November 2026, the crate was
not on crates.io, the `v0.4.0-alpha1` tag did not exist, and the library's
stack (PRs #869, #870, #873, and #880) was unmerged. So:

- The samples ran against the library's source at commit `cd634074` through a
  `[patch.crates-io]` entry in a scratch copy. No path dependency is committed,
  because the `deps` anchor renders on two pages.
- `samples/Cargo.lock` comes from that run, so its `wireframe` entry has no
  registry source. `make wireframe-samples` fails until the crate is published.
- `source_base` and `docs_url` point at the release, so those links 404 until
  it exists. **Do not deploy this site before the tag and crates are
  published.**
- `wireframe_published: false` makes pages call the date a target.

At publication, in this order:

1. Confirm the published crates: `wireframe` and `wireframe_testing`, both at
   the same version, since the testing page names the latter. If the library
   stack changed after `cd634074`, re-read the claims it touched.
2. Run `cargo update -p wireframe` in `templates/wireframe/samples/`, then
   `make wireframe-samples`.
3. Set `wireframe_published: true`, the true release date, and
   `samples_verified_against: "wireframe 0.4.0-alpha1"`, and update
   `rust_verified` and `samples_verified_on`. A test holds the flag to the
   lockfile, so doing only one fails the build tests.
4. Check that every link under `source_base` and `docs_url` resolves.
5. Update `latest_release` for wireframe with `df12_pages/bump.py`.

### What the release taught

The site follows these, and states each plainly where it matters:

- **Inbound order.** Codec decode, deserialize envelope, reassemble, assemble,
  route. Outbound: fragment, serialize, wrap, `before_send`, encode. Earlier
  copy had reassembly before deserialization and serializing before
  fragmenting, which was wrong for 0.3.0 too.
- **The factory runs once per server run**, and the prepared application is
  shared by every connection.
- **The server reads first.** Even without `with_preamble` it reads a first
  byte under a 10-second deadline, so it never speaks first.
- **An error from the preamble success handler closes the connection.**
- **`middleware::from_fn` cannot be passed to `WireframeApp::wrap`.** `wrap`
  accepts only a `Transform` whose output is a `HandlerService`.
- **Routed handlers return nothing.** The default `HandlerService` echoes the
  request payload, and middleware writes replies through
  `ServiceResponse::frame_mut()`.
- **One reply per request.** `PushQueues`, `ConnectionActor`,
  `Response::Stream`, `Response::MultiPacket`, `SessionRegistry`, extractors,
  and recovery policies ship and are tested, but `WireframeServer` does not
  drive them. Of the protocol hooks, only `before_send` runs on a server
  connection. The client's `call_streaming` works, so its sample uses a plain
  Tokio server.
- **A custom `Packet` changes what handlers see, not the wire.** The sample
  sends and receives `Envelope` and shows the handler a `Stroke`.
- **The read timeout is a housekeeping tick, and shutdown has no deadline.** An
  idle connection stays open, and it holds up `drained`.
- **Pool sockets open on first use.** Measured in the sample: against a port
  with nothing listening, `acquire` returns at once, and the first `call` takes
  30 seconds and fails with `pooled connection checkout timed out`, from bb8's
  default checkout timeout. The library's documents do not yet mention this.
- **`wireframe_connections_active` counts actors**, so it stays flat on
  `WireframeServer`, and only an application's own `inc_codec_error` calls
  record `wireframe_codec_errors_total`.
- **`SessionRegistry::default()` needs a `Default` frame type**, which
  `Envelope` is not.

Two facts the reference mockup got wrong are absent: there are no derive macros
for protocol definition and no string routes. The mockup's illustrative Rust is
not used anywhere.

## Identity

The visual direction is the supplied specification, "Wireframe | Visual
identity and design language" (v0.1, 31 October 2026), in
`../wireframe-reference/`. Its creative thesis is "make the invisible protocol
legible": X-Y vector-display beam art on a green-black field, a crisp core, a
faint underdrawing, and an optional halo. The owner's review pushed the
execution further than the specification's restraint: the site should look as
if a serious amount of computing were being thrown at vector-scan hardware,
with the energy of Tron and Rez, and never like a raster screen.

- **Colour.** The daisyUI `wireframe` theme carries the specification's
  section 14 tokens, and `src/styles/wireframe.css` records the contrast of
  each against the grounds it sits on. Mint is identity and the route in use,
  cyan marks frames and data, amber marks traffic on the move, magenta marks
  the one selected or correlated object, and `#FF687A` is for errors only. One
  theme, dark only.
- **Type.** Sintony (400 and 700) sets all interface and prose, with synthesis
  off. Monaspace Krypton (400 and 600) sets code, with ligatures off. Both are
  the Fontsource 5.3.0 Latin builds, self-hosted beside their OFL licences.
- **Logotype.** The site publishes the supplied raster master,
  `logotype.png`, at the owner's request, overriding the specification's
  instruction never to rasterize the wordmark. An earlier SVG redrawing was
  retired. `scripts/build_wireframe_logo_assets.py` crops the master into a
  header lockup, a hero wordmark, a symbol, and PNG favicons. It keys the
  near-black ground to alpha by treating the art as light emitted over black
  (alpha is the brightest channel; colour is un-premultiplied), and feathers
  the cropped halo so no rectangle shows. Rerun it with the master's path when
  the artwork changes. A test holds every brand image to the keyed files.
- **The beam.** The hero's scope scene is generated by
  `scripts/generate_wireframe_scope.py`: the scene is laid out in three
  dimensions and projected through a pinhole camera at build time into labelled
  SVG, whose strokes are `M`/`L` paths carrying a `data-beam` role. `scope.ts`
  redraws those strokes on a canvas as a vector monitor would. It never clears
  the canvas, so persistence leaves trails, and draws with additive light, so
  crossings and vertices burn brightest. It also draws faint flyback between
  paths, drifts the deflection, runs pulses along the lit route, and fires a
  rare deflection glitch. It runs only while the scene is on screen and the
  page is visible. The "complexity, reduced" drawing uses the same script.
- **Glow and motion.** Halos are filters and shadows only, removed under
  `prefers-contrast: more` and forced colours. The wordmark strikes once on
  load, the hero line takes a brief mint and cyan ghost every seven seconds
  (never red and blue fringing), and the journey's amber rail carries a
  travelling pulse and lights each station as a scroll-driven animation reaches
  it. Under `prefers-reduced-motion` or `prefers-contrast: more` the beam stays
  off and the labelled SVG is the whole picture; under reduced motion nothing
  else moves either.
- **Icons.** `src/static/wireframe/assets/icons/sprite.svg` draws the
  specification's vocabulary on a 24 by 24 grid: frame, route, gates, pulses,
  fragments, outbound, proof, and budget.

### The scope

The playful world is an X-Y vector display driven hard. A request is the beam,
the byte stream is the display list, a frame is a stroke, the router is
deflection, middleware is modulation, a handler is where the beam dwells, a
fragmented message is a stroke drawn with blanked gaps, the reply is the
retrace, and state that outlives a frame is phosphor persistence. The metaphor
follows the library's structure and stops where it would mislead: a beam is
deflected to one handler, because routing selects a handler and never
broadcasts.

The site's first world, a railway marshalling yard, was retired at the owner's
request, as was an early cast of animal characters. No page, plate, prompt, or
sample identifier mentions either; the sample crate is `vector-scope`.

## Site map

| Route                                     | Page                             |
| ----------------------------------------- | -------------------------------- |
| `/wireframe/`                             | Home                             |
| `/wireframe/getting-started/`             | A first server, end to end       |
| `/wireframe/guides/`                      | Guide index                      |
| `/wireframe/guides/routing/`              | Routes, envelopes, and handlers  |
| `/wireframe/guides/codecs/`               | Frame codecs and preambles       |
| `/wireframe/guides/middleware/`           | Middleware and lifecycle hooks   |
| `/wireframe/guides/streaming/`            | Streaming, push, and sessions    |
| `/wireframe/guides/large-messages/`       | Fragmentation and memory budgets |
| `/wireframe/guides/client/`               | The client runtime               |
| `/wireframe/guides/testing/`              | Testing at the frame             |
| `/wireframe/guides/production/`           | Running in production            |
| `/wireframe/architecture/`                | The stack, layer by layer        |
| `/wireframe/examples/`                    | Worked examples                  |
| `/wireframe/roadmap/`                     | Released, next, and further out  |
| `/wireframe/scope/`                       | The scope (field guide)          |
| `/wireframe/privacy-policy/` and siblings | Shared legal pages               |

The home page follows the specification's reading path and the mockup's energy:
identity and proposition beside the scope scene, a capability row and release
readout, three numbered panels (two working examples and the "complexity,
reduced" drawing), the station track, capabilities, the world, mxd,
installation, and a tagline strip.

## Templates

- `_layout.jinja` is the chrome, `_article.jinja` the rail-and-column layout
  for getting started, the guides, and architecture.
- `data/pages.jinja` is the one catalogue of article titles, leads, sections,
  icons, upstream sources, and docs.rs paths. The guide index, the side rail,
  and each page's contents list read from it; a test holds the contents list to
  the page's section headings.
- `data/plates.jinja` catalogues every illustration with its dimensions, alt
  text, label, and caption, rendered by the `plate` macro.
- `components.jinja` holds the macros that need no highlighting. `_code.jinja`
  holds the code panels, because they use the build-time `highlight` tag that
  the shared legal-page renderer does not load.
- `_scope.svg.jinja` is the hero scene, generated; edit the script, not the
  file. A test holds it to its generator and to the path grammar the beam reads.
  `_reduction.svg.jinja` is the third panel's drawing, laid out once from a
  seeded random tangle and committed.

## Code panels and verification

Every working example is cut from `templates/wireframe/samples/`, a Cargo
package that depends on `wireframe = "=0.4.0-alpha1"`. A panel is
`code.code(file, anchor)`, which includes the file and keeps the lines between
`// ANCHOR: name` and `// ANCHOR_END: name` (or `#` in TOML), the mdBook
convention. Each panel's bar says "Working example" in words, as the
specification's source taxonomy asks; shell commands are labelled as commands.
Tests hold every panel to consecutive lines of its file, every named anchor to
its file, the crate's wireframe version and lockfile to `template_vars`, and
every sample to containing no Jinja delimiters.

Run the samples with:

```bash
make wireframe-samples
```

It needs a Rust toolchain and the network, so it is not a commit gate, and it
fails until the release is published; see
[Before the release is published](#before-the-release-is-published). On
7 November 2026 all 13 test binaries passed with Rust 1.99.1 against the
library's source at `cd634074`, with tokio-util 0.7.20. When the release moves,
bump the crate and `template_vars` together, rerun the samples, re-read each
"In 0.4.0-alpha1" callout against the new release, and update the verification
date.

Some samples are not rendered at all, and exist to hold a page's claim to code
that ran: a rejected preamble closes, a silent client is disconnected, a
trailing byte fails decoding, `before_send` sees routed replies, an open
connection holds up the drain, and a pool opens its sockets on first use.

`ScopeStyle` in `df12_pages/wireframe_highlighting.py` owns syntax colours, and
`scripts/generate_wireframe_pygments_css.py` writes
`src/styles/wireframe/syntax.css`. A test fails when the two disagree.

`copy-code.ts` adds a labelled copy control to each panel. Without script the
code is still selectable text in a keyboard-reachable region. `scope.ts` is
loaded only by pages with a `data-wf-scope` root; its geometry helpers are
tested in `tests/js/wireframe-scope.test.mjs`.

## Imagery

The six plates were generated with gpt-image-2 (`generate_image`, high quality)
on 31 October 2026 and checked by eye against their briefs. Every prompt shared
one style block:

- X-Y vector-scan display art: a calligraphic CRT driven hard, with the energy
  of Tron and Rez. Thin luminous lines with crisp cores and a soft phosphor
  halo; vertices and crossings burning brightest; persistence trails behind
  moving shapes; faint retrace lines between shapes.
- Mint `#7CFFB3` structure, cyan `#00FFFF` frames, amber `#FFB347` traffic in
  motion, and magenta `#FF6AD5` only on the one selected or correlated object,
  on `#030E0C`.
- Line work only. No scanlines, pixels, dithering, or RGB fringing; no text,
  numerals, logos, people, vehicles, or trains.

`scope` (16:9, the world plate) shows cubes passing a rhombus gateway with one
lit route. `fragments`, `queues`, `outbound`, `calibration`, and `construction`
(3:2) illustrate the large-message, streaming, client, testing, and roadmap
pages. Each plate's alt text describes what the image actually shows; the
calibration loop, for example, carries several pieces rather than the four the
prompt asked for. The WebP files under `src/static/wireframe/assets/images/`
are quality 86, each with a `-half` variant for `srcset`. The sub-site's images
are outside the main `build:images` step, so re-encode both sizes when
replacing a plate. The masters are in the gpt-image-2 output directory for this
worktree.

## Checks

Run the contributor guide's gates, rebuild with `bun run build`, and inspect
the pages at 1440, 1280, 1024, 768, 390, and 320 pixels.
`tests/test_wireframe_build.py` checks routes, local links and fragments,
sample parity, generated assets (the scope scene, the syntax partial, and the
keyed logotype), release boundaries, and legal pages.
`tests/test_wireframe_browser.py`, marked `playwright`, runs axe over every
page at 390 and 1440 pixels and checks that nothing but a code or table region
scrolls sideways at 320.
