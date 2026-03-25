"""Render sub-site homepages from freeform template context."""

from __future__ import annotations

import datetime as dt
import typing as typ
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

if typ.TYPE_CHECKING:
    from .config import SubSiteHomepageConfig


class SubSiteHomePageBuilder:
    """Render a sub-site homepage from freeform context data."""

    def __init__(
        self,
        config: SubSiteHomepageConfig,
        *,
        templates_dir: Path | None = None,
    ) -> None:
        """Initialize the sub-site homepage builder.

        Parameters
        ----------
        config : SubSiteHomepageConfig
            Homepage configuration with output path, title, and freeform
            context dict consumed by the sub-site's ``home_page.jinja``.
        templates_dir : Path, optional
            Directory containing Jinja templates for this sub-site.
        """
        self.config = config
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template("home_page.jinja")

    def run(self) -> Path:
        """Render and write the sub-site homepage HTML."""
        output_path = self.config.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        context = {
            "title": self.config.title,
            **self.config.context,
            "generated_at": dt.datetime.now(dt.UTC),
        }
        html = self.template.render(**context)
        if not html.endswith("\n"):
            html += "\n"
        output_path.write_text(html, encoding="utf-8")
        return output_path


__all__ = ["SubSiteHomePageBuilder"]
