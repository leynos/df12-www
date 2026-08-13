"""Tests for the generated Episodic syntax-highlighting stylesheet."""

from __future__ import annotations

from df12_pages.episodic_highlighting import EpisodicStyle
from scripts.generate_episodic_pygments_css import STYLESHEET, build_css


def test_committed_stylesheet_matches_the_generator() -> None:
    """The checked-in stylesheet is regenerated from the Pygments style."""
    assert STYLESHEET.read_text(encoding="utf-8") == build_css(), (
        f"{STYLESHEET} is stale; rerun scripts/generate_episodic_pygments_css.py"
    )


def test_every_token_family_has_an_explicit_colour() -> None:
    """Every Episodic token family resolves to the deliberate signal palette."""
    missing = [
        token
        for token in EpisodicStyle.styles
        if not EpisodicStyle.style_for_token(token)["color"]
    ]
    assert not missing, f"token families without an explicit colour: {missing}"


def test_generator_targets_tracked_static_source() -> None:
    """Generated syntax CSS must be copied from source, never written to public."""
    assert STYLESHEET.parts[-6:] == (
        "src",
        "static",
        "episodic",
        "assets",
        "styles",
        "syntax.css",
    )
