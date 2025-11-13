"""Site-level configuration loader for df12 page generation."""

from __future__ import annotations

import dataclasses as dc
import datetime as dt
import typing as typ
from pathlib import Path

from ruamel.yaml import YAML


class SiteConfigError(ValueError):
    """Raised when the site configuration is invalid or incomplete."""


@dc.dataclass(slots=True)
class SectionLayout:
    """Describes how a section should be presented."""

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


DEFAULT_DOC_PATH = "docs/users-guide.md"
LANGUAGE_MANIFESTS: dict[str, str] = {
    "rust": "Cargo.toml",
    "python": "pyproject.toml",
    "typescript": "package.json",
}


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


@dc.dataclass(slots=True)
class SiteConfig:
    """Collection of page configs alongside shared defaults."""

    pages: dict[str, PageConfig]
    default_page: str | None = None
    docs_index_output: Path = Path("public/docs.html")
    theme: ThemeConfig | None = None
    homepage: HomepageConfig | None = None

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


def load_site_config(path: Path) -> SiteConfig:
    """Load the YAML configuration describing page and site layout choices.

    Parameters
    ----------
    path : Path
        Filesystem path to the YAML layout configuration file (for example,
        ``pages.yaml``).

    Returns
    -------
    SiteConfig
        Parsed site configuration, including page definitions, default theme,
        docs index output path, and optional homepage configuration.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist at ``path``.
    TypeError
        If the top-level YAML structure is not a mapping.
    SiteConfigError
        If required sections or fields are missing or invalid in the
        configuration (for example, no pages are defined).
    YAMLError
        If the YAML content cannot be parsed by the underlying loader.

    Examples
    --------
    Load a site configuration from the default layout file:

    >>> from pathlib import Path
    >>> from df12_pages.config import load_site_config
    >>> config = load_site_config(Path("pages.yaml"))
    >>> sorted(config.pages.keys())[:1]
    ['getting-started']
    """
    if not path.exists():
        msg = f"Configuration file '{path}' not found."
        raise FileNotFoundError(msg)

    loader = YAML(typ="safe")
    loader.version = (1, 2)
    with path.open("r", encoding="utf-8") as handle:
        loaded = loader.load(handle) or {}
    if not isinstance(loaded, dict):  # pragma: no cover - config error guard
        msg = "Top-level YAML structure must be a mapping."
        raise TypeError(msg)
    raw: dict[str, typ.Any] = dict(loaded)
    defaults = raw.get("defaults", {}) or {}
    homepage_raw = raw.get("homepage")

    default_theme = _build_theme_config(defaults.get("theme", {}) or {})
    default_output_dir = Path(defaults.get("output_dir", "public"))
    default_filename_prefix = defaults.get("filename_prefix", "docs-")
    default_pygments_style = defaults.get("pygments_style", "monokai")
    default_page_title_suffix = defaults.get("page_title_suffix", "Docs")
    default_source_label = defaults.get("source_label", "Source material")
    default_footer_note = defaults.get("footer_note", "")
    default_page = defaults.get("default_page")
    default_branch = defaults.get("branch", "main")
    default_doc_path = defaults.get("doc_path", DEFAULT_DOC_PATH)
    default_repo = defaults.get("repo")
    default_language = defaults.get("language")
    docs_index_output = Path(defaults.get("docs_index_output", "public/docs.html"))

    shared_layouts = raw.get("layouts", {}) or {}
    pages_raw = raw.get("pages") or {}
    if not pages_raw:
        msg = "No pages defined in layout configuration."
        raise SiteConfigError(msg)

    page_defaults = _PageDefaults(
        theme=default_theme,
        output_dir=default_output_dir,
        filename_prefix=default_filename_prefix,
        pygments_style=default_pygments_style,
        page_title_suffix=default_page_title_suffix,
        source_label=default_source_label,
        footer_note=default_footer_note,
        branch=default_branch,
        doc_path=default_doc_path,
        repo=default_repo,
        language=default_language,
        shared_layouts=shared_layouts,
    )

    pages: dict[str, PageConfig] = {}
    for key, payload in pages_raw.items():
        if not isinstance(payload, dict):
            continue
        pages[key] = _build_page_config(
            key=key,
            payload=payload,
            defaults=page_defaults,
        )

    homepage_config = _build_homepage_config(homepage_raw) if homepage_raw else None

    return SiteConfig(
        pages=pages,
        default_page=default_page,
        docs_index_output=docs_index_output,
        theme=default_theme,
        homepage=homepage_config,
    )


@dc.dataclass(slots=True)
class _PageDefaults:
    """Internal container for page default configuration values."""

    theme: ThemeConfig
    output_dir: Path
    filename_prefix: str
    pygments_style: str
    page_title_suffix: str
    source_label: str
    footer_note: str
    branch: str
    doc_path: str
    repo: str | None
    language: str | None
    shared_layouts: typ.Mapping[str, typ.Any]


def _build_page_config(
    *,
    key: str,
    payload: typ.Mapping[str, typ.Any],
    defaults: _PageDefaults,
) -> PageConfig:
    """Build a PageConfig for a single page entry using defaults and overrides."""
    repo = payload.get("repo", defaults.repo)
    branch = payload.get("branch", defaults.branch)
    language = payload.get("language", defaults.language)
    doc_path = payload.get("doc_path", defaults.doc_path)
    source_url = payload.get("source_url")
    if not source_url and repo:
        source_url = _build_repo_url(repo, branch, doc_path)
    if not source_url:
        msg = f"Page '{key}' is missing 'source_url' or 'repo'."
        raise SiteConfigError(msg)

    label = payload.get("label") or key.replace("-", " ").title()
    source_label = payload.get("source_label", defaults.source_label)
    title_suffix = payload.get("page_title_suffix", defaults.page_title_suffix)
    filename_prefix = payload.get("filename_prefix", defaults.filename_prefix)
    output_dir = Path(payload.get("output_dir", defaults.output_dir))
    pygments_style = payload.get("pygments_style", defaults.pygments_style)
    footer_note = payload.get("footer_note", defaults.footer_note)
    theme = _merge_theme(defaults.theme, payload.get("theme"))

    layouts = _merge_layouts(defaults.shared_layouts, payload.get("layouts"))

    manifest_url = payload.get("manifest_url")
    if not manifest_url and repo:
        manifest_path = payload.get("manifest_path") or _default_manifest_path(language)
        if manifest_path:
            manifest_url = _build_repo_url(repo, branch, manifest_path)

    description_override = payload.get("description")
    latest_release = payload.get("latest_release")
    latest_release_published_at = _parse_timestamp(
        payload.get("latest_release_published_at")
    )

    return PageConfig(
        key=key,
        label=label,
        source_url=source_url,
        source_label=source_label,
        page_title_suffix=title_suffix,
        filename_prefix=filename_prefix,
        output_dir=output_dir,
        pygments_style=pygments_style,
        footer_note=footer_note,
        theme=theme,
        layouts=layouts,
        repo=repo,
        branch=branch,
        language=language.lower() if isinstance(language, str) else language,
        manifest_url=manifest_url,
        description_override=description_override,
        doc_path=doc_path,
        latest_release=latest_release,
        latest_release_published_at=latest_release_published_at,
    )


def _build_homepage_config(payload: typ.Mapping[str, typ.Any]) -> HomepageConfig:
    """Build the homepage configuration from the provided payload."""
    if not isinstance(payload, dict):
        msg = "Homepage configuration must be a mapping."
        raise SiteConfigError(msg)

    output = Path(payload.get("output", "public/index.html"))
    title = payload.get("title")
    if not title:
        msg = "Homepage configuration requires a 'title'."
        raise SiteConfigError(msg)

    navigation = payload.get("navigation", {}) or {}
    nav_links = _build_nav_links(navigation.get("links"))
    if not nav_links:
        msg = "Homepage navigation requires at least one link."
        raise SiteConfigError(msg)

    hero = _build_hero_config(payload.get("hero"))
    systems = _build_systems_config(payload.get("systems"))
    worlds = _build_worlds_config(payload.get("worlds"))
    footer = _build_footer_config(payload.get("footer"))

    return HomepageConfig(
        output=output,
        title=str(title),
        nav_links=nav_links,
        hero=hero,
        systems=systems,
        worlds=worlds,
        footer=footer,
    )


def _build_nav_links(
    entries: list[typ.Mapping[str, object]] | None,
) -> list[NavLinkConfig]:
    """Build navigation link configurations for the homepage."""
    links: list[NavLinkConfig] = []
    if not isinstance(entries, list):
        return links
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        href = entry.get("href")
        if not label or not href:
            msg = "Homepage navigation links require 'label' and 'href'."
            raise SiteConfigError(msg)
        links.append(
            NavLinkConfig(
                label=str(label),
                href=str(href),
                variant=_optional_str(entry.get("variant")),
                nav_target=_optional_str(entry.get("nav_target")),
            )
        )
    return links


def _build_hero_config(payload: typ.Mapping[str, object] | None) -> HeroConfig:
    """Build the hero section configuration for the homepage."""
    if not isinstance(payload, dict):
        msg = "Homepage hero configuration must be a mapping."
        raise SiteConfigError(msg)
    required = [
        "brand_text",
        "eyebrow",
        "title_primary",
        "title_secondary",
        "accent_text",
        "description",
    ]
    for key in required:
        if not payload.get(key):
            msg = f"Homepage hero is missing '{key}'."
            raise SiteConfigError(msg)
    ctas = _build_ctas(payload.get("ctas"))
    if not ctas:
        msg = "Homepage hero requires at least one CTA."
        raise SiteConfigError(msg)
    return HeroConfig(
        brand_text=str(payload["brand_text"]),
        eyebrow=str(payload["eyebrow"]),
        title_primary=str(payload["title_primary"]),
        title_secondary=str(payload["title_secondary"]),
        accent_text=str(payload["accent_text"]),
        description=str(payload["description"]),
        ctas=ctas,
    )


def _build_ctas(
    entries: list[typ.Mapping[str, object]] | None,
) -> list[CTAButtonConfig]:
    """Build call-to-action button configurations for the hero section."""
    buttons: list[CTAButtonConfig] = []
    if not isinstance(entries, list):
        return buttons
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        href = entry.get("href")
        variant = entry.get("variant")
        if not (label and href and variant):
            msg = "CTA entries require 'label', 'href', and 'variant'."
            raise SiteConfigError(msg)
        buttons.append(
            CTAButtonConfig(label=str(label), href=str(href), variant=str(variant))
        )
    return buttons


def _build_systems_config(
    payload: typ.Mapping[str, object] | None,
) -> SystemsSectionConfig:
    """Build the systems section configuration for the homepage."""
    if not isinstance(payload, dict):
        msg = "Homepage systems configuration must be a mapping."
        raise SiteConfigError(msg)
    heading = payload.get("heading")
    kicker = payload.get("kicker")
    if not (heading and kicker):
        msg = "Homepage systems section requires 'heading' and 'kicker'."
        raise SiteConfigError(msg)
    cards = _build_system_cards(payload.get("cards"))
    if not cards:
        msg = "Homepage systems section requires at least one card."
        raise SiteConfigError(msg)
    return SystemsSectionConfig(heading=str(heading), kicker=str(kicker), cards=cards)


def _build_system_cards(
    entries: list[typ.Mapping[str, object]] | None,
) -> list[SystemCardConfig]:
    """Build system card configurations for the systems section."""
    cards: list[SystemCardConfig] = []
    if not isinstance(entries, list):
        return cards
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        description = entry.get("description")
        href = entry.get("href")
        icon = entry.get("icon")
        meta_label = entry.get("meta_label")
        if not (label and description and href and icon and meta_label):
            msg = (
                "System cards require 'label', 'description', 'href', 'icon', "
                "and 'meta_label'."
            )
            raise SiteConfigError(msg)
        external = entry.get("external", True)
        cards.append(
            SystemCardConfig(
                label=str(label),
                description=str(description),
                href=str(href),
                icon=str(icon),
                meta_label=str(meta_label),
                external=bool(external),
            )
        )
    return cards


def _build_worlds_config(
    payload: typ.Mapping[str, object] | None,
) -> WorldsSectionConfig:
    """Build the worlds section configuration for the homepage."""
    if not isinstance(payload, dict):
        msg = "Homepage worlds configuration must be a mapping."
        raise SiteConfigError(msg)
    heading = payload.get("heading")
    kicker = payload.get("kicker")
    if not (heading and kicker):
        msg = "Homepage worlds section requires 'heading' and 'kicker'."
        raise SiteConfigError(msg)
    cards = _build_world_cards(payload.get("cards"))
    if not cards:
        msg = "Homepage worlds section requires at least one card."
        raise SiteConfigError(msg)
    return WorldsSectionConfig(heading=str(heading), kicker=str(kicker), cards=cards)


def _build_world_cards(
    entries: list[typ.Mapping[str, object]] | None,
) -> list[WorldCardConfig]:
    """Build world card configurations for the worlds section."""
    cards: list[WorldCardConfig] = []
    if not isinstance(entries, list):
        return cards
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        description = entry.get("description")
        href = entry.get("href")
        cta_label = entry.get("cta_label")
        if not (label and description and href and cta_label):
            msg = "World cards require 'label', 'description', 'href', and 'cta_label'."
            raise SiteConfigError(msg)
        classes = _normalize_classes(entry.get("classes"))
        if not classes:
            msg = f"World card '{label}' must define CSS classes."
            raise SiteConfigError(msg)
        image = _build_world_image(entry.get("image"), label)
        external = entry.get("external", False)
        cards.append(
            WorldCardConfig(
                label=str(label),
                description=str(description),
                href=str(href),
                classes=classes,
                image=image,
                cta_label=str(cta_label),
                external=bool(external),
            )
        )
    return cards


def _build_world_image(
    payload: typ.Mapping[str, object] | None, label: str
) -> WorldImageConfig:
    """Build world image configuration for a specific world card."""
    if not isinstance(payload, dict):
        msg = f"World card '{label}' must define an image mapping."
        raise SiteConfigError(msg)
    try:
        width = int(payload.get("width"))
        height = int(payload.get("height"))
    except (TypeError, ValueError) as exc:
        msg = f"World card '{label}' image requires numeric 'width' and 'height'."
        raise SiteConfigError(msg) from exc
    required = ["avif", "webp", "fallback", "alt", "sizes"]
    for key in required:
        if not payload.get(key):
            msg = f"World card '{label}' image missing '{key}'."
            raise SiteConfigError(msg)
    return WorldImageConfig(
        avif=str(payload["avif"]),
        webp=str(payload["webp"]),
        fallback=str(payload["fallback"]),
        alt=str(payload["alt"]),
        width=width,
        height=height,
        sizes=str(payload["sizes"]),
    )


def _build_footer_config(
    payload: typ.Mapping[str, object] | None,
) -> FooterConfig:
    """Build the footer configuration for the homepage."""
    if not isinstance(payload, dict):
        msg = "Homepage footer configuration must be a mapping."
        raise SiteConfigError(msg)
    required = [
        "site_name",
        "blurb",
        "oss_heading",
        "contact_heading",
        "closing_lede",
        "copyright_year",
    ]
    for key in required:
        if payload.get(key) in (None, ""):
            msg = f"Homepage footer is missing '{key}'."
            raise SiteConfigError(msg)
    oss_links = _build_footer_links(payload.get("oss_links"), default_external=True)
    contact_links = _build_footer_links(
        payload.get("contact_links"), default_external=False
    )
    if not oss_links or not contact_links:
        msg = "Homepage footer requires OSS and contact links."
        raise SiteConfigError(msg)
    try:
        copyright_year = int(payload.get("copyright_year"))
    except (TypeError, ValueError) as exc:
        msg = "Homepage footer 'copyright_year' must be numeric."
        raise SiteConfigError(msg) from exc
    return FooterConfig(
        site_name=str(payload["site_name"]),
        blurb=str(payload["blurb"]),
        oss_heading=str(payload["oss_heading"]),
        contact_heading=str(payload["contact_heading"]),
        closing_lede=str(payload["closing_lede"]),
        copyright_year=copyright_year,
        oss_links=oss_links,
        contact_links=contact_links,
    )


def _build_footer_links(
    entries: list[typ.Mapping[str, object]] | None, *, default_external: bool
) -> list[FooterLinkConfig]:
    """Build footer link configurations with an optional default external flag."""
    links: list[FooterLinkConfig] = []
    if not isinstance(entries, list):
        return links
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        href = entry.get("href")
        if not (label and href):
            msg = "Footer links require 'label' and 'href'."
            raise SiteConfigError(msg)
        external = entry.get("external")
        if external is None:
            external = default_external
        links.append(
            FooterLinkConfig(
                label=str(label),
                href=str(href),
                variant=_optional_str(entry.get("variant")),
                icon=_optional_str(entry.get("icon")),
                external=bool(external),
            )
        )
    return links


def _normalize_classes(value: str | list[object] | None) -> list[str]:
    """Normalize class definitions into a list of non-empty strings."""
    if isinstance(value, str):
        return [segment for segment in value.split() if segment]
    if isinstance(value, list):
        return [str(segment).strip() for segment in value if str(segment).strip()]
    return []


def _optional_str(value: object | None) -> str | None:
    """Return a stripped string value or None when empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_repo_url(repo: str, ref: str, path: str) -> str:
    """Build the raw GitHub URL for a file at the given ref and path."""
    normalized = path.lstrip("/")
    ref_segment = ref if ref.startswith("refs/") else f"refs/heads/{ref}"
    return f"https://raw.githubusercontent.com/{repo}/{ref_segment}/{normalized}"


def _default_manifest_path(language: str | None) -> str | None:
    """Return the default manifest path for the given language, if any."""
    if not language:
        return None
    return LANGUAGE_MANIFESTS.get(language.lower())


def _merge_theme(
    base: ThemeConfig, override: typ.Mapping[str, typ.Any] | None
) -> ThemeConfig:
    """Merge an override theme mapping into the base ThemeConfig."""
    if not override:
        return base
    return ThemeConfig(
        hero_eyebrow=override.get("hero_eyebrow", base.hero_eyebrow),
        hero_tagline=override.get("hero_tagline", base.hero_tagline),
        doc_label=override.get("doc_label", base.doc_label),
        site_name=override.get("site_name", base.site_name),
    )


def _build_theme_config(payload: typ.Mapping[str, typ.Any]) -> ThemeConfig:
    """Build a ThemeConfig instance from the provided mapping payload."""
    base = ThemeConfig()
    return ThemeConfig(
        hero_eyebrow=payload.get("hero_eyebrow", base.hero_eyebrow),
        hero_tagline=payload.get("hero_tagline", base.hero_tagline),
        doc_label=payload.get("doc_label", base.doc_label),
        site_name=payload.get("site_name", base.site_name),
    )


def _merge_layouts(
    shared_layouts: typ.Mapping[str, typ.Any],
    page_layouts: typ.Mapping[str, typ.Any] | None,
) -> dict[str, SectionLayout]:
    """Merge shared and page-specific layout mappings into section layouts."""
    result: dict[str, SectionLayout] = {}
    combined: dict[str, typ.Any] = dict(shared_layouts)
    if page_layouts:
        combined.update(page_layouts)
    for slug, payload in combined.items():
        if not isinstance(payload, dict):
            continue
        result[slug] = SectionLayout(
            device=payload.get("device", "default"),
            step_order=list(payload.get("step_order", []) or []),
            emphasized_code_block=payload.get("emphasized_code_block"),
        )
    return result


def _parse_timestamp(value: dt.datetime | str | None) -> dt.datetime | None:
    """Parse a timestamp value into a timezone-aware UTC datetime, if possible."""
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str):
        sanitized = value.strip()
        if not sanitized:
            return None
        if sanitized.endswith("Z"):
            sanitized = sanitized[:-1] + "+00:00"
        try:
            parsed = dt.datetime.fromisoformat(sanitized)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)
