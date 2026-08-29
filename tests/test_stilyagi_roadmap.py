"""Tests for the status marking on the Stilyagi roadmap illustration.

The illustration carries one call-out label per slice, and the timeline
below it carries one row per slice. Both state the same thing — whether a
slice has shipped, is in flight, or is planned — from two places in one
template, so they can drift apart. These tests render the real page and
assert they agree, and that each label states its status without relying on
colour.

Usage
-----
Run ``pytest tests/test_stilyagi_roadmap.py -v`` or ``make test``.
"""

from __future__ import annotations

import re
import typing as typ
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from df12_pages.config import ContentPageConfig
from df12_pages.content_page import ContentPageGenerator

if typ.TYPE_CHECKING:
    from bs4.element import Tag

STILYAGI_TEMPLATES = "templates/stilyagi"
ROADMAP_CSS = Path("src/styles/stilyagi/pages/roadmap.css")

#: Phase-row class -> (label status class, mark, spoken status). ``later``
#: takes no status class because planned is the label's default appearance.
STATUS_CONTRACT: dict[str, tuple[str | None, str, str]] = {
    "done": ("is-done", "✓", "shipped"),
    "current": ("is-current", "◐", "in flight"),
    "later": (None, "⭘", "planned"),
}

_SLICE_RE = re.compile(r"(\d{2})")


@pytest.fixture(scope="module")
def roadmap(tmp_path_factory: pytest.TempPathFactory) -> BeautifulSoup:
    """Render the roadmap page once and parse it."""
    config = ContentPageConfig(
        key="roadmap",
        label="Roadmap",
        template="pages/roadmap.jinja",
        output_slug="roadmap",
    )
    generator = ContentPageGenerator(
        config,
        tmp_path_factory.mktemp("out"),
        templates_dir=Path(STILYAGI_TEMPLATES).resolve(),
        nav_links=[],
        stylesheet="assets/styles/stilyagi-site.css",
    )
    output_path = generator.run()
    return BeautifulSoup(output_path.read_text(encoding="utf-8"), "html.parser")


def _classes(tag: Tag) -> set[str]:
    """Return a tag's classes as a set.

    ``Tag.get`` types a class attribute as possibly a bare string, which
    ``set`` would split into characters; normalise before comparing.
    """
    value = tag.get("class") or []
    if isinstance(value, str):
        return set(value.split())
    return set(value)


def _slice_number(text: str) -> str:
    """Return the two-digit slice number leading a label or phase heading."""
    match = _SLICE_RE.search(text)
    assert match is not None, f"expected a slice number in {text!r}"
    return match.group(1)


def _labels_by_slice(soup: BeautifulSoup) -> dict[str, Tag]:
    """Return each call-out label, keyed by its slice number."""
    return {
        _slice_number(label.get_text()): label for label in soup.select(".illo-label")
    }


def _phase_status_by_slice(soup: BeautifulSoup) -> dict[str, str]:
    """Return each timeline row's status class, keyed by its slice number."""
    statuses = {}
    for phase in soup.select(".phase"):
        number = phase.select_one(".ph-num")
        assert number is not None, "every phase row should carry a number"
        classes = _classes(phase)
        status = classes & STATUS_CONTRACT.keys()
        assert len(status) == 1, (
            f"phase {number.get_text(strip=True)} should carry exactly one "
            f"status class, found {sorted(classes)}"
        )
        statuses[_slice_number(number.get_text())] = status.pop()
    return statuses


class TestRoadmapCallOuts:
    """The illustration's labels agree with the timeline beneath them."""

    def test_every_slice_has_one_call_out(self, roadmap: BeautifulSoup) -> None:
        """A slice without a label would leave its leader line unexplained."""
        labels = _labels_by_slice(roadmap)
        phases = _phase_status_by_slice(roadmap)

        assert labels.keys() == phases.keys(), (
            "every timeline slice should have exactly one call-out label"
        )

    def test_call_out_status_matches_its_phase(self, roadmap: BeautifulSoup) -> None:
        """The two statements of a slice's status must not drift apart."""
        labels = _labels_by_slice(roadmap)

        for slice_number, phase_status in _phase_status_by_slice(roadmap).items():
            expected, _mark, _spoken = STATUS_CONTRACT[phase_status]
            classes = _classes(labels[slice_number])
            status_classes = classes & {"is-done", "is-current"}
            actual = status_classes.pop() if status_classes else None

            assert actual == expected, (
                f"slice {slice_number} is {phase_status!r} in the timeline but "
                f"its call-out carries {actual!r} rather than {expected!r}"
            )

    def test_each_call_out_carries_its_mark(self, roadmap: BeautifulSoup) -> None:
        """The mark is what tells the states apart when colour cannot."""
        labels = _labels_by_slice(roadmap)

        for slice_number, phase_status in _phase_status_by_slice(roadmap).items():
            _status_class, expected_mark, _spoken = STATUS_CONTRACT[phase_status]
            mark = labels[slice_number].select_one(".illo-mark")

            assert mark is not None, f"slice {slice_number} should carry a mark"
            assert mark.get_text(strip=True) == expected_mark, (
                f"slice {slice_number} is {phase_status!r} so its mark should "
                f"be {expected_mark!r}"
            )

    def test_marks_are_hidden_from_assistive_technology(
        self, roadmap: BeautifulSoup
    ) -> None:
        """A screen reader should hear the status, not a symbol's name."""
        for mark in roadmap.select(".illo-label .illo-mark"):
            assert mark.get("aria-hidden") == "true", (
                "marks are decorative; the status is carried by the hidden "
                "suffix instead"
            )

    def test_each_call_out_names_its_status(self, roadmap: BeautifulSoup) -> None:
        """Absence of a mark only reads as "planned" if you can see the rest."""
        labels = _labels_by_slice(roadmap)

        for slice_number, phase_status in _phase_status_by_slice(roadmap).items():
            _status_class, _mark, spoken = STATUS_CONTRACT[phase_status]
            suffix = labels[slice_number].select_one(".sr-only")

            assert suffix is not None, (
                f"slice {slice_number} should name its status for a screen reader"
            )
            assert suffix.get_text(strip=True) == f"({spoken})", (
                f"slice {slice_number} is {phase_status!r} in the timeline"
            )

    def test_the_three_states_use_three_marks(self) -> None:
        """Two states sharing a mark would collapse back onto colour alone."""
        marks = [mark for _class, mark, _spoken in STATUS_CONTRACT.values()]

        assert len(set(marks)) == len(marks), f"marks are not distinct: {marks}"


@pytest.fixture(scope="module")
def stylesheet() -> str:
    """Return the roadmap stylesheet's text."""
    return ROADMAP_CSS.read_text(encoding="utf-8")


class TestRoadmapCallOutStyles:
    """The status fills exist, and planned keeps the default appearance."""

    @pytest.mark.parametrize(
        ("selector", "fill"),
        [
            (".illo-label.is-done", "--color-signal-sage-solid"),
            (".illo-label.is-current", "--color-press-red"),
        ],
    )
    def test_status_fill_is_declared(
        self, stylesheet: str, selector: str, fill: str
    ) -> None:
        """Each marked state paints its own ground behind paper-coloured type."""
        pattern = re.compile(
            re.escape(selector) + r"\s*\{[^}]*" + re.escape(fill), re.DOTALL
        )

        assert pattern.search(stylesheet), (
            f"{selector} should set its background to var({fill})"
        )

    def test_planned_declares_no_fill_of_its_own(self, stylesheet: str) -> None:
        """Planned is the base rule; a third fill would be a second source."""
        assert ".illo-label.is-planned" not in stylesheet, (
            "planned should inherit the base .illo-label appearance rather "
            "than declare its own"
        )
