"""Parsing helpers for Netsuke markdown content."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Tuple


SECTION_PATTERN = re.compile(r"^##\s+(.*)", re.MULTILINE)
SUBSECTION_PATTERN = re.compile(r"^###\s+(.*)", re.MULTILINE)


@dataclass(slots=True)
class Subsection:
    title: str
    markdown: str


@dataclass(slots=True)
class Section:
    title: str
    short_title: str
    slug: str
    order: int
    markdown: str
    intro_markdown: str
    subsections: List[Subsection]


def _clean_heading(text: str) -> str:
    cleaned = text.replace("\\", "").strip()
    return cleaned


def _slugify(title: str) -> str:
    import re as _re

    no_number = _re.sub(r"^\d+\.?\s*", "", title.lower())
    slug = _re.sub(r"[^a-z0-9]+", "-", no_number).strip("-")
    return slug or "section"


def _unique_slug(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _split_subsections(body: str) -> Tuple[str, List[Subsection]]:
    matches = list(SUBSECTION_PATTERN.finditer(body))
    if not matches:
        return body.strip(), []

    intro = body[: matches[0].start()].strip()
    subsections: List[Subsection] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        chunk = body[start:end].strip()
        heading = _clean_heading(match.group(1))
        subsections.append(Subsection(title=heading, markdown=chunk))
    return intro, subsections


def parse_sections(markdown_text: str) -> List[Section]:
    """Split the upstream markdown file into ordered sections."""

    entries = list(SECTION_PATTERN.finditer(markdown_text))
    sections: List[Section] = []
    if not entries:
        return sections

    used_slugs: set[str] = set()
    for idx, match in enumerate(entries):
        start = match.end()
        end = entries[idx + 1].start() if idx + 1 < len(entries) else len(markdown_text)
        body = markdown_text[start:end].strip()
        heading = _clean_heading(match.group(1))
        short_title = re.sub(r"^\d+\.?\s*", "", heading).strip()
        slug = _unique_slug(_slugify(heading), used_slugs)
        intro, subsections = _split_subsections(body)
        sections.append(
            Section(
                title=heading,
                short_title=short_title or heading,
                slug=slug,
                order=idx + 1,
                markdown=body,
                intro_markdown=intro,
                subsections=subsections,
            )
        )
    return sections
