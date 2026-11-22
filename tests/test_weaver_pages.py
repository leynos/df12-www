"""Markup invariants held by the Weaver page templates.

These render a page template directly, in an environment of its own, so a
change that quietly reverts the markup fails here in milliseconds rather than
waiting for the served-page browser suite.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag

from df12_pages.templating import template_environment

if typ.TYPE_CHECKING:
    from minijinja import Environment

REPO_ROOT = Path(__file__).resolve().parents[1]
WEAVER_TEMPLATES = REPO_ROOT / "templates" / "weaver"


@pytest.fixture(scope="module")
def weaver() -> Environment:
    """Load the Weaver templates in an environment of their own."""
    return template_environment(WEAVER_TEMPLATES)


def test_the_telemetry_pulse_is_a_hidden_dot_beside_the_live_label(
    weaver: Environment,
) -> None:
    """The feed row animates a decorative dot, never the words beside it."""
    rendered = str(weaver.render_template("pages/how-it-works.jinja", nav_links=[]))
    soup = BeautifulSoup(rendered, "html.parser")

    feed = soup.find(string=lambda text: bool(text) and "INTERNAL TELEMETRY" in text)
    assert feed is not None, "the architecture page must name its telemetry feed"
    row = feed.find_parent("div")
    assert isinstance(row, Tag), "the feed label must sit in its header row"

    dot = row.select_one("span.animate-pulse")
    assert isinstance(dot, Tag), "the live indicator must still pulse"
    assert dot.get("aria-hidden") == "true", (
        "the pulse is decoration, so it must be hidden from assistive tools"
    )

    label = dot.parent
    assert isinstance(label, Tag), "the dot must pulse inside the label container"
    assert label.get_text(strip=True) == "LIVE", (
        f"the row must read LIVE without the dot's markup: {label}"
    )
    assert "animate-pulse" not in (label.get("class") or []), (
        "the pulse belongs to the dot, not to the label it sits beside"
    )
    assert "●" not in rendered, (
        "the bullet belonged to the old combined label and must not return"
    )
