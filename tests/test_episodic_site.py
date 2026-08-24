"""Integration tests for the generated Episodic sub-site."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from df12_pages.cli import _generate_subsite
from df12_pages.config import load_site_config

REPO_ROOT = Path(__file__).resolve().parent.parent


EXPECTED_ROUTES = (
    "",
    "terms-of-use",
    "privacy-policy",
    "code-of-conduct",
    "why",
    "workflow",
    "workflow/content",
    "workflow/quality",
    "workflow/audio",
    "architecture",
    "interfaces",
    "docs",
    "docs/getting-started",
    "docs/api",
    "roadmap",
    "contributing",
    "hosting",
)
EXPECTED_ROUTE_COUNT = 17


def test_episodic_generation_renders_every_configured_route(tmp_path: Path) -> None:
    """The configured home, shared, and content routes render to full pages."""
    site_config = load_site_config(REPO_ROOT / "config/pages.yaml")
    episodic = site_config.sites["episodic"]
    episodic.output_dir = tmp_path / "episodic"
    assert episodic.homepage is not None, "Episodic must configure a homepage"
    episodic.homepage.output = episodic.output_dir / "index.html"

    _generate_subsite(site_config, episodic)

    assert len(EXPECTED_ROUTES) == EXPECTED_ROUTE_COUNT, (
        "route fixture must cover every configured Episodic route"
    )
    for route in EXPECTED_ROUTES:
        output_path = episodic.output_dir / route / "index.html"
        assert output_path.is_file(), f"missing rendered route: /episodic/{route}/"
        assert "<main" in output_path.read_text(encoding="utf-8"), (
            f"rendered route lacks its main landmark: /episodic/{route}/"
        )


def test_interface_catalogue_links_resolve_to_configured_routes(tmp_path: Path) -> None:
    """Every catalogue destination resolves to a configured Episodic route."""
    site_config = load_site_config(REPO_ROOT / "config/pages.yaml")
    episodic = site_config.sites["episodic"]
    episodic.output_dir = tmp_path / "episodic"
    assert episodic.homepage is not None, "Episodic must configure a homepage"
    episodic.homepage.output = episodic.output_dir / "index.html"
    _generate_subsite(site_config, episodic)

    configured_slugs = {page.output_slug for page in episodic.content_pages}
    configured_slugs.update(
        site_config.shared_content[key].output_slug
        for key in episodic.shared_content_refs
    )
    configured_targets = {f"/episodic/{slug}/" for slug in configured_slugs}
    configured_targets.add("/episodic/")
    soup = BeautifulSoup(
        (episodic.output_dir / "interfaces" / "index.html").read_text(encoding="utf-8"),
        "html.parser",
    )
    catalogue_targets = {
        link["href"]
        for row in soup.select('article[id^="interface-"]')
        for link in row.select("a.text-link")
    }
    assert catalogue_targets, (
        "interface catalogue must render its configured detail links"
    )
    assert catalogue_targets <= configured_targets, (
        "interface catalogue links must resolve to configured Episodic routes"
    )


def test_roadmap_task_macro_renders_nested_tasks_with_missing_optional_fields() -> None:
    """The recursive roadmap macro accepts incomplete nested task records."""
    environment = Environment(
        autoescape=True,
        loader=FileSystemLoader(REPO_ROOT / "templates/episodic"),
    )
    rendered = environment.from_string(
        '{% import "records.jinja" as rec %}{{ rec.roadmap_task(task) }}'
    ).render(
        task={
            "done": False,
            "id": "1",
            "subtasks": [{"done": True, "id": "1.1", "title": "Nested task"}],
            "title": "Parent task",
        }
    )
    soup = BeautifulSoup(rendered, "html.parser")
    nested = soup.select_one("ul.task-list--nested")
    assert nested is not None, (
        "parent tasks with subtasks must render a nested task list"
    )
    nested_title = nested.select_one("li.task .task__title")
    assert nested_title is not None, "nested task must render its title"
    assert nested_title.get_text(strip=True) == "Nested task"
