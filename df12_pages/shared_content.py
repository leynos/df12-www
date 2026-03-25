"""Render shared-copy pages (terms of use, privacy policy, etc.) into a site."""

from __future__ import annotations

import datetime as dt
import typing as typ
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader
from markdown import markdown

if typ.TYPE_CHECKING:
    from .config import NavLinkConfig, SharedContentConfig


class SharedContentGenerator:
    """Render a shared markdown page into a site's template wrapper."""

    def __init__(  # noqa: PLR0913
        self,
        shared_config: SharedContentConfig,
        output_dir: Path,
        *,
        templates_dir: Path | None = None,
        template_name: str = "shared_content_page.jinja",
        nav_links: list[NavLinkConfig] | None = None,
        parent_link: NavLinkConfig | None = None,
        stylesheet: str | None = None,
    ) -> None:
        """Initialize the shared content generator.

        Parameters
        ----------
        shared_config : SharedContentConfig
            Shared content definition with source path/URL and output slug.
        output_dir : Path
            Root output directory for this site.
        templates_dir : Path, optional
            Directory containing Jinja templates.
        template_name : str
            Name of the Jinja template to render.
        nav_links : list[NavLinkConfig], optional
            Navigation links for the page header.
        parent_link : NavLinkConfig, optional
            Link back to the parent site.
        stylesheet : str, optional
            Path to the site stylesheet.
        """
        self.shared_config = shared_config
        self.output_dir = output_dir
        self.template_name = template_name
        self.nav_links = nav_links or []
        self.parent_link = parent_link
        self.stylesheet = stylesheet
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template(self.template_name)
        self._markdown_extensions = ["sane_lists", "tables", "fenced_code"]

    def run(self) -> Path:
        """Fetch or read markdown, render HTML, wrap in template, and write."""
        source = self.shared_config.source
        if "://" in source:
            raw_md = self._fetch_url(source)
        else:
            raw_md = Path(source).read_text(encoding="utf-8")

        body_html = markdown(
            raw_md,
            extensions=self._markdown_extensions,
            output_format="html5",
        )

        output_path = self.output_dir / self.shared_config.output_slug / "index.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        context = {
            "title": self.shared_config.label,
            "body_html": body_html,
            "generated_at": dt.datetime.now(dt.UTC),
            "nav_links": self.nav_links,
            "parent_link": self.parent_link,
            "stylesheet": self.stylesheet,
        }
        html = self.template.render(**context)
        if not html.endswith("\n"):
            html += "\n"
        output_path.write_text(html, encoding="utf-8")
        return output_path

    @staticmethod
    def _fetch_url(url: str) -> str:
        """Fetch markdown content from a remote URL."""
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.text


__all__ = ["SharedContentGenerator"]
