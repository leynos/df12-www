"""Invariants the Stilyagi sub-site must hold after its daisyUI migration.

Stilyagi moved from eleven hand-written stylesheets onto the repository's
compiled Tailwind v4 and daisyUI v5 pipeline (issue #67). Two properties
define "done", and each is asserted here so a later change cannot quietly
undo one:

1. The build emits the compiled stylesheet, and it carries both the daisyUI
   theme slots and the design-language tokens the partials consume.
2. Every published Stilyagi page links the compiled stylesheet, and none
   still links one of the removed hand-written sheets.

The ``built_site`` fixture in ``conftest.py`` runs the full ``bun run
build``, so a missing stylesheet fails the suite rather than skipping it —
the pattern ``test_weaver_build.py`` established.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STILYAGI = REPO_ROOT / "public" / "stilyagi"
COMPILED_STYLESHEET = PUBLIC_STILYAGI / "assets" / "styles" / "stilyagi.css"

#: The stylesheets the migration deleted. A link to any of them in published
#: markup means a template regressed to the pre-migration chrome.
RETIRED_STYLESHEETS = (
    "colors-and-type.css",
    "motifs-and-components.css",
    "stilyagi-site.css",
    "assets/styles/pages/",
)


@pytest.mark.timeout(300)
def test_stilyagi_stylesheet_is_compiled(built_site: Path) -> None:
    """The build should emit a Stilyagi stylesheet carrying the theme."""
    assert COMPILED_STYLESHEET.is_file(), (
        f"expected a compiled stylesheet at {COMPILED_STYLESHEET}; "
        "is build:css:stilyagi wired into build:css?"
    )
    compiled = COMPILED_STYLESHEET.read_text(encoding="utf-8")
    assert "--color-primary" in compiled, (
        "expected the compiled stylesheet to define the daisyUI theme slots; "
        "found no --color-primary"
    )
    # The design-language names the partials speak. --color-press-red is the
    # theme's alias for the primary fill; --color-accent-text is the
    # inheriting type token every dark panel re-points. Losing either breaks
    # the palette's role split silently.
    for token in ("--color-press-red", "--color-accent-text"):
        assert token in compiled, (
            f"expected the compiled stylesheet to carry {token}; is the "
            "@theme block in src/styles/stilyagi.css still intact?"
        )


@pytest.mark.timeout(300)
def test_stilyagi_pages_link_only_the_compiled_stylesheet(
    built_site: Path,
) -> None:
    """Every published page links the compiled sheet and no retired one."""
    pages = sorted(PUBLIC_STILYAGI.rglob("*.html"))
    assert pages, f"expected published pages under {PUBLIC_STILYAGI}"
    for page in pages:
        markup = page.read_text(encoding="utf-8")
        assert "/stilyagi/assets/styles/stilyagi.css" in markup, (
            f"{page.relative_to(REPO_ROOT)} does not link the compiled stylesheet"
        )
        for retired in RETIRED_STYLESHEETS:
            assert retired not in markup, (
                f"{page.relative_to(REPO_ROOT)} still references the retired "
                f"stylesheet path {retired!r}"
            )
