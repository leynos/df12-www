"""High-level orchestration for Netsuke documentation generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import Markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from .config import DocLayoutConfig, SectionLayout, load_layout_config
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

    def code_block(self, code: str, language: Optional[str] = None) -> str:
        lang = language or "text"
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            lexer = get_lexer_by_name("text")
        return highlight(code, lexer, self._formatter)


@dataclass(slots=True)
class SectionModel:
    title: str
    short_title: str
    slug: str
    order: int
    layout: str
    intro_html: str
    default_html: str
    numbered_steps: List[Dict[str, str]]
    split_panel: Dict[str, str]


class NetsukeDocGenerator:
    """Fetch Netsuke docs markdown and emit themed HTML per section."""

    def __init__(
        self,
        source_url: str,
        *,
        layout_config_path: Path | None = None,
        templates_dir: Path | None = None,
    ) -> None:
        self.source_url = source_url
        self.layout_config_path = layout_config_path or Path("docs/netsuke-section-layouts.yaml")
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.config: DocLayoutConfig = load_layout_config(self.layout_config_path)
        self.renderer = HtmlContentRenderer(self.config.pygments_style)
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template("doc_page.jinja")

    def run(self, *, output_dir: Path | None = None) -> List[Path]:
        """Generate HTML files, returning the written paths."""

        markdown_source = self._fetch_markdown()
        sections = parse_sections(markdown_source)
        if not sections:
            raise RuntimeError("No second-level sections were found in the upstream markdown.")

        out_dir = output_dir or self.config.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        nav_items = self._build_nav(sections)
        written: List[Path] = []
        for section in sections:
            layout = self._resolve_layout(section.slug)
            section_model = self._build_section_model(section, layout)
            context = {
                "section": section_model,
                "nav_items": nav_items,
                "theme": self.config.theme,
                "generated_at": datetime.now(timezone.utc),
                "source_url": self.source_url,
                "pygments_css": self.renderer.stylesheet,
            }
            html = self.template.render(**context)
            filename = f"{self.config.filename_prefix}{section.slug}.html"
            output_path = out_dir / filename
            output_path.write_text(html, encoding="utf-8")
            written.append(output_path)
        return written

    def _fetch_markdown(self) -> str:
        resp = requests.get(self.source_url, timeout=30)
        resp.raise_for_status()
        return resp.text

    def _build_nav(self, sections: Iterable[Section]) -> List[Dict[str, str]]:
        nav = []
        for section in sections:
            nav.append(
                {
                    "label": section.short_title,
                    "href": f"{self.config.filename_prefix}{section.slug}.html",
                    "slug": section.slug,
                }
            )
        return nav

    def _resolve_layout(self, slug: str) -> SectionLayout:
        return self.config.layouts.get(slug, SectionLayout())

    def _build_section_model(self, section: Section, layout: SectionLayout) -> SectionModel:
        intro_html = self.renderer.markdown(section.intro_markdown)
        default_html = self.renderer.markdown(section.markdown)
        numbered_steps: List[Dict[str, str]] = []
        split_panel = {"primary_html": "", "secondary_html": ""}
        resolved_layout = layout.device

        if layout.device == "numbered_steps":
            numbered_steps = self._prepare_numbered_steps(section, layout)
            if not numbered_steps:
                resolved_layout = "default"
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
        )

    def _prepare_numbered_steps(self, section: Section, layout: SectionLayout) -> List[Dict[str, str]]:
        subsections = list(section.subsections)
        if not subsections:
            return []

        if layout.step_order:
            ordered: List[Subsection] = []
            lower_map = {sub.title.lower(): sub for sub in subsections}
            for desired in layout.step_order:
                match = lower_map.get(desired.lower())
                if match and match not in ordered:
                    ordered.append(match)
            for sub in subsections:
                if sub not in ordered:
                    ordered.append(sub)
            subsections = ordered

        steps: List[Dict[str, str]] = []
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

    def _prepare_split_panel(self, section: Section, layout: SectionLayout) -> Dict[str, str]:
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


def generate_netsuke_docs(source_url: str, *, layout_config: Path | None = None) -> List[Path]:
    """Convenience wrapper used by CLI scripts."""

    generator = NetsukeDocGenerator(source_url, layout_config_path=layout_config)
    return generator.run()
