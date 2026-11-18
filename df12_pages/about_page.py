"""df12 about page rendering pipeline."""

from __future__ import annotations

import datetime as dt
import typing as typ
from pathlib import Path

from .templating import template_environment

if typ.TYPE_CHECKING:
    from .config import AboutPageConfig


class AboutPageBuilder:
    """Render the About page from structured config data."""

    def __init__(
        self, about: AboutPageConfig, *, templates_dir: Path | None = None
    ) -> None:
        """Initialize the builder and Jinja environment."""
        self.about = about
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.env = template_environment(self.templates_dir)

    def run(self) -> Path:
        """Render and write the About page HTML, returning the output path."""
        output_path = self.about.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        context = {"about": self.about, "generated_at": dt.datetime.now(dt.UTC)}
        html = self.env.render_template("about_page.jinja", **context)
        if not html.endswith("\n"):
            html += "\n"
        output_path.write_text(html, encoding="utf-8")
        return output_path


__all__ = ["AboutPageBuilder"]
