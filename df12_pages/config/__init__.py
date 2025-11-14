"""Load and validate site configuration YAML for df12 documentation builds.

This subpackage parses the project's ``pages.yaml`` file, merges global defaults
with per-page overrides, resolves source URLs/manifest paths, and produces
strongly typed dataclasses (:class:`SiteConfig`, :class:`PageConfig`, etc.)
that downstream generators consume. The primary entry point is
:func:`load_site_config`, which ensures required fields are present, applies
defaults, and returns a :class:`SiteConfig` ready for doc rendering.

Examples
--------
>>> from pathlib import Path
>>> from df12_pages.config import load_site_config
>>> site = load_site_config(Path("config/pages.yaml"))  # doctest: +SKIP
>>> page = site.get_page("getting-started")  # doctest: +SKIP
>>> page.source_url  # doctest: +SKIP
'https://github.com/df12/docs/blob/main/getting-started.md'
"""

from .loader import load_site_config
from .models import (
    CTAButtonConfig,
    FooterConfig,
    FooterLinkConfig,
    HeroConfig,
    HomepageConfig,
    NavLinkConfig,
    PageConfig,
    SectionLayout,
    SiteConfig,
    SiteConfigError,
    SystemCardConfig,
    SystemsSectionConfig,
    ThemeConfig,
    WorldCardConfig,
    WorldImageConfig,
    WorldsSectionConfig,
)

__all__ = [
    "CTAButtonConfig",
    "FooterConfig",
    "FooterLinkConfig",
    "HeroConfig",
    "HomepageConfig",
    "NavLinkConfig",
    "PageConfig",
    "SectionLayout",
    "SiteConfig",
    "SiteConfigError",
    "SystemCardConfig",
    "SystemsSectionConfig",
    "ThemeConfig",
    "WorldCardConfig",
    "WorldImageConfig",
    "WorldsSectionConfig",
    "load_site_config",
]
