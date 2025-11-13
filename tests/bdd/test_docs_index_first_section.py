"""Behaviour tests for docs index entry ordering.

This module exercises the behaviour of the generated documentation index page
to ensure that the "first" docs section linked from the product card matches
the intended ordering in the site configuration rather than the underlying
filesystem or generation order. These checks help guard against regressions
where users would be sent to an unexpected starting page for the docs.

The tests are implemented as pytest-bdd scenarios backed by the
``docs_index_first_section.feature`` feature file. They construct a temporary
docs tree, run the docs index builder, and then assert on the resulting HTML
to verify the primary index entry and related external links.

Usage:
    Run these behaviour tests with pytest, for example:

        pytest tests/bdd/test_docs_index_first_section.py -v

    or as part of the full suite:

        make test

Prerequisites:
    - The development dependencies (including pytest-bdd and BeautifulSoup)
      installed via ``uv sync --group dev``.
    - Access to the feature file at
      ``features/docs_index_first_section.feature`` within this repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from pytest_bdd import given, scenarios, then, when

from df12_pages.config import load_site_config
from df12_pages.docs_index import DocsIndexBuilder
from df12_pages.generator import PageContentGenerator

FEATURE_FILE = (
    Path(__file__).resolve().parents[2]
    / "features"
    / "docs_index_first_section.feature"
)
scenarios(FEATURE_FILE)


@pytest.fixture
def scenario_state() -> dict[str, object]:
    """Return a mutable dict used to share scenario state across BDD steps."""
    return {}


@given("a docs config for ordering behaviour")
def given_docs_config(tmp_path: Path, scenario_state: dict[str, object]) -> None:
    """Set up a temporary docs configuration for ordering behaviour tests.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory provided by pytest for constructing a docs tree
        and configuration file.
    scenario_state : dict[str, object]
        Mutable state dictionary shared across BDD steps, used here to store
        the generated ``pages.yaml`` configuration path.

    Returns
    -------
    None
        This step registers the configuration path in ``scenario_state`` for
        later steps and does not return a value.
    """
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
    """Populate scenario state with markdown containing out-of-order section names.

    Parameters
    ----------
    scenario_state : dict[str, object]
        Mutable state dictionary shared across BDD steps where the stubbed
        ``markdown`` content is stored for later use.

    Returns
    -------
    None
        This step mutates ``scenario_state`` in place and does not return a
        value.
    """
    scenario_state["markdown"] = (
        "## Zebra Start\nZebra body.\n\n## Alpha Next\nAlpha body.\n"
    )


@when("I render the docs and build the index")
def when_render_and_index(
    scenario_state: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Render the docs and build the index for the ordering scenario.

    Parameters
    ----------
    scenario_state : dict[str, object]
        Mutable state dictionary shared across BDD steps. This step reads the
        stored configuration path and updates it with the generated
        ``index_path`` for the docs index.
    monkeypatch : pytest.MonkeyPatch
        Pytest monkeypatch fixture used to stub out
        ``PageContentGenerator._fetch_markdown`` so the page content comes
        from the scenario state instead of the network.

    Returns
    -------
    None
        This step mutates ``scenario_state`` in place by setting the
        ``index_path`` key and does not return a value.
    """
    config = load_site_config(scenario_state["config_path"])
    page = config.get_page("ordering")

    def _fake_fetch(self: PageContentGenerator) -> str:
        """Fetch fake page content for the docs index tests."""
        return scenario_state["markdown"]  # type: ignore[index]

    monkeypatch.setattr(PageContentGenerator, "_fetch_markdown", _fake_fetch)
    generator = PageContentGenerator(page)
    generator.run()

    builder = DocsIndexBuilder(config)
    index_path = builder.run()
    scenario_state["index_path"] = index_path


@then("the docs index entry links to the true first section")
def then_index_links_first_section(scenario_state: dict[str, object]) -> None:
    """Verify docs index entry links to the true first section."""
    index_path: Path = scenario_state["index_path"]  # type: ignore[assignment]
    soup = BeautifulSoup(index_path.read_text(encoding="utf-8"), "html.parser")
    entry = soup.select_one(".product-card a.product-card__meta")
    assert entry is not None, (
        "expected product-card meta link in docs index for first section"
    )
    href = entry.get("href")
    assert href is not None, "expected href attribute on product-card meta link"
    assert href.endswith("docs-zebra-start.html"), (
        f"expected href to end with 'docs-zebra-start.html', got {href!r}"
    )


@then("the docs card exposes repo, release, and registry links")
def then_card_has_external_links(scenario_state: dict[str, object]) -> None:
    """Verify docs card exposes repo, release, and registry links."""
    index_path: Path = scenario_state["index_path"]  # type: ignore[assignment]
    soup = BeautifulSoup(index_path.read_text(encoding="utf-8"), "html.parser")
    repo_link = soup.select_one("[data-test='docs-card-repo']")
    release_link = soup.select_one("[data-test='docs-card-release']")
    package_link = soup.select_one("[data-test='docs-card-package']")
    assert repo_link is not None, "expected a repo link element on the docs card"
    assert repo_link.get("href") == "https://github.com/df12/zebra", (
        "expected repo link href to be 'https://github.com/df12/zebra', "
        f"got {repo_link.get('href')!r}"
    )
    assert release_link is not None, "expected a release link element on the docs card"
    assert (
        release_link.get("href") == "https://github.com/df12/zebra/releases/tag/v1.2.3"
    ), (
        "expected release link href to be "
        "'https://github.com/df12/zebra/releases/tag/v1.2.3', "
        f"got {release_link.get('href')!r}"
    )
    assert package_link is not None, "expected a package link element on the docs card"
    assert package_link.get("href") == "https://crates.io/crates/zebra", (
        "expected package link href to be 'https://crates.io/crates/zebra', "
        f"got {package_link.get('href')!r}"
    )
