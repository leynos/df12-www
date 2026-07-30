"""Render shared-copy pages (terms of use, privacy policy, etc.) into a site."""

from __future__ import annotations

import datetime as dt
import re
import typing as typ
from pathlib import Path

import nh3
import requests
from jinja2 import Environment, FileSystemLoader
from markdown import markdown

if typ.TYPE_CHECKING:
    from .config import SharedContentConfig, SharedContentPageChrome


class SharedContentGenerator:
    """Render a shared markdown page into a site's template wrapper."""

    _LEADING_H1_RE = re.compile(
        r"\A(?:\ufeff)?\s*#\s+.+?(?:\r?\n)+(?:\r?\n)*",
        re.DOTALL,
    )

    def __init__(
        self,
        shared_config: SharedContentConfig,
        output_dir: Path,
        *,
        templates_dir: Path | None = None,
        template_name: str = "shared_content_page.jinja",
        page_chrome: SharedContentPageChrome | None = None,
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
        page_chrome : SharedContentPageChrome, optional
            Site chrome metadata for the rendered page shell.
        """
        self.shared_config = shared_config
        self.output_dir = output_dir
        self.template_name = template_name
        self.page_chrome = page_chrome
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template(self.template_name)
        self._markdown_extensions = ["sane_lists", "tables", "fenced_code", "smarty"]

    def run(self) -> Path:
        """Fetch or read markdown, render HTML, wrap in template, and write.

        Remote HTTP sources are sanitised with ``nh3`` after markdown
        rendering to prevent XSS from untrusted content.
        """
        source = self.shared_config.source
        if "://" in source:
            raw_md = self._fetch_url(source)
        else:
            raw_md = Path(source).read_text(encoding="utf-8")
        body_markdown = self._strip_leading_h1(raw_md)

        body_html = markdown(
            body_markdown,
            extensions=self._markdown_extensions,
            output_format="html5",
        )
        body_html = nh3.clean(body_html)

        output_path = self.output_dir / self.shared_config.output_slug / "index.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        page_chrome = self.page_chrome

        context = {
            "title": self.shared_config.label,
            "eyebrow": self.shared_config.eyebrow,
            "summary": self.shared_config.summary,
            "body_html": body_html,
            "generated_at": dt.datetime.now(dt.UTC),
            "nav_links": page_chrome.nav_links if page_chrome else [],
            "parent_link": page_chrome.parent_link if page_chrome else None,
            "stylesheet": page_chrome.stylesheet if page_chrome else None,
            "lang": page_chrome.lang if page_chrome else "en",
            "theme_name": page_chrome.theme_name if page_chrome else "df12",
            "site_brand": page_chrome.site_brand if page_chrome else "df12",
            "site_home_url": page_chrome.site_home_url if page_chrome else "/",
            "site_title_suffix": (
                page_chrome.site_title_suffix if page_chrome else "df12"
            ),
        }
        html = self.template.render(**context)
        if not html.endswith("\n"):
            html += "\n"
        output_path.write_text(html, encoding="utf-8")
        return output_path

    @classmethod
    def _strip_leading_h1(cls, raw_md: str) -> str:
        """Remove a source-level H1 that duplicates the page shell title."""
        return cls._LEADING_H1_RE.sub("", raw_md, count=1)

    @staticmethod
    def _fetch_url(url: str) -> str:
        """Fetch markdown content from a remote URL."""
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.text


__all__ = ["SharedContentGenerator"]
