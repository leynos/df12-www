"""Invariants the Stilyagi sub-site must hold after its daisyUI migration.

Stilyagi moved from eleven hand-written stylesheets onto the repository's
compiled Tailwind v4 and daisyUI v5 pipeline (issue #67). Three properties
define "done", and each is asserted here so a later change cannot quietly
undo one:

1. The build emits the compiled stylesheet, and it carries the daisyUI
   theme slots, the design-language tokens the partials consume, and the
   generated Pygments rules that now compile in rather than link
   separately.
2. Every published Stilyagi page links the compiled stylesheet, and none
   still links a removed hand-written sheet or the Pygments source file.
3. The published markup keeps the class names the migration renamed to
   dodge daisyUI's component selectors, and none of the colliding bare
   names creeps back in.

The ``built_site`` fixture in ``conftest.py`` runs the full ``bun run
build``, so a missing stylesheet fails the suite rather than skipping it —
the pattern ``test_weaver_build.py`` established.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STILYAGI = REPO_ROOT / "public" / "stilyagi"
COMPILED_STYLESHEET = PUBLIC_STILYAGI / "assets" / "styles" / "stilyagi.css"

#: Stylesheet paths no published page may link. The first three were deleted
#: by the migration; ``syntax.css`` still exists in ``src/static`` because
#: the Pygments generator owns it, but it compiles into the entrypoint now
#: and a separate link to it would double-apply the rules unlayered.
RETIRED_STYLESHEETS = (
    "colors-and-type.css",
    "motifs-and-components.css",
    "stilyagi-site.css",
    "assets/styles/pages/",
    "assets/styles/syntax.css",
)

#: Class tokens each published page must carry. These are the names the
#: migration chose to stay clear of daisyUI's component selectors
#: (``timeline``, ``card``, ``status``, ``tabs``/``tab``) plus the
#: page-scope classes the per-page partials hang their selectors on.
EXPECTED_PAGE_CLASSES = {
    "why/index.html": ("why-page", "tenet-card"),
    "how/index.html": ("how-page",),
    "roadmap/index.html": ("roadmap-page", "slice-timeline", "pacing-card"),
    "design/index.html": ("adr-status",),
    "docs/index.html": ("syntax-tabs", "syntax-tab"),
}

#: daisyUI component names the migration renamed away from. Any of these as
#: a whole class token would pick up daisyUI's component styling — the flex
#: ``timeline`` blowout was the original symptom.
RETIRED_CLASS_TOKENS = frozenset({"timeline", "card", "status", "tabs", "tab"})

_CLASS_ATTR_RE = re.compile(r'class="([^"]*)"')


def _class_tokens(markup: str) -> frozenset[str]:
    """Return every whole class token used in ``markup``."""
    return frozenset(
        token for attr in _CLASS_ATTR_RE.findall(markup) for token in attr.split()
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
    # The generated Pygments block compiles in via the entrypoint's @import
    # of src/static/stilyagi/assets/styles/syntax.css. The custom property
    # proves the generated variables arrived; the descendant selector proves
    # the token rules did too. (The BEGIN/END marker comments do not survive
    # minification, so they cannot anchor this check.)
    for marker in ("--stilyagi-syntax-keyword", ".stilyagi-syntax .kn"):
        assert marker in compiled, (
            f"expected the compiled stylesheet to carry {marker!r}; is the "
            "syntax.css @import in src/styles/stilyagi.css still intact?"
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


@pytest.mark.timeout(300)
def test_stilyagi_pages_keep_the_renamed_classes(built_site: Path) -> None:
    """Published markup carries the renamed classes and no colliding one.

    The DOM suites exercise these class names too, but against hand-built
    fixtures in ``tests/js/helpers/stilyagi.mjs`` — a template that
    regressed to a bare daisyUI name would sail past them. This test reads
    the pages the build actually publishes.
    """
    for relative, expected in EXPECTED_PAGE_CLASSES.items():
        page = PUBLIC_STILYAGI / relative
        assert page.is_file(), f"expected a published page at {page}"
        tokens = _class_tokens(page.read_text(encoding="utf-8"))
        for cls in expected:
            assert cls in tokens, (
                f"public/stilyagi/{relative} no longer carries the class "
                f"{cls!r}; did the template regress to a daisyUI-colliding "
                "name or lose its page-scope class?"
            )
    for page in sorted(PUBLIC_STILYAGI.rglob("*.html")):
        collisions = (
            _class_tokens(page.read_text(encoding="utf-8")) & RETIRED_CLASS_TOKENS
        )
        assert not collisions, (
            f"{page.relative_to(REPO_ROOT)} uses the daisyUI-colliding "
            f"class token(s) {sorted(collisions)}; use the renamed "
            "equivalents instead"
        )
