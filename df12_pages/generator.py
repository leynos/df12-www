"""High-level orchestration for documentation page generation."""

from __future__ import annotations

import dataclasses as dc
from datetime import datetime, timezone
from pathlib import Path
import re
import typing as typ

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import Markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from .config import PageConfig, SectionLayout
from .markdown_parser import Section, Subsection, parse_sections

CODE_BLOCK_PATTERN = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)


class HtmlContentRenderer:
    """Render markdown and code snippets with consistent styling."""

    def __init__(self, pygments_style: str = "monokai") -> None:
        self.pygments_style = pygments_style
        self._formatter = HtmlFormatter(style=pygments_style, cssclass="codehilite")

    @property
    def stylesheet(self) -> str:
        return self._formatter.get_style_defs(".codehilite")

    def markdown(self, text: str) -> str:
        if not text.strip():
            return ""
        md = Markdown(
            extensions=["fenced_code", "codehilite", "tables", "sane_lists"],
            extension_configs={
                "codehilite": {
                    "linenums": False,
                    "guess_lang": False,
                    "css_class": "codehilite",
                    "pygments_style": self.pygments_style,
                }
            },
        )
        return md.convert(text)

    def code_block(self, code: str, language: str | None = None) -> str:
        lang = language or "text"
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            lexer = get_lexer_by_name("text")
        return highlight(code, lexer, self._formatter)


@dc.dataclass(slots=True)
class SectionModel:
    title: str
    short_title: str
    slug: str
    order: int
    layout: str
    intro_html: str
    default_html: str
    numbered_steps: list[dict[str, str]]
    split_panel: dict[str, str]
    subsections: list[dict[str, str]]
    toc_items: list[dict[str, str]]


class PageContentGenerator:
    """Fetch page markdown and emit themed HTML per section."""

    def __init__(
        self,
        page_config: PageConfig,
        *,
        templates_dir: Path | None = None,
        source_url: str | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self.page = page_config
        self.source_url = source_url or page_config.source_url
        self.output_dir_override = output_dir
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.renderer = HtmlContentRenderer(page_config.pygments_style)
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template("doc_page.jinja")

    def run(self) -> list[Path]:
        """Generate HTML files, returning the written paths."""

        markdown_source = self._fetch_markdown()
        sections = parse_sections(markdown_source)
        if not sections:
            msg = "No second-level sections were found in the upstream markdown."
            raise RuntimeError(msg)

        out_dir = self.output_dir_override or self.page.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        generated_at = datetime.now(timezone.utc)
        section_bundle: list[tuple[Section, SectionModel, str]] = []
        for section in sections:
            layout = self._resolve_layout(section.slug)
            section_model = self._build_section_model(section, layout)
            html_title = self._format_page_title(section)
            section_bundle.append((section, section_model, html_title))

        nav_groups = self._build_nav_groups([bundle[1] for bundle in section_bundle])
        written: list[Path] = []
        for section, section_model, html_title in section_bundle:
            context = {
                "section": section_model,
                "nav_groups": nav_groups,
                "theme": self.page.theme,
                "generated_at": generated_at,
                "source_url": self.source_url,
                "source_label": self.page.source_label,
                "pygments_css": self.renderer.stylesheet,
                "page": self.page,
                "html_title": html_title,
                "footer_note": self.page.footer_note,
            }
            html = self.template.render(**context)
            filename = f"{self.page.filename_prefix}{section.slug}.html"
            output_path = out_dir / filename
            output_path.write_text(html, encoding="utf-8")
            written.append(output_path)
        return written

    def _fetch_markdown(self) -> str:
        resp = requests.get(self.source_url, timeout=30)
        resp.raise_for_status()
        return resp.text

    def _build_nav_groups(self, section_models: list[SectionModel]) -> list[dict[str, typ.Any]]:
        groups: list[dict[str, typ.Any]] = []
        for model in section_models:
            page_url = f"{self.page.filename_prefix}{model.slug}.html"
            entries: list[dict[str, typ.Any]] = [
                {
                    "label": model.short_title,
                    "href": page_url,
                    "section_slug": model.slug,
                    "is_primary": True,
                }
            ]
            if model.subsections:
                for block in model.subsections:
                    href = f"{page_url}#{block['anchor']}"
                    entries.append(
                        {
                            "label": block["title"],
                            "href": href,
                            "section_slug": model.slug,
                            "is_primary": False,
                        }
                    )
            groups.append({"label": model.short_title, "slug": model.slug, "entries": entries})
        return groups

    def _resolve_layout(self, slug: str) -> SectionLayout:
        return self.page.layouts.get(slug, SectionLayout())

    def _build_section_model(self, section: Section, layout: SectionLayout) -> SectionModel:
        intro_html = self.renderer.markdown(section.intro_markdown)
        default_html = self.renderer.markdown(section.markdown)
        numbered_steps: list[dict[str, str]] = []
        split_panel = {"primary_html": "", "secondary_html": ""}
        subsections = self._build_subsection_blocks(section)
        toc_items = [
            {"label": block["title"], "anchor": block["anchor"]}
            for block in subsections
        ]
        resolved_layout = layout.device

        if layout.device == "numbered_steps":
            numbered_steps = self._prepare_numbered_steps(section, layout)
            if not numbered_steps:
                resolved_layout = "default"
            else:
                toc_items = [
                    {"label": step["title"], "anchor": step["anchor"]}
                    for step in numbered_steps
                ]
        elif layout.device == "split_panel":
            split_panel = self._prepare_split_panel(section, layout)
            if not split_panel.get("secondary_html"):
                resolved_layout = "default"

        return SectionModel(
            title=section.title,
            short_title=section.short_title,
            slug=section.slug,
            order=section.order,
            layout=resolved_layout,
            intro_html=intro_html,
            default_html=default_html,
            numbered_steps=numbered_steps,
            split_panel=split_panel,
            subsections=subsections,
            toc_items=toc_items,
        )

    def _prepare_numbered_steps(self, section: Section, layout: SectionLayout) -> list[dict[str, str]]:
        subsections = list(section.subsections)
        if not subsections:
            return []

        if layout.step_order:
            ordered: list[Subsection] = []
            lower_map = {sub.title.lower(): sub for sub in subsections}
            for desired in layout.step_order:
                match = lower_map.get(desired.lower())
                if match and match not in ordered:
                    ordered.append(match)
            for sub in subsections:
                if sub not in ordered:
                    ordered.append(sub)
            subsections = ordered

        steps: list[dict[str, str]] = []
        for idx, sub in enumerate(subsections, start=1):
            html = self.renderer.markdown(sub.markdown)
            steps.append(
                {
                    "title": sub.title,
                    "number": idx,
                    "html": html,
                    "anchor": f"{section.slug}-step-{idx}",
                }
            )
        return steps

    def _prepare_split_panel(self, section: Section, layout: SectionLayout) -> dict[str, str]:
        matches = list(CODE_BLOCK_PATTERN.finditer(section.markdown))
        if not matches:
            return {"primary_html": self.renderer.markdown(section.markdown), "secondary_html": ""}

        index = layout.emphasized_code_block or 0
        if index >= len(matches):
            index = 0
        match = matches[index]
        lang = match.group(1) or "text"
        code = match.group(2).strip("\n")
        before = section.markdown[: match.start()]
        after = section.markdown[match.end() :]
        primary_md = (before + "\n\n" + after).strip()
        return {
            "primary_html": self.renderer.markdown(primary_md),
            "secondary_html": self.renderer.code_block(code, lang),
        }

    def _format_page_title(self, section: Section) -> str:
        site_name = self.page.theme.site_name
        suffix = self.page.page_title_suffix
        return f"{site_name} — {section.short_title} | {suffix}"

    def _build_subsection_blocks(self, section: Section) -> list[dict[str, str]]:
        if not section.subsections:
            return []

        blocks: list[dict[str, str]] = []
        used: set[str] = set()
        for idx, sub in enumerate(section.subsections, start=1):
            anchor = self._section_anchor(section.slug, sub.title, idx, used)
            html = self.renderer.markdown(sub.markdown)
            blocks.append({"title": sub.title, "anchor": anchor, "html": html})
        return blocks

    def _section_anchor(
        self, section_slug: str, title: str, index: int, used: set[str]
    ) -> str:
        base_title = self._slugify(title)
        if base_title:
            base = f"{section_slug}-{base_title}"
        else:
            base = f"{section_slug}-part-{index}"
        return self._unique_anchor(base, used)

    @staticmethod
    def _unique_anchor(base: str, used: set[str]) -> str:
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used.add(candidate)
        return candidate

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug
