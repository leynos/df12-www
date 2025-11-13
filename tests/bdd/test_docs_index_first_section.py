"""Behaviour tests for docs index entry ordering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from pytest_bdd import given, scenarios, then, when

from df12_pages.config import load_site_config
from df12_pages.docs_index import DocsIndexBuilder
from df12_pages.generator import PageContentGenerator

FEATURE_FILE = Path(__file__).resolve().parents[2] / "features" / "docs_index_first_section.feature"
scenarios(FEATURE_FILE)


@pytest.fixture
def scenario_state() -> dict[str, object]:
    return {}


@given("a docs config for ordering behaviour")
def given_docs_config(tmp_path: Path, scenario_state: dict[str, object]) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    config_path = tmp_path / "pages.yaml"
    config_path.write_text(
        f"""
defaults:
  output_dir: {docs_root}
  docs_index_output: {tmp_path / "docs.html"}
pages:
  ordering:
    label: Ordering Docs
    source_url: https://example.invalid/docs.md
    repo: df12/zebra
    language: rust
    latest_release: v1.2.3
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    scenario_state["config_path"] = config_path


@given("markdown with out-of-order section names is stubbed")
def given_markdown_stub(scenario_state: dict[str, object]) -> None:
    scenario_state["markdown"] = (
        "## Zebra Start\n"
        "Zebra body.\n\n"
        "## Alpha Next\n"
        "Alpha body.\n"
    )


@when("I render the docs and build the index")
def when_render_and_index(
    scenario_state: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_site_config(scenario_state["config_path"])
    page = config.get_page("ordering")

    def _fake_fetch(self: PageContentGenerator) -> str:  # noqa: D401
        return scenario_state["markdown"]  # type: ignore[index]

    monkeypatch.setattr(PageContentGenerator, "_fetch_markdown", _fake_fetch)
    generator = PageContentGenerator(page)
    generator.run()

    builder = DocsIndexBuilder(config)
    index_path = builder.run()
    scenario_state["index_path"] = index_path


@then("the docs index entry links to the true first section")
def then_index_links_first_section(scenario_state: dict[str, object]) -> None:
    index_path: Path = scenario_state["index_path"]  # type: ignore[assignment]
    soup = BeautifulSoup(index_path.read_text(encoding="utf-8"), "html.parser")
    entry = soup.select_one(".product-card a.product-card__meta")
    assert entry is not None
    href = entry.get("href")
    assert href is not None
    assert href.endswith("docs-zebra-start.html")


@then("the docs card exposes repo, release, and registry links")
def then_card_has_external_links(scenario_state: dict[str, object]) -> None:
    """Verify docs card exposes repo, release, and registry links."""
    index_path: Path = scenario_state["index_path"]  # type: ignore[assignment]
    soup = BeautifulSoup(index_path.read_text(encoding="utf-8"), "html.parser")
    repo_link = soup.select_one("[data-test='docs-card-repo']")
    release_link = soup.select_one("[data-test='docs-card-release']")
    package_link = soup.select_one("[data-test='docs-card-package']")
    assert repo_link is not None, "expected a repo link element on the docs card"
    assert (
        repo_link.get("href") == "https://github.com/df12/zebra"
    ), f"expected repo link href to be 'https://github.com/df12/zebra', got {repo_link.get('href')!r}"
    assert release_link is not None, "expected a release link element on the docs card"
    assert (
        release_link.get("href") == "https://github.com/df12/zebra/releases/tag/v1.2.3"
    ), (
        "expected release link href to be 'https://github.com/df12/zebra/releases/tag/v1.2.3', "
        f"got {release_link.get('href')!r}"
    )
    assert package_link is not None, "expected a package link element on the docs card"
    assert (
        package_link.get("href") == "https://crates.io/crates/zebra"
    ), (
        "expected package link href to be 'https://crates.io/crates/zebra', "
        f"got {package_link.get('href')!r}"
    )
