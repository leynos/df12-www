"""Rendered contracts introduced by the Weaver 0.1.0 content refresh."""

from __future__ import annotations

import typing as typ

import pytest

from tests.support.weaver_browser import DESKTOP_HEIGHT, _evaluate, _open

if typ.TYPE_CHECKING:
    import collections.abc as cabc

pytestmark = pytest.mark.playwright

COMMAND_PAGES = (
    "commands/observe/",
    "commands/act/",
    "commands/verify/",
)
MOBILE_TABLE_WIDTH = 767
DESKTOP_TABLE_WIDTH = 768
COMMAND_TABLE_CELL_COUNT = 3
MOBILE_GRID_TRACK_COUNT = 2
VISUALLY_HIDDEN_SIZE = 1
HOMEPAGE_HERO_COUNT = 2

TABLE_LAYOUT = (
    "JSON.stringify((() => {"
    "const table = document.querySelector('.command-table');"
    "const head = table?.tHead;"
    "const row = table?.tBodies[0]?.rows[0];"
    "const cells = row ? [...row.cells] : [];"
    "if (!table || !head || !row || cells.length !== 3) return {found: false};"
    "const headStyle = getComputedStyle(head);"
    "const headBox = head.getBoundingClientRect();"
    "const rowStyle = getComputedStyle(row);"
    "const secondStyle = getComputedStyle(cells[1]);"
    "const thirdStyle = getComputedStyle(cells[2]);"
    "const tracks = rowStyle.gridTemplateColumns === 'none' ? [] : "
    "rowStyle.gridTemplateColumns.split(' ').filter(Boolean);"
    "return {found: true, rowCount: table.tBodies[0].rows.length, "
    "cellCount: cells.length, tableDisplay: getComputedStyle(table).display, "
    "headDisplay: headStyle.display, headPosition: headStyle.position, "
    "headWidth: headBox.width, headHeight: headBox.height, "
    "headClip: headStyle.clipPath, rowDisplay: rowStyle.display, "
    "gridTrackCount: tracks.length, secondAlign: secondStyle.textAlign, "
    "thirdStart: thirdStyle.gridColumnStart, "
    "thirdEnd: thirdStyle.gridColumnEnd, "
    "thirdPaddingTop: thirdStyle.paddingTop, "
    "page: document.documentElement.scrollWidth, viewport: innerWidth};"
    "})())"
)


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", COMMAND_PAGES)
def test_command_tables_become_accessible_cards_below_the_breakpoint(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The 767px layout keeps headings accessible and stacks each row."""
    _open(drive, served, page, MOBILE_TABLE_WIDTH, DESKTOP_HEIGHT)
    layout = _evaluate(drive, TABLE_LAYOUT)

    assert layout["found"]
    assert layout["rowCount"] > 0
    assert layout["cellCount"] == COMMAND_TABLE_CELL_COUNT
    assert layout["headDisplay"] != "none"
    assert layout["headPosition"] == "absolute"
    assert layout["headWidth"] <= VISUALLY_HIDDEN_SIZE
    assert layout["headHeight"] <= VISUALLY_HIDDEN_SIZE
    assert layout["headClip"] == "inset(50%)"
    assert layout["rowDisplay"] == "grid"
    assert layout["gridTrackCount"] == MOBILE_GRID_TRACK_COUNT
    assert layout["secondAlign"] == "right"
    assert layout["thirdStart"] == "1"
    assert layout["thirdEnd"] == "-1"
    assert layout["thirdPaddingTop"] == "0px"
    assert layout["page"] <= layout["viewport"]


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", COMMAND_PAGES)
def test_command_tables_restore_table_layout_at_the_breakpoint(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The 768px boundary restores headings, columns, and ordinary cells."""
    _open(drive, served, page, DESKTOP_TABLE_WIDTH, DESKTOP_HEIGHT)
    layout = _evaluate(drive, TABLE_LAYOUT)

    assert layout["found"]
    assert layout["rowCount"] > 0
    assert layout["tableDisplay"] == "table"
    assert layout["headDisplay"] == "table-header-group"
    assert layout["headPosition"] == "static"
    assert layout["headWidth"] > VISUALLY_HIDDEN_SIZE
    assert layout["headHeight"] > VISUALLY_HIDDEN_SIZE
    assert layout["headClip"] == "none"
    assert layout["rowDisplay"] == "table-row"
    assert layout["gridTrackCount"] == 0
    assert layout["secondAlign"] == "left"
    assert layout["thirdStart"] == "auto"
    assert layout["thirdEnd"] == "auto"
    assert layout["thirdPaddingTop"] != "0px"
    assert layout["page"] <= layout["viewport"]


@pytest.mark.timeout(900)
def test_refreshed_command_navigation_is_published(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """The sidebar exposes the Read, Change, and Verification routes."""
    _open(drive, served, "commands/", DESKTOP_TABLE_WIDTH, DESKTOP_HEIGHT)
    report = _evaluate(
        drive,
        "JSON.stringify((() => { const hrefs = ["
        "'/weaver/commands/observe/', '/weaver/commands/act/', "
        "'/weaver/commands/verify/']; return {navigation: Object.fromEntries("
        "hrefs.map((href) => [href, document.querySelector("
        '`nav a[href="${href}"]`)?.textContent.trim()])), '
        "headings: [...document.querySelectorAll('main h3')]"
        ".map((heading) => heading.textContent.trim())}; })())",
    )

    assert report["navigation"] == {
        "/weaver/commands/observe/": "/read",
        "/weaver/commands/act/": "/change",
        "/weaver/commands/verify/": "/verification",
    }
    assert {"Read", "Change", "Verification"} <= set(report["headings"])


@pytest.mark.timeout(900)
def test_command_index_publishes_the_machine_selector_contract(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """The generated command index carries the new machine-facing contract."""
    _open(drive, served, "commands/", DESKTOP_TABLE_WIDTH, DESKTOP_HEIGHT)
    contract = _evaluate(
        drive,
        "JSON.stringify((() => { const text = document.body.textContent; "
        "return {grammar: text.includes('weaver <resource> <verb> [FLAGS]'), "
        "json: text.includes('--json'), "
        "selector: text.includes('weaver.selector.v1'), "
        "complete: text.includes('weaver.selector-stream-end.v1')}; })())",
    )

    assert contract == {
        "grammar": True,
        "json": True,
        "selector": True,
        "complete": True,
    }


@pytest.mark.timeout(900)
def test_docs_publish_the_architecture_decision_library(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """The docs route renders its Architecture Decisions anchor and links."""
    _open(drive, served, "docs/", DESKTOP_TABLE_WIDTH, DESKTOP_HEIGHT)
    report = _evaluate(
        drive,
        "JSON.stringify((() => { const section = "
        "document.querySelector('#architecture'); return {"
        "anchor: Boolean(document.querySelector('a[href=\"#architecture\"]')), "
        "heading: section?.querySelector('h2')?.textContent.trim(), "
        "links: [...(section?.querySelectorAll('a[href]') ?? [])]"
        ".map((link) => link.href).sort()}; })())",
    )

    assert report["anchor"]
    assert report["heading"] == "Architecture Decisions"
    assert report["links"] == sorted(
        [
            "https://github.com/leynos/weaver/blob/main/docs/adr-001-plugin-capability-model-and-act-extricate.md",
            "https://github.com/leynos/weaver/blob/main/docs/adr-007-agent-native-command-surface.md",
            "https://github.com/leynos/weaver/blob/main/docs/rfcs/0002-multi-workspace-daemon.md",
            "https://github.com/leynos/weaver/blob/main/docs/rfcs/0003-sempai-query-to-selector.md",
            "https://github.com/leynos/weaver/blob/main/docs/ui-gap-analysis.md",
        ]
    )


@pytest.mark.timeout(900)
def test_homepage_publishes_complete_local_image_assets(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """The responsive hero and selector figure load their local image assets."""
    _open(drive, served, "", DESKTOP_TABLE_WIDTH, DESKTOP_HEIGHT)
    images = _evaluate(
        drive,
        "JSON.stringify([...document.images].map((image) => ({"
        "src: image.getAttribute('src'), alt: image.getAttribute('alt'), "
        "complete: image.complete, naturalWidth: image.naturalWidth})))",
    )

    hero = [
        image
        for image in images
        if image["src"] == "/weaver/assets/home/home-hero-loom-architecture.png"
    ]
    selector = [
        image
        for image in images
        if image["src"] == "/weaver/assets/home/home-sempai-query-pipeline.png"
    ]

    assert len(hero) == HOMEPAGE_HERO_COUNT
    assert sorted(image["alt"] == "" for image in hero) == [False, True]
    assert len(selector) == 1
    assert selector[0]["alt"]
    assert all(image["complete"] and image["naturalWidth"] > 0 for image in images)
