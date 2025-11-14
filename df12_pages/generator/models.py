"""Shared dataclasses used by the page generation pipeline."""

from __future__ import annotations

import dataclasses as dc


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
    numbered_steps : list[dict[str, str]]
        Collection of numbered step metadata (title, number, html, anchor).
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
    numbered_steps: list[dict[str, str]]
    split_panel: dict[str, str]
    subsections: list[dict[str, str]]
    toc_items: list[dict[str, str]]


__all__ = ["SectionModel"]
