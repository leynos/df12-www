"""What the users' guide says about Weaver, checked against Weaver.

A users' guide is the one document a reader cannot verify for themselves
without doing the thing it describes, so a route that has moved or a control
that has been renamed is worse here than in the developers' guide: the reader
has no way to tell they are being misled.

These check the claims that can be checked mechanically — the routes it links
to, the controls it names, and the breakpoint it quotes — against the
published tree and the sources that decide them. What the drawer *does* is
covered by the browser and happy-dom suites; this is about whether the guide
still describes the same thing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
USERS_GUIDE = REPO_ROOT / "docs" / "users-guide.md"
WEAVER_TEMPLATES = REPO_ROOT / "templates" / "weaver"
WEAVER_SCRIPTS = REPO_ROOT / "src" / "static" / "weaver" / "assets" / "js"
CHROME_CSS = REPO_ROOT / "src" / "styles" / "weaver" / "chrome.css"

# A Markdown link to somewhere under /weaver/.
WEAVER_LINK = re.compile(r"\]\((/weaver/[^)]*)\)")


@pytest.fixture(scope="module")
def weaver_section() -> str:
    """Return just the Weaver part of the users' guide.

    Scoped so a link added elsewhere in the guide — to Episodic, say — is not
    held to Weaver's published tree.
    """
    text = USERS_GUIDE.read_text(encoding="utf-8")
    start = text.index("## 4. Weaver")
    remainder = text[start + 1 :]
    end = remainder.find("\n## ")
    return remainder if end == -1 else remainder[:end]


def test_the_guide_has_a_weaver_section() -> None:
    """The other tests here are vacuous without it."""
    assert "## 4. Weaver" in USERS_GUIDE.read_text(encoding="utf-8"), (
        "the users' guide has no Weaver section, so nothing below is checking anything"
    )


# A link may point at a section (`/weaver/install/#quick-start`), and the
# fragment is resolved by the browser, not the filesystem; carried into the
# path check it would report a published page as missing.
def _page(route: str) -> str:
    """Return the route's path, with any fragment or query dropped."""
    return route.split("#", 1)[0].split("?", 1)[0]


@pytest.mark.timeout(600)
def test_every_weaver_route_the_guide_links_to_is_published(
    built_site: Path, weaver_section: str
) -> None:
    """A link in a users' guide is a promise that the page is there."""
    linked = sorted({match.group(1) for match in WEAVER_LINK.finditer(weaver_section)})
    assert linked, "the Weaver section links to no Weaver pages at all"

    missing = [
        route
        for route in linked
        if not (
            built_site / _page(route).removeprefix("/weaver/").strip("/") / "index.html"
        )
        .resolve()
        .is_file()
        and _page(route).strip("/") != "weaver"
    ]
    assert not missing, (
        f"the users' guide links to Weaver pages that the build does not "
        f"publish: {missing}"
    )


@pytest.mark.parametrize(
    ("route", "path"),
    [
        ("/weaver/install/#quick-start", "/weaver/install/"),
        ("/weaver/commands/?format=html", "/weaver/commands/"),
        ("/weaver/?utm_source=guide#top", "/weaver/"),
        ("/weaver/commands/act/", "/weaver/commands/act/"),
    ],
)
def test_a_fragment_or_query_does_not_change_the_route(route: str, path: str) -> None:
    """The browser resolves fragments and queries; the filesystem must not see them."""
    assert _page(route) == path, f"{route!r} should normalize to {path!r}"


@pytest.mark.timeout(600)
@pytest.mark.parametrize(
    "route", ["/weaver/install/#quick-start", "/weaver/commands/?format=html"]
)
def test_a_route_with_a_fragment_still_resolves_to_its_page(
    built_site: Path, route: str
) -> None:
    """The published-page check must accept a link that points at a section.

    These routes carry the components the guide's links happen not to use
    today, so the stripping is exercised against the built tree rather than
    waiting for a fragment-bearing link to appear and fail.
    """
    resolved = (
        built_site / _page(route).removeprefix("/weaver/").strip("/") / "index.html"
    ).resolve()
    assert resolved.is_file(), (
        f"{route} should resolve to a published page at {resolved}"
    )


@pytest.mark.parametrize("route", ["/weaver/", "/weaver/install/", "/weaver/commands/"])
def test_the_guide_names_the_routes_a_reader_starts_from(
    weaver_section: str, route: str
) -> None:
    """The entry point and the two pages the section promises to point at."""
    assert route in weaver_section, (
        f"the Weaver section should send a reader to {route}; it links to "
        f"{sorted({m.group(1) for m in WEAVER_LINK.finditer(weaver_section)})}"
    )


def test_the_breakpoint_the_guide_quotes_is_the_one_in_force(
    weaver_section: str,
) -> None:
    """A number in prose is the kind of thing that goes quietly out of date.

    The stylesheet hides the sidebar below 1024px and the script closes the
    drawer at or above it, so the two are one boundary written two ways. The
    guide quotes it, and this is what stops that quotation drifting.
    """
    assert "1024" in weaver_section, (
        "the guide should tell a reader where the layout changes"
    )

    css = CHROME_CSS.read_text(encoding="utf-8")
    assert "@media (max-width: 1023px)" in css, (
        "the stylesheet's drawer breakpoint has moved away from 1023px, so the "
        "guide's 1024 is no longer the boundary"
    )
    script = (WEAVER_SCRIPTS / "mobile-nav.js").read_text(encoding="utf-8")
    assert 'matchMedia("(min-width: 1024px)")' in script, (
        "the script's breakpoint has moved away from 1024px, so the guide's "
        "number is no longer the boundary"
    )


def test_the_controls_the_guide_describes_exist(weaver_section: str) -> None:
    """Each named control, traced to the thing that provides it."""
    script = (WEAVER_SCRIPTS / "mobile-nav.js").read_text(encoding="utf-8")

    assert "drawer" in weaver_section.lower(), "the guide should name the drawer"
    assert 'btn.id = "mobile-nav-toggle"' in script, (
        "the guide describes a button that opens the drawer; the script no "
        "longer builds one"
    )
    assert 'backdrop.id = "mobile-nav-backdrop"' in script, (
        "the guide says the area beside the drawer dismisses it; the script no "
        "longer builds a backdrop"
    )
    assert '"Escape"' in script, (
        "the guide says Escape dismisses the drawer; the script no longer "
        "listens for it"
    )
    assert "document.body.style.overflowY" in script, (
        "the guide says the page behind the drawer does not scroll vertically; "
        "the script no longer locks it"
    )


def test_the_guide_describes_the_copy_controls_that_exist(
    weaver_section: str,
) -> None:
    """Including, honestly, that pressing one shows the reader nothing."""
    assert "Copy" in weaver_section, "the guide should name the copy control"

    controls = [
        source
        for source in sorted(WEAVER_TEMPLATES.rglob("*.jinja"))
        if "df12WeaverCopy(" in source.read_text(encoding="utf-8")
    ]
    assert controls, (
        "the guide describes copy controls, but no template calls the copy seam"
    )
    named = {source.stem for source in controls}
    assert {"install", "home_page"} <= named, (
        f"the guide says the install and home pages carry them; they are in "
        f"{sorted(named)}"
    )

    # The guide promises no confirmation. If one is ever added — a toast, or a
    # live region — the guide is wrong and should be corrected rather than
    # left saying nothing happens. Only the templates carrying a copy control
    # are held to that: a live region elsewhere in the chrome would announce
    # something else entirely.
    markup = "\n".join(source.read_text(encoding="utf-8") for source in controls)
    assert "aria-live" not in markup, (
        "a live region has appeared in the Weaver templates, so a copy may now "
        "announce itself; the users' guide says it does not and needs updating"
    )
