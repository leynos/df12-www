"""Unit tests for the shared MiniJinja template layer and highlight filter.

``df12_pages.templating`` decides loading, escaping and the reproducible build
timestamp for every page builder, while ``df12_pages.jinja_highlight`` turns a
template filter block into Pygments markup. A mistake in either surfaces only
as a subtly wrong rendered page, so each rule is pinned here directly rather
than through a full build.
"""

from __future__ import annotations

import datetime as dt
import typing as typ

import pytest

from df12_pages.jinja_highlight import DEFAULT_CSS_CLASS, highlight_code
from df12_pages.templating import build_timestamp, template_environment

if typ.TYPE_CHECKING:
    from pathlib import Path

#: The Unix timestamp used by the test fixtures: 2 October 2026, 00:00 UTC.
REFERENCE_EPOCH = 1790899200
REFERENCE_EPOCH_UTC = dt.datetime(2026, 10, 2, tzinfo=dt.UTC)


def test_build_timestamp_returns_the_current_utc_time_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a reproducible epoch the build stamps the present moment."""
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)

    before = dt.datetime.now(dt.UTC)
    stamp = build_timestamp()
    after = dt.datetime.now(dt.UTC)

    assert stamp.tzinfo is dt.UTC, f"expected a UTC datetime, got {stamp!r}"
    assert before <= stamp <= after, (
        f"expected a timestamp between {before!r} and {after!r}, got {stamp!r}"
    )


def test_build_timestamp_honours_the_reproducible_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SOURCE_DATE_EPOCH`` fixes the rendered date for reproducible builds."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(REFERENCE_EPOCH))

    assert build_timestamp() == REFERENCE_EPOCH_UTC


def test_build_timestamp_rejects_a_non_integer_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed epoch is a configuration error, not a silent fallback."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-a-timestamp")

    with pytest.raises(ValueError, match="invalid literal"):
        build_timestamp()


@pytest.mark.parametrize(
    ("suffix", "escaped"),
    [
        ("page.html", True),
        ("page.xml", True),
        ("page.jinja", False),
        ("page.txt", False),
    ],
)
def test_escape_by_suffix_escapes_only_markup_documents(
    tmp_path: Path, suffix: str, *, escaped: bool
) -> None:
    """The document builders escape HTML and XML but leave other suffixes raw."""
    (tmp_path / suffix).write_text("{{ value }}", encoding="utf-8")
    environment = template_environment(tmp_path, escape_by_suffix=True)

    rendered = environment.render_template(suffix, value="<b>x</b>")

    expected = "&lt;b&gt;x&lt;/b&gt;" if escaped else "<b>x</b>"
    assert rendered == expected, f"{suffix} rendered {rendered!r}"


def test_escape_by_suffix_false_escapes_every_suffix(tmp_path: Path) -> None:
    """The other builders enable HTML escaping for their own ``.jinja`` files."""
    (tmp_path / "page.jinja").write_text("{{ value }}", encoding="utf-8")
    environment = template_environment(tmp_path, escape_by_suffix=False)

    rendered = environment.render_template("page.jinja", value="<b>x</b>")

    assert rendered == "&lt;b&gt;x&lt;/b&gt;", f"rendered {rendered!r}"


def test_highlight_code_rejects_an_unknown_lexer() -> None:
    """A typo in a template's lexer name must fail the build, not pass through."""
    with pytest.raises(RuntimeError, match="names an unknown Pygments lexer"):
        highlight_code("x = 1", "no-such-lexer")


def test_highlight_code_adds_a_tab_stop_to_the_scrolling_wrapper() -> None:
    """A region that scrolls itself must also be reachable from the keyboard."""
    rendered = highlight_code("x = 1", "python", DEFAULT_CSS_CLASS)

    assert 'class="hm-syntax"' in rendered
    assert 'tabindex="0"' in rendered, (
        f"the scrolling wrapper needs a tab stop; got {rendered!r}"
    )


def test_highlight_code_leaves_a_non_scrolling_wrapper_unfocusable() -> None:
    """A wrapper the stylesheet does not scroll needs no pointless tab stop."""
    rendered = highlight_code("x = 1", "python", "code-inner")

    assert 'class="code-inner"' in rendered
    assert 'tabindex="0"' not in rendered, (
        f"a non-scrolling wrapper should not be focusable; got {rendered!r}"
    )
