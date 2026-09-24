"""Integer fields in the site configuration: ``_as_int`` and its callers.

YAML hands the loaders untyped scalars, and three builders need integers
from them: a world card's image ``width`` and ``height``, the homepage
footer's ``copyright_year``, and the about page avatar's dimensions.
``_as_int`` converts each as ``int()`` would, except that it refuses a
boolean, which ``int()`` would quietly read as 0 or 1, and anything that is
not a number or a string. The builders then decide what a bad value costs:
the world image and footer raise ``SiteConfigError``, and the avatar is
left out.
"""

from __future__ import annotations

import pytest

from df12_pages.config import SiteConfigError
from df12_pages.config.about import _build_avatar
from df12_pages.config.helpers import _as_int
from df12_pages.config.homepage import _build_footer_config, _build_world_image

#: The copyright year the footer fixtures carry.
YEAR = 2026


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(640, 640, id="int"),
        pytest.param(3.0, 3, id="integral-float"),
        pytest.param(2.9, 2, id="fractional-float-truncates"),
        pytest.param("42", 42, id="numeric-string"),
        pytest.param(" 7\n", 7, id="padded-string"),
        pytest.param("-3", -3, id="negative-string"),
    ],
)
def test_as_int_converts_as_int_would(value: object, expected: int) -> None:
    """Numbers and integer strings convert exactly as ``int()`` converts them."""
    assert _as_int(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(None, id="none"),
        pytest.param([640], id="list"),
        pytest.param({"w": 640}, id="mapping"),
    ],
)
def test_as_int_refuses_booleans_and_non_scalars(value: object) -> None:
    """A boolean is not read as 0 or 1, and a non-scalar is refused outright."""
    with pytest.raises(TypeError, match="expected an integer"):
        _as_int(value)


@pytest.mark.parametrize("value", ["abc", "3.0", ""])
def test_as_int_rejects_strings_that_are_not_integers(value: str) -> None:
    """A string must spell an integer; ``int()``'s ``ValueError`` passes through."""
    with pytest.raises(ValueError, match="invalid literal"):
        _as_int(value)


def _world_image(**overrides: object) -> dict[str, object]:
    """Return a complete world-card image mapping with *overrides* applied."""
    return {
        "avif": "/images/world.avif",
        "webp": "/images/world.webp",
        "fallback": "/images/world.png",
        "alt": "A world",
        "width": 1200,
        "height": "800",
        "sizes": "100vw",
        **overrides,
    }


def test_world_image_reads_numeric_dimensions() -> None:
    """An integer and an integer string both become the image's dimensions."""
    image = _build_world_image(_world_image(), "Weaver")
    assert (image.width, image.height) == (1200, 800)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"width": True}, id="boolean-width"),
        pytest.param({"height": "tall"}, id="word-height"),
        pytest.param({"width": "12.5"}, id="decimal-string-width"),
    ],
)
def test_world_image_rejects_non_numeric_dimensions(
    overrides: dict[str, object],
) -> None:
    """A dimension that is not an integer fails the load, naming the card."""
    with pytest.raises(SiteConfigError, match="'Weaver' image requires numeric"):
        _build_world_image(_world_image(**overrides), "Weaver")


def _footer(**overrides: object) -> dict[str, object]:
    """Return a complete homepage footer mapping with *overrides* applied."""
    return {
        "site_name": "df12",
        "blurb": "Tools and sites.",
        "oss_heading": "Open source",
        "contact_heading": "Contact",
        "closing_lede": "Say hello.",
        "copyright_year": YEAR,
        "oss_links": [{"label": "GitHub", "href": "https://github.com/leynos"}],
        "contact_links": [{"label": "Email", "href": "mailto:hello@example.com"}],
        **overrides,
    }


@pytest.mark.parametrize("year", [YEAR, str(YEAR)])
def test_footer_reads_the_copyright_year(year: object) -> None:
    """An integer year and a year written as a string both load."""
    assert _build_footer_config(_footer(copyright_year=year)).copyright_year == YEAR


@pytest.mark.parametrize("year", [True, "MMXXVI", [YEAR]])
def test_footer_rejects_a_year_that_is_not_an_integer(year: object) -> None:
    """A boolean, a word, or a list fails the load."""
    with pytest.raises(SiteConfigError, match="'copyright_year' must be numeric"):
        _build_footer_config(_footer(copyright_year=year))


def _avatar(**overrides: object) -> dict[str, object]:
    """Return a complete about-page avatar mapping with *overrides* applied."""
    return {
        "src": "/images/me.webp",
        "alt": "Portrait",
        "width": 320,
        "height": "320",
        **overrides,
    }


def test_avatar_reads_numeric_dimensions() -> None:
    """An integer and an integer string both become the avatar's dimensions."""
    avatar = _build_avatar(_avatar())
    assert avatar is not None
    assert (avatar.width, avatar.height) == (320, 320)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"width": False}, id="boolean-width"),
        pytest.param({"height": "square"}, id="word-height"),
        pytest.param({"width": None}, id="missing-width"),
    ],
)
def test_avatar_is_omitted_when_a_dimension_is_not_an_integer(
    overrides: dict[str, object],
) -> None:
    """The about page drops a malformed avatar rather than failing the load."""
    assert _build_avatar(_avatar(**overrides)) is None
