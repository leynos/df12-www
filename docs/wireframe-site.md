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

The visual direction is "Wireframe | Visual identity and design language:
Common Signal", version 0.4 (18 November 2026), in
`../wireframe-reference/wireframe-visual-identity-v0.4.md`. It retains the
original mood book's palette and premise: a legible civic network drawn in
early-1980s X-Y vector geometry, with deliberate roads and junctions, crisp
line cores, limited local bloom, and generous near-black space. Version 0.4
superseded 0.3 on two points that govern this site: keep the existing home page
in its order, and let the plates play under ordinary motion settings, with
posters and Play controls only when the browser asks for reduced motion.

This branch, `wireframe-common-signal`, was cut from `0227ac5` at the owner's
request. A v0.3 pass made on `wireframe-www` (`f3c317b`) reorganized the home
page into four documentary chapters, which version 0.4 forbids; nothing was
taken from it except the checked logo hashes, which match.

- **Marque and tagline.** "Common Signal" is a small typographic marque beside
  the retained wordmark, as real text. The principal tagline, "What we connect,
  we should understand.", appears exactly in the hero and once in the closing
  strip.
- **Colour.** The daisyUI `wireframe` theme carries the seven roles: void
  `#040911`, cobalt `#477CF8` (structure), signal `#63EBF4` (information,
  focus, the primary action), flow `#38F49D` (the route taken, and links),
  capacity `#F04FA5` (budgets only), halt `#FE536C` (real stops only), and
  notice `#FFEB39` (notices and proposals). The supporting tokens are the
  identity's, plus three the audit required: `--color-ink-dim` `#8FA6B8` for
  captions (5.99:1 on raised), `--color-cobalt-text` `#7A9FFA` for cobalt as
  type (cobalt itself is 3.97:1 on raised), and `--color-tick` `#4F7896` for
  boundaries that identify a control (3.21:1 on raised). Every old use of mint,
  cyan, amber, and magenta was reassigned by meaning, not by hue: magenta no
  longer marks the current page or a correlated message (flow and explicit
  labels do), and amber no longer marks traffic.
- **Type.** Sintony (400 and 700) sets all interface and prose, with synthesis
  off. Monaspace Krypton (400 and 600) sets code, with ligatures off. Both are
  the Fontsource 5.3.0 Latin builds, self-hosted beside their OFL licences.
- **Logotype.** The site publishes the supplied raster master,
  `logotype.png`, at the owner's request.
  `scripts/build_wireframe_logo_assets.py` crops the master into a header
  lockup, a hero wordmark, a symbol, and PNG favicons, keying the near-black
  ground to alpha. Common Signal keeps these files exactly;
  `tests/fixtures/wireframe-logos.sha256` records their bytes, and their green
  is a deliberate exception to the palette. The wordmark no longer flickers on
  load.
- **Motion.** The plates move as described under [Plates](#plates). The
  journey rail keeps the original site's amber trace at the owner's request:
  `--color-trace` `#FFB347`, outside the palette and used for that trace and
  its stations only, with a three-layer halo and a pulse that runs down it
  every 2.8 seconds. Its stations light as they scroll past. Under reduced
  motion the rail is lit and still; under more contrast its halo and pulse go.
  The pulse is continuous motion without a pause control, as the plates now
  are. The deflection glitch on the hero line and the wordmark's ignition were
  removed: the identity excludes recurring glitches and logo motion.
- **Icons.** `src/static/wireframe/assets/icons/sprite.svg` draws frame,
  route, gates, pulses, fragments, outbound, proof, and budget on a 24 by 24
  grid.

### The four movements

The mood book's movements, the visible city, the public machine, bounds and
budgets, and operations in the open, are a visual and editorial vocabulary
across the existing sections, not a sitemap. Copy follows the identity's
register: a short heading, then the literal mechanism. The city is a setting;
no page implies a municipal customer, a hosted service, or live telemetry.

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
| `/wireframe/scope/`                       | Common Signal (field guide)      |
| `/wireframe/privacy-policy/` and siblings | Shared legal pages               |

The home page keeps the sections and order it had at `0227ac5`, as version 0.4
requires, with one owner-directed removal: the hero with its figure, now Plate
27; the capability row and release readout; three numbered panels (two working
examples and Plate 28), on a wider 105rem row; the "Frame. Route. Handle."
station track, with its anchors; the "What it carries" bento; mxd;
installation; and the tagline strip. On 19 November 2026, at the owner's
request, the "The scope" section's heading, copy, and colour key were removed;
its Plate 29 fly-through stays as a full-width band between the bento and mxd.
The field guide at `/wireframe/scope/` remains, linked from the footer. Two
bento cells swapped places so that the large-messages cell, with Plate 15 and
its RFC 0007 note, is the full-width plate cell; a cell holding playback
buttons cannot be a link, so its heading carries the link.

## Templates

- `_layout.jinja` is the chrome, `_article.jinja` the rail-and-column layout
  for getting started, the guides, and architecture.
- `data/pages.jinja` is the one catalogue of article titles, leads, sections,
  icons, upstream sources, and docs.rs paths. The guide index, the side rail,
  and each page's contents list read from it; a test holds the contents list to
  the page's section headings.
- `data/plates.jinja` catalogues every plate: its source title, kind
  (technical diagram, concept artwork, or civic setting), alt text, caption,
  and status line, with a source link where it has one. The `plate` macro
  renders the poster, the hidden controls, and the caption.
- `components.jinja` holds the macros that need no highlighting. `_code.jinja`
  holds the code panels, because they use the build-time `highlight` tag that
  the shared legal-page renderer does not load.
- `main_note` marks, at the point of use, what the library's main branch has
  changed since the candidate; `proposal` names an RFC with its status and link.

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
library's source at `cd634074`, with tokio-util 0.7.20. On 19 November 2026
they passed again, 29 tests in 13 binaries, with Rust 1.100.0, in a scratch
copy whose `[patch.crates-io]` points `wireframe` and `wireframe_testing` at an
export of `cd634074`; the `wireframe` lock entry was unchanged. When the
release moves, bump the crate and `template_vars` together, rerun the samples,
re-read each "In 0.4.0-alpha1" callout against the new release, and update the
verification date.

Some samples are not rendered at all, and exist to hold a page's claim to code
that ran: a rejected preamble closes, a silent client is disconnected, a
trailing byte fails decoding, `before_send` sees routed replies, an open
connection holds up the drain, and a pool opens its sockets on first use.

`SignalStyle` in `df12_pages/wireframe_highlighting.py` owns syntax colours, and
`scripts/generate_wireframe_pygments_css.py` writes
`src/styles/wireframe/syntax.css`. A test fails when the two disagree.

`copy-code.ts` adds a labelled copy control to each panel. Without script the
code is still selectable text in a keyboard-reachable region.

## Plates

Every illustration is a Three.js scene from
[leynos/wireframe-3js](https://github.com/leynos/wireframe-3js) at
`57be19c6183be36f5d4b811d31ea29bae3fdf251`, the pin the identity brief named.
The research for the brief inspected `94ed75af`; `57be19c` is newer and already
moves Plates 27 and 28 from the old site palette to the new roles, with
matching posters captured by the source's documented procedure. The source tree
states no licence for the original scenes; they are reused at the owner's
direction. Three.js's MIT licence is vendored beside the module.

| Plate | Title                 | Kind              | Where                                   |
| ----- | --------------------- | ----------------- | --------------------------------------- |
| 27    | One request's path    | Technical diagram | Home hero                               |
| 28    | Complexity, reduced   | Technical diagram | Home, third step                        |
| 15    | Independent budgets   | Concept artwork   | Home bento; RFC 0007, proposed          |
| 29    | Avenue fly-through    | Civic setting     | Home, full-width band                   |
| 04    | The threshold         | Civic setting     | Getting started                         |
| 08    | Routing table         | Civic setting     | Guide index                             |
| 07    | The envelope          | Concept artwork   | Routing guide                           |
| 12    | Inside the channel    | Concept artwork   | Codecs guide                            |
| 11    | Streams and datagrams | Concept artwork   | Streaming guide; RFC 0009, proposed     |
| 17    | Buffer instruments    | Concept artwork   | Large-messages guide; bars illustrative |
| 18    | Civic sphere          | Civic setting     | Client guide                            |
| 21    | Conformance harness   | Concept artwork   | Testing guide; RFC 0008, proposed       |
| 25    | Maintenance           | Civic setting     | Production guide                        |
| 03    | System architecture   | Civic setting     | Architecture                            |
| 30    | Transit panorama      | Civic setting     | Examples; field guide                   |
| 06    | Seven proposals       | Concept artwork   | Roadmap; RFCs 0003 to 0009, proposed    |
| 26    | The common signal     | Civic setting     | Field guide                             |

Every page but the middleware guide and the legal pages carries one. The
middleware guide has none: the nearest scene, Plate 13, draws a guarded core in
the capacity colour, which would misstate what middleware is. Plate 07's tag
reads `DATA-ID` and `ROUTE`; its caption says those are the artwork's labels,
not wireframe's field names.

Plate 27's labels were checked against the candidate's inbound path:
`FrameCodec` cuts frames, the envelope carries message ID 2 and correlation ID
7, the router selects one handler through middleware, and the reply keeps the
correlation ID. It omits optional reassembly and assembly, and says so. Its
reply path is violet (`#C9A2FF`, the source's civic-sphere colour), not
capacity magenta, and is labelled. Plates 09 and 16, whose payloads travel in
red, and Plate 11, which would imply datagram support, were not used. The old
gpt-image-2 rasters drew the retired palette's meanings and were removed.

Rebuild the vendored copy with:

```bash
make wireframe-plates WIREFRAME_3JS_SOURCE=../wireframe-3js
make check-wireframe-plates WIREFRAME_3JS_SOURCE=../wireframe-3js
```

The first exports the pin, applies `scripts/wireframe-plates/*.patch`, runs the
source's `make build` (Node.js 22 or later; `npm ci` against its lockfile,
Three.js 0.182.0, esbuild 0.28.2), and writes the module, the posters, the
licence, and `PROVENANCE.txt`; the second rebuilds and compares. Two builds
matched byte for byte. The module is 601,013 bytes (about 163 KB gzipped),
because it bundles Three.js and all 30 scenes. The seventeen posters total
about 1.3 MB, 12 to 177 KB each, and only the plates on a page are fetched.

The one local patch, `explicit-motion.patch`, adds an `allow-motion` attribute.
The pinned element always draws a fixed still when
`prefers-reduced-motion: reduce` matches, so without it a Play button under
reduced motion could not animate anything. The site sets it only from a Play
click, on that one element, and removes the element when the preference
changes. Global media queries are not spoofed and no permission is stored.

To add a plate, add its ID to `POSTERS` in the import script, rerun it, and add
a catalogue entry; a test fails if the two disagree.

### Playback

`plates.ts` is a classic script on every page. It imports the module only when
a plate may render, and never under reduced motion until Play.

| Situation                                    | Result                                                                                       |
| -------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Ordinary motion, page load                   | The hero's module load starts at once; the scene mounts and plays when in view, no Play gate |
| Ordinary motion, a plate scrolls into view   | It mounts and plays, with no controls                                                        |
| Reduced motion at load                       | Posters only, with **Play illustration**; no module, no WebGL                                |
| Play under reduced motion                    | That plate alone plays, with **Show still** to return it to the poster                       |
| Preference changes to reduce                 | Every scene is removed at once and every opt-in is forgotten                                 |
| Preference changes back                      | Plates in view play again                                                                    |
| No JavaScript                                | The poster and caption; controls stay hidden                                                 |
| No WebGL 2, a failed import, or context loss | The poster, with "Live illustration unavailable; showing the still."                         |
| `prefers-contrast: more` or forced colours   | Live scenes draw with low glow                                                               |
| Print                                        | The poster and caption; no controls                                                          |

At most four plates keep a renderer. Mounting one more releases the least
recently seen plate that is out of view; a plate in view is never released. No
page shows more than four plates, so in practice the cap only bounds contexts
kept by plates that have scrolled away. The element suspends its own frames off
screen and in a hidden tab, and caps itself at 30 frames a second.

The element is hidden from assistive technology. The poster's `alt` and the
caption are the plate's one description; a civic setting's poster has empty alt
text. The buttons are native, outside the art, 44 pixels tall, and described by
the plate's title.

The identity asks for a Pause control on every autoplaying plate and an
optional glow control. The owner removed both on 19 November 2026. The plates
therefore move for longer than five seconds with no way to stop them under
ordinary motion, which WCAG 2.2's Pause, Stop, Hide criterion (2.2.2) asks for;
a visitor who needs stillness has to set the browser's reduced-motion
preference, which the site honours. Restore a Pause control before claiming
WCAG 2.2 AA conformance for the plates.

## Release evidence

The copy distinguishes four targets, and each claim names its own:

| Target                       | Evidence                                                                                       | Used for                                                   |
| ---------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 0.3.0, released              | crates.io                                                                                      | mxd's dependency; the migration starting point             |
| 0.4.0-alpha1 candidate       | Library source at `cd634074`; the samples ran against it on 7 November 2026                    | Every guide and working example                            |
| main at `7351347`            | Read on 18 November 2026 (README, ADR 0017, roadmap, source); not compiled against the samples | `main_note` asides and the roadmap's "Since the candidate" |
| Proposals, RFCs 0003 to 0009 | `docs/rfcs/rfc-000N-*.md` at `7351347`, each "Status: proposed"; roadmap phase 21 unticked     | Proposal labels, links, and concept-artwork captions       |

On 18 November 2026 the `v0.4.0-alpha1` tag still did not exist, crates.io
listed 0.3.0 as the newest release, and `cd634074` was not an ancestor of the
library's main branch: it sits on a recovered side branch, and main's
`Cargo.toml` still says 0.3.0. So the candidate's guides remain the site's
evidence, labelled as unpublished, and where main has since diverged the page
says so at the point of use:

- `route_response` handlers return a `Response`, and every server connection
  runs a `ConnectionActor`, so streamed replies reach the wire (#888).
- ADR 0017 removes the extractor building blocks and `app_data` (#902).
- `stop()` ends idle connections at their read boundary, so an idle peer no
  longer holds up `drained`; `production.rs`'s shutdown sample would fail
  against main.
- Teardown runs once on a connection-local runtime (#886), and the
  active-connection gauge counts accepted sockets.

Push queues, `SessionRegistry`, request bodies, `on_eof`, recovery policies,
and the codec error metric remain unwired on main. When a release is cut from
main, retarget the samples, recheck every guide, and remove the notes that no
longer apply.

## Checks

Run the contributor guide's gates, rebuild with `bun run build`, and inspect
the pages at 1440, 1280, 1024, 768, 390, and 320 pixels.
`tests/test_wireframe_build.py` checks routes, local links and fragments,
sample parity, generated assets (the syntax partial and the keyed logotype),
the protected logo bytes, the vendored plates against their provenance, plates
that stand without script, the home page's section order and station anchors,
the marque and tagline, proposal labels beside every RFC link, release
boundaries, and legal pages. `tests/js/wireframe-plates.test.mjs` drives the
playback table above with fakes. `tests/test_wireframe_browser.py`, marked
`playwright`, runs axe over every page at 390 and 1440 pixels, checks that
nothing but a code or table region scrolls sideways at 320, and runs the real
runtime in both motion modes.
