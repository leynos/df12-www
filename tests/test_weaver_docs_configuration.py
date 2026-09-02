"""Rendered contract for the Weaver docs-hub configuration section."""

from pathlib import Path

from bs4 import BeautifulSoup

from df12_pages.config import load_site_config
from df12_pages.content_page import ContentPageGenerator

REPO_ROOT = Path(__file__).resolve().parents[1]
EXACT_PRECEDENCE = "built-in defaults < config files < profile < environment < flags"
DISPLAYED_LAYERS = (
    ("5", "CLI flags"),
    ("4", "Environment variables"),
    ("3", "Profile"),
    ("2", "Configuration files"),
    ("1", "Built-in defaults"),
)
MINIMUM_PRECEDENCE_COLUMNS = 2


def test_docs_hub_publishes_the_planned_profile_precedence(
    tmp_path: Path,
) -> None:
    """The configuration section presents one coherent five-layer contract."""
    site_config = load_site_config(REPO_ROOT / "config" / "pages.yaml")
    weaver = site_config.sites["weaver"]
    docs_config = next(page for page in weaver.content_pages if page.key == "docs")
    output = ContentPageGenerator(
        docs_config,
        tmp_path,
        templates_dir=weaver.templates_dir,
        nav_links=weaver.nav_links,
        stylesheet=weaver.stylesheet,
        parent_link=weaver.parent_link,
        base_path=weaver.base_path,
        template_vars=weaver.template_vars,
    ).run()
    docs = BeautifulSoup(
        output.read_text(encoding="utf-8"),
        "html.parser",
    )
    configuration = docs.select_one("section#configuration")
    assert configuration is not None, "the docs hub must publish #configuration"

    configuration_text = configuration.get_text(" ", strip=True)
    assert EXACT_PRECEDENCE in configuration_text

    precedence_table = configuration.select_one("table")
    assert precedence_table is not None
    displayed_layers: list[tuple[str, str]] = []
    for row in precedence_table.select("tbody tr"):
        cells = row.select("td")
        assert len(cells) >= MINIMUM_PRECEDENCE_COLUMNS, (
            "each precedence row must name a priority and source"
        )
        displayed_layers.append(
            (
                cells[0].get_text(" ", strip=True),
                cells[1].get_text(" ", strip=True),
            )
        )
    assert tuple(displayed_layers) == DISPLAYED_LAYERS

    flags_heading = next(
        (
            heading
            for heading in configuration.select("h4")
            if heading.get_text(" ", strip=True) == "CLI Flags"
        ),
        None,
    )
    assert flags_heading is not None, "the configuration section must list CLI flags"
    flags_table = flags_heading.find_next("table")
    assert flags_table is not None
    profile_rows = [
        row
        for row in flags_table.select("tbody tr")
        if "--profile" in row.get_text(" ", strip=True)
    ]
    assert len(profile_rows) == 1
    profile_text = profile_rows[0].get_text(" ", strip=True)
    assert "--profile <NAME>" in profile_text
    assert "Planned for 0.1.0. Select a saved profile" in profile_text
    assert (
        "overrides configuration files and is overridden by environment variables "
        "and CLI flags" in profile_text
    )
