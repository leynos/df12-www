"""Invariants the Netsuke sub-site must hold after its daisyUI migration.

The Netsuke sub-site is moving off the Tailwind Play CDN onto the repository's
compiled Tailwind v4 and daisyUI v5 pipeline. See
``docs/execplans/netsuke-daisy-migration.md``. Two properties define "done",
and each is asserted here so a later change cannot quietly undo one:

1. The stylesheet is compiled by the build rather than assembled in the
   browser, and carries the daisyUI theme.
2. No published Netsuke page loads the Play CDN.

Each was written failing, with a strict ``xfail`` marker naming the milestone
that turned it green — a marker left in place after the behaviour arrived
would itself have failed the suite, so none could be forgotten. Both now pass
on their own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_weaver_build import SUBRESOURCE

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_NETSUKE = REPO_ROOT / "public" / "netsuke"
COMPILED_STYLESHEET = PUBLIC_NETSUKE / "assets" / "css" / "himotoshi.css"

# The Play CDN's host, as a browser would be sent to fetch it. Anchored on
# the host rather than the whole URL so a version-pinned variant
# (`https://cdn.tailwindcss.com/3.4.1`) is caught as well.
PLAY_CDN = re.compile(r"cdn\.tailwindcss\.com")


@pytest.mark.timeout(300)
def test_netsuke_stylesheet_is_compiled(built_site: Path) -> None:
    """The build should emit a Netsuke stylesheet carrying the daisyUI theme.

    The hand-written stylesheet is copied into place today, so the file exists
    either way; what distinguishes the compiled one is the theme it carries.
    """
    del built_site  # the fixture is the build; the tree it returns is Weaver's
    assert COMPILED_STYLESHEET.is_file(), (
        f"expected a compiled stylesheet at {COMPILED_STYLESHEET}; "
        "is build:css:netsuke wired into build:css?"
    )
    compiled = COMPILED_STYLESHEET.read_text(encoding="utf-8")
    assert "--color-primary" in compiled, (
        "expected the compiled stylesheet to define the daisyUI theme slots; "
        "found no --color-primary"
    )


@pytest.mark.timeout(300)
def test_netsuke_pages_do_not_load_the_play_cdn(built_site: Path) -> None:
    """No published Netsuke page should fetch Tailwind from the Play CDN.

    This looks at the attributes that make a browser fetch something, through
    the same pattern the Weaver suite uses, and then asks whether any of those
    fetches reaches the Play CDN's host. Netsuke still loads fonts and icons
    from elsewhere, which is out of this migration's scope; the Play CDN is
    the one remote subresource it retires.
    """
    del built_site
    offenders: dict[str, list[str]] = {}
    for page in sorted(PUBLIC_NETSUKE.rglob("*.html")):
        markup = page.read_text(encoding="utf-8")
        remote = sorted(
            {
                match.group(0)[:80]
                for match in SUBRESOURCE.finditer(markup)
                if PLAY_CDN.search(markup[match.start() : match.start() + 120])
            }
        )
        if remote:
            offenders[str(page.relative_to(PUBLIC_NETSUKE))] = remote

    assert not offenders, (
        "expected no Netsuke page to load the Tailwind Play CDN, but these do: "
        f"{offenders}"
    )
