"""What Cuprum's responsive stylesheet does when a browser lays a page out.

The Cuprum partials change layout at four widths, and nothing else checks
that they still do: the route map trades its strip for a drop-down below
80rem, the documentation rail folds into a drop-down below 64rem, the
capability matrix turns its rows into cards below 48rem, and the content
panels run full bleed below 480px, where a long code line has to scroll
inside its own region rather than widen the page. A rule dropped from a
partial, a layer reordered, or a daisyUI utility recapturing a property
leaves the markup and the build tests intact while the page lays out
wrongly, so each fact is read back from the browser as computed styles and
boxes.

The pages are served from the built ``public/`` tree through the shared
``served`` and ``drive`` fixtures, so the suite relies on the site build the
``built_site`` fixture runs. One page carries each fact, which keeps a slow
suite lean.

Marked ``playwright``, so `-m "not playwright"` deselects the lot while
iterating on something else.
"""

from __future__ import annotations

import json
import typing as typ

import pytest

from tests.support.weaver_browser import _evaluate

if typ.TYPE_CHECKING:
    import collections.abc as cabc

pytestmark = pytest.mark.playwright

# The first URL segment of every Cuprum page.
BASE_PATH = "/cuprum/"

# Every width is measured at this height, as the rendered-page checks in
# AGENTS.md set it.
HEIGHT = 900

# Sub-pixel slack for comparing a box edge with the viewport: the gutter is a
# `clamp()` over `vw`, so the negative margin that cancels it is fractional.
EDGE_TOLERANCE_PX = 1

# One page per fact, each chosen because it carries the component under test.
ROUTE_MAP_PAGE = "getting-started/"
MATRIX_PAGE = "internals/rust-extension/"
# Its first code panel sits directly in the page shell, so at phone width the
# bleed has nothing else in the way of the screen edge.
BLEED_PAGE = "examples/first-command/"
DOCS_NAV_PAGE = "docs/guides/run-a-command/"

# The narrowest width the site supports, and one page of each kind that
# carries code: the home page, the tutorial, a job sheet, a guide, and an API
# group, whose visible examples hold lines of 82 characters.
NARROWEST = 320
NARROW_CODE_PAGES = (
    "",
    "getting-started/",
    "examples/first-command/",
    "docs/guides/run-a-command/",
    "docs/api/adapters/",
)

# Which of two alternative elements is laid out — the wide layout's and the
# narrow layout's — each reported with its computed display and whether it
# has a box at all.
SWAP = """JSON.stringify((() => {
  const read = (selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;
    const box = el.getBoundingClientRect();
    return {display: getComputedStyle(el).display,
      shown: box.width > 0 && box.height > 0};
  };
  return {wide: read(__WIDE__), narrow: read(__NARROW__)};
})())"""

# The first capability matrix: the table's own display, its header row's box,
# every body row's display, and every hidden column label's display and box.
MATRIX = """JSON.stringify((() => {
  const table = document.querySelector('.cu-matrix');
  if (!table) return null;
  const head = table.querySelector('thead');
  const headBox = head ? head.getBoundingClientRect() : null;
  return {
    table: getComputedStyle(table).display,
    head: head ? {display: getComputedStyle(head).display,
      width: headBox.width, height: headBox.height} : null,
    rows: [...table.querySelectorAll('tbody tr')]
      .map((row) => getComputedStyle(row).display),
    labels: [...table.querySelectorAll('.cu-matrix__label')].map((label) => ({
      display: getComputedStyle(label).display,
      height: label.getBoundingClientRect().height})),
  };
})())"""

# The first code panel that is not nested in another panel, which is the
# shape `src/styles/cuprum/bleed.css` sends to the screen edge.
BLEED = """JSON.stringify((() => {
  const nested = '.cu-code, .cu-output, .cu-figure, .cu-callout, .cu-card';
  const panel = [...document.querySelectorAll('.cu-code')]
    .find((el) => !el.parentElement.closest(nested));
  if (!panel) return null;
  const box = panel.getBoundingClientRect();
  return {left: box.left, right: box.right, width: box.width,
    viewport: document.documentElement.clientWidth};
})())"""

# The document's width against the viewport's, and every rendered code
# scroll region's scroll extent against its own box. A region inside a closed
# `<details>` has no box and is left out, since it cannot scroll anything.
NARROW_CODE = """JSON.stringify((() => {
  const regions = [...document.querySelectorAll('.code-scroll')]
    .filter((el) => el.getClientRects().length > 0 && el.clientWidth > 0)
    .map((el) => ({label: el.getAttribute('aria-label'),
      scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
      right: el.getBoundingClientRect().right}));
  return {page: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth, regions};
})())"""


def _open(drive: cabc.Callable[..., str], served: str, page: str, width: int) -> None:
    """Size the viewport, then load one Cuprum page into it.

    The order matters: a page loaded before the resize lays out at the old
    width, and the media queries this is checking would report the wrong
    layout.
    """
    drive("set", "viewport", str(width), str(HEIGHT))
    drive("open", f"{served}{BASE_PATH}{page}")


def _assert_one_laid_out(
    drive: cabc.Callable[..., str],
    where: str,
    selectors: dict[str, str],
    names: dict[str, str],
    layout: str,
) -> None:
    """Assert that the *layout* element is laid out and the other is hidden.

    *selectors* and *names* map ``"wide"`` and ``"narrow"`` to each element's
    selector and to the name a failure message calls it by.
    """
    expression = SWAP.replace("__WIDE__", json.dumps(selectors["wide"]))
    expression = expression.replace("__NARROW__", json.dumps(selectors["narrow"]))
    swap = _evaluate(drive, expression)
    assert swap["wide"] is not None and swap["narrow"] is not None, (  # noqa: PT018 - one guard for the two probes
        f"{where} should carry both the {names['wide']} and the "
        f"{names['narrow']}; got {swap}"
    )
    other = "narrow" if layout == "wide" else "wide"
    shown, hidden = swap[layout], swap[other]
    assert shown["shown"], (
        f"{where} should lay out the {names[layout]}; it is "
        f"display: {shown['display']} with no box"
    )
    assert hidden["display"] == "none", (
        f"{where} should hide the {names[other]}; it is display: {hidden['display']}"
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize(
    ("width", "layout"),
    [(1440, "wide"), (1280, "wide"), (1024, "narrow"), (390, "narrow")],
    ids=["1440", "1280", "1024", "390"],
)
def test_the_route_map_is_a_strip_only_from_80rem(
    drive: cabc.Callable[..., str], served: str, width: int, layout: str
) -> None:
    """From 80rem the route map is a strip; below it, a drop-down.

    `.cu-routemap__menu` is `display: none` by default and swaps with
    `.cu-routemap__scroll` under `@media (width < 80rem)`. Exactly one is laid
    out at any width, or the strip scrolls sideways where it does not fit, or
    a screen reader meets every section link twice.
    """
    _open(drive, served, ROUTE_MAP_PAGE, width)
    _assert_one_laid_out(
        drive,
        f"{BASE_PATH}{ROUTE_MAP_PAGE} at {width}px",
        {"wide": ".cu-routemap__scroll", "narrow": ".cu-routemap__menu"},
        {"wide": "route-map strip", "narrow": "route-map drop-down"},
        layout,
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize(
    ("width", "layout"),
    [(1440, "wide"), (1024, "wide"), (768, "narrow"), (390, "narrow")],
    ids=["1440", "1024", "768", "390"],
)
def test_the_docs_rail_shows_only_from_64rem(
    drive: cabc.Callable[..., str], served: str, width: int, layout: str
) -> None:
    """From 64rem the docs contents are a rail; below it, a drop-down.

    `.cu-docs-nav__rail` is `display: none` by default and swaps with
    `.cu-docs-nav__menu` under `@media (width >= 64rem)`, so a screen reader
    meets the links once whichever is showing.
    """
    _open(drive, served, DOCS_NAV_PAGE, width)
    _assert_one_laid_out(
        drive,
        f"{BASE_PATH}{DOCS_NAV_PAGE} at {width}px",
        {"wide": ".cu-docs-nav__rail", "narrow": ".cu-docs-nav__menu"},
        {"wide": "docs rail", "narrow": "docs drop-down"},
        layout,
    )


@pytest.mark.timeout(900)
def test_the_capability_matrix_becomes_cards_below_48rem(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """Below 48rem each matrix row is a card that labels its own cells.

    The table's `display: block !important` has to beat daisyUI's `.table`
    in the utilities layer, the header row is visually hidden rather than
    removed, and each cell's `.cu-matrix__label` appears to name its column.
    Losing any one leaves a table squeezed into a phone or a card whose
    values have no names.
    """
    width = 390
    _open(drive, served, MATRIX_PAGE, width)
    where = f"{BASE_PATH}{MATRIX_PAGE} at {width}px"
    matrix = _evaluate(drive, MATRIX)

    assert matrix is not None, f"{where} should carry a capability matrix"
    assert matrix["table"] == "block", (
        f"{where} should lay the matrix out as a block of cards; it is "
        f"display: {matrix['table']}"
    )
    head = matrix["head"]
    assert head is not None, f"{where} should keep its header row in the markup"
    assert head["width"] <= 1 and head["height"] <= 1, (  # noqa: PT018 - one box, two axes
        f"{where} should visually hide the header row; it lays out at "
        f"{head['width']}x{head['height']}px"
    )
    assert matrix["rows"], f"{where} has a matrix with no body rows"
    assert set(matrix["rows"]) == {"block"}, (
        f"{where} should lay every row out as a card; rows are {matrix['rows']}"
    )
    assert matrix["labels"], f"{where} has no column labels in its cells"
    unshown = [
        label
        for label in matrix["labels"]
        if label["display"] != "block" or label["height"] <= 0
    ]
    assert not unshown, (
        f"{where} should show every cell's column label; "
        f"{len(unshown)} of {len(matrix['labels'])} are not: {unshown[:3]}"
    )


@pytest.mark.timeout(900)
def test_the_capability_matrix_stays_a_table_from_48rem(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """At 48rem and up the matrix is an ordinary table with its header row."""
    width = 1024
    _open(drive, served, MATRIX_PAGE, width)
    where = f"{BASE_PATH}{MATRIX_PAGE} at {width}px"
    matrix = _evaluate(drive, MATRIX)

    assert matrix is not None, f"{where} should carry a capability matrix"
    assert matrix["table"] in {"table", "inline-table"}, (
        f"{where} should lay the matrix out as a table; it is "
        f"display: {matrix['table']}"
    )
    head = matrix["head"]
    assert head is not None, f"{where} should keep its header row in the markup"
    assert head["display"] == "table-header-group" and head["height"] > 1, (  # noqa: PT018 - one element, display and box
        f"{where} should lay out the header row; it is display: "
        f"{head['display']} at {head['width']}x{head['height']}px"
    )
    assert set(matrix["rows"]) == {"table-row"}, (
        f"{where} should lay every row out as a table row; rows are {matrix['rows']}"
    )
    shown = [label for label in matrix["labels"] if label["display"] != "none"]
    assert not shown, (
        f"{where} should hide the per-cell column labels the header row "
        f"replaces; {len(shown)} are shown"
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize("width", [390, NARROWEST])
def test_a_code_panel_runs_full_bleed_below_480px(
    drive: cabc.Callable[..., str], served: str, width: int
) -> None:
    """Below 480px a top-level code panel spans the whole viewport.

    `src/styles/cuprum/bleed.css` cancels the page gutter with a negative
    inline margin, so the panel's box starts at the screen's left edge and is
    exactly as wide as the viewport.
    """
    _open(drive, served, BLEED_PAGE, width)
    where = f"{BASE_PATH}{BLEED_PAGE} at {width}px"
    panel = _evaluate(drive, BLEED)

    assert panel is not None, f"{where} should carry a top-level code panel"
    assert abs(panel["left"]) <= EDGE_TOLERANCE_PX, (
        f"{where} should start its code panel at the screen edge; its left "
        f"edge is at {panel['left']}px"
    )
    assert abs(panel["width"] - panel["viewport"]) <= EDGE_TOLERANCE_PX, (
        f"{where} should run its code panel the full {panel['viewport']}px of "
        f"the viewport; it is {panel['width']}px wide"
    )


@pytest.mark.timeout(900)
def test_a_code_panel_sits_inside_the_gutter_from_480px(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """At 480px and up the bleed does not apply and the gutter shows."""
    width = 768
    _open(drive, served, BLEED_PAGE, width)
    where = f"{BASE_PATH}{BLEED_PAGE} at {width}px"
    panel = _evaluate(drive, BLEED)

    assert panel is not None, f"{where} should carry a top-level code panel"
    assert panel["left"] > EDGE_TOLERANCE_PX, (
        f"{where} should inset its code panel inside the gutter; its left "
        f"edge is at {panel['left']}px"
    )
    assert panel["right"] < panel["viewport"] - EDGE_TOLERANCE_PX, (
        f"{where} should inset its code panel inside the gutter; its right "
        f"edge is at {panel['right']}px in a {panel['viewport']}px viewport"
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize(
    "page", [pytest.param(page, id=page or "home") for page in NARROW_CODE_PAGES]
)
def test_long_code_scrolls_in_its_own_region_at_320px(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """At 320px a long code line scrolls its region, not the page.

    `.code-scroll` carries `contain: inline-size`, which stops a line's
    min-content width propagating up the grid. Without it the document grows
    to the longest line and every paragraph needs a sideways scroll to read.
    The region itself must still scroll, or the line has been clipped rather
    than contained.
    """
    _open(drive, served, page, NARROWEST)
    where = f"{BASE_PATH}{page} at {NARROWEST}px"
    layout = _evaluate(drive, NARROW_CODE)

    assert layout["page"] <= layout["viewport"], (
        f"{where} lays out {layout['page']}px wide in a {layout['viewport']}px "
        "viewport, so the whole page scrolls sideways"
    )
    regions = layout["regions"]
    assert regions, f"{where} should lay out at least one code scroll region"
    overhanging = [
        region
        for region in regions
        if region["right"] > layout["viewport"] + EDGE_TOLERANCE_PX
    ]
    assert not overhanging, (
        f"{where} has code regions reaching past the "
        f"{layout['viewport']}px viewport: {overhanging}"
    )
    assert any(region["scrollWidth"] > region["clientWidth"] for region in regions), (
        f"{where} should scroll a long code line inside its region; no region "
        f"overflows its own box: {regions}"
    )
