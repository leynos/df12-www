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


def prepare_numbered_steps(
    renderer: HtmlContentRenderer,
    section: Section,
    layout: SectionLayout,
    *,
    figures: cabc.Mapping[str, str],
    subsection_anchors: dict[str, str] | None = None,
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
    subsection_anchors : dict[str, str] or None, optional
        Mapping of subsection title to content-based anchor string, as
        produced by :meth:`PageContentGenerator._build_subsection_blocks`. When
        provided, each step's ``content_anchor`` is set to the corresponding
        value so that nav links and in-page anchors remain consistent.
    """
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

    anchors = subsection_anchors or {}
    steps: list[NumberedStep] = []
    for idx, sub in enumerate(subsections, start=1):
        html = renderer.markdown(sub.markdown, figures=figures)
        step_anchor = f"{section.slug}-step-{idx}"
        content_anchor = anchors.get(sub.title, step_anchor)
        steps.append(
            NumberedStep(
                title=sub.title,
                number=idx,
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
) -> dict[str, str]:
    """Render split-panel HTML blocks for the section based on layout hints."""
    matches = list(CODE_BLOCK_PATTERN.finditer(section.markdown))
    if not matches:
        return {
            "primary_html": renderer.markdown(section.markdown, figures=figures),
            "secondary_html": "",
        }

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
        "primary_html": renderer.markdown(primary_md, figures=figures),
        "secondary_html": renderer.code_block(code, lang),
    }


__all__ = ["prepare_numbered_steps", "prepare_split_panel"]
