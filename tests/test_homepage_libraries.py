"""Tests for the libraries group beneath the homepage's systems grid.

The group is optional: a ``libraries`` mapping inside ``homepage.systems`` in
``config/pages.yaml`` adds a heading, a kicker, and compact links below the
product cards. These tests pin the builder's contract, the shipped config,
and the rendered markup.
"""

from __future__ import annotations

import dataclasses as dc
import typing as typ
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from df12_pages.config import SiteConfigError, load_site_config
from df12_pages.config.homepage import _build_libraries_config
from df12_pages.homepage import HomePageBuilder

if typ.TYPE_CHECKING:
    from df12_pages.config import HomepageConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "config" / "pages.yaml"

VALID_LINKS: list[dict[str, object]] = [
    {
        "label": "Cuprum",
        "description": "Typed command execution.",
        "href": "cuprum/",
        "meta_label": "Learn more",
        "external": False,
    },
    {
        "label": "rstest-bdd",
        "description": "BDD for rstest.",
        "href": "https://github.com/leynos/rstest-bdd",
        "meta_label": "View on GitHub",
    },
]
VALID_LIBRARIES: dict[str, object] = {
    "heading": "Libraries",
    "kicker": "Smaller parts.",
    "links": VALID_LINKS,
}


def _homepage() -> HomepageConfig:
    """Load the homepage block from the repository's config."""
    homepage = load_site_config(CONFIG).homepage
    assert homepage is not None, "config/pages.yaml should define a homepage"
    return homepage


class TestBuildLibrariesConfig:
    """The builder's parsing and validation contract."""

    def test_absent_group_is_none(self) -> None:
        """A systems section without libraries renders no group."""
        assert _build_libraries_config(None) is None, (
            "an absent libraries payload should yield no libraries config"
        )

    def test_valid_group_is_parsed(self) -> None:
        """Links keep their order, and `external` defaults to true."""
        libraries = _build_libraries_config(VALID_LIBRARIES)

        assert libraries is not None
        assert libraries.heading == "Libraries"
        assert [link.label for link in libraries.links] == ["Cuprum", "rstest-bdd"]
        assert [link.external for link in libraries.links] == [False, True]

    @pytest.mark.parametrize("missing", ["heading", "kicker"])
    def test_missing_heading_or_kicker_raises(self, missing: str) -> None:
        """A group without its heading or kicker is a configuration error."""
        payload = {
            key: value for key, value in VALID_LIBRARIES.items() if key != missing
        }
        with pytest.raises(SiteConfigError, match="libraries require"):
            _build_libraries_config(payload)

    def test_empty_links_raise(self) -> None:
        """A group with no links would render an empty heading."""
        with pytest.raises(SiteConfigError, match="libraries require"):
            _build_libraries_config({**VALID_LIBRARIES, "links": []})

    @pytest.mark.parametrize("missing", ["label", "description", "href", "meta_label"])
    def test_link_missing_field_raises(self, missing: str) -> None:
        """A malformed link fails loudly rather than being dropped."""
        link = {k: v for k, v in VALID_LINKS[0].items() if k != missing}
        with pytest.raises(SiteConfigError, match="Library links require"):
            _build_libraries_config({**VALID_LIBRARIES, "links": [link]})

    @pytest.mark.parametrize("field", ["label", "description", "href", "meta_label"])
    @pytest.mark.parametrize("value", ["", "   ", 42, None, ["Cuprum"]])
    def test_link_text_must_be_a_non_empty_string(
        self, field: str, value: object
    ) -> None:
        """Blank or non-string text fails rather than being coerced with str()."""
        link = {**VALID_LINKS[0], field: value}
        with pytest.raises(SiteConfigError, match=f"non-empty string for '{field}'"):
            _build_libraries_config({**VALID_LIBRARIES, "links": [link]})

    @pytest.mark.parametrize("value", ["no", "false", 0, 1, None])
    def test_external_must_be_boolean(self, value: object) -> None:
        """`external: "no"` would be truthy under bool(); it is rejected instead."""
        link = {**VALID_LINKS[0], "external": value}
        with pytest.raises(SiteConfigError, match="'external' must be true or false"):
            _build_libraries_config({**VALID_LIBRARIES, "links": [link]})


def test_shipped_config_lists_cuprum_and_rstest_bdd() -> None:
    """The homepage's Tools section lists the two initial libraries."""
    libraries = _homepage().systems.libraries

    assert libraries is not None, "homepage.systems.libraries should be configured"
    by_label = {link.label: link for link in libraries.links}
    assert set(by_label) == {"Cuprum", "rstest-bdd"}
    assert by_label["Cuprum"].href == "cuprum/"
    assert not by_label["Cuprum"].external, "Cuprum is a local sub-site"
    assert by_label["rstest-bdd"].external


def test_rendered_homepage_lists_libraries_in_the_tools_section(tmp_path: Path) -> None:
    """The group renders inside #systems, with a labelled heading."""
    homepage = dc.replace(_homepage(), output=tmp_path / "index.html")
    soup = BeautifulSoup(HomePageBuilder(homepage).run().read_text(), "html.parser")

    group = soup.select_one("#systems section.libraries")
    assert group is not None, "the libraries group should sit inside #systems"
    heading = group.find(id=group["aria-labelledby"])
    assert heading is not None
    assert heading.get_text(strip=True) == "Libraries"

    links = {}
    for anchor in group.select("a.library-card"):
        title = anchor.select_one(".library-card__title")
        assert title is not None, "each library link names its library"
        links[title.get_text(strip=True)] = anchor
    assert links["Cuprum"]["href"] == "cuprum/"
    assert "target" not in links["Cuprum"].attrs
    assert links["rstest-bdd"]["target"] == "_blank"
    assert "noopener" in links["rstest-bdd"]["rel"]


def test_rendered_homepage_omits_the_group_without_libraries(tmp_path: Path) -> None:
    """No libraries mapping, no empty section."""
    homepage = _homepage()
    homepage = dc.replace(
        homepage,
        output=tmp_path / "index.html",
        systems=dc.replace(homepage.systems, libraries=None),
    )
    soup = BeautifulSoup(HomePageBuilder(homepage).run().read_text(), "html.parser")

    assert soup.select_one(".libraries") is None
