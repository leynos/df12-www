"""What `templates/weaver/_chrome.jinja` renders.

The two macros here decide the sidebar on every Weaver page: which link is
marked current, what each one is dressed as, and whether the numbered prefix
appears. The browser suite checks the result on a served page, which is the
right place for "exactly one link is current" — but it loads seventeen pages
to do it, and it cannot easily reach the cases the site does not currently
render: an unnumbered resource link, a non-current install link, a nav with
nothing marked current.

Rendering the macros directly reaches all of them in milliseconds, and pins
the class strings the stylesheet is written against.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest

from df12_pages.templating import template_environment

if typ.TYPE_CHECKING:
    from minijinja import Environment

REPO_ROOT = Path(__file__).resolve().parents[1]
WEAVER_TEMPLATES = REPO_ROOT / "templates" / "weaver"

# The three class strings the template declares, restated here so a change to
# one is a change to this file too. `weaver-nav-link` is what `mobile-nav.js`
# and the browser suite both select on; `weaver-nav-link--current` is what
# `chrome.css` styles.
BASE_CLASS = "weaver-nav-link"
CURRENT_CLASS = "weaver-nav-link--current"


@pytest.fixture(scope="module")
def chrome() -> Environment:
    """Load `_chrome.jinja` in an environment of its own.

    Isolated from the generator's environment so these tests describe the
    template rather than the way the site happens to configure Jinja.
    """
    return template_environment(WEAVER_TEMPLATES)


def _nav_link(env: Environment, *args: str) -> str:
    """Render the sidebar link macro with the supplied positional arguments."""
    return env.render_str(
        '{% import "_chrome.jinja" as ui %}{{ ui.nav_link(*args) }}', args=args
    )


def _current_href(env: Environment, links: list[dict[str, str | bool]]) -> str:
    """Render the macro that selects the current navigation link."""
    return env.render_str(
        '{% import "_chrome.jinja" as ui %}{{ ui.current_href(links) }}', links=links
    )


def test_the_current_link_is_marked_for_the_reader_and_for_assistive_tools(
    chrome: Environment,
) -> None:
    """`aria-current` is the half a stylesheet cannot supply."""
    rendered = str(
        _nav_link(chrome, "/weaver/safety/", "04", "Safety", "/weaver/safety/")
    )

    assert 'href="/weaver/safety/"' in rendered, rendered
    assert ">Safety" in rendered or "Safety" in rendered, rendered
    assert BASE_CLASS in rendered, (
        f"the base class is what selects a nav link: {rendered}"
    )
    assert CURRENT_CLASS in rendered, f"the current link should say so: {rendered}"
    assert 'aria-current="page"' in rendered, (
        f"a current link must be announced as such, not only coloured: {rendered}"
    )
    assert ">04<" in rendered, f"the section number should show: {rendered}"
    assert "opacity-75" not in rendered, (
        f"the current link's index is not dimmed: {rendered}"
    )


def test_a_link_that_is_not_current_is_dressed_differently_and_says_nothing(
    chrome: Environment,
) -> None:
    """The other twelve links, and the dimming that had to clear AA."""
    rendered = str(
        _nav_link(chrome, "/weaver/safety/", "04", "Safety", "/weaver/docs/")
    )

    assert BASE_CLASS in rendered, rendered
    assert CURRENT_CLASS not in rendered, (
        f"only the page being rendered is current: {rendered}"
    )
    assert "aria-current" not in rendered, (
        f"a non-current link must not claim to be the current page: {rendered}"
    )
    assert ">04<" in rendered, f"the section number still shows: {rendered}"
    assert "opacity-75" in rendered, (
        "the index is dimmed on the links that are not current, at the opacity "
        f"that clears AA on the sidebar's cream: {rendered}"
    )


def test_a_resource_link_carries_no_number(
    chrome: Environment,
) -> None:
    """The links at the foot of the nav are unnumbered, and get no empty span."""
    rendered = str(
        _nav_link(chrome, "/weaver/roadmap/", "", "Roadmap", "/weaver/docs/")
    )

    assert BASE_CLASS in rendered, rendered
    assert "font-mono" not in rendered, (
        f"an unnumbered link has no index span to be monospaced: {rendered}"
    )
    assert "&gt;" not in rendered, (
        f"the install marker belongs to the install variant alone: {rendered}"
    )
    assert "Roadmap" in rendered, rendered


def test_the_install_link_is_marked_when_it_is_not_the_current_page(
    chrome: Environment,
) -> None:
    """It is a call to action, so it gets a marker in place of a number."""
    rendered = str(
        _nav_link(chrome, "/weaver/install/", "", "Install", "/weaver/docs/", "install")
    )

    assert "&gt;" in rendered, (
        f"an unnumbered install link should carry its marker: {rendered}"
    )
    assert "font-mono" in rendered, f"the install variant is monospaced: {rendered}"
    assert CURRENT_CLASS not in rendered, rendered

    # On its own page it is current, and the marker gives way to that.
    current = str(
        _nav_link(
            chrome, "/weaver/install/", "", "Install", "/weaver/install/", "install"
        )
    )
    assert "&gt;" not in current, (
        f"the marker points at somewhere to go, not where you are: {current}"
    )
    assert CURRENT_CLASS in current, current
    assert 'aria-current="page"' in current, current


def test_the_current_href_is_taken_from_whichever_link_is_flagged(
    chrome: Environment,
) -> None:
    """One lookup, passed to every link, rather than a flag per call site."""
    nav_links = [
        {"href": "/weaver/", "current": False},
        {"href": "/weaver/safety/", "current": True},
        {"href": "/weaver/docs/", "current": False},
    ]

    assert str(_current_href(chrome, nav_links)) == "/weaver/safety/", (
        f"got {str(_current_href(chrome, nav_links))!r}"
    )


def test_a_page_outside_the_nav_yields_an_empty_current_href(
    chrome: Environment,
) -> None:
    """The legal pages are rendered with the sidebar but are not listed in it.

    An empty string is what makes every `href == current_href` comparison
    false, so no link is highlighted — which is the wanted result, and the
    reason the macro cannot simply return `none`.
    """
    nav_links = [
        {"href": "/weaver/", "current": False},
        {"href": "/weaver/docs/", "current": False},
    ]

    assert str(_current_href(chrome, nav_links)) == "", (
        f"expected an empty string, got {str(_current_href(chrome, nav_links))!r}"
    )
    assert str(_current_href(chrome, [])) == "", (
        "an empty nav should also yield an empty string rather than failing"
    )

    # And the empty string must not accidentally match a link.
    rendered = str(
        _nav_link(
            chrome,
            "/weaver/safety/",
            "04",
            "Safety",
            str(_current_href(chrome, nav_links)),
        )
    )
    assert CURRENT_CLASS not in rendered, (
        f"no link should be current on a page outside the nav: {rendered}"
    )
