"""Homepage builder for df12 marketing site."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import HomepageConfig


class HomePageBuilder:
    """Render the marketing homepage from structured config data."""

    def __init__(self, homepage: HomepageConfig, *, templates_dir: Path | None = None) -> None:
        self.homepage = homepage
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template("home_page.jinja")

    def run(self) -> Path:
        """Render the homepage HTML to the configured output path."""
        output_path = self.homepage.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        context = {
            "homepage": self.homepage,
            "generated_at": dt.datetime.now(dt.UTC),
        }
        html = self.template.render(**context)
        if not html.endswith("\n"):
            html += "\n"
        output_path.write_text(html, encoding="utf-8")
        return output_path
