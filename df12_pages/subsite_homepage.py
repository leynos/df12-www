"""Build and render sub-site homepage documents.

This module adapts the generic site-generation pipeline to sub-sites whose
homepages are driven by freeform template context instead of the strongly typed
main-site homepage dataclasses. The builder is intentionally narrow: it loads a
sub-site-local Jinja template, injects the configured context plus generation
metadata, and writes the final HTML document to the requested output path.
"""

from __future__ import annotations

import dataclasses as dc
import datetime as dt
import typing as typ
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .jinja_highlight import HighlightExtension

if typ.TYPE_CHECKING:
    from .config import NavLinkConfig, SubSiteHomepageConfig


class SubSiteHomePageBuilder:
    """Render a sub-site homepage from freeform context data."""

    def __init__(
        self,
        config: SubSiteHomepageConfig,
        *,
        templates_dir: Path | None = None,
        nav_links: list[NavLinkConfig] | None = None,
        parent_link: NavLinkConfig | None = None,
        base_path: str | None = None,
    ) -> None:
        """Initialize the sub-site homepage builder.

        Parameters
        ----------
        config : SubSiteHomepageConfig
            Homepage configuration with output path, title, and freeform
            context dict consumed by the sub-site's ``home_page.jinja``.
        templates_dir : Path, optional
            Directory containing Jinja templates for this sub-site.
        nav_links : list[NavLinkConfig], optional
            Navigation links to expose in the template context.
        parent_link : NavLinkConfig, optional
            Parent site link to expose in the template context.
        base_path : str, optional
            Absolute path prefix for the sub-site (e.g. ``/mxd/``).  When
            provided, the nav link whose href equals *base_path* is marked
            as current.
        """
        self.config = config
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.nav_links = nav_links or []
        self.parent_link = parent_link
        self.base_path = base_path
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
            extensions=[HighlightExtension],
        )
        self.template = self.env.get_template("home_page.jinja")

    def run(self) -> Path:
        """Render and write the sub-site homepage HTML.

        Returns
        -------
        Path
            The filesystem path written for the rendered homepage.

        Raises
        ------
        OSError
            Raised when creating parent directories or writing the output
            file fails.

        Notes
        -----
        Renders ``home_page.jinja`` with ``homepage`` and ``generated_at``
        context keys.  The ``homepage`` dict merges ``config.context`` with
        the configured ``title`` field.  A trailing newline is appended to
        the rendered HTML when absent.
        """
        output_path = self.config.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        nav_dicts = [dc.asdict(link) for link in self.nav_links]
        if self.base_path is not None:
            for entry in nav_dicts:
                if entry.get("href") == self.base_path:
                    entry["current"] = True
                    break
        context = {
            "homepage": {
                **self.config.context,
                "title": self.config.title,
            },
            "nav_links": nav_dicts,
            "parent_link": dc.asdict(self.parent_link) if self.parent_link else None,
            "generated_at": dt.datetime.now(dt.UTC),
        }
        html = self.template.render(**context)
        if not html.endswith("\n"):
            html += "\n"
        output_path.write_text(html, encoding="utf-8")
        return output_path


__all__ = ["SubSiteHomePageBuilder"]
