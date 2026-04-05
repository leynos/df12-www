"""Shared dataclasses used by the page generation pipeline."""

from __future__ import annotations

import dataclasses as dc
import typing as typ


class NumberedStep(typ.TypedDict):
    """A single numbered step within a section layout.

    Attributes
    ----------
    title
        Display heading for the step.
    number
        1-based ordinal shown in the step badge.
    html
        Pre-rendered HTML body of the step.
    anchor
        Step-number-based fragment identifier (``section-step-N``).
    content_anchor
        Content-based fragment identifier derived from the subsection title,
        matching the anchor used in sidebar navigation links.
    """

    title: str
    number: int
    html: str
    anchor: str
    content_anchor: str


@dc.dataclass(slots=True)
class SectionModel:
    """Structured data passed to the doc section template.

    Attributes
    ----------
    title : str
        Full section title.
    short_title : str
        Title used for navigation labels.
    slug : str
        URL-safe identifier for the section.
    order : int
        Numerical ordering of the section within the document.
    layout : str
        Layout variant (e.g., ``"default"``, ``"numbered_steps"``).
    intro_html : str
        Rendered HTML for the introduction block.
    default_html : str
        Rendered HTML for the main markdown body.
    numbered_steps : list[NumberedStep]
        Collection of numbered step metadata (title, number, html, anchor,
        content_anchor).
    split_panel : dict[str, str]
        Mapping containing ``primary_html`` and ``secondary_html`` for split layouts.
    subsections : list[dict[str, str]]
        List of subsection dictionaries with ``title``, ``anchor``, and ``html``.
    toc_items : list[dict[str, str]]
        Table-of-contents entries with ``label`` and ``anchor``.
    """

    title: str
    short_title: str
    slug: str
    order: int
    layout: str
    intro_html: str
    default_html: str
    numbered_steps: list[NumberedStep]
    split_panel: dict[str, str]
    subsections: list[dict[str, str]]
    toc_items: list[dict[str, str]]


__all__ = ["NumberedStep", "SectionModel"]
