"""Tests for the Himotoshi Pygments style and its generated ``.hm-syntax`` CSS."""

from __future__ import annotations

import re

import pytest
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Punctuation

from df12_pages.highlighting import HimotoshiStyle
from scripts.generate_himotoshi_pygments_css import (
    BEGIN,
    END,
    STYLESHEET,
    build_css,
)
from scripts.pygments_css import _token_classes

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
SAMPLES = (
    ("netsuke", NETSUKEFILE_SOURCE),
    ("netsuke-console", CONSOLE_SOURCE),
    ("toml", TOML_SOURCE),
    ("powershell", POWERSHELL_SOURCE),
)

#: A whole ``class`` attribute value. Pygments writes a space-separated
#: ancestor chain for token types it has no single standard class for, such
#: as ``class="p p-Indicator"``, so matching the attribute wholesale and
#: splitting afterwards is the only way to see those names at all.
CLASS_ATTRIBUTE = re.compile(r'class="([^"]*)"')

#: A ``.hm-syntax`` descendant selector's class chain. Compound selectors
#: such as ``.hm-syntax .p.p-Indicator`` carry more than one name.
STYLED_SELECTOR = re.compile(r"\.hm-syntax \.([\w.-]+)")


def _emitted_class_attributes(lexer_name: str, source: str) -> list[str]:
    """Return each token span's whole ``class`` value from highlighted markup."""
    markup = highlight(
        source,
        get_lexer_by_name(lexer_name),
        HtmlFormatter(cssclass="hm-syntax", wrapcode=True),
    )
    return [value for value in CLASS_ATTRIBUTE.findall(markup) if value != "hm-syntax"]


def _styled_class_names(css: str) -> set[str]:
    """Return every class name the generated block styles."""
    return {name for chain in STYLED_SELECTOR.findall(css) for name in chain.split(".")}


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

        The question asked is whether each span picks up a colour, not
        whether every name in its class attribute is mentioned in the CSS.
        For a token type Pygments has no standard class for it writes an
        ancestor chain — ``class="l l-Scalar l-Scalar-Plain"`` for a plain
        YAML scalar — and the span is coloured by the ``l`` in that chain.
        Demanding a rule for every name would fail on those without any
        token rendering wrongly.
        """
        attributes = _emitted_class_attributes(lexer_name, source)
        styled = _styled_class_names(build_css())
        unstyled = [value for value in attributes if not set(value.split()) & styled]

        assert attributes, f"the {lexer_name} sample should produce token classes"
        assert not unstyled, f"spans emitted with no styled class: {sorted(unstyled)}"

    def test_samples_still_exercise_the_regressed_subtype_classes(self) -> None:
        """The samples keep reaching the classes that were left unstyled.

        The defect showed up as comments and strings rendering at body
        colour. Editing a sample could quietly stop producing those classes
        and leave the coverage assertion above passing vacuously.
        """
        emitted = {
            name
            for lexer_name, source in SAMPLES
            for value in _emitted_class_attributes(lexer_name, source)
            for name in value.split()
        }

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

        This shares the type scale's breakpoint above. The two were once
        0.02px apart, which meant a hair's width of viewport where the
        padding had gone but the type had not shrunk.
        """
        css = build_css()

        assert "@media (max-width: 459.98px) {" in css, (
            "the padding rule should share the small-mobile breakpoint"
        )
        assert "@media (max-width: 460px) {" not in css, (
            "the near-duplicate 460px breakpoint should be gone"
        )
        assert "padding-block: 0;" in css, (
            "the narrow-viewport rule should drop the pre's block padding"
        )
        assert "padding-left: 0;" in css, (
            "the narrow-viewport rule should drop the pre's left padding"
        )

    def test_declared_subtypes_keep_the_extras_they_inherit(self) -> None:
        """A subtype that restates only its colour keeps its parent's italic.

        Pygments resolves a token by copying its parent's flags and then
        applying whatever the child restates, so ``Comment.Preproc`` — the
        Jinja ``{% ... %}`` markers, declared as a bare colour — is italic
        because ``Comment`` is. Reading the raw spec strings instead of the
        formatter's resolved style dropped that, and the markers rendered
        upright while every other comment class did not.
        """
        css = build_css()
        preproc = next(
            line for line in css.splitlines() if line.startswith(".hm-syntax .cp ")
        )

        assert "font-style: italic;" in preproc, (
            f"Comment.Preproc should inherit Comment's italic: {preproc}"
        )

    def test_the_local_token_class_algorithm_still_behaves(self) -> None:
        """Pin the token-class contract owned by the shared local helper.

        The helper mirrors Pygments' class algorithm through the public
        ``STANDARD_TYPES`` mapping, including the space-separated ancestor
        chain that the grouping in ``scripts.pygments_css`` needs.
        """
        formatter = HtmlFormatter(style=HimotoshiStyle, cssclass="hm-syntax")

        plain = _token_classes(formatter, Comment.Single)
        compound = _token_classes(formatter, Punctuation.Indicator)

        assert plain == "c1", f"expected the leaf class alone, got {plain!r}"
        assert compound.split() == ["p", "p-Indicator"], (
            f"expected a space-separated ancestor chain, got {compound!r}"
        )

        prefixed_formatter = HtmlFormatter(
            style=HimotoshiStyle,
            cssclass="hm-syntax",
            classprefix="tok-",
        )
        prefixed_plain = _token_classes(prefixed_formatter, Comment.Single)
        prefixed_compound = _token_classes(
            prefixed_formatter,
            Punctuation.Indicator,
        )

        assert prefixed_plain == "tok-c1", (
            f"expected the prefixed leaf class, got {prefixed_plain!r}"
        )
        assert prefixed_compound.split() == ["tok-p", "tok-p-Indicator"], (
            "expected every class in the ancestor chain to carry the prefix, "
            f"got {prefixed_compound!r}"
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

        The comparison has to reach back as far as ``src``: the published
        tree mirrors the source layout, so every component below it matches
        either way and only that segment tells the two apart.
        """
        assert STYLESHEET.parts[-6:] == (
            "src",
            "static",
            "netsuke",
            "assets",
            "css",
            "himotoshi.css",
        ), f"unexpected stylesheet target: {STYLESHEET}"
