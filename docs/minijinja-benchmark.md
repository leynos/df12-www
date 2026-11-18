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

The committed Netsuke browser baseline differs on the ten date-bearing
forthcoming pages at both desktop and phone widths. All 40 normalized
computed-style snapshots per viewport matched between Jinja2 and MiniJinja on
this host. The committed reference snapshots were left intact.
