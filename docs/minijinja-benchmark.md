# MiniJinja build benchmark

Replacing Jinja2 3.1.6 with MiniJinja 3.1.0 reduced the mean wall-clock time for
`pages generate --all-sites` from 33.56 s to 7.23 s (4.64× as fast). The
workload generated 940 HTML pages from the main site and its eight sub-sites.

## Page generation

| Wall-clock component | Jinja2   | MiniJinja | Change    |
| -------------------- | -------: | --------: | --------: |
| Template processing  | 26.988 s | 0.843 s   | −26.145 s |
| Other work           | 6.576 s  | 6.387 s   | −0.189 s  |
| Overall              | 33.565 s | 7.230 s   | −26.334 s |

Each figure is the mean of five fresh processes per engine, measured from
launch to exit. The runs were interleaved in pairs with the order reversed
between pairs. Totals ranged from 32.96 to 34.64 s with Jinja2 and from 6.94 to
7.41 s with MiniJinja.

Monotonic timers covered environment construction, named template loading,
compilation and rendering. Nested engine calls counted once. The Pygments
`highlight()` call was timed separately and counted under other work, along
with process startup, HTTP replay, Markdown and Mermaid rendering, file I/O and
logging. The template figure includes the Python glue around the engine. The
0.19 s change elsewhere falls within the observed run-to-run variation.

## Complete website build

Three measured `bun run build` invocations per engine included asset copying,
TypeScript compilation, Tailwind, image processing, page generation and search
index generation. One unmeasured build per checkout warmed the asset outputs.
The page generator used each checkout's locked environment, the same HTTP
replay and the same template timers as above.

| Wall-clock component | Jinja2   | MiniJinja | Change    |
| -------------------- | -------: | --------: | --------: |
| Template processing  | 25.106 s | 0.833 s   | −24.273 s |
| Other work           | 20.070 s | 19.762 s  | −0.309 s  |
| Overall              | 45.176 s | 20.595 s  | −24.581 s |

## Scalene profile

Scalene 2.4.0 profiled a separate all-sites run per engine with
`scalene run --cpu-only --profile-all`. Its elapsed time fell from 44.74 s to
8.50 s. Jinja2's lexer and syntax-tree nodes accounted for 7.1% and 7.9% of the
baseline CPU samples, respectively. The wall-clock partition above uses timers
so that work in the native MiniJinja extension and time waiting on other
processes are included.

## Inputs and output checks

Both versions ran on CPython 3.13.11 under Linux on an AMD Ryzen Threadripper
PRO 3955WX, with the same eight logical CPUs available. The baseline was commit
`88df2d66b7af1c1d98c6f0e3dd9699a4835ce743`. Both read the same configuration
and replayed the same 126 HTTP responses from disk, including GitHub's
unavailable optional metadata responses. Timed runs executed the Mermaid CLI
and wrote the generated pages to separate, warm output trees. Live network
latency will affect builds that fetch their inputs again.

A separate output comparison also replayed identical Mermaid SVGs because the
diagram renderer varies some path coordinates across invocations. Of the 940
HTML files, 930 matched byte for byte. The remaining ten matched after HTML
parsing and collapsing ordinary whitespace, preserving whitespace inside code
blocks. Their computed-style and layout checks matched in Chromium. The
representative Episodic roadmap Syrupy snapshot was recorded with Jinja2 and
passed unchanged with MiniJinja.

The two complete builds published the same asset paths. Tailwind also detects
the MiniJinja `filter` keyword as a possible CSS class, which added 1,833
uncompressed bytes to the Episodic stylesheet. No generated Episodic element
uses that class. The Netsuke search indexes differed only in their build
timestamps.

The initial November run differed from the committed Netsuke browser baseline
on ten forthcoming pages whose headings include the build date. All 40
normalized computed-style snapshots per viewport matched between Jinja2 and
MiniJinja on this host. The browser test build now sets `SOURCE_DATE_EPOCH` to
2 October 2026 to reproduce the heading widths in the committed captures.

## Free-threaded document workers

The follow-up benchmark uses the MiniJinja site at commit `8648fe2` as the
starting point. Run the workers with CPython 3.15.2t as follows.

```bash
uv python install cpython-3.15.2+freethreaded-linux-x86_64-gnu
uv run --locked --no-dev --python 3.15.2t pages generate --all-sites --doc-workers 8
```

For the complete website build, Bun passes the following environment settings
through to `uv run pages generate --all-sites`.

```bash
UV_PYTHON=3.15.2t UV_NO_DEV=1 INPUT_DOC_WORKERS=8 bun run build
```

The worker-count sweep used the same eight logical CPUs and frozen HTTP
responses as the original benchmark. Each timing includes a fresh process, real
Mermaid execution and writing all generated files. The timed processes reported
the GIL disabled at exit.

| Document workers | Mean over three builds |
| ---------------: | ---------------------: |
| 1                | 8.34 s                 |
| 2                | 7.34 s                 |
| 4                | 6.13 s                 |
| 8                | 5.34 s                 |

Every run of `_write_documents` logs the effective worker count beside the
configured limit, the bundle count, each bundle's render time and that site's
total write time at `INFO` on standard error. `generate` adds one further line
for the whole invocation, so a maintainer can follow a normal build without the
benchmark harness:

```bash
uv run --locked --no-dev --python 3.15.2t pages generate --all-sites --doc-workers 8
```

These log lines describe the work inside one process; they are not the
fresh-process figures in the tables above. `_write_documents` runs once per
site, so its total covers that site's ordered writes plus the waits between
batches, and its worker count is the smaller of the limit and that site's
bundle count. The `generate` total spans every requested site, but starts after
configuration is loaded and stops before the process exits. Comparing either
with the sweep means accounting for interpreter start-up, configuration loading
and the sites that have no document bundles; the sweep remains the recorded
measurement, and these lines are a sanity check on its shape rather than a
reproduction of it.

A separate interleaved run compared the previous MiniJinja commit with the
worker implementation. The 3.15.2t controls used the same interpreter and
locked dependencies, with `PYTHON_GIL=1` for the GIL-enabled cases. Each cell
is the mean of three all-sites page-generation runs.

| Runtime                           | One worker | Eight workers |
| --------------------------------- | ---------: | ------------: |
| CPython 3.13.11, commit `8648fe2` | 7.58 s     | —             |
| CPython 3.15.2t, GIL enabled      | 8.80 s     | 10.01 s       |
| CPython 3.15.2t, GIL disabled     | 8.70 s     | 5.63 s        |

Eight workers with the GIL disabled cut page-generation time by 35.3% against
the one-worker run on the same interpreter, from 8.70 s to 5.63 s. Against the
committed serial generator at 7.58 s the same run is 25.8% faster, but that
comparison spans two changes at once: the 7.58 s run used CPython 3.13.11, and
the eight-worker run uses 3.15.2t with the worker pool and its own locked
dependencies. The table records those measurements; it does not separate the
interpreter's share of the difference from the worker pool's. The 35.3% figure
above is the one taken on a single interpreter. For the complete warm
`bun run build`, which also compiles CSS and scripts, processes assets, and
indexes search, the mean fell from 22.56 s to 20.50 s (9.1%) over three
measured builds per version.

Scalene 2.4.0 enabled the GIL for its native extensions. py-spy 0.4.3 could not
locate the interpreter. CPython's sampling profiler captured the main thread
and all eight pool threads with the GIL disabled. Of 1,469 worker samples
inside a render job, 1,334 included the Markdown renderer. The main thread was
waiting for an ordered result in 350 of its 562 samples. These are wall-clock
samples and include time spent waiting.

```bash
uv run --locked --no-dev --python 3.15.2t python -m profiling.sampling run \
  --all-threads --blocking -r 100hz --gecko -o threads.json \
  .venv/bin/pages generate --all-sites --doc-workers 8
```

With fixed diagram SVGs for the equivalence check, the eight-worker output
matched the serial CPython 3.15.2t output and the earlier MiniJinja baseline
byte for byte across all 1,007 generated files, including all 940 HTML pages.
