"""Turn a parsed markdown section into the blocks a page template renders.

Each helper here is pure: it takes the parsed section, the layout that shapes
it and the renderer that converts markdown, and returns template data. They
live apart from :class:`~df12_pages.generator.page_generator.PageContentGenerator`
so that module keeps only the orchestration that needs page configuration.
"""

from __future__ import annotations

import typing as typ

from df12_pages.generator.models import NumberedStep
from df12_pages.generator.renderer import CODE_BLOCK_PATTERN, HtmlContentRenderer

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from df12_pages.config import SectionLayout
    from df12_pages.markdown_parser import Section, Subsection


def prepare_numbered_steps(  # noqa: PLR0913 -- layout, figures and ref are values
    renderer: HtmlContentRenderer,
    section: Section,
    layout: SectionLayout,
    *,
    figures: cabc.Mapping[str, str],
    link_ref: str | None = None,
    subsection_anchors: cabc.Sequence[str] | None = None,
) -> list[NumberedStep]:
    """Return numbered step data for ``section`` based on the provided layout.

    Parameters
    ----------
    renderer : HtmlContentRenderer
        Renderer that converts each step's markdown.
    section : Section
        The parsed markdown section containing subsections.
    layout : SectionLayout
        Layout configuration that may specify a custom step ordering.
    figures : Mapping[str, str]
        Compiled Mermaid figures for the document, by placeholder token.
    link_ref : str, optional
        Git ref the document's fetch answered from, so each step's relative
        links point into the tree it came from.
    subsection_anchors : Sequence[str] or None, optional
        One content-based anchor per subsection, in the section's original
        order, as produced by
        :meth:`PageContentGenerator._build_subsection_blocks`. An anchor
        travels with the subsection it was built for, so reordering the
        steps does not re-point them, and two subsections that share a title
        keep the distinct anchors their content earned. A subsection with no
        entry falls back to its ``{slug}-step-{n}`` anchor.
    """
    indexed = list(enumerate(section.subsections, start=1))
    if not indexed:
        return []

    if layout.step_order:
        ordered: list[tuple[int, Subsection]] = []
        remaining = list(indexed)
        for desired in layout.step_order:
            wanted = desired.lower()
            match = next(
                (item for item in remaining if item[1].title.lower() == wanted),
                None,
            )
            if match is not None:
                ordered.append(match)
                remaining.remove(match)
        indexed = ordered + remaining

    anchors = list(subsection_anchors) if subsection_anchors is not None else []
    steps: list[NumberedStep] = []
    for number, (position, sub) in enumerate(indexed, start=1):
        html = renderer.markdown(sub.markdown, figures=figures, link_ref=link_ref)
        step_anchor = f"{section.slug}-step-{number}"
        content_anchor = (
            anchors[position - 1] if position <= len(anchors) else step_anchor
        )
        steps.append(
            NumberedStep(
                title=sub.title,
                number=number,
                html=html,
                anchor=step_anchor,
                content_anchor=content_anchor,
            )
        )
    return steps


def prepare_split_panel(
    renderer: HtmlContentRenderer,
    section: Section,
    layout: SectionLayout,
    figures: cabc.Mapping[str, str],
    *,
    link_ref: str | None = None,
) -> dict[str, str]:
    """Render split-panel HTML blocks for the section based on layout hints.

    The block named by ``layout.emphasized_code_block`` moves into the
    secondary panel and is removed from the primary markdown. An index
    outside the section's blocks -- including a negative one, which Python
    would otherwise read from the end -- falls back to the first block.

    Parameters
    ----------
    renderer : HtmlContentRenderer
        Renderer that converts markdown and highlights the selected block.
    section : Section
        The parsed section whose code blocks are split out.
    layout : SectionLayout
        Layout configuration naming the emphasized block.
    figures : Mapping[str, str]
        Compiled Mermaid figures for the document, by placeholder token.
    link_ref : str, optional
        Git ref the document's fetch answered from, so the panels' relative
        links point into the tree it came from.

    Returns
    -------
    dict
        ``primary_html`` and ``secondary_html``. The secondary panel is empty
        when the section holds no code block, which the caller reads as a
        reason to fall back to the default layout.
    """
    matches = list(CODE_BLOCK_PATTERN.finditer(section.markdown))
    if not matches:
        return {
            "primary_html": renderer.markdown(
                section.markdown, figures=figures, link_ref=link_ref
            ),
            "secondary_html": "",
        }

    index = layout.emphasized_code_block or 0
    if not 0 <= index < len(matches):
        index = 0
    match = matches[index]
    lang = match.group(1) or "text"
    code = match.group(2).strip("\n")
    before = section.markdown[: match.start()]
    after = section.markdown[match.end() :]
    primary_md = (before + "\n\n" + after).strip()
    return {
        "primary_html": renderer.markdown(
            primary_md, figures=figures, link_ref=link_ref
        ),
        "secondary_html": renderer.code_block(code, lang),
    }


__all__ = ["prepare_numbered_steps", "prepare_split_panel"]
