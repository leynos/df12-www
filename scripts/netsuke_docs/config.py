"""Configuration helpers for Netsuke documentation generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass(slots=True)
class SectionLayout:
    """Describes how a section should be presented."""

    device: str = "default"
    step_order: List[str] = field(default_factory=list)
    emphasized_code_block: int | None = None


@dataclass(slots=True)
class ThemeConfig:
    hero_eyebrow: str = "Netsuke"
    hero_tagline: str = "User Guide"
    doc_label: str = "Docs"
    site_name: str = "df12 Productions"


@dataclass(slots=True)
class DocLayoutConfig:
    output_dir: Path
    filename_prefix: str
    pygments_style: str
    theme: ThemeConfig
    layouts: Dict[str, SectionLayout]


def load_layout_config(path: Path) -> DocLayoutConfig:
    """Load the YAML configuration describing doc layout choices."""

    raw: Dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    defaults = raw.get("defaults", {})

    output_dir = Path(defaults.get("output_dir", "public"))
    filename_prefix = defaults.get("filename_prefix", "docs-netsuke-")
    pygments_style = defaults.get("pygments_style", "monokai")

    theme = ThemeConfig(
        hero_eyebrow=defaults.get("hero_eyebrow", "Netsuke"),
        hero_tagline=defaults.get("hero_tagline", "Declarative build system"),
        doc_label=defaults.get("doc_label", "Docs"),
        site_name=defaults.get("site_name", "df12 Productions"),
    )

    layout_entries = raw.get("layouts", {}) or {}
    layouts: Dict[str, SectionLayout] = {}
    for slug, payload in layout_entries.items():
        if not isinstance(payload, dict):
            continue
        layouts[slug] = SectionLayout(
            device=payload.get("device", "default"),
            step_order=payload.get("step_order", []) or [],
            emphasized_code_block=payload.get("emphasized_code_block"),
        )

    return DocLayoutConfig(
        output_dir=output_dir,
        filename_prefix=filename_prefix,
        pygments_style=pygments_style,
        theme=theme,
        layouts=layouts,
    )
