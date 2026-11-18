# wireframe sub-site

The sub-site at `/wireframe/` documents wireframe, the Rust router for
frame-based binary protocols that mxd runs on. It publishes 18 routes: the home
page, 14 content pages, and the three shared legal pages. The parent homepage
links it from its libraries group.

This document records where the site's facts come from, what the release
taught, how the identity was applied, and how the code and art were made.

## Evidence checked on 18 November 2026

The site baseline was `0227ac5`. The sparse registry indices for
[wireframe](https://index.crates.io/wi/re/wireframe) and
[wireframe_testing](https://index.crates.io/wi/re/wireframe_testing) end at
0.3.0. Upstream has no alpha release tag. The API link opens published 0.3.0.

- **Development.** The
  [README](https://github.com/leynos/wireframe/blob/7351347e1965260a4f6b5292a44e8ca1af9d8364/README.md)
  documents frame codecs, message-ID routing and middleware. Routed handlers
  receive the envelope by reference. Accepted ADR 017 removes extractors.
- **Alpha in development.**
  [PR 873](https://github.com/leynos/wireframe/pull/873) is open. The site is
  developed alongside its alpha. The unchanged sample package passed 29 tests
  on Rust 1.100.0 against head `d1e4fd8170dddf67f6f300b961de52f078d527a2` with
  a locked offline build. The source base links to that commit. The registry
  manifest remains pinned.
- **Standalone components.** The alpha actor and push queues have their
  own tests. The sample server does not drive them.
- **Proposed.**
  [RFCs 0003–0009](https://github.com/leynos/wireframe/tree/7351347e1965260a4f6b5292a44e8ca1af9d8364/docs/rfcs)
  describe future contracts. Their artwork illustrates proposals.

## Sources and release status

The technical guides describe the development source for wireframe
0.4.0-alpha1, targeted for 15 November 2026, with proposals identified
separately. The sources are, in order of authority:

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
- `source_base` points to the tested PR head. The header
  links to the published API. Keep the alpha deployment on hold.
- `wireframe_published: false` makes pages call the date a target.

At publication, in this order:

1. Confirm the published crates: `wireframe` and `wireframe_testing`, both at
   the same version, since the testing page names the latter. If the library
   stack changed after the tested PR head, re-read the claims it touched.
2. Run `cargo update -p wireframe` in `templates/wireframe/samples/`, then
   `make wireframe-samples`.
3. Set `wireframe_published: true`, the true release date, and
   `samples_verified_against: "wireframe 0.4.0-alpha1"`, and update
   `rust_verified` and `samples_verified_on`. A test holds the flag to the
   lockfile, so doing only one fails the build tests.
4. Update `published_api_version`, `source_base` and `docs_url` together.
   Verify the API links and replace the temporary checkout instructions on
   Getting started with the registry command.
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
  `Response::Stream`, `Response::MultiPacket`, `SessionRegistry`, and recovery
  policies exist and are tested, but `WireframeServer` does not drive them. Of
  the protocol hooks, only `before_send` runs on a server connection. The
  client's `call_streaming` works, so its sample uses a plain Tokio server.
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

## Common Signal

Visual identity v0.3 (18 November 2026) retains the green Wireframe marks,
Sintony and Monaspace Krypton. Cobalt gives the city structure, cyan identifies
information, green follows a route and magenta represents capacity. Red marks
failure and yellow calls attention to a proposal. The field guide at
`/wireframe/scope/` describes all seven roles. The four home sections move from
city routes through message processing and resource budgets to testing.
Mechanism guides use text and code. Legal notices share only the site chrome.

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

## Templates

- `_layout.jinja` is the chrome, `_article.jinja` the rail-and-column layout
  for getting started, the guides, and architecture.
- `data/pages.jinja` is the one catalogue of article titles, leads, sections,
  icons, upstream sources, and docs.rs paths. The guide index, the side rail,
  and each page's contents list read from it; a test holds the contents list to
  the page's section headings.
- `data/plates.jinja` catalogues every illustration with its title,
  interpretation and status, rendered by the `plate` macro.
- `components.jinja` holds the macros that need no highlighting. `_code.jinja`
  holds the code panels, because they use the build-time `highlight` tag that
  the shared legal-page renderer does not load.

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

To repeat the alpha check without editing the published sample manifest, export
the pinned PR head (fetch `refs/pull/873/head` if needed) to a scratch
directory and run from the site root:

```bash
cargo test --locked --offline --manifest-path templates/wireframe/samples/Cargo.toml \
  --config "patch.crates-io.wireframe.path='/absolute/path/to/export'"
```

Some samples are not rendered at all, and exist to hold a page's claim to code
that ran: a rejected preamble closes, a silent client is disconnected, a
trailing byte fails decoding, `before_send` sees routed replies, an open
connection holds up the drain, and a pool opens its sockets on first use.

`ScopeStyle` in `df12_pages/wireframe_highlighting.py` owns syntax colours, and
`scripts/generate_wireframe_pygments_css.py` writes
`src/styles/wireframe/syntax.css`. A test fails when the two disagree.

`copy-code.ts` adds a labelled copy control to each panel. Without script the
code is still selectable text in a keyboard-reachable region.

## Reproducing the illustrations

The site builds and serves the checked-in files under
`src/static/wireframe/assets/vendor/plates/`. Only maintainers reproducing the
vendor import need Node 22+ and the atlas source. From the site checkout:

```bash
git clone https://github.com/leynos/wireframe-3js.git /tmp/wireframe-atlas
scripts/import-wireframe-plates.sh /tmp/wireframe-atlas
```

The importer exports commit `94ed75af8b92fb63064c7fc5bb6c7ddb77acf7c9`, builds
with its
[npm lockfile](https://github.com/leynos/wireframe-3js/blob/94ed75af8b92fb63064c7fc5bb6c7ddb77acf7c9/package-lock.json)
(Three.js 0.182.0 and esbuild 0.28.2), and copies the ES module, Three.js
notice, and the original posters from the distribution. Plates 29, 15 and 25
use the original geometry and colours. The upstream build copies these stills
from `demo/posters`. The dependency notice covers Three.js.

The page loads a small host module. Play imports the atlas and creates one
element. Its shadow root owns its canvas, observers and render loop. All
controls and captions are HTML outside the shadow. Pause, a reduced-motion
change, context loss or starting another plate removes the instance and
disposes its GPU context. Returning to the page keeps an explicitly paused
scene still. Reduced motion takes precedence over playback.

## Checks

Run the contributor guide's gates, rebuild with `bun run build`, and inspect
the pages at 1440, 1280, 1024, 768, 390, and 320 pixels.
`tests/test_wireframe_build.py` checks routes, local links and fragments,
sample parity, poster-first rendering, generated assets (the syntax partial and
the keyed logotype), release boundaries, and legal pages.
`tests/test_wireframe_browser.py`, marked `playwright`, runs axe over every
page at 390 and 1440 pixels and checks that nothing but a code or table region
scrolls sideways at 320.

### Common Signal delivery evidence

On 18 November 2026 Chromium rendered all 18 routes at widths of 1440, 1280,
1024, 768, 390 and 320 CSS pixels. All 108 layouts fit their viewport. Each
route also fit at 320px with 200% text and with WCAG text spacing. The original
masthead and long references needed wrapping at enlarged sizes. The documents
retain keyboard-reachable code and table scrollers.

The original home loaded a canvas driver for its two SVG drawings. The new page
requests the avenue still, a 3,533-byte playback controller and the existing
copy script. The other two posters use native lazy loading. Chromium requested
zero atlas bytes before Play. With an uncompressed local HTTP server, Resource
Timing reported these body and transfer sizes:

| Asset              | Body bytes | Transfer bytes |
| ------------------ | ---------: | -------------: |
| Avenue poster      | 71,192     | 71,492         |
| Budgets poster     | 14,426     | 14,726         |
| Maintenance poster | 32,342     | 32,642         |
| Optional atlas     | 599,120    | 599,420        |

Switching plates left one live WebGL context. Pause released it. Draw calls
stopped offscreen and on a simulated hidden-tab event. Changing reduced motion
while playing disposed the instance. Scrolling, resizing and restoring
visibility left the poster in place. The artwork occupied the same box before
and after enhancement. All captions and navigation remained readable with
JavaScript disabled, a rejected module import or failed WebGL creation. After
context loss, Play created a fresh context. Print hid the controls.

Rendered body text on Void measured 18.27:1. Plate captions on their panel
measured 8.46:1, playback text and borders 12.43:1, and the quiet control
border on the raised surface 3.95:1. Cobalt on that surface measured 3.97:1 and
is used for structure. Hashes in the logo test fixture cover the two responsive
wordmark sizes, three lockups, symbol and favicons.

[Desktop](evidence/wireframe/desktop.webp) ·
[Phone](evidence/wireframe/narrow.webp) ·
[Reduced motion](evidence/wireframe/reduced.webp) ·
[WebGL context loss](evidence/wireframe/fallback.webp)
