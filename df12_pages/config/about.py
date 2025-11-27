"""About-page configuration builders."""

from __future__ import annotations

import typing as typ
from pathlib import Path

from .helpers import _optional_str
from .homepage import _build_footer_config, _build_nav_links
from .models import (
    AboutLocationConfig,
    AboutPageConfig,
    AvatarConfig,
    FocusCardConfig,
    FooterConfig,
    PrincipleConfig,
    SiteConfigError,
)


def _build_about_config(
    payload: typ.Mapping[str, typ.Any] | None, *, fallback_footer: FooterConfig | None
) -> AboutPageConfig | None:
    """Build the About page configuration from the provided payload."""
    if payload is None:
        return None
    if not isinstance(payload, dict):
        msg = "About configuration must be a mapping."
        raise SiteConfigError(msg)

    output = Path(payload.get("output", "public/about.html"))
    title = payload.get("title")
    if not title:
        msg = "About configuration requires a 'title'."
        raise SiteConfigError(msg)

    navigation = payload.get("navigation", {}) or {}
    brand_href = navigation.get("brand_href", "index.html")
    brand_text = navigation.get("brand_text", "df12")
    nav_links = _build_nav_links(navigation.get("links"))
    if not nav_links:
        msg = "About navigation requires at least one link."
        raise SiteConfigError(msg)

    hero = payload.get("hero") or {}
    hero_name = hero.get("name")
    hero_email = hero.get("email")
    hero_intro = hero.get("intro")
    avatar = _build_avatar(hero.get("avatar"))
    if not (hero_name and hero_email and hero_intro and avatar):
        msg = (
            "About hero requires 'name', 'email', 'intro', and an 'avatar' block."
        )
        raise SiteConfigError(msg)

    about_block = payload.get("about") or {}
    about_blurb = about_block.get("blurb")
    location = _build_location(about_block.get("location"))
    if not (about_blurb and location):
        msg = "About section requires 'blurb' text and a 'location' block."
        raise SiteConfigError(msg)

    focus_cards = _build_focus_cards(payload.get("focus"))
    principles = _build_principles(payload.get("principles"))
    footer = _build_footer_config(payload.get("footer")) or fallback_footer
    if footer is None:
        msg = "About configuration requires a 'footer' block."
        raise SiteConfigError(msg)

    return AboutPageConfig(
        output=output,
        title=str(title),
        nav_links=nav_links,
        hero_name=str(hero_name),
        hero_email=str(hero_email),
        hero_intro=str(hero_intro),
        avatar=avatar,
        about_blurb=str(about_blurb),
        location=location,
        focus_cards=focus_cards,
        principles=principles,
        footer=footer,
        brand_href=str(brand_href),
        brand_text=str(brand_text),
    )


def _build_avatar(payload: typ.Mapping[str, object] | None) -> AvatarConfig | None:
    """Build avatar metadata used by the hero."""
    match payload:
        case {"src": src, "alt": alt, "width": width, "height": height}:
            pass
        case _:
            return None
    try:
        width_int = int(width)
        height_int = int(height)
    except (TypeError, ValueError):
        return None
    return AvatarConfig(
        src=str(src),
        alt=str(alt),
        width=width_int,
        height=height_int,
    )


def _build_location(
    payload: typ.Mapping[str, object] | None,
) -> AboutLocationConfig | None:
    """Build the location callout block."""
    match payload:
        case {"title": title, "description": description, "icon": icon}:
            pass
        case _:
            return None
    return AboutLocationConfig(
        title=str(title),
        description=str(description),
        icon=str(icon),
    )


def _build_focus_cards(
    payload: typ.Mapping[str, object] | None,
) -> list[FocusCardConfig]:
    """Build focus area cards from configuration."""
    cards: list[FocusCardConfig] = []
    entries = None
    if isinstance(payload, dict):
        entries = payload.get("cards")
    match entries:
        case list() as items:
            iterable = items
        case _:
            return cards

    for entry in iterable:
        match entry:
            case {
                "title": title,
                "description": description,
                "icon": icon,
                **rest,
            }:
                pass
            case _:
                continue
        tone = _optional_str(rest.get("tone")) or "primary"
        cards.append(
            FocusCardConfig(
                title=str(title),
                description=str(description),
                icon=str(icon),
                tone=tone,
            )
        )
    if not cards:
        msg = "Focus section requires at least one card."
        raise SiteConfigError(msg)
    return cards


def _build_principles(
    payload: typ.Mapping[str, object] | list[typ.Mapping[str, object]] | None,
) -> list[PrincipleConfig]:
    """Build the list of design principles."""
    entries: list[typ.Mapping[str, object]] | None = None
    if isinstance(payload, dict):
        entries = payload.get("items")
    elif isinstance(payload, list):
        entries = payload
    if entries is None:
        return []

    principles: list[PrincipleConfig] = []
    for entry in entries:
        match entry:
            case {"title": title, "description": description}:
                principles.append(
                    PrincipleConfig(title=str(title), description=str(description))
                )
            case _:
                continue
    if not principles:
        msg = "Design principles require at least one item."
        raise SiteConfigError(msg)
    return principles


__all__ = ["_build_about_config"]
