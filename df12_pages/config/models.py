"""Typed dataclasses describing df12 site configuration structures."""

from __future__ import annotations

import dataclasses as dc
import datetime as dt  # noqa: TC003 - used for runtime type metadata
import typing as typ
from pathlib import Path


class SiteConfigError(ValueError):
    """Raised when the site configuration is invalid or incomplete."""


@dc.dataclass(slots=True)
class SectionLayout:
    """Describe how a documentation section should be presented."""

    device: str = "default"
    step_order: list[str] = dc.field(default_factory=list)
    emphasized_code_block: int | None = None


@dc.dataclass(slots=True)
class ThemeConfig:
    """Visual theming applied to generated documentation."""

    hero_eyebrow: str = "df12"
    hero_tagline: str = "Documentation"
    doc_label: str = "Docs"
    site_name: str = "df12 Productions"


@dc.dataclass(slots=True)
class NavLinkConfig:
    """Navigation link metadata for the marketing homepage."""

    label: str
    href: str
    variant: str | None = None
    nav_target: str | None = None
    current: bool = False


@dc.dataclass(slots=True)
class CTAButtonConfig:
    """Call-to-action button within the homepage hero."""

    label: str
    href: str
    variant: str


@dc.dataclass(slots=True)
class HeroConfig:
    """Hero copy and CTAs for the marketing homepage."""

    brand_text: str
    eyebrow: str
    title_primary: str
    title_secondary: str
    accent_text: str
    description: str
    ctas: list[CTAButtonConfig]


@dc.dataclass(slots=True)
class SystemCardConfig:
    """Product tile content for the systems section."""

    label: str
    description: str
    href: str
    icon: str
    meta_label: str
    external: bool = True


@dc.dataclass(slots=True)
class SystemsSectionConfig:
    """Systems grid configuration for the homepage."""

    heading: str
    kicker: str
    cards: list[SystemCardConfig]


@dc.dataclass(slots=True)
class WorldImageConfig:
    """Responsive media metadata for a world highlight."""

    avif: str
    webp: str
    fallback: str
    alt: str
    width: int
    height: int
    sizes: str


@dc.dataclass(slots=True)
class WorldCardConfig:
    """Narrative world card rendered on the homepage."""

    label: str
    description: str
    href: str
    classes: list[str]
    image: WorldImageConfig
    cta_label: str
    external: bool = False


@dc.dataclass(slots=True)
class WorldsSectionConfig:
    """Collection of narrative world entries."""

    heading: str
    kicker: str
    cards: list[WorldCardConfig]


@dc.dataclass(slots=True)
class FooterLinkConfig:
    """Footer hyperlink metadata."""

    label: str
    href: str
    variant: str | None = None
    icon: str | None = None
    external: bool = True


@dc.dataclass(slots=True)
class FooterConfig:
    """Footer copy and link groups for the homepage."""

    site_name: str
    blurb: str
    oss_heading: str
    contact_heading: str
    closing_lede: str
    copyright_year: int
    oss_links: list[FooterLinkConfig]
    contact_links: list[FooterLinkConfig]


@dc.dataclass(slots=True)
class HomepageConfig:
    """Aggregated homepage content sourced from YAML config."""

    output: Path
    title: str
    nav_links: list[NavLinkConfig]
    hero: HeroConfig
    systems: SystemsSectionConfig
    worlds: WorldsSectionConfig
    footer: FooterConfig


@dc.dataclass(slots=True)
class AvatarConfig:
    """Profile photo metadata for the about page."""

    src: str
    alt: str
    width: int
    height: int

    @property
    def src_webp(self) -> str:
        """Return the WebP variant path for this image."""
        return self.src.rsplit(".", 1)[0] + ".webp"

    @property
    def src_avif(self) -> str:
        """Return the AVIF variant path for this image."""
        return self.src.rsplit(".", 1)[0] + ".avif"


@dc.dataclass(slots=True)
class AboutLocationConfig:
    """Location blurb displayed in the about section."""

    title: str
    description: str
    icon: str


@dc.dataclass(slots=True)
class FocusCardConfig:
    """Highlight card describing a focus area."""

    title: str
    description: str
    icon: str
    tone: str


@dc.dataclass(slots=True)
class PrincipleConfig:
    """Design principle entry with title and supporting copy."""

    title: str
    description: str


@dc.dataclass(slots=True)
class AboutPageConfig:
    """Content model for the df12 about page."""

    output: Path
    title: str
    nav_links: list[NavLinkConfig]
    hero_name: str
    hero_email: str
    hero_intro: str
    avatar: AvatarConfig
    about_blurb: str
    location: AboutLocationConfig
    focus_cards: list[FocusCardConfig]
    principles: list[PrincipleConfig]
    footer: FooterConfig
    brand_href: str = "index.html"
    brand_text: str = "df12"


#: Valid project categories for docs index grouping, in display order.
PAGE_CATEGORIES: typ.Final[tuple[str, ...]] = (
    "tool",
    "library",
    "app",
    "game",
    "skill",
)


@dc.dataclass(slots=True)
class PageConfig:
    """A fully resolved page definition sourced from YAML config."""

    key: str
    label: str
    source_url: str
    source_label: str
    page_title_suffix: str
    filename_prefix: str
    output_dir: Path
    pygments_style: str
    footer_note: str
    theme: ThemeConfig
    layouts: dict[str, SectionLayout]
    repo: str | None
    branch: str
    language: str | None
    manifest_url: str | None
    description_override: str | None
    doc_path: str
    latest_release: str | None
    latest_release_published_at: dt.datetime | None
    category: str = "tool"


@dc.dataclass(slots=True)
class SharedContentConfig:
    """Shared-copy page rendered into each sub-site."""

    key: str
    label: str
    source: str
    output_slug: str
    eyebrow: str | None = None
    summary: str | None = None
    sections: bool = False
    toc: bool = False
    toc_exclude: tuple[str, ...] = ()
    divider_sections: tuple[str, ...] = ()


@dc.dataclass(slots=True)
class ContentPageConfig:
    """A sub-site page rendered from a Jinja template with rich HTML content."""

    key: str
    label: str
    template: str
    output_slug: str


@dc.dataclass(slots=True)
class SharedContentPageChrome:
    """Template chrome metadata for shared-content pages."""

    nav_links: list[NavLinkConfig] = dc.field(default_factory=list)
    parent_link: NavLinkConfig | None = None
    stylesheet: str | None = None
    lang: str = "en"
    theme_name: str = "df12"
    site_brand: str = "df12"
    site_home_url: str = "/"
    site_title_suffix: str = "df12"
    template_vars: dict[str, typ.Any] = dc.field(default_factory=dict)


@dc.dataclass(slots=True)
class SubSiteHomepageConfig:
    """Homepage config with freeform template context."""

    output: Path
    title: str
    context: dict[str, typ.Any]


@dc.dataclass(slots=True)
class SubSiteConfig:
    """Self-contained sub-site with own templates and CSS."""

    key: str
    output_dir: Path
    templates_dir: Path
    stylesheet: str
    base_path: str
    theme: ThemeConfig
    pages: dict[str, PageConfig]
    homepage: SubSiteHomepageConfig | None
    about: AboutPageConfig | None
    docs_index_output: Path | None
    shared_content_refs: list[str]
    nav_links: list[NavLinkConfig]
    parent_link: NavLinkConfig | None
    static_assets_dir: Path | None
    content_pages: list[ContentPageConfig] = dc.field(default_factory=list)
    template_vars: dict[str, typ.Any] = dc.field(default_factory=dict)


@dc.dataclass(slots=True)
class SiteConfig:
    """Collection of page configs alongside shared defaults."""

    pages: dict[str, PageConfig]
    default_page: str | None = None
    docs_index_output: Path = Path("public/docs.html")
    theme: ThemeConfig | None = None
    homepage: HomepageConfig | None = None
    about: AboutPageConfig | None = None
    sites: dict[str, SubSiteConfig] = dc.field(default_factory=dict)
    shared_content: dict[str, SharedContentConfig] = dc.field(default_factory=dict)

    def get_page(self, page_id: str | None) -> PageConfig:
        """Return the requested page or fall back to the configured default."""
        if page_id is None:
            return self._get_default_page()
        try:
            return self.pages[page_id]
        except KeyError as exc:  # pragma: no cover - defensive guard
            available = ", ".join(sorted(self.pages))
            msg = f"Unknown page '{page_id}'. Known pages: {available}"
            raise KeyError(msg) from exc

    def _get_default_page(self) -> PageConfig:
        """Return the configured default page or the first defined page."""
        if self.default_page and self.default_page in self.pages:
            return self.pages[self.default_page]
        if not self.pages:  # pragma: no cover - configuration error
            msg = "No pages configured in layout file."
            raise SiteConfigError(msg)
        first_key = next(iter(self.pages))
        return self.pages[first_key]


__all__ = [
    "PAGE_CATEGORIES",
    "AboutLocationConfig",
    "AboutPageConfig",
    "AvatarConfig",
    "CTAButtonConfig",
    "ContentPageConfig",
    "FocusCardConfig",
    "FooterConfig",
    "FooterLinkConfig",
    "HeroConfig",
    "HomepageConfig",
    "NavLinkConfig",
    "PageConfig",
    "PrincipleConfig",
    "SectionLayout",
    "SharedContentConfig",
    "SharedContentPageChrome",
    "SiteConfig",
    "SiteConfigError",
    "SubSiteConfig",
    "SubSiteHomepageConfig",
    "SystemCardConfig",
    "SystemsSectionConfig",
    "ThemeConfig",
    "WorldCardConfig",
    "WorldImageConfig",
    "WorldsSectionConfig",
]
