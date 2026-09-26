"""Rendering tests for the forthcoming-preview catalogue.

``forthcoming_data.jinja`` is the single source of truth for the
forthcoming-capability previews: the hub's card grid, every preview page's
sidebar, header chip, and previous/next footer, and the roadmap's links into
a preview's sections all render from its ``previews`` list and macros. This
module exercises those macros directly against the real template, so a typo
in a key, a renamed section, or a catalogue reorder fails here rather than
in a published page.
"""

from __future__ import annotations

import re
import typing as typ
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import UndefinedError

from df12_pages.jinja_highlight import HighlightExtension

NETSUKE_TEMPLATES = Path("templates/netsuke").resolve()
TEMPLATE_VARS: dict[str, object] = {
    "netsuke_version": "0.0.0-test",
    "netsuke_release_date": "1 January 2000",
    "netsuke_rust_nightly": "nightly-2000-01-01",
}

#: The four closing sections every preview's catalogue entry shares.
#: `confidence` is not among them: `testing-framework` and `linter` close
#: with `design`/`architecture` instead.
SHARED_CLOSING_SECTION_IDS = frozenset({"status", "why", "shallow-end", "access"})

#: `footer` always renders exactly a previous link and a next link, one of
#: which leads back to the hub at either end of the catalogue.
FOOTER_LINK_COUNT = 2


def _forthcoming_environment() -> Environment:
    """Build a Jinja environment matching `ContentPageGenerator`'s."""
    env = Environment(
        loader=FileSystemLoader(str(NETSUKE_TEMPLATES)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=[HighlightExtension],
    )
    # Jinja types `globals` as the literal of its default namespace; it is
    # open by design.
    typ.cast("dict[str, object]", env.globals).update(TEMPLATE_VARS)
    return env


def _render_macro(source: str, **context: object) -> BeautifulSoup:
    """Render a template string that imports the forthcoming macro module."""
    env = _forthcoming_environment()
    preamble = '{% import "forthcoming_data.jinja" as fc %}'
    html = env.from_string(preamble + source).render(**context)
    return BeautifulSoup(html, "html.parser")


def _catalogue() -> list[dict[str, object]]:
    """Return the `previews` list from the real template module."""
    env = _forthcoming_environment()
    module = env.get_template("forthcoming_data.jinja").module
    # `TemplateModule` exposes whatever the template sets at module scope;
    # ty has no way to know `previews` is among them.
    return typ.cast("list[dict[str, object]]", typ.cast("typ.Any", module).previews)


def _release_order(target: object) -> tuple[int, ...]:
    """Sort key for a ``vMAJOR.MINOR.PATCH`` target whose patch may be ``x``."""
    parts = str(target).removeprefix("v").split(".")
    return tuple(10**6 if part == "x" else int(part) for part in parts)


class TestHref:
    """`href` builds a preview's page link, or a link into one of its sections."""

    @pytest.mark.parametrize(
        "key",
        ["system-facts", "standard-library", "artefacts"],
    )
    def test_href_of_a_preview(self, key: str) -> None:
        """A bare key links to the preview's own page."""
        soup = _render_macro('{{ fc.href("' + key + '") }}')

        assert soup.get_text() == f"/netsuke/forthcoming/{key}/"

    @pytest.mark.parametrize(
        ("key", "section"),
        [
            ("system-facts", "why"),
            ("standard-library", "confidence"),
            ("linter", "architecture"),
        ],
    )
    def test_href_of_a_section(self, key: str, section: str) -> None:
        """A key with a section links to that in-page anchor."""
        soup = _render_macro(
            '{{ fc.href("' + key + '", "' + section + '") }}',
        )

        assert soup.get_text() == f"/netsuke/forthcoming/{key}/#{section}"

    def test_href_fails_the_build_for_an_unknown_preview(self) -> None:
        """An unlisted key calls the deliberately undefined raise global.

        Nothing defines `raise_unknown_preview`, so referencing a preview
        the catalogue does not have raises `UndefinedError`, which is how a
        stale link fails the build rather than publishing a link to
        nowhere.
        """
        with pytest.raises(UndefinedError):
            _render_macro('{{ fc.href("no-such-preview") }}')

    def test_href_fails_the_build_for_an_unknown_section(self) -> None:
        """A section not listed on the preview also fails the build."""
        with pytest.raises(UndefinedError):
            _render_macro(
                '{{ fc.href("system-facts", "no-such-section") }}',
            )


class TestUnknownPreviewFailsEveryMacro:
    """Every macro keyed on a preview rejects an unlisted key the same way."""

    def test_sidebar_fails_the_build_for_an_unknown_preview(self) -> None:
        """`sidebar` raises before it can render an empty sources list."""
        with pytest.raises(UndefinedError):
            _render_macro('{{ fc.sidebar("no-such-preview") }}')

    def test_header_fails_the_build_for_an_unknown_preview(self) -> None:
        """`header`, called with a lede body, still raises on a bad key."""
        with pytest.raises(UndefinedError):
            _render_macro(
                '{% call fc.header("no-such-preview") %}lede{% endcall %}',
            )


class TestFooter:
    """`footer` links to the previous and next preview in catalogue order."""

    def test_footer_at_the_first_preview(self) -> None:
        """The first preview's `prev` leads back to the hub."""
        soup = _render_macro('{{ fc.footer("system-facts") }}')
        links = soup.select("a[href]")

        assert len(links) == FOOTER_LINK_COUNT
        prev, nxt = links
        assert prev["href"] == "/netsuke/forthcoming/"
        assert "Back" in prev.get_text()
        assert "Forthcoming capabilities" in prev.get_text()
        assert nxt["href"] == "/netsuke/forthcoming/standard-library/"
        assert "Next preview" in nxt.get_text()
        assert "Standard Library" in nxt.get_text()

    def test_footer_at_a_middle_preview(self) -> None:
        """A middle preview links to both its neighbours."""
        soup = _render_macro('{{ fc.footer("standard-library") }}')
        links = soup.select("a[href]")

        assert len(links) == FOOTER_LINK_COUNT
        prev, nxt = links
        assert prev["href"] == "/netsuke/forthcoming/system-facts/"
        assert "Previous preview" in prev.get_text()
        assert "System Facts" in prev.get_text()
        assert nxt["href"] == "/netsuke/forthcoming/structured-commands/"
        assert "Next preview" in nxt.get_text()
        assert "Structured Commands" in nxt.get_text()

    def test_footer_at_the_last_preview(self) -> None:
        """The last preview's `next` leads back to the hub."""
        soup = _render_macro('{{ fc.footer("artefacts") }}')
        links = soup.select("a[href]")

        assert len(links) == FOOTER_LINK_COUNT
        prev, nxt = links
        assert prev["href"] == "/netsuke/forthcoming/typed-inputs/"
        assert "Previous preview" in prev.get_text()
        assert "Typed Inputs" in prev.get_text()
        assert nxt["href"] == "/netsuke/forthcoming/"
        assert "Back" in nxt.get_text()
        assert "Forthcoming capabilities" in nxt.get_text()


class TestTargetLabelAndChip:
    """The release-nearness chip text and dot colour vary with `target`."""

    def test_target_label_names_the_release(self) -> None:
        """A named target renders "Preview targeted at <release>"."""
        soup = _render_macro(
            '{{ fc.target_label({"target": "v0.1.1"}) }}',
        )

        assert soup.get_text() == "Preview targeted at v0.1.1"

    def test_target_label_with_no_named_release(self) -> None:
        """An absent target renders the proposed-with-no-release wording."""
        soup = _render_macro('{{ fc.target_label({"target": none}) }}')

        assert soup.get_text() == "Proposed · no release named"

    def test_chip_dot_is_primary_for_a_named_target(self) -> None:
        """The status dot is `bg-primary` when a release has been named."""
        soup = _render_macro('{{ fc.chip({"target": "v0.1.1"}) }}')
        dot = soup.select_one(".hm-chip span")

        assert dot is not None
        assert "bg-primary" in dot.get_attribute_list("class")
        chip = soup.select_one(".hm-chip")
        assert chip is not None, "the chip renders"
        assert chip.get_text().strip() == "Preview targeted at v0.1.1"

    def test_chip_dot_is_muted_with_no_named_target(self) -> None:
        """The status dot is `bg-base-300` when no release has been named."""
        soup = _render_macro('{{ fc.chip({"target": none}) }}')
        dot = soup.select_one(".hm-chip span")

        assert dot is not None
        assert "bg-base-300" in dot.get_attribute_list("class")
        chip = soup.select_one(".hm-chip")
        assert chip is not None, "the chip renders"
        assert chip.get_text().strip() == "Proposed · no release named"


class TestCatalogueInvariants:
    """Structural invariants the `previews` list itself must hold."""

    def test_keys_are_unique(self) -> None:
        """No two previews share a slug."""
        keys = [entry["key"] for entry in _catalogue()]

        assert len(keys) == len(set(keys))

    def test_every_entry_carries_the_shared_closing_sections(self) -> None:
        """Every entry's sections include status, why, shallow-end, access.

        These are the sections the roadmap and other pages are entitled to
        link into regardless of which preview they name; `confidence` is
        not among them, since `testing-framework` and `linter` close with
        `design`/`architecture` instead.
        """
        for entry in _catalogue():
            section_ids = {
                section["id"]
                for section in typ.cast("list[dict[str, str]]", entry["sections"])
            }

            assert section_ids >= SHARED_CLOSING_SECTION_IDS, entry["key"]

    def test_section_ids_are_unique_within_an_entry(self) -> None:
        """No preview repeats a section id, which would collide as anchors."""
        for entry in _catalogue():
            section_ids = [
                section["id"]
                for section in typ.cast("list[dict[str, str]]", entry["sections"])
            ]

            assert len(section_ids) == len(set(section_ids)), entry["key"]

    def test_catalogue_lists_named_releases_first_and_earliest_first(
        self,
    ) -> None:
        """Named releases lead, in release order, then the unscheduled ones.

        The hub, the sidebars, and the footers all follow catalogue order,
        so the order is the reader's sense of what is nearest. A target
        such as ``v0.1.x`` sorts after every ``v0.1`` patch release and
        before ``v0.2.0``.
        """
        targets = [entry["target"] for entry in _catalogue()]
        named = [target for target in targets if target is not None]

        assert targets[: len(named)] == named, (
            f"every preview with a named release should precede those without "
            f"one; the catalogue lists targets as {targets}"
        )
        assert named == sorted(named, key=_release_order), (
            f"named releases should run earliest first; got {named}"
        )


class TestInlineChipStylesheet:
    """The `.hm-chip--inline` modifier stays compact, not a themed colour."""

    def test_hm_chip_inline_is_sized_for_running_text(self) -> None:
        """The rule carries the compact sizing an inline chip needs."""
        stylesheet = Path("src/styles/netsuke/himotoshi.css").read_text(
            encoding="utf-8"
        )
        rule = re.search(r"\.hm-chip--inline\s*\{([^}]*)\}", stylesheet)

        assert rule is not None, "the inline chip modifier is defined"
        body = rule.group(1)
        assert "font-size: 0.625rem" in body
        assert "line-height: 1.4" in body
        assert "padding: 0 0.4rem" in body
        assert "white-space: nowrap" in body
        assert "gap: 0" in body
        assert "vertical-align" in body
