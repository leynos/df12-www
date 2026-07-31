"""Render shared-copy pages (terms of use, privacy policy, etc.) into a site."""

from __future__ import annotations

import datetime as dt
import re
import typing as typ
from pathlib import Path

import nh3
import requests
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from markdown import markdown

if typ.TYPE_CHECKING:
    from .config import SharedContentConfig, SharedContentPageChrome

_STRUCTURE_TAGS = frozenset({"section", "nav"})
_CLASS_BEARING_TAGS = (
    "a",
    "div",
    "h2",
    "h3",
    "li",
    "nav",
    "ol",
    "p",
    "section",
    "span",
    "ul",
)


def _sanitizer_allowlists() -> tuple[set[str], dict[str, set[str]]]:
    """Extend the ``nh3`` defaults with the structural markup we generate."""
    tags = set(nh3.ALLOWED_TAGS) | _STRUCTURE_TAGS
    attributes = {tag: set(allowed) for tag, allowed in nh3.ALLOWED_ATTRIBUTES.items()}
    for tag in _CLASS_BEARING_TAGS:
        attributes.setdefault(tag, set()).add("class")
    attributes["section"].add("id")
    attributes["nav"].add("aria-label")
    attributes["div"].add("aria-hidden")
    return tags, attributes


def _slugify(text: str) -> str:
    """Turn a heading title into an anchor-friendly identifier."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


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
        self._markdown_extensions = [
            "sane_lists",
            "tables",
            "fenced_code",
            "smarty",
            "attr_list",
            "admonition",
        ]

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
        body_html = self._apply_structure(body_html)
        tags, attributes = _sanitizer_allowlists()
        body_html = nh3.clean(body_html, tags=tags, attributes=attributes)

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

    def _apply_structure(self, body_html: str) -> str:
        """Rewrite rendered Markdown into the structured page layout.

        Three transformations run in order, each driven by content markers or
        configuration so pages without them pass through unchanged:

        1. ``card`` admonitions become badge cards
           (``.content-card`` with a ``.content-card__badge`` circle).
        2. When ``sections`` is enabled, each ``h2``-delimited run of content
           is wrapped in ``<section class="content-section">``; the section
           takes the heading's ``attr_list`` id (or a slug of its title), and
           titles listed in ``divider_sections`` gain a top-border modifier.
        3. When ``toc`` is enabled, a ``<nav class="content-toc">`` linking to
           each section (minus ``toc_exclude`` titles) is inserted first.
        """
        config = self.shared_config
        has_cards = "admonition" in body_html
        if not (has_cards or config.sections or config.toc):
            return body_html

        soup = BeautifulSoup(body_html, "html.parser")
        self._transform_cards(soup)
        if config.sections or config.toc:
            sections = self._wrap_sections(soup)
            if config.toc and sections:
                self._insert_toc(soup, sections)
        return str(soup)

    @staticmethod
    def _transform_cards(soup: BeautifulSoup) -> None:
        """Convert ``card`` admonition blocks into badge-card markup."""
        for admonition in soup.select("div.admonition.card"):
            class_attr = admonition.get("class")
            raw_classes = (
                [class_attr] if isinstance(class_attr, str) else list(class_attr or [])
            )
            classes = [cls for cls in raw_classes if cls not in {"admonition", "card"}]
            badge_text = ""
            title = admonition.find("p", class_="admonition-title")
            if title is not None:
                badge_text = title.get_text(strip=True)
                title.decompose()

            card = soup.new_tag("div")
            variant_classes = [f"content-card--{cls}" for cls in classes]
            card["class"] = " ".join(["content-card", *variant_classes])
            badge = soup.new_tag("div")
            badge["class"] = "content-card__badge"
            badge["aria-hidden"] = "true"
            badge.string = badge_text
            body = soup.new_tag("div")
            body["class"] = "content-card__body"
            for child in list(admonition.children):
                body.append(child.extract())
            card.append(badge)
            card.append(body)
            admonition.replace_with(card)

    def _wrap_sections(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        """Group ``h2``-delimited content into sections; return (id, title)."""
        headings = list(soup.find_all("h2", recursive=False))
        sections: list[tuple[str, str]] = []
        for heading in headings:
            title = heading.get_text(strip=True)
            raw_id = heading.get("id")
            section_id = (
                raw_id if isinstance(raw_id, str) and raw_id else _slugify(title)
            )
            section = soup.new_tag("section")
            section["id"] = section_id
            section_classes = ["content-section"]
            if title in self.shared_config.divider_sections:
                section_classes.append("content-section--divider")
            section["class"] = " ".join(section_classes)

            heading.insert_before(section)
            if heading.get("id"):
                del heading["id"]
            node = heading
            while node is not None:
                following = node.next_sibling
                section.append(node.extract())
                node = following
                if node is None or (getattr(node, "name", None) == "section"):
                    break
                if getattr(node, "name", None) == "h2":
                    break
            sections.append((section_id, title))
        return sections

    def _insert_toc(
        self,
        soup: BeautifulSoup,
        sections: list[tuple[str, str]],
    ) -> None:
        """Insert a table of contents linking to the wrapped sections."""
        entries = [
            (section_id, title)
            for section_id, title in sections
            if title not in self.shared_config.toc_exclude
        ]
        if not entries:
            return
        nav = soup.new_tag("nav")
        nav["class"] = "content-toc"
        nav["aria-label"] = "Contents"
        toc_list = soup.new_tag("ul")
        for section_id, title in entries:
            item = soup.new_tag("li")
            link = soup.new_tag("a", href=f"#{section_id}")
            link.string = title
            item.append(link)
            toc_list.append(item)
        nav.append(toc_list)
        first_section = soup.find("section")
        if first_section is not None:
            first_section.insert_before(nav)
        else:
            soup.insert(0, nav)

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
