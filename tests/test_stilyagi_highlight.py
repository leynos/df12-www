"""Tests for the Stilyagi Pygments style and the highlight tag's wrapper class."""

from __future__ import annotations

import re
import typing as typ

from bs4 import BeautifulSoup
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_style_by_name
from pygments.token import Comment, Keyword, Token

from df12_pages.config import ContentPageConfig
from df12_pages.content_page import ContentPageGenerator
from df12_pages.stilyagi_highlighting import StilyagiStyle
from scripts.generate_stilyagi_pygments_css import (
    BEGIN,
    END,
    STYLESHEET,
    build_css,
)

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

#: Exercises the token families the sub-site's rule example uses: comments,
#: imports, class and function definitions, docstrings, strings, and numbers.
SAMPLE_SOURCE = (
    "# rules/heading_depth.py\n"
    "from stilyagi.rule import Rule, Level\n"
    "\n"
    "\n"
    "class HeadingDepthRule(Rule):\n"
    '    """Reject Markdown headings deeper than level 3."""\n'
    "\n"
    '    code = "MD201"\n'
    "    level = Level.WARNING\n"
    "    capabilities = ()\n"
    "\n"
    "    def check_heading(self, h) -> None:\n"
    "        if h.depth > 3:\n"
    '            self.report(span=h.marker_span, message=f"depth {h.depth}")\n'
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
        """Return one 0-255 channel linearized per the sRGB transfer function."""
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

    def test_generated_css_styles_every_class_pygments_emits(self) -> None:
        """The stylesheet covers token subtypes, not just declared categories.

        Pygments emits the most specific class it has — ``c1`` for a
        single-line comment, ``kn`` for an import keyword — while the style
        declares broad categories and lets subtypes inherit. A generator that
        emitted a rule per declared token would leave most of the markup's
        classes unstyled, which is invisible until someone reads the page.

        For a token type Pygments has no standard class for it writes an
        ancestor chain rather than one name — ``class="p p-Indicator"`` —
        so the attribute is matched whole and split afterwards. Matching
        only lowercase single names would skip such an attribute
        entirely rather than partially. The Python sample happens to
        produce none today, but the extraction should not be what
        decides that.
        """
        markup = highlight(
            SAMPLE_SOURCE,
            get_lexer_by_name("python"),
            HtmlFormatter(cssclass="stilyagi-syntax", wrapcode=True),
        )
        attributes = [
            value
            for value in re.findall(r'class="([^"]*)"', markup)
            if value != "stilyagi-syntax"
        ]
        styled = {
            name
            for chain in re.findall(r"\.stilyagi-syntax \.([\w.-]+)", build_css())
            for name in chain.split(".")
        }
        unstyled = [value for value in attributes if not set(value.split()) & styled]

        assert attributes, "the sample should produce token classes"
        assert not unstyled, f"spans emitted with no styled class: {sorted(unstyled)}"

    def test_committed_stylesheet_matches_the_generator(self) -> None:
        """The checked-in block is regenerated, never hand-edited.

        ``syntax.css`` is committed but its marked block is build output. A
        style change that lands without rerunning the generator leaves the
        stylesheet describing the old palette, which nothing else here would
        notice: every other assertion reads ``build_css()`` directly.
        """
        css = STYLESHEET.read_text(encoding="utf-8")
        start = css.find(BEGIN)
        end = css.find(END)

        assert start != -1, f"{STYLESHEET} should carry the BEGIN marker"
        assert end != -1, f"{STYLESHEET} should carry the END marker"

        committed = css[start : end + len(END)]

        assert committed == build_css(), (
            f"{STYLESHEET} is stale; rerun scripts/generate_stilyagi_pygments_css.py"
        )

    def test_layout_rules_stay_before_the_generated_marker(self) -> None:
        """The generator owns tokens, while hand-written CSS owns layout."""
        css = STYLESHEET.read_text(encoding="utf-8")
        marker = css.index(BEGIN)
        generated = css[marker : css.index(END) + len(END)]
        layout_rules = (
            ".code-scroll {",
            ".stilyagi-syntax {\n  flex: 1;",
            ".stilyagi-syntax pre {",
        )

        for rule in layout_rules:
            assert rule in css[:marker], (
                f"{rule!r} should remain before the generated marker"
            )
            assert rule not in generated, f"{rule!r} should not be generated"

    def test_generator_writes_to_the_tracked_stylesheet(self) -> None:
        """The target is the tracked source, not the git-ignored build output.

        ``public/`` is rebuilt from ``src/static/``, so regenerating into
        ``public/`` would lose the new rules on the next clean build. The
        Netsuke generator did exactly that for months; this asserts the
        sister generator cannot drift the same way. The comparison reaches
        back to ``src`` because the published tree mirrors the source
        layout, and only that segment tells the two apart.
        """
        assert STYLESHEET.parts[-6:] == (
            "src",
            "static",
            "stilyagi",
            "assets",
            "styles",
            "syntax.css",
        ), f"unexpected stylesheet target: {STYLESHEET}"

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
