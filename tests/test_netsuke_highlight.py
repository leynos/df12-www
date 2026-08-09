"""Tests for the Himotoshi Pygments style and its generated ``.hm-syntax`` CSS."""

from __future__ import annotations

import re

import pytest
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name

from scripts.generate_himotoshi_pygments_css import (
    BEGIN,
    END,
    STYLESHEET,
    build_css,
)

#: A Netsukefile exercising comments, YAML keys, Jinja expressions, quoted
#: and plain scalars, and the block scalars the examples use for commands.
NETSUKEFILE_SOURCE = (
    "# Build the documentation set.\n"
    'netsuke_version: "1.0.0"\n'
    "\n"
    "vars:\n"
    "  greeting: Hello\n"
    "\n"
    "rules:\n"
    "  - name: render\n"
    "    command: >-\n"
    "      printf '%s\\n' \"{{ greeting }}\" > {{ outs }}\n"
)

#: A console session exercising the prompt, command, and output tokens.
CONSOLE_SOURCE = (
    "$ netsuke build --jobs 4\n"
    "[1/3] render docs/index.md\n"
    "[3/3] link build/site\n"
    "$ echo 'done'\n"
    "done\n"
)

#: The docs' configuration page highlights TOML: integers, booleans, and
#: strings of both quote flavours.
TOML_SOURCE = (
    "# netsuke.toml\n"
    "jobs = 4\n"
    "strict = true\n"
    'target = "docs"\n'
    "tags = ['fast', 'quiet']\n"
)

#: The install page highlights PowerShell for the Windows path.
POWERSHELL_SOURCE = (
    "# Install on Windows\n"
    "$env:NETSUKE_JOBS = 4\n"
    'Write-Host "Installing Netsuke" -ForegroundColor Green\n'
)

#: Every lexer the sub-site's templates name in a ``{% highlight %}`` tag.
SAMPLES = [
    ("netsuke", NETSUKEFILE_SOURCE),
    ("netsuke-console", CONSOLE_SOURCE),
    ("toml", TOML_SOURCE),
    ("powershell", POWERSHELL_SOURCE),
]


class TestHimotoshiPygmentsCss:
    """The generated block covers what the lexers actually emit."""

    @pytest.mark.parametrize(("lexer_name", "source"), SAMPLES)
    def test_generated_css_styles_every_class_pygments_emits(
        self,
        lexer_name: str,
        source: str,
    ) -> None:
        """The stylesheet covers token subtypes, not just declared categories.

        Pygments emits the most specific class it has — ``c1`` for a
        single-line comment, ``s2`` for a double-quoted string — while the
        style declares broad categories and lets subtypes inherit. A
        generator that emitted a rule per declared token would leave most of
        the markup's classes unstyled, which is invisible until someone reads
        the page.
        """
        markup = highlight(
            source,
            get_lexer_by_name(lexer_name),
            HtmlFormatter(cssclass="hm-syntax", wrapcode=True),
        )
        emitted = set(re.findall(r'class="([a-z0-9]+)"', markup))
        emitted.discard("hm-syntax")
        styled = set(re.findall(r"\.hm-syntax \.([a-z0-9]+)[ ,.{]", build_css()))

        assert emitted, f"the {lexer_name} sample should produce token classes"
        assert not emitted - styled, (
            f"classes emitted but unstyled: {sorted(emitted - styled)}"
        )

    def test_samples_still_exercise_the_regressed_subtype_classes(self) -> None:
        """The samples keep reaching the classes that were left unstyled.

        The defect showed up as comments and strings rendering at body
        colour. Editing a sample could quietly stop producing those classes
        and leave the coverage assertion above passing vacuously.
        """
        emitted: set[str] = set()
        for lexer_name, source in SAMPLES:
            markup = highlight(
                source,
                get_lexer_by_name(lexer_name),
                HtmlFormatter(cssclass="hm-syntax", wrapcode=True),
            )
            emitted |= set(re.findall(r'class="([a-z0-9]+)"', markup))

        # Comment.Single, String.Double, String.Single, Number.Integer,
        # Keyword.Constant, Name, Name.Constant, Text.Whitespace.
        regressed = {"c1", "s2", "s1", "mi", "kc", "n", "no", "w"}

        assert not regressed - emitted, (
            f"samples no longer emit: {sorted(regressed - emitted)}"
        )

    def test_generated_css_keeps_the_small_mobile_type_scale(self) -> None:
        """The narrow-viewport font-size override lives in the generated block.

        It once sat inside the markers as a hand edit, which the generator
        silently discarded on its next run. Emitting it keeps long terminal
        lines fitting on small screens across regenerations.
        """
        css = build_css()

        assert "@media (max-width: 459.98px) {" in css, (
            "the generated block should carry the small-mobile media query"
        )
        assert "font-size: 0.7rem;" in css, (
            "the small-mobile rule should shrink the code type scale"
        )

    def test_generated_css_drops_the_small_mobile_pre_padding(self) -> None:
        """Narrow viewports reclaim the pre's own leading and block insets.

        The wrapper chrome keeps its padding: that gutter is what holds the
        code off the dark ground's edge, and stripping it too left the text
        flush against the block border.
        """
        css = build_css()

        assert "@media (max-width: 460px) {" in css, (
            "the generated block should carry the narrow-viewport media query"
        )
        assert "padding-block: 0;" in css, (
            "the narrow-viewport rule should drop the pre's block padding"
        )
        assert "padding-left: 0;" in css, (
            "the narrow-viewport rule should drop the pre's left padding"
        )

    def test_committed_stylesheet_matches_the_generator(self) -> None:
        """The checked-in block is regenerated, never hand-edited.

        ``himotoshi.css`` is committed but its marked block is build output.
        A style change that lands without rerunning the generator leaves the
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
            f"{STYLESHEET} is stale; rerun scripts/generate_himotoshi_pygments_css.py"
        )

    def test_generator_writes_to_the_tracked_stylesheet(self) -> None:
        """The target is the tracked source, not the git-ignored build output.

        ``public/`` is rebuilt from ``src/static/``, so regenerating into
        ``public/`` would lose the new rules on the next clean build.
        """
        assert STYLESHEET.parts[-5:] == (
            "static",
            "netsuke",
            "assets",
            "css",
            "himotoshi.css",
        ), f"unexpected stylesheet target: {STYLESHEET}"
