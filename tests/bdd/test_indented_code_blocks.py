"""Behaviour tests for indented fenced code blocks.

These pytest-bdd scenarios prove that indented fenced code samples render with
syntax highlighting when Markdown is processed via ``PageContentGenerator``.
The feature file ``indented_code_blocks.feature`` drives the scenario to ensure
Rust snippets nested inside lists retain their ``codehilite`` metadata so they
display the expected language label.

Usage
-----
Run ``pytest tests/bdd/test_indented_code_blocks.py -v`` after installing the
dev dependencies (``uv sync --group dev``). The scenario relies on the
``scenario_state`` fixture and stubs ``PageContentGenerator._fetch_markdown`` to
avoid network calls, so no external services are required.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from pytest_bdd import given, scenarios, then, when

from df12_pages.config import load_site_config
from df12_pages.generator import PageContentGenerator

FEATURE_FILE = (
    Path(__file__).resolve().parents[2] / "features" / "indented_code_blocks.feature"
)
scenarios(FEATURE_FILE)


@pytest.fixture
def scenario_state() -> dict[str, object]:
    """Return a mutable dict used to share scenario state across BDD steps."""
    return {}


@given("a docs config for indented code blocks")
def given_config(tmp_path: Path, scenario_state: dict[str, object]) -> None:
    """Set up a docs config used to exercise indented fenced code blocks."""
    output_dir = tmp_path / "docs"
    output_dir.mkdir()
    config_path = tmp_path / "pages.yaml"
    config_path.write_text(
        f"""
defaults:
  output_dir: {output_dir}
pages:
  sample:
    label: Sample Docs
    source_url: https://example.invalid/docs.md
    description: Sample description
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    scenario_state["config_path"] = config_path
    scenario_state["output_dir"] = output_dir


@given("markdown content with indented fenced code blocks is stubbed")
def given_stubbed_markdown(scenario_state: dict[str, object]) -> None:
    """Populate scenario state with stubbed markdown containing indented code blocks."""
    scenario_state["markdown"] = (
        "## Intro\n"
        "- **Example** demonstrates inline code\n\n"
        "  ```rust,no_run\n"
        '  fn main() { println!("hi"); }\n'
        "  ```\n"
    )


@when("I render the sample docs page")
def when_render_docs(
    scenario_state: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render the sample docs page for the indented code blocks scenario."""
    config_path = typ.cast("Path", scenario_state["config_path"])
    config = load_site_config(config_path)
    page = config.get_page("sample")

    def _fake_fetch(self: PageContentGenerator) -> str:
        """Return stubbed markdown content for indented code block tests."""
        return typ.cast("str", scenario_state["markdown"])

    monkeypatch.setattr(PageContentGenerator, "_fetch_markdown", _fake_fetch)
    output_dir = typ.cast("Path", scenario_state["output_dir"])
    generator = PageContentGenerator(page, output_dir=output_dir)
    written = generator.run()
    scenario_state["written"] = written


@then("the HTML includes a highlighted code block for the sample")
def then_html_has_code_block(scenario_state: dict[str, object]) -> None:
    """Verify the rendered HTML includes a highlighted Rust code block."""
    written = typ.cast("list[Path]", scenario_state["written"])
    html = written[0].read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    code_blocks = soup.select(".codehilite code")
    assert any("fn main" in block.get_text() for block in code_blocks), (
        "expected a highlighted code block containing 'fn main' in the rendered HTML"
    )
    assert any(
        block.find_parent("div", class_="codehilite").get("data-language") == "rust"
        for block in code_blocks
    ), "expected a codehilite block with data-language='rust'"
