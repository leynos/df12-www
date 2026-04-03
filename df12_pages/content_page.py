"""Render rich-HTML content pages from Jinja templates for sub-sites."""

from __future__ import annotations

import dataclasses as dc
import datetime as dt
import typing as typ

from jinja2 import Environment, FileSystemLoader

if typ.TYPE_CHECKING:
    from pathlib import Path

    from .config import ContentPageConfig, NavLinkConfig


class ContentPageGenerator:
    """Render a Jinja page template with shared chrome into a sub-site directory."""

    def __init__(  # noqa: PLR0913 -- template rendering requires config, output, templates, nav, stylesheet, parent link
        self,
        config: ContentPageConfig,
        output_dir: Path,
        *,
        templates_dir: Path,
        nav_links: list[NavLinkConfig],
        stylesheet: str,
        parent_link: NavLinkConfig | None = None,
    ) -> None:
        self.config = config
        self.output_dir = output_dir
        self.templates_dir = templates_dir
        self.nav_links = nav_links
        self.stylesheet = stylesheet
        self.parent_link = parent_link
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def run(self) -> Path:
        """Render the page template and write the output file."""
        template = self.env.get_template(self.config.template)
        marked_nav = self._mark_current_nav()
        context = {
            "nav_links": marked_nav,
            "parent_link": self.parent_link,
            "stylesheet": self.stylesheet,
            "generated_at": dt.datetime.now(dt.UTC),
        }
        html = template.render(**context)
        if not html.endswith("\n"):
            html += "\n"
        output_path = self.output_dir / self.config.output_slug / "index.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def _mark_current_nav(self) -> list[dict[str, typ.Any]]:
        """Return nav_links dicts with ``current`` flag for the active page."""
        target_href = f"../{self.config.output_slug}/"
        result: list[dict[str, typ.Any]] = []
        for link in self.nav_links:
            entry = dc.asdict(link)
            if link.href == target_href:
                entry["current"] = True
                entry["href"] = "./"
            result.append(entry)
        return result


__all__ = ["ContentPageGenerator"]
