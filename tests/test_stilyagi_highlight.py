"""Tests for the Stilyagi Pygments style and the highlight tag's wrapper class."""

from __future__ import annotations

import typing as typ

from bs4 import BeautifulSoup
from pygments.styles import get_style_by_name
from pygments.token import Comment, Keyword, Token

from df12_pages.config import ContentPageConfig
from df12_pages.content_page import ContentPageGenerator
from df12_pages.stilyagi_highlighting import StilyagiStyle

if typ.TYPE_CHECKING:
    from pathlib import Path

RULE_FRAGMENT = (
    "from stilyagi.rule import Rule, Level\n"
    "\n"
    "\n"
    "class HeadingDepthRule(Rule):\n"
    '    """Reject Markdown headings deeper than level 3."""\n'
    "\n"
    '    code = "MD201"\n'
)

#: The lamp-black ground the sub-site sets code on.
INK = "#0f0f0f"
#: WCAG 2.2 AA floor for body text.
MIN_CONTRAST = 4.5
#: sRGB threshold below which the transfer function is linear.
_SRGB_LINEAR_CUTOFF = 0.04045


def _relative_luminance(colour: str) -> float:
    """Return the WCAG relative luminance of a ``#rrggbb`` colour."""

    def channel(value: int) -> float:
        fraction = value / 255
        if fraction <= _SRGB_LINEAR_CUTOFF:
            return fraction / 12.92
        return ((fraction + 0.055) / 1.055) ** 2.4

    digits = colour.lstrip("#")
    red, green, blue = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def _contrast_ratio(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two ``#rrggbb`` colours."""
    first, second = _relative_luminance(foreground), _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


class TestStilyagiHighlighting:
    """The Stilyagi style and the highlight tag's configurable wrapper."""

    def test_style_is_registered_and_uses_the_ink_background(self) -> None:
        """The style resolves by name and renders on the ink ground."""
        style = get_style_by_name("stilyagi")
        assert style.background_color == INK, (
            "the style background should be the lamp-black ink"
        )

    def test_every_token_colour_clears_the_body_text_floor(self) -> None:
        """Each token colour meets WCAG 2.2 AA against the ink ground.

        The palette's paper-surface reds, sages, and magentas fall below the
        floor on this ground, so the style carries lightened variants; this
        guards against a future edit reintroducing a paper-surface value.
        """
        failures: list[str] = []
        for token, spec in StilyagiStyle.styles.items():
            colour = next((word for word in spec.split() if word.startswith("#")), "")
            if not colour:
                continue
            ratio = _contrast_ratio(colour, INK)
            if ratio < MIN_CONTRAST:
                failures.append(f"{token} {colour} is {ratio:.2f}:1")
        assert not failures, (
            f"token colours below {MIN_CONTRAST}:1 on {INK}: {failures}"
        )

    def test_style_covers_the_tokens_python_source_produces(self) -> None:
        """Keywords and comments are styled rather than inheriting body text."""
        for token in (Keyword, Comment, Token):
            assert token in StilyagiStyle.styles, f"{token} should carry a colour"

    def test_highlight_tag_honours_a_named_wrapper_class(
        self,
        tmp_path: Path,
    ) -> None:
        """A second tag argument replaces the default ``hm-syntax`` wrapper."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "page.jinja").write_text(
            "{% highlight 'python', 'stilyagi-syntax' %}{% raw %}\n"
            + RULE_FRAGMENT
            + "{% endraw %}{% endhighlight %}\n",
            encoding="utf-8",
        )

        config = ContentPageConfig(
            key="page",
            label="Page",
            template="page.jinja",
            output_slug="page",
        )
        generator = ContentPageGenerator(
            config,
            tmp_path / "out",
            templates_dir=templates_dir,
            nav_links=[],
            stylesheet="assets/styles/stilyagi-site.css",
        )
        output_path = generator.run()

        soup = BeautifulSoup(output_path.read_text(encoding="utf-8"), "html.parser")
        block = soup.find("div", class_="stilyagi-syntax")
        assert block is not None, "the named wrapper class should be used"
        assert soup.find("div", class_="hm-syntax") is None, (
            "the Netsuke default should not leak into a named block"
        )
        assert block.find("span", class_="kn") is not None, (
            "`import` should lex as a keyword"
        )
        assert block.get_text().strip() == RULE_FRAGMENT.strip(), (
            "highlighted source text should round-trip unchanged"
        )

    def test_highlight_tag_still_defaults_to_the_netsuke_wrapper(
        self,
        tmp_path: Path,
    ) -> None:
        """Omitting the class keeps the Netsuke sub-site's existing markup."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "page.jinja").write_text(
            "{% highlight 'python' %}{% raw %}\n"
            "x = 1\n"
            "{% endraw %}{% endhighlight %}\n",
            encoding="utf-8",
        )

        config = ContentPageConfig(
            key="page",
            label="Page",
            template="page.jinja",
            output_slug="page",
        )
        generator = ContentPageGenerator(
            config,
            tmp_path / "out",
            templates_dir=templates_dir,
            nav_links=[],
            stylesheet="assets/site.css",
        )
        output_path = generator.run()

        soup = BeautifulSoup(output_path.read_text(encoding="utf-8"), "html.parser")
        assert soup.find("div", class_="hm-syntax") is not None, (
            "the default wrapper class should be unchanged"
        )
