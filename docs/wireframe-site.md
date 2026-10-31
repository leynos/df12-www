# wireframe sub-site

The sub-site at `/wireframe/` documents wireframe, the Rust router for
frame-based binary protocols that mxd runs on. It publishes 18 routes: the home
page, 14 content pages, and the three shared legal pages. The parent homepage
links it from its libraries group.

This document records where the site's facts come from, what the release
taught, how the identity was applied, and how the code and art were made.

## Sources and release status

Every claim describes the released crate, wireframe 0.3.0, published on
crates.io on 6 April 2026, unless the page labels it as unreleased. The sources
are, in order of authority:

1. The published crate source (`~/.cargo/registry/src/*/wireframe-0.3.0`),
   which settles any disagreement.
2. The sample crate under `templates/wireframe/samples/`, which compiles and
   runs every working example against 0.3.0.
3. The user's guide as tagged at `v0.3.0`, not the default branch, which
   already documents breaking 0.4.0 changes.

`config/pages.yaml` holds the release facts in the sub-site's `template_vars`:
`wireframe_version`, `wireframe_tag`, `wireframe_released`, `tokio_util_pin`,
`rust_verified`, and `samples_verified_on`. The API reference is docs.rs for
0.3.0 (`docs_url`) rather than a transcription, because rustdoc is generated
from the release and cannot drift from it.

### What the release taught

Building the sample crate against 0.3.0 contradicted the upstream user's guide
in several places. The site states each of these plainly:

- **tokio-util 0.7.20 breaks the build.** It adds
  `Encoder<&[u8]> for LengthDelimitedCodec`, so `framed.send(bytes.into())` in
  wireframe's inbound handler no longer infers a type (E0283). A fresh
  dependency resolves 0.7.20. The sample lockfile pins 0.7.19, and the home and
  getting-started pages tell readers to do the same. The upstream default
  branch still locks 0.7.19, so the break is not visible there.
- **`middleware::from_fn` cannot be passed to `WireframeApp::wrap`.** `wrap`
  accepts only a `Transform` whose output is a `HandlerService`; `from_fn`
  produces an `FnService`. The guide's quick start therefore does not compile.
  Routed middleware is written as a `Transform`, as the upstream `ping_pong`
  example does.
- **Routed handlers return nothing.** A handler is an `Arc`'d closure from
  `&Envelope` to a boxed future of `()`. The default `HandlerService` echoes
  the request payload, and middleware writes replies through
  `ServiceResponse::frame_mut()`. The README's extractor-style handlers are not
  in 0.3.0.
- **The routed server path sends one reply per request.** `PushQueues`,
  `ConnectionActor`, `Response::Stream`, `Response::MultiPacket`, and the
  `WireframeProtocol` hooks ship and are tested, but `WireframeServer` and
  `handle_connection` do not drive them. The client's `call_streaming` works,
  so its sample uses a plain Tokio server.
- **The app factory runs once per connection.** 0.4.0 changes this to once
  per server run.
- **A preamble success handler cannot reject a connection.** Its error is
  logged and the connection proceeds; only a decode failure or a timeout closes
  it.
- **The read timeout is a housekeeping tick.** When `read_timeout_ms` elapses,
  expired partial messages are purged and the connection keeps waiting. Idle
  connections are not closed.
- **Codec recovery policies are not consulted.** `CodecError`,
  `RecoveryPolicy`, `RecoveryPolicyHook`, and `on_eof` exist, but any decoder
  error closes the connection.
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
package that depends on `wireframe = "=0.3.0"`. A panel is
`code.code(file, anchor)`, which includes the file and keeps the lines between
`// ANCHOR: name` and `// ANCHOR_END: name` (or `#` in TOML), the mdBook
convention. Each panel's bar says "Working example" in words, as the
specification's source taxonomy asks; shell commands are labelled as commands.
Tests hold every panel to consecutive lines of its file, every named anchor to
its file, the crate's wireframe and tokio-util versions to `template_vars`, and
every sample to containing no Jinja delimiters.

Run the samples with:

```bash
make wireframe-samples
```

It needs a Rust toolchain and the network, so it is not a commit gate. On
31 October 2026 all 13 test binaries passed with Rust 1.99.0. When the release
moves, bump the crate and `template_vars` together, rerun the samples, re-read
each "In 0.3.0" callout against the new release, and update the verification
date.

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
