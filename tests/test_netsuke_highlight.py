"""Tests for the Netsuke Pygments syntaxes and the highlight template tag."""

from __future__ import annotations

import typing as typ

from bs4 import BeautifulSoup
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_style_by_name
from pygments.token import Generic, Name, Token

from df12_pages.config import ContentPageConfig
from df12_pages.content_page import ContentPageGenerator

if typ.TYPE_CHECKING:
    from pathlib import Path

MANIFEST_FRAGMENT = (
    'netsuke_version: "1.0.0"\n'
    "rules:\n"
    "  - name: compile\n"
    '    command: "{{ cc }} -c {{ ins }} -o {{ outs }}"\n'
)

SESSION_FRAGMENT = "$ cargo build \\\n    --release\n   Compiling netsuke\n"


def test_netsuke_lexer_tokenizes_yaml_keys_and_jinja() -> None:
    """The ``netsuke`` lexer marks YAML keys and Jinja expressions distinctly."""
    lexer = get_lexer_by_name("netsuke")
    tokens = list(lexer.get_tokens(MANIFEST_FRAGMENT))

    key_values = [value for token, value in tokens if token in Name.Tag]
    assert "netsuke_version" in key_values
    assert "rules" in key_values

    jinja_values = {
        value
        for token, value in tokens
        if token not in Token.Literal.String and "cc" in value
    }
    assert jinja_values, "Jinja variable inside {{ ... }} should not lex as string"


def test_netsuke_console_lexer_commands_and_output() -> None:
    """``netsuke-console`` treats ``$`` lines as commands and others as output."""
    lexer = get_lexer_by_name("netsuke-console")
    tokens = list(lexer.get_tokens(SESSION_FRAGMENT))

    prompts = [value for token, value in tokens if token in Generic.Prompt]
    assert prompts == ["$ "]

    output = "".join(value for token, value in tokens if token in Generic.Output)
    assert "Compiling netsuke" in output
    assert "--release" not in output, "continued command line must not lex as output"


def test_himotoshi_style_uses_charcoal_background() -> None:
    """The shared style renders on the Himotoshi charcoal surface."""
    style = get_style_by_name("himotoshi")
    assert style.background_color == "#2e2a25"


def test_highlight_tag_renders_hm_syntax_block(tmp_path: Path) -> None:
    """The ``{% highlight %}`` tag renders Pygments markup with intact text."""
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "page.jinja").write_text(
        "{% highlight 'netsuke' %}{% raw %}\n"
        + MANIFEST_FRAGMENT
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
        stylesheet="assets/site.css",
    )
    output_path = generator.run()

    soup = BeautifulSoup(output_path.read_text(encoding="utf-8"), "html.parser")
    block = soup.find("div", class_="hm-syntax")
    assert block is not None, "highlight tag should emit a .hm-syntax wrapper"
    assert block.find("span", class_="nt") is not None, "YAML keys should be .nt"
    assert block.get_text().strip() == MANIFEST_FRAGMENT.strip()
