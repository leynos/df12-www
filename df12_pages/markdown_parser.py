r"""Parse Markdown-driven documentation into structured sections.

This module powers df12's documentation generator by splitting Markdown into
ordered sections and subsections, normalising headings, and returning
dataclasses that the HTML renderer consumes.

Example
-------
>>> from df12_pages.markdown_parser import parse_sections
>>> sections = parse_sections("## Intro\nBody text\n\n### Details\nMore")
>>> sections[0].title
'Intro'
"""

from __future__ import annotations

import dataclasses as dc
import re

SECTION_PATTERN = re.compile(r"^##\s+(.*)", re.MULTILINE)
SUBSECTION_PATTERN = re.compile(r"^###\s+(.*)", re.MULTILINE)
BOLD_HEADING_PATTERN = re.compile(r"^\s*\*\*(.+?)\*\*\s*$", re.MULTILINE)


@dc.dataclass(slots=True)
class Subsection:
    """Third-level heading and rendered Markdown body.

    Attributes
    ----------
    title : str
        Text content of the subsection heading.
    markdown : str
        Markdown (sans heading) that belongs to this subsection.
    """

    title: str
    markdown: str


@dc.dataclass(slots=True)
class Section:
    """Second-level heading metadata and child subsections.

    Attributes
    ----------
    title : str
        Full section heading (including numbering).
    short_title : str
        Heading with numbering stripped for navigation.
    slug : str
        URL-safe identifier unique within the document.
    order : int
        1-based order of the section in the document.
    markdown : str
        Markdown content for the section (excluding the heading itself).
    intro_markdown : str
        Text preceding the first subsection; may be empty.
    subsections : list[Subsection]
        Parsed third-level subsections within this section.
    """

    title: str
    short_title: str
    slug: str
    order: int
    markdown: str
    intro_markdown: str
    subsections: list[Subsection]


def _clean_heading(text: str) -> str:
    """Return a cleaned heading, removing escapes and whitespace."""
    return text.replace("\\", "").strip()


def _slugify(title: str) -> str:
    no_number = re.sub(r"^\d+\.?\s*", "", title.lower())
    slug = re.sub(r"[^a-z0-9]+", "-", no_number).strip("-")
    return slug or "section"


def _unique_slug(base: str, used: set[str]) -> str:
    """Generate a unique slug, appending numeric suffixes when needed."""
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _promote_bold_headings(body: str) -> str:
    """Convert bold-only lines into level-three headings for parsing."""

    def _replace(match: re.Match[str]) -> str:
        """Turn a regex match into a promoted heading or passthrough."""
        title = match.group(1).strip()
        return f"### {title}" if title else match.group(0)

    return BOLD_HEADING_PATTERN.sub(_replace, body)


def _split_subsections(body: str) -> tuple[str, list[Subsection]]:
    """Return intro text and parsed Subsections from section body."""
    body = _promote_bold_headings(body)
    matches = list(SUBSECTION_PATTERN.finditer(body))
    if not matches:
        return "", []

    intro = body[: matches[0].start()].strip()
    subsections: list[Subsection] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        chunk = body[start:end].strip()
        heading = _clean_heading(match.group(1))
        subsections.append(Subsection(title=heading, markdown=chunk))
    return intro, subsections


def parse_sections(markdown_text: str) -> list[Section]:
    """Split markdown into ordered Section objects with subsections.

    Parameters
    ----------
    markdown_text : str
        Raw markdown content with ``##`` section headings and optional
        ``###`` subsections.

    Returns
    -------
    list[Section]
        Parsed sections including titles, slugs, intro markdown, and their
        associated ``Subsection`` entries. Returns an empty list when no
        second-level headings are present.
    """
    entries = list(SECTION_PATTERN.finditer(markdown_text))
    if not entries:
        return []

    sections: list[Section] = []
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
