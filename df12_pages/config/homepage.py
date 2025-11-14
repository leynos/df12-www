"""Homepage-specific configuration builders."""

from __future__ import annotations

import typing as typ
from pathlib import Path

from .helpers import _normalize_classes, _optional_str
from .models import (
    CTAButtonConfig,
    FooterConfig,
    FooterLinkConfig,
    HeroConfig,
    HomepageConfig,
    NavLinkConfig,
    SiteConfigError,
    SystemCardConfig,
    SystemsSectionConfig,
    WorldCardConfig,
    WorldImageConfig,
    WorldsSectionConfig,
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
            msg = "Hero CTA entries require 'label', 'href', and 'variant'."
            raise SiteConfigError(msg)
        buttons.append(
            CTAButtonConfig(
                label=str(label),
                href=str(href),
                variant=str(variant),
            )
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
    cards = _build_system_cards(payload.get("cards"))
    if not (heading and kicker and cards):
        msg = "Systems section requires 'heading', 'kicker', and cards."
        raise SiteConfigError(msg)
    return SystemsSectionConfig(
        heading=str(heading),
        kicker=str(kicker),
        cards=cards,
    )


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
    cards = _build_world_cards(payload.get("cards"))
    if not (heading and kicker and cards):
        msg = "Worlds section requires 'heading', 'kicker', and cards."
        raise SiteConfigError(msg)
    return WorldsSectionConfig(
        heading=str(heading),
        kicker=str(kicker),
        cards=cards,
    )


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
        image = entry.get("image")
        classes = _normalize_classes(entry.get("classes"))
        cta_label = entry.get("cta_label", "Explore")
        if not (label and description and href and image):
            msg = "World cards require 'label', 'description', 'href', and 'image'."
            raise SiteConfigError(msg)
        cards.append(
            WorldCardConfig(
                label=str(label),
                description=str(description),
                href=str(href),
                classes=classes,
                image=_build_world_image(image, str(label)),
                cta_label=str(cta_label),
                external=bool(entry.get("external", False)),
            )
        )
    return cards


def _build_world_image(
    payload: typ.Mapping[str, object] | None, label: str
) -> WorldImageConfig:
    """Build world image configuration for a specific world card."""
    if not isinstance(payload, dict):
        msg = f"World card '{label}' requires an image mapping."
        raise SiteConfigError(msg)
    required = ["avif", "webp", "fallback", "alt", "width", "height", "sizes"]
    for key in required:
        if not payload.get(key):
            msg = f"World card '{label}' image missing '{key}'."
            raise SiteConfigError(msg)
    try:
        width = int(payload.get("width"))
        height = int(payload.get("height"))
    except (TypeError, ValueError) as exc:
        msg = f"World card '{label}' image requires numeric 'width' and 'height'."
        raise SiteConfigError(msg) from exc
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


__all__ = [
    "_build_ctas",
    "_build_footer_config",
    "_build_footer_links",
    "_build_hero_config",
    "_build_homepage_config",
    "_build_nav_links",
    "_build_system_cards",
    "_build_systems_config",
    "_build_world_cards",
    "_build_world_image",
    "_build_worlds_config",
]
