"""Behaviour tests for indented fenced code blocks."""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from pytest_bdd import given, scenarios, then, when

from df12_pages.config import load_site_config
from df12_pages.generator import PageContentGenerator

FEATURE_FILE = Path(__file__).resolve().parents[2] / "features" / "indented_code_blocks.feature"
scenarios(FEATURE_FILE)


@pytest.fixture
def scenario_state() -> dict[str, object]:
    return {}


@given("a docs config for indented code blocks")
def given_config(tmp_path: Path, scenario_state: dict[str, object]) -> None:
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
    config = load_site_config(scenario_state["config_path"])
    page = config.get_page("sample")

    def _fake_fetch(self: PageContentGenerator) -> str:  # noqa: D401  # TODO: bypass D401; test doubles mirror production method signature
        return scenario_state["markdown"]  # type: ignore[index]

    monkeypatch.setattr(PageContentGenerator, "_fetch_markdown", _fake_fetch)
    generator = PageContentGenerator(page, output_dir=scenario_state["output_dir"])
    written = generator.run()
    scenario_state["written"] = written


@then("the HTML includes a highlighted code block for the sample")
def then_html_has_code_block(scenario_state: dict[str, object]) -> None:
    written: list[Path] = scenario_state["written"]  # type: ignore[assignment]
    html = written[0].read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    code_blocks = soup.select(".codehilite code")
    assert any("fn main" in block.get_text() for block in code_blocks)
    assert any(
        block.find_parent("div", class_="codehilite").get("data-language") == "rust"
        for block in code_blocks
    )
