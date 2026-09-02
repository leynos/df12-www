"""Rendered contracts introduced by the Weaver 0.1.0 content refresh."""

from __future__ import annotations

import typing as typ

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

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
MINIMUM_SUPPORTED_WIDTH = 320
MAXIMUM_SUPPORTED_WIDTH = 1440
RESPONSIVE_WIDTHS = st.one_of(
    st.integers(min_value=MINIMUM_SUPPORTED_WIDTH, max_value=MOBILE_TABLE_WIDTH),
    st.integers(min_value=DESKTOP_TABLE_WIDTH, max_value=MAXIMUM_SUPPORTED_WIDTH),
)
PAGE_CONTENT_CONTRACTS = (
    pytest.param(
        "",
        (
            (
                'select(.schema == "weaver.selector.v1" and '
                '(.captures.NAME.text | startswith("old_")))'
            ),
            "weaver symbols rename --selectors - --new-name run --dry-run",
        ),
        id="homepage-selector-stream-contract",
    ),
    pytest.param(
        "commands/observe/",
        ("definitions get", "references list", "diagnostics list", "cards get Planned"),
        id="read-commands",
    ),
    pytest.param(
        "commands/act/",
        (
            "patches apply Planned",
            "symbols rename Planned",
            "symbols move Planned",
            "stale source",
            "Double-Lock",
        ),
        id="change-commands",
    ),
    pytest.param(
        "commands/verify/",
        ("diagnostics list", "the Double-Lock", "policy Planned", "tests Planned"),
        id="verification-commands",
    ),
    pytest.param(
        "sempai/",
        (
            "--query",
            "--expr",
            "--rule",
            "weaver.selector.v1",
            "--selectors <path|->",
            "weaver-syntax-compat-v1",
        ),
        id="sempai-selector-contract",
    ),
    pytest.param(
        "how-it-works/",
        (
            "Planned — RFC 0002",
            "One Daemon, Many Workspaces",
            "One local, per-user weaverd serves every repository",
            "loopback-only TCP",
        ),
        id="workspace-daemon-contract",
    ),
    pytest.param(
        "safety/",
        (
            "Double-Lock",
            "recognised parser and language-server path",
            "no remotely reachable endpoint",
            "loopback-only TCP",
        ),
        id="safety-contract",
    ),
    pytest.param(
        "docs/",
        (
            "Architecture Decisions",
            "The RFC and ADR entries are Status: Proposed",
            "WEAVER_DAEMON_SOCKET",
            "daemon_socket",
            "tcp://127.0.0.1:9779",
        ),
        id="documentation-contract",
    ),
    pytest.param(
        "install/",
        (
            "weaver --capabilities",
            "weaver definitions get",
            "weaver act apply-patch",
            "Planned 0.1.0 resource-style diagnostics workflow",
        ),
        id="installation-contract",
    ),
    pytest.param(
        "roadmap/",
        (
            "Foundations: built",
            "Items marked Planned are not implemented yet",
            "restart-surviving idempotency",
            "Discord is not live yet",
        ),
        id="roadmap-contract",
    ),
    pytest.param(
        "jacquard/",
        ("Planned", "design intent, not current CLI behaviour", '"card_version": 1'),
        id="jacquard-contract",
    ),
    pytest.param(
        "why-weaver/",
        ("weaver symbols list", "Safety-First Posture", "Double-Lock"),
        id="why-weaver-contract",
    ),
)

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


def _assert_table_exists(layout: dict[str, typ.Any]) -> None:
    """Reject a passing layout assertion that inspected no command rows."""
    assert layout["found"]
    assert layout["rowCount"] > 0
    assert layout["cellCount"] == COMMAND_TABLE_CELL_COUNT
    assert layout["page"] <= layout["viewport"]


def _assert_mobile_table_layout(layout: dict[str, typ.Any]) -> None:
    """Assert the accessible card layout used below the breakpoint."""
    _assert_table_exists(layout)
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


def _assert_desktop_table_layout(layout: dict[str, typ.Any]) -> None:
    """Assert the native table layout used from the breakpoint upwards."""
    _assert_table_exists(layout)
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


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", COMMAND_PAGES)
def test_command_tables_become_accessible_cards_below_the_breakpoint(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The 767px layout keeps headings accessible and stacks each row."""
    _open(drive, served, page, MOBILE_TABLE_WIDTH, DESKTOP_HEIGHT)
    layout = _evaluate(drive, TABLE_LAYOUT)

    _assert_mobile_table_layout(layout)


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", COMMAND_PAGES)
def test_command_tables_restore_table_layout_at_the_breakpoint(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The 768px boundary restores headings, columns, and ordinary cells."""
    _open(drive, served, page, DESKTOP_TABLE_WIDTH, DESKTOP_HEIGHT)
    layout = _evaluate(drive, TABLE_LAYOUT)

    _assert_desktop_table_layout(layout)


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", COMMAND_PAGES)
@settings(max_examples=12, deadline=None)
@example(width=MINIMUM_SUPPORTED_WIDTH)
@example(width=390)
@example(width=640)
@example(width=MOBILE_TABLE_WIDTH)
@example(width=DESKTOP_TABLE_WIDTH)
@example(width=1024)
@example(width=1280)
@example(width=MAXIMUM_SUPPORTED_WIDTH)
@given(width=RESPONSIVE_WIDTHS)
def test_command_table_layout_holds_across_supported_widths(
    drive: cabc.Callable[..., str], served: str, page: str, width: int
) -> None:
    """Every supported width follows exactly one responsive table contract."""
    _open(drive, served, page, width, DESKTOP_HEIGHT)
    layout = _evaluate(drive, TABLE_LAYOUT)

    if width < DESKTOP_TABLE_WIDTH:
        _assert_mobile_table_layout(layout)
    else:
        _assert_desktop_table_layout(layout)


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
@pytest.mark.parametrize(("page", "expected"), PAGE_CONTENT_CONTRACTS)
def test_refreshed_page_contracts_are_rendered(
    drive: cabc.Callable[..., str], served: str, page: str, expected: tuple[str, ...]
) -> None:
    """Each refreshed page publishes its representative external contract."""
    _open(drive, served, page, DESKTOP_TABLE_WIDTH, DESKTOP_HEIGHT)
    text = _evaluate(
        drive,
        "JSON.stringify(document.body.innerText.replace(/\\s+/g, ' ').trim())",
    )
    folded_text = text.casefold()

    for fragment in expected:
        assert fragment.casefold() in folded_text, (
            f"/weaver/{page} does not publish {fragment!r}"
        )


@pytest.mark.timeout(900)
def test_main_site_publishes_refreshed_weaver_metadata(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """The main project card and reference library carry the refreshed labels."""
    drive("set", "viewport", str(DESKTOP_TABLE_WIDTH), str(DESKTOP_HEIGHT))
    drive("open", f"{served}/")
    homepage = _evaluate(
        drive,
        "JSON.stringify(document.body.innerText.replace(/\\s+/g, ' ').trim())",
    )
    drive("open", f"{served}/docs.html")
    reference_library = _evaluate(
        drive,
        "JSON.stringify(document.body.innerText.replace(/\\s+/g, ' ').trim())",
    )

    assert (
        "CLI tooling for code-aware AI agents. Semantic code operations as "
        "composable shell primitives."
    ) in homepage
    assert "query, select, change, all Double-Lock verified" in reference_library


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
