"""Render rich-HTML content pages from Jinja templates for sub-sites."""

from __future__ import annotations

import dataclasses as dc
import datetime as dt
import typing as typ

from jinja2 import Environment, FileSystemLoader

from .jinja_highlight import HighlightExtension

if typ.TYPE_CHECKING:
    from pathlib import Path

    from .config import ContentPageConfig, NavLinkConfig


class _MarkedNavLink(typ.TypedDict):
    """Template-facing navigation entry with current-page state."""

    label: str
    href: str
    variant: str | None
    nav_target: str | None
    current: bool


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
        base_path: str | None = None,
        template_vars: dict[str, object] | None = None,
    ) -> None:
        self.config = config
        self.output_dir = output_dir
        self.templates_dir = templates_dir
        self.nav_links = nav_links
        self.stylesheet = stylesheet
        self.parent_link = parent_link
        self.base_path = base_path
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
            extensions=[HighlightExtension],
        )
        if template_vars:
            self.env.globals.update(template_vars)

    def run(self) -> Path:
        """Render the page template and write the output file.

        Returns
        -------
        Path
            Absolute path to the written ``index.html`` output file.

        Raises
        ------
        jinja2.TemplateNotFound
            If the template named in :attr:`config.template` does not exist in
            the configured templates directory.
        OSError
            If the output directory cannot be created or the file cannot be
            written.
        """
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

    def _mark_current_nav(self) -> list[_MarkedNavLink]:
        """Return nav_links dicts with ``current`` flag for the active page."""
        if self.base_path is not None:
            target_href = f"{self.base_path}{self.config.output_slug}/"
        else:
            target_href = f"../{self.config.output_slug}/"
        current_href = self._current_nav_href(target_href)
        result: list[_MarkedNavLink] = []
        for link in self.nav_links:
            entry = typ.cast("_MarkedNavLink", dc.asdict(link))
            entry["current"] = False
            if link.href == current_href:
                entry["current"] = True
                if self.base_path is None and link.href == target_href:
                    entry["href"] = "./"
            result.append(entry)
        return result

    def _current_nav_href(self, target_href: str) -> str | None:
        """Return the nav href to mark current for ``target_href``.

        An explicit ``nav_href`` on the page config wins, so a page that lives
        outside every navigation prefix (``/netsuke/forthcoming/`` under
        Roadmap, say) can still light up the item it belongs to. Otherwise the
        exact match, then the longest parent prefix, is used.
        """
        if self.config.nav_href is not None:
            return self.config.nav_href
        nav_hrefs = [link.href for link in self.nav_links]
        if target_href in nav_hrefs:
            return target_href
        root_href = self.base_path if self.base_path is not None else "../"
        current_href: str | None = None
        for href in nav_hrefs:
            if href == root_href or not target_href.startswith(href):
                continue
            if current_href is None or len(href) > len(current_href):
                current_href = href
        return current_href


__all__ = ["ContentPageGenerator"]
