"""Integration tests for the generated Episodic sub-site."""

from __future__ import annotations

from pathlib import Path

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


def test_episodic_generation_renders_every_configured_route(tmp_path: Path) -> None:
    """The configured home, shared, and content routes render to full pages."""
    site_config = load_site_config(REPO_ROOT / "config/pages.yaml")
    episodic = site_config.sites["episodic"]
    episodic.output_dir = tmp_path / "episodic"
    assert episodic.homepage is not None
    episodic.homepage.output = episodic.output_dir / "index.html"

    _generate_subsite(site_config, episodic)

    assert len(EXPECTED_ROUTES) == 17  # noqa: PLR2004
    for route in EXPECTED_ROUTES:
        output_path = episodic.output_dir / route / "index.html"
        assert output_path.is_file(), f"missing rendered route: /episodic/{route}/"
        assert "<main" in output_path.read_text(encoding="utf-8")
