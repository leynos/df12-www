# wireframe sub-site: site map and copy

This document records the plan for the sub-site at `/wireframe/`: the concept,
the site map, the copy, the imagery, and the evidence the copy rests on. It is
the brief the templates were built from. Once the templates hold the copy, they
are authoritative and this file records why they say what they say.

## Sources of truth

- The released crate, `wireframe` 0.3.0 on crates.io, published 6 April 2026.
  Every claim on the site describes 0.3.0 unless it is labelled as unreleased.
- The user's guide as tagged at `v0.3.0` (`docs/users-guide.md`), not the
  guide on the default branch, which already documents breaking 0.4.0 changes.
- The published crate source under `~/.cargo/registry/src/*/wireframe-0.3.0`,
  which settles any disagreement between the guide, the README, and the code.
- The sample crate under `templates/wireframe/samples/`, which compiles and
  runs every code panel against 0.3.0 (`make wireframe-samples`).
- The design reference in `../wireframe-reference/`: the logotype, the colour
  and beam system, the prototype mockup, and the journey flow.

### Findings that shape the copy

1. **wireframe 0.3.0 does not compile against tokio-util 0.7.20.** That
   release adds `Encoder<&[u8]> for LengthDelimitedCodec`, so
   `framed.send(bytes.into())` in `src/app/inbound_handler.rs` no longer infers
   a type (E0283). A fresh `cargo add wireframe` resolves 0.7.20 and fails.
   Pinning `tokio-util` to 0.7.19 in the lockfile fixes it. The upstream
   default branch still locks 0.7.19, so the break is not yet visible there.
   The getting-started page states the pin plainly.
2. **Routed handlers return nothing.** A 0.3.0 handler is
   `Arc<dyn Fn(&Envelope) -> Pin<Box<dyn Future<Output = ()>>>>`. The default
   `HandlerService` echoes the request payload; replies are written in
   middleware through `ServiceResponse::frame_mut()`. The README's
   extractor-style handlers (`handle_login(req: Message<Login>)`) describe the
   design direction, not the release. The mockup's derive macros and string
   routes are fiction and do not appear.
3. **Push queues, the connection actor, and streaming responses are building
   blocks.** `PushQueues`, `ConnectionActor`, `Response::Stream`, and
   `Response::MultiPacket` ship and are tested, but `WireframeServer` and
   `handle_connection` do not drive the connection actor in 0.3.0: a routed
   request gets one reply. The streaming guide says so and shows the actor
   driven directly.
4. **The client consumes streams.** `WireframeClient::call_streaming` and
   `receive_streaming` read multi-frame responses that end in a terminator the
   envelope recognizes through `Packet::is_stream_terminator`.

## Concept: the night yard

Serious tools, playful worlds. The serious tool is a frame router; the playful
world is a railway marshalling yard drawn in vector light, worked at night.

Frames are freight. A byte stream arrives as a train; the codec uncouples it
into wagons at each length prefix; middleware weighs and stamps each wagon; the
router reads the waybill, its message ID, and throws the points so the wagon
runs down the right siding to its handler. Long loads are split across several
wagons and rejoined before anyone unloads them. The reply leaves the same way
it came in.

The metaphor carries real structure: sidings are routes, the waybill is the
envelope, the weighbridge is middleware, the uncoupler is the codec, the
coupling train of fragments is fragmentation, and the express and slow lines
are high- and low-priority push queues.

### The night shift (product-specific characters)

The core Logisphere crew does not appear. Three wireframe creatures work the
yard, each mapped to one layer. Their key appears on first use (the home page)
and on the field-guide page.

| Character | Creature                                    | Station        | Concept     | Beam colour |
| --------- | ------------------------------------------- | -------------- | ----------- | ----------- |
| Snip      | A wireframe crab with cutter claws          | Arrival throat | Frame codec | Cyan        |
| Octa      | An owl whose body is the logo's octahedron  | Signal tower   | Router      | Vector mint |
| Tally     | A tortoise with a geodesic shell and a lamp | Weighbridge    | Middleware  | Amber       |

The marked wagon, the one frame the page follows, is magenta: the beam system
reserves magenta for the selected and the rare.

Characters illustrate; they do not narrate. Body copy stays in the df12 voice
and never explains the conceit.

## Visual system

The direction comes from the supplied colour and beam system: flat colour is
authoritative; glow is optional emphasis. Every drawn element has a crisp core,
faint structure behind it, and at most a soft halo.

- **Ground.** Night `#030E0C` for the page, `#091A16` for panels, `#102720`
  for raised panels. One theme, dark only: the brand is light drawn on a dark
  screen, and a paper variant would be a different brand.
- **Beams.** Vector mint `#7CFFB3` is the signal and the primary action. Cyan
  `#00FFFF` marks frames and data. Amber `#FFB347` marks the active path.
  Magenta `#FF6AD5` marks the selected and the rare: the current page, the
  marked wagon. Ink `#F1FFF8` is readable text.
- **Structure.** Hairlines and a faint perspective grid in a dim mint. Corners
  are square; panels carry small registration ticks at their corners, as the
  mockup's frame does. Radius is zero everywhere.
- **Type.** Martian Mono, a wide technical monospace with a width axis, sets
  display type, labels, navigation, and code (code at a narrower width). Geist
  sets body copy. Both are OFL and self-hosted.
- **Glow.** A halo appears on the logotype, the hero beam, and the focus ring.
  It never carries meaning, and the flat colour underneath always meets
  contrast on its own.
- **Motion.** The marked wagon travels the home page's journey track as the
  section scrolls through view (a CSS scroll-driven animation). It conveys the
  order of the pipeline. Under `prefers-reduced-motion` it sits still at the
  router.

## Site map

Eighteen routes: the home page, fourteen content pages, and the three shared
legal pages.

| Route                                | Title                            | Job                                                         |
| ------------------------------------ | -------------------------------- | ----------------------------------------------------------- |
| `/wireframe/`                        | Binary protocols, routed.        | State the thesis, follow one frame, show real code.         |
| `/wireframe/getting-started/`        | A first server, end to end.      | Add the crate, route a message, answer it, call it.         |
| `/wireframe/guides/`                 | Guides                           | Index the eight task guides.                                |
| `/wireframe/guides/routing/`         | Routes, envelopes, and handlers  | Message IDs, `Envelope`, custom `Packet` types.             |
| `/wireframe/guides/codecs/`          | Frame codecs and preambles       | Length-delimited defaults, `FrameCodec`, preambles, errors. |
| `/wireframe/guides/middleware/`      | Middleware and lifecycle hooks   | Answer in middleware; setup, teardown, protocol hooks.      |
| `/wireframe/guides/streaming/`       | Streaming, push, and sessions    | `Response`, push queues, the connection actor, sessions.    |
| `/wireframe/guides/large-messages/`  | Fragmentation and memory budgets | Fragmenter, reassembly, assembly, budgets.                  |
| `/wireframe/guides/client/`          | The client runtime               | Builder, correlated calls, streams, pools.                  |
| `/wireframe/guides/testing/`         | Testing at the frame             | `testkit` drivers: partial frames, fragments, slow I/O.     |
| `/wireframe/guides/production/`      | Running in production            | Workers, readiness, shutdown, backoff, metrics.             |
| `/wireframe/architecture/`           | The yard, layer by layer.        | The pipeline, the vocabulary, the layering order.           |
| `/wireframe/examples/`               | Worked examples                  | The upstream examples, and mxd.                             |
| `/wireframe/roadmap/`                | Released, next, and further out. | 0.3.0 today, the unreleased 0.4.0 changes, the road to 1.0. |
| `/wireframe/yard/`                   | The night yard                   | The field guide: cast, beams, type, provenance.             |
| `/wireframe/privacy-policy/` and kin | Shared legal pages               | Netsuke layout; no cast, no art.                            |

Primary navigation: `← df12`, Home, Get started, Guides, Architecture,
Examples, Roadmap; then API (docs.rs, external) and GitHub; then the primary
action, Get started. The API reference is docs.rs for 0.3.0 rather than a
transcription: rustdoc is generated from the release and cannot drift from it.

## Copy

House rules: df12 voice (compressed, precise, dry, grounded, playful);
en-GB-oxendict; impersonal constructions outside calls to action; headings in
sentence case; no startup vocabulary; one label per intent (Get started, View
on GitHub, Read the guide).

### Home

- **Title:** wireframe · Binary protocols, routed.
- **Description:** A Rust framework for servers and clients that speak custom
  binary protocols. Frame the bytes, route by message ID, and keep the protocol
  out of the business logic.

**Hero.**

- Eyebrow: A Rust framework for binary protocols
- Heading: the wireframe logotype, then "Binary protocols, routed."
- Deck: Frame the bytes, route by message ID, wrap it all in middleware.
  Actix Web's shape, for everything that isn't HTTP.
- Actions: Get started · View on GitHub
- Plate: the night yard. Snip at the arrival throat, Octa in the signal
  tower, amber points fanning out to three sidings, one magenta wagon.

**Manifest strip** (below the hero, four cells):

- `0.3.0` · On crates.io since 6 April 2026
- `Tokio` · Async I/O underneath, one worker per core by default
- `ISC` · Licence
- `mxd` · The first server built on it

**Follow one frame.** Every request takes the same route through the yard.
Bytes arrive, a codec cuts them into frames, middleware weighs each one, and
the router sends it down the siding its message ID names. The reply leaves the
way it came.

| Station     | Line                     | Detail                                                                         |
| ----------- | ------------------------ | ------------------------------------------------------------------------------ |
| Arrival     | Bytes off the socket     | A Tokio stream. An optional preamble is read and validated first.              |
| Uncoupling  | Cut at the length prefix | `FrameCodec` decodes frames: by default a 4-byte big-endian prefix, 1 KiB cap. |
| Rejoining   | Long loads, reassembled  | Optional fragment reassembly, bounded by size and time.                        |
| Waybill     | Read the envelope        | Message ID, correlation ID, payload bytes.                                     |
| Weighbridge | Weigh and stamp          | Middleware wraps every request and every reply.                                |
| Points      | Route by message ID      | One handler per ID; registering an ID twice fails at setup.                    |
| Siding      | Do the work              | The handler runs with the envelope it was sent.                                |
| Departure   | Serialize, frame, send   | The reply goes back through middleware, the serializer, and the codec.         |

**Define. Route. Serve.** Two panels cut from the sample crate: the messages
and the application, then the server and a client call.

- Note: The handler observes; middleware writes the reply. In 0.3.0 a routed
  handler returns nothing, and the default reply echoes the request payload.
- Proof line: Compiled and run against wireframe 0.3.0 on {date}.

**What the yard handles.** Six cells, each linking to its guide:

- Bring your own framing. `FrameCodec` describes any wire format. Hotline,
  MySQL, and RESP codecs ship as worked examples.
- Answer in middleware. `from_fn` for a closure, `Transform` for a reusable
  layer; setup and teardown hooks for per-connection state.
- Long loads, bounded. Fragmentation, message assembly, and per-connection
  memory budgets that pace reads at 80% and abort at the cap.
- Push and streams, as parts. Priority push queues, a fair connection actor,
  and multi-frame responses, ready to drive.
- The same rails, outbound. `WireframeClient` shares the codec and serializer,
  correlates replies, consumes streams, and pools sockets.
- Test at the frame. Feed partial frames one byte at a time, fragment
  payloads, and pace slow readers under paused time.

**The night shift.** Three hands work the yard.

- Snip, the uncoupler, cuts the incoming train at every length prefix. The
  codec.
- Octa, the yardmaster, reads each waybill and throws the points. The router.
- Tally, at the weighbridge, weighs and stamps every wagon in both
  directions, and does not hurry. Middleware.

**Already carrying traffic.** mxd, df12's Hotline server, runs on wireframe
0.3.0. Its transport adapter frames and routes the Hotline protocol; its domain
crate never imports wireframe. Link: Read about mxd.

**Add it to Cargo.toml.** The dependency block from the sample crate, then:
wireframe 0.3.0 does not build against tokio-util 0.7.20. Pin 0.7.19 until a
fixed release: `cargo update -p tokio-util --precise 0.7.19`.

### Getting started: A first server, end to end

Intro: Add the crate, route one message, answer it in middleware, and call it
from a client in the same process.

1. **Add the dependencies.** wireframe 0.3.0, Tokio, and bincode 2. The pin.
2. **Describe the messages.** `bincode::Encode` and `BorrowDecode` derive
   `Message` for any type; `to_bytes` and `from_bytes` come with it.
3. **Route and answer.** Register a handler under message ID 1; a `from_fn`
   middleware decodes the `Ping`, calls the handler, and writes a `Pong`.
4. **Serve it.** `WireframeServer::new(factory).bind(addr)?` and
   `run_with_shutdown`. Port 0 and `local_addr` for tests; `ready_signal` to
   know when it is listening.
5. **Call it.** `WireframeClient::builder().connect(addr)` and
   `call_correlated`, which stamps a correlation ID and checks the reply
   carries it back.
6. **Next.** Routing, codecs, middleware, testing.

### Guides

Each guide opens with a one-sentence lead, holds three to five sections, and
links the matching docs.rs pages and upstream source.

- **Routes, envelopes, and handlers.** Lead: A message ID picks the handler;
  the envelope carries everything else. Sections: register routes (and the
  duplicate-route error); the bundled `Envelope`; bring your own `Packet`;
  correlation IDs and `inherit_correlation`; route without decoding through
  `FrameMetadata`.
- **Frame codecs and preambles.** Lead: Framing is a trait, not a fork.
  Sections: the defaults (length-delimited, 4-byte big-endian, 1024-byte
  frames, 100 ms read timeout); `buffer_capacity` and `with_codec`; write a
  `FrameCodec`; validate a preamble; codec errors and recovery policies.
- **Middleware and lifecycle hooks.** Lead: Handlers observe; middleware
  answers. Sections: `from_fn`; `Transform` for reusable layers; write the
  reply; connection setup and teardown; protocol hooks; accept two message
  versions.
- **Streaming, push, and sessions.** Lead: 0.3.0 ships the parts for
  server-initiated traffic; the routed connection path does not drive them yet.
  Sections: the `Response` variants; multi-packet channels and back-pressure;
  priority push queues and fairness; driving the connection actor; the session
  registry.
- **Fragmentation and memory budgets.** Lead: Long loads cross the yard in
  pieces and are rejoined before anyone unloads them. Sections: enable
  fragmentation; the `Fragmenter` and `Reassembler`; protocol-level message
  assembly; the three-tier memory budget.
- **The client runtime.** Lead: The client runs on the same rails: same codec,
  same serializer, same envelope. Sections: build and connect; correlated
  calls; consume a stream; hooks and tracing; pools (`pool` feature).
- **Testing at the frame.** Lead: Networks deliver bytes in whatever pieces
  they like; tests should too. Sections: enable `testkit`; drive an app with
  codec payloads; partial frames, one byte at a time; fragments; slow readers
  and writers.
- **Running in production.** Lead: The server is a typestate, a worker pool,
  and an accept loop that backs off. Sections: bind and workers; readiness and
  shutdown; accept backoff; read timeouts and the failure threshold; metrics.

### Architecture: The yard, layer by layer

Intro: Four layers, four nouns, one fixed order. Sections: the vocabulary
(frame, envelope, message, fragment); the inbound path; the outbound path;
where state lives (app data, per-connection state, sessions); what 0.3.0 does
not do yet.

### Examples: Worked examples

Intro: The upstream repository ships runnable examples; mxd is the full-size
one. Cards for echo, ping_pong, packet_enum, metadata_routing, hotline_codec,
mysql_codec, resp_codec, client_echo_login, async_stream, and multi_packet,
each with its command (`cargo run --example <name> --features examples`) and
what it demonstrates; then mxd.

### Roadmap: Released, next, and further out

Intro: 0.3.0 is the release. 0.4.0 is in progress on the default branch and
breaks things on purpose. Sections: in 0.3.0; unreleased (prepared application
root, `ClientError` and `ServerError` non-exhaustive, `PoolSaturated`, bounded
peer decoding, `SocketOptions::linger` removed); toward 1.0 (zero-copy
payloads, formal verification of message assembly, client ergonomics).

### The night yard (field guide)

Intro: How the sub-site is drawn, and who works the yard. Sections: the night
shift and their stations; the beam system with contrast figures; type;
illustration provenance (gpt-image-2, date, prompt grammar); what never appears
(legal pages carry no cast and no art).

## Imagery

Every raster is generated with gpt-image-2 and carries no text: labels,
captions, and numbers are HTML. The prompt grammar is constant: thin luminous
vector lines on a near-black green ground, crisp cores with a soft halo, a
faint perspective grid, vector mint for structure, cyan for frames, amber for
the active path, one magenta accent at most; no fills beyond faint translucent
planes; no text, numbers, logos, or UI chrome.

| File                      | Use                  | Scene                                                                 |
| ------------------------- | -------------------- | --------------------------------------------------------------------- |
| `night-yard`              | Home hero            | The whole yard: arrival train, Snip, signal tower with Octa, sidings. |
| `cast-snip`               | Cast, field guide    | Snip at the arrival throat, claws open over a coupling.               |
| `cast-octa`               | Cast, field guide    | Octa in the signal tower, one wing on a points lever.                 |
| `cast-tally`              | Cast, field guide    | Tally on the weighbridge, a wagon on the scale.                       |
| `long-load`               | Large messages guide | One long load carried by a rake of coupled wagons.                    |
| `two-lines`               | Streaming guide      | Express and slow lines merging at a junction under a fair signal.     |
| `outbound`                | Client guide         | A small locomotive leaving the yard on the same rails.                |
| `proving-loop`            | Testing guide        | A test loop with a wagon fed through in pieces.                       |
| `yard-under-construction` | Roadmap              | Unbuilt sidings drawn as dashed construction lines.                   |

Each image is encoded to WebP at full and half width; the sub-site's images sit
outside the main `build:images` step.
