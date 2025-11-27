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
    match payload:
        case dict() as data:
            output = Path(data.get("output", "public/index.html"))
            title = data.get("title")
        case _:
            msg = "Homepage configuration must be a mapping."
            raise SiteConfigError(msg)
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
    match entries:
        case list() as items:
            iterable = items
        case _:
            return links
    for entry in iterable:
        match entry:
            case {"label": label, "href": href, **rest}:
                pass
            case _:
                continue
        if not label or not href:
            msg = "Homepage navigation links require 'label' and 'href'."
            raise SiteConfigError(msg)
        links.append(
            NavLinkConfig(
                label=str(label),
                href=str(href),
                variant=_optional_str(rest.get("variant")),
                nav_target=_optional_str(rest.get("nav_target")),
                current=bool(rest.get("current", False)),
            )
        )
    return links


def _build_hero_config(payload: typ.Mapping[str, object] | None) -> HeroConfig:
    """Build the hero section configuration for the homepage."""
    match payload:
        case {
            "brand_text": brand_text,
            "eyebrow": eyebrow,
            "title_primary": title_primary,
            "title_secondary": title_secondary,
            "accent_text": accent_text,
            "description": description,
            **rest,
        }:
            pass
        case _:
            msg = "Homepage hero configuration must be a mapping."
            raise SiteConfigError(msg)
    for key, value in {
        "brand_text": brand_text,
        "eyebrow": eyebrow,
        "title_primary": title_primary,
        "title_secondary": title_secondary,
        "accent_text": accent_text,
        "description": description,
    }.items():
        if not value:
            msg = f"Homepage hero is missing '{key}'."
            raise SiteConfigError(msg)
    ctas = _build_ctas(rest.get("ctas"))
    if not ctas:
        msg = "Homepage hero requires at least one CTA."
        raise SiteConfigError(msg)
    return HeroConfig(
        brand_text=str(brand_text),
        eyebrow=str(eyebrow),
        title_primary=str(title_primary),
        title_secondary=str(title_secondary),
        accent_text=str(accent_text),
        description=str(description),
        ctas=ctas,
    )


def _build_ctas(
    entries: list[typ.Mapping[str, object]] | None,
) -> list[CTAButtonConfig]:
    """Build call-to-action button configurations for the hero section."""
    buttons: list[CTAButtonConfig] = []
    match entries:
        case list() as items:
            iterable = items
        case _:
            return buttons
    for entry in iterable:
        match entry:
            case {"label": label, "href": href, "variant": variant, **_rest}:
                pass
            case _:
                continue
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
    match payload:
        case {"heading": heading, "kicker": kicker, **rest}:
            cards = _build_system_cards(rest.get("cards"))
        case _:
            msg = "Homepage systems configuration must be a mapping."
            raise SiteConfigError(msg)
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
    match entries:
        case list() as items:
            iterable = items
        case _:
            return cards
    for entry in iterable:
        match entry:
            case {
                "label": label,
                "description": description,
                "href": href,
                "icon": icon,
                "meta_label": meta_label,
                **rest,
            }:
                pass
            case _:
                continue
        if not (label and description and href and icon and meta_label):
            msg = (
                "System cards require 'label', 'description', 'href', 'icon', "
                "and 'meta_label'."
            )
            raise SiteConfigError(msg)
        external = rest.get("external", True)
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
    match payload:
        case {"heading": heading, "kicker": kicker, **rest}:
            cards = _build_world_cards(rest.get("cards"))
        case _:
            msg = "Homepage worlds configuration must be a mapping."
            raise SiteConfigError(msg)
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
    match entries:
        case list() as items:
            iterable = items
        case _:
            return cards
    for entry in iterable:
        match entry:
            case {
                "label": label,
                "description": description,
                "href": href,
                "image": image,
                **rest,
            }:
                pass
            case _:
                continue
        classes = _normalize_classes(rest.get("classes"))
        cta_label = rest.get("cta_label", "Explore")
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
                external=bool(rest.get("external", False)),
            )
        )
    return cards


def _build_world_image(
    payload: typ.Mapping[str, object] | None, label: str
) -> WorldImageConfig:
    """Build world image configuration for a specific world card."""
    match payload:
        case (
            {
                "avif": avif,
                "webp": webp,
                "fallback": fallback,
                "alt": alt,
                "width": width_value,
                "height": height_value,
                "sizes": sizes,
            } as data
        ):
            required = ["avif", "webp", "fallback", "alt", "width", "height", "sizes"]
        case _:
            msg = f"World card '{label}' requires an image mapping."
            raise SiteConfigError(msg)
    for key in required:
        if not data.get(key):
            msg = f"World card '{label}' image missing '{key}'."
            raise SiteConfigError(msg)
    try:
        width = int(width_value)
        height = int(height_value)
    except (TypeError, ValueError) as exc:
        msg = f"World card '{label}' image requires numeric 'width' and 'height'."
        raise SiteConfigError(msg) from exc
    return WorldImageConfig(
        avif=str(avif),
        webp=str(webp),
        fallback=str(fallback),
        alt=str(alt),
        width=width,
        height=height,
        sizes=str(sizes),
    )


def _build_footer_config(
    payload: typ.Mapping[str, object] | None,
) -> FooterConfig:
    """Build the footer configuration for the homepage."""
    match payload:
        case dict() as data:
            pass
        case _:
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
        if data.get(key) in (None, ""):
            msg = f"Homepage footer is missing '{key}'."
            raise SiteConfigError(msg)
    oss_links = _build_footer_links(data.get("oss_links"), default_external=True)
    contact_links = _build_footer_links(
        data.get("contact_links"), default_external=False
    )
    if not oss_links or not contact_links:
        msg = "Homepage footer requires OSS and contact links."
        raise SiteConfigError(msg)
    try:
        copyright_year = int(data.get("copyright_year"))
    except (TypeError, ValueError) as exc:
        msg = "Homepage footer 'copyright_year' must be numeric."
        raise SiteConfigError(msg) from exc
    return FooterConfig(
        site_name=str(data["site_name"]),
        blurb=str(data["blurb"]),
        oss_heading=str(data["oss_heading"]),
        contact_heading=str(data["contact_heading"]),
        closing_lede=str(data["closing_lede"]),
        copyright_year=copyright_year,
        oss_links=oss_links,
        contact_links=contact_links,
    )


def _build_footer_links(
    entries: list[typ.Mapping[str, object]] | None, *, default_external: bool
) -> list[FooterLinkConfig]:
    """Build footer link configurations with an optional default external flag."""
    links: list[FooterLinkConfig] = []
    match entries:
        case list() as items:
            iterable = items
        case _:
            return links
    for entry in iterable:
        match entry:
            case {"label": label, "href": href, **rest}:
                pass
            case _:
                continue
        if not (label and href):
            msg = "Footer links require 'label' and 'href'."
            raise SiteConfigError(msg)
        external = rest.get("external")
        if external is None:
            external = default_external
        links.append(
            FooterLinkConfig(
                label=str(label),
                href=str(href),
                variant=_optional_str(rest.get("variant")),
                icon=_optional_str(rest.get("icon")),
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
