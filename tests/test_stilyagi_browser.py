"""Computed-style contracts for the compiled Stilyagi stylesheet.

The build tests prove the compiled stylesheet exists and the published
markup carries the migrated class names; the syrupy snapshots pin the
markup structure. What none of them see is the rendered result — a cascade
regression (a partial dropped from the entrypoint, a layer reordered, a
daisyUI component selector recapturing a renamed class) leaves both intact
while the page paints wrongly. These tests load the built pages in a real
Chromium and read the computed styles back.

Three groups of contract:

* The two grounds. The home page's body must be ink type on the paper
  surface, and the ``personas`` panel must be the inverse — an ink ground
  whose accent type resolves through the re-pointed
  ``--color-accent-text`` and still clears WCAG AA contrast.
* The renamed components. Each class the migration renamed away from a
  daisyUI component name must still paint as the design language says:
  borders, fills, and type colours, at the desktop width and — visible and
  inside the viewport — at the mobile width.
* A normalized computed-style snapshot per component, so a deliberate
  design change shows as a reviewable diff and an accidental one fails.

The browser tests are marked ``playwright`` and skip through the same
guard ``test_stilyagi_focus.py`` established (no Chromium, no bun, or no
playwright package). ``TestSupportHelpers`` needs no browser and always
runs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import typing as typ
from pathlib import Path

import pytest

from tests.support.stilyagi_browser import (
    DESKTOP_VIEWPORT,
    INK,
    INK_SOFT,
    JAZZ_OCHRE,
    MOBILE_VIEWPORT,
    PAPER,
    PAPER_SHADE,
    PRESS_RED,
    PRESS_RED_ON_INK,
    PRESS_RED_TEXT,
    SIGNAL_SAGE_SOLID,
    class_tokens,
    contrast_ratio,
    http_serve,
    installed_chromium,
    normalize_style,
    parse_css_color,
    relative_luminance,
    skip_unless_browser_available,
)

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = REPO_ROOT / "public"
STYLE_PROBE = Path(__file__).parent / "support" / "stilyagi_style_probe.mjs"
COMPILED_STYLESHEET_PATH = "/stilyagi/assets/styles/stilyagi.css"

#: WCAG 2.2 AA for body text.
TEXT_CONTRAST_FLOOR = 4.5

#: The daisyUI component names the migration renamed away from. None of the
#: probed elements may carry one as a whole class token.
BARE_DAISYUI_TOKENS = frozenset({"timeline", "card", "status", "tabs", "tab"})

# The selectors under contract, named once so the jobs and the assertions
# cannot drift apart.
BODY = "body"
TENET_CARD = ".valueset .tenet-card"
TENET_NUM = ".valueset .tenet-card .vs-num"
PERSONAS = ".personas"
PERSONAS_RED = ".personas h2 .red"
SLICE_TIMELINE = ".slice-timeline"
PACING_CARD = ".pacing .pacing-card"
PACING_TITLE = ".pacing .pacing-card .tt"
ADR_STATUS = ".adr-card .adr-status:not(.prov)"
ADR_STATUS_PROV = ".adr-card .adr-status.prov"
SYNTAX_TABS = ".suppress .syntax-tabs"
SYNTAX_TAB_ACTIVE = ".suppress .syntax-tab.active"
SYNTAX_TAB_IDLE = ".suppress .syntax-tab:not(.active)"

#: Desktop probe jobs: page path (under ``/stilyagi/``) and the selectors
#: whose computed styles the contracts below read.
DESKTOP_JOBS = {
    "home": ("", [BODY]),
    "why": ("why/", [TENET_CARD, TENET_NUM, PERSONAS, PERSONAS_RED]),
    "roadmap": ("roadmap/", [SLICE_TIMELINE, PACING_CARD, PACING_TITLE]),
    "design": ("design/", [ADR_STATUS, ADR_STATUS_PROV]),
    "docs": ("docs/", [SYNTAX_TABS, SYNTAX_TAB_ACTIVE, SYNTAX_TAB_IDLE]),
}

#: One representative selector per page for the mobile fit check. The point
#: is not to restate every desktop contract at 390px but to prove each
#: renamed component is still shown and still inside the viewport there.
MOBILE_JOBS = {
    "why": ("why/", [TENET_CARD, PERSONAS]),
    "roadmap": ("roadmap/", [SLICE_TIMELINE, PACING_CARD]),
    "design": ("design/", [ADR_STATUS]),
    "docs": ("docs/", [SYNTAX_TABS, SYNTAX_TAB_ACTIVE]),
}

#: Pages that scroll horizontally at the mobile width for reasons that
#: predate the migration, recorded rather than fixed because a layout
#: change is a design decision this suite must not make. The ``why``
#: page's personas table has a min-content width of ~412px under the same
#: rules the hand-written ``pages/why.css`` shipped (verified against
#: the pre-migration stylesheet in git history); wrapping it in a scroll
#: container is the fix, and it belongs to a design change, not to the
#: migration. The overflow test asserts each entry still fires.
PREEXISTING_OVERFLOW = frozenset({"why"})

#: The computed properties worth snapshotting: paint and typography, not
#: geometry — box sizes shift with font loading and viewport, and the
#: layout facts the contracts care about are asserted directly instead.
SNAPSHOT_PROPERTIES = (
    "display",
    "position",
    "visibility",
    "backgroundColor",
    "color",
    "borderTopWidth",
    "borderBottomWidth",
    "borderTopStyle",
    "borderBottomStyle",
    "borderTopColor",
    "borderBottomColor",
    "fontFamily",
    "textTransform",
)


def assert_rgb_close(
    observed: str, expected: tuple[int, int, int], context: str, tolerance: int = 2
) -> None:
    """Assert a computed colour string matches an expected sRGB triple.

    A small tolerance absorbs the rounding a browser applies when it
    reports a colour it stored in a wider space; it is far below any
    difference a palette regression would produce.
    """
    red, green, blue, alpha = parse_css_color(observed)
    assert alpha == 1.0, f"{context}: expected an opaque colour, got {observed!r}"
    deltas = [
        abs(channel - want)
        for channel, want in zip((red, green, blue), expected, strict=True)
    ]
    assert max(deltas) <= tolerance, (
        f"{context}: expected rgb{expected}, observed {observed!r}"
    )


def _jobs_payload(origin: str) -> dict[str, typ.Any]:
    """Assemble the probe's stdin payload for both viewports."""
    jobs = []
    for name, (page, selectors) in DESKTOP_JOBS.items():
        width, height = DESKTOP_VIEWPORT
        jobs.append(
            {
                "name": f"desktop-{name}",
                "url": f"{origin}/stilyagi/{page}",
                "width": width,
                "height": height,
                "selectors": selectors,
            }
        )
    for name, (page, selectors) in MOBILE_JOBS.items():
        width, height = MOBILE_VIEWPORT
        jobs.append(
            {
                "name": f"mobile-{name}",
                "url": f"{origin}/stilyagi/{page}",
                "width": width,
                "height": height,
                "selectors": selectors,
            }
        )
    return {"jobs": jobs}


@pytest.fixture(scope="module")
def probed(built_site: Path) -> dict[str, typ.Any]:
    """Serve the built tree, run the probe once, and return its results.

    One probe run covers every page and both viewports, so the suite pays
    for a single Chromium launch however many contracts read from it.
    """
    skip_unless_browser_available()
    if not PUBLIC_ROOT.is_dir():  # pragma: no cover - defensive
        message = f"expected the built tree at {PUBLIC_ROOT}"
        raise FileNotFoundError(message)
    bun_exe = typ.cast("str", shutil.which("bun"))
    environment = os.environ | {
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE": typ.cast("str", installed_chromium())
    }
    with http_serve(PUBLIC_ROOT) as port:
        payload = _jobs_payload(f"http://127.0.0.1:{port}")
        try:
            probe = subprocess.run(  # noqa: S603 - fixed argv, paths from fixtures
                [bun_exe, str(STYLE_PROBE)],
                cwd=REPO_ROOT,
                env=environment,
                input=json.dumps(payload),
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.CalledProcessError as exc:  # pragma: no cover - guard
            missing = ("Cannot find package", "Cannot find module")
            if any(text in exc.stderr for text in missing):
                pytest.skip(
                    "the Playwright node package is not installed; run "
                    "`bun add -d playwright` to run these checks locally"
                )
            raise
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - guard
            pytest.skip(f"style probe timed out: {exc}")
    return json.loads(probe.stdout)


def _element(probed: dict[str, typ.Any], job: str, selector: str) -> dict[str, typ.Any]:
    """Return one probed element, failing with the page named if absent."""
    result = probed[job]["elements"][selector]
    assert result["found"], (
        f"{job}: expected {selector!r} on the page; the selector matched nothing"
    )
    return result


@pytest.mark.playwright
@pytest.mark.timeout(300)
class TestGrounds:
    """The paper ground, the ink ground, and the type they carry."""

    def test_home_is_ink_type_on_the_paper_surface(
        self, probed: dict[str, typ.Any]
    ) -> None:
        """The light surface: paper behind, ink in front, AA between them."""
        body = _element(probed, "desktop-home", BODY)
        assert_rgb_close(body["backgroundColor"], PAPER, "/stilyagi/ body background")
        assert_rgb_close(body["color"], INK, "/stilyagi/ body text colour")
        observed = contrast_ratio(
            parse_css_color(body["color"])[:3], body["contentGround"]
        )
        assert observed >= TEXT_CONTRAST_FLOOR, (
            f"/stilyagi/ body: ink on paper measures {observed:.2f}:1, "
            f"under the {TEXT_CONTRAST_FLOOR}:1 floor"
        )

    def test_home_loads_the_compiled_stylesheet(
        self, probed: dict[str, typ.Any]
    ) -> None:
        """The one stylesheet the layout links is the one the page loads."""
        stylesheets = probed["desktop-home"]["page"]["stylesheets"]
        assert COMPILED_STYLESHEET_PATH in stylesheets, (
            f"/stilyagi/ loaded stylesheets {stylesheets}; expected "
            f"{COMPILED_STYLESHEET_PATH} among them"
        )

    def test_personas_panel_is_the_ink_ground(self, probed: dict[str, typ.Any]) -> None:
        """The dark surface: the panel's fill resolves to the ink role."""
        personas = _element(probed, "desktop-why", PERSONAS)
        assert_rgb_close(
            personas["backgroundColor"],
            INK,
            f"/stilyagi/why/ {PERSONAS} background",
        )
        assert_rgb_close(
            personas["color"], PAPER, f"/stilyagi/why/ {PERSONAS} text colour"
        )

    def test_accent_text_re_points_on_the_ink_ground(
        self, probed: dict[str, typ.Any]
    ) -> None:
        """``--color-accent-text`` resolves to the on-ink red inside the panel.

        On paper the token is the darkened press-red; the ink-ground block
        in ``site-base.css`` re-points it to the lightened on-ink variant.
        This is the palette's role split, and it fails silently if the
        re-point block loses the panel's selector.
        """
        red = _element(probed, "desktop-why", PERSONAS_RED)
        assert_rgb_close(
            red["color"],
            PRESS_RED_ON_INK,
            f"/stilyagi/why/ {PERSONAS_RED} accent colour",
        )
        observed = contrast_ratio(
            parse_css_color(red["color"])[:3], red["contentGround"]
        )
        assert observed >= TEXT_CONTRAST_FLOOR, (
            f"/stilyagi/why/ {PERSONAS_RED}: the on-ink red measures "
            f"{observed:.2f}:1 against rgb{tuple(red['contentGround'])}, under "
            f"the {TEXT_CONTRAST_FLOOR}:1 floor"
        )

    def test_accent_text_stays_the_paper_variant_on_paper(
        self, probed: dict[str, typ.Any]
    ) -> None:
        """The same token, outside the panel, is the paper-ground red."""
        num = _element(probed, "desktop-why", TENET_NUM)
        assert_rgb_close(
            num["color"],
            PRESS_RED_TEXT,
            f"/stilyagi/why/ {TENET_NUM} accent colour",
        )


@pytest.mark.playwright
@pytest.mark.timeout(300)
class TestRenamedComponents:
    """Each renamed component still paints as the design language says."""

    def test_slice_timeline_keeps_its_structural_rule(
        self, probed: dict[str, typ.Any]
    ) -> None:
        """The roadmap timeline opens under a heavy ink rule, not a flexbox."""
        timeline = _element(probed, "desktop-roadmap", SLICE_TIMELINE)
        context = f"/stilyagi/roadmap/ {SLICE_TIMELINE}"
        assert timeline["display"] == "block", (
            f"{context}: expected display block (daisyUI's timeline is flex); "
            f"observed {timeline['display']!r}"
        )
        assert timeline["borderTopWidth"] == "4px", (
            f"{context}: expected the 4px structural rule on top; observed "
            f"{timeline['borderTopWidth']!r}"
        )
        assert timeline["borderTopStyle"] == "solid"
        assert_rgb_close(timeline["borderTopColor"], INK, f"{context} rule colour")
        assert timeline["width"] > 0, f"{context}: the timeline has no width"

    def test_pacing_card_is_a_ruled_paper_card(
        self, probed: dict[str, typ.Any]
    ) -> None:
        """A hairline ink frame around paper, titled in the accent red."""
        card = _element(probed, "desktop-roadmap", PACING_CARD)
        context = f"/stilyagi/roadmap/ {PACING_CARD}"
        assert_rgb_close(card["backgroundColor"], PAPER, f"{context} fill")
        assert card["borderTopWidth"] == "1px", (
            f"{context}: expected the 1px frame; observed {card['borderTopWidth']!r}"
        )
        assert_rgb_close(card["borderTopColor"], INK, f"{context} frame colour")
        title = _element(probed, "desktop-roadmap", PACING_TITLE)
        assert_rgb_close(
            title["color"], PRESS_RED_TEXT, f"/stilyagi/roadmap/ {PACING_TITLE} colour"
        )
        assert title["textTransform"] == "uppercase"

    def test_adr_status_is_a_sage_stamp(self, probed: dict[str, typ.Any]) -> None:
        """The accepted stamp: paper type on the sage fill, set as a stamp."""
        status = _element(probed, "desktop-design", ADR_STATUS)
        context = f"/stilyagi/design/ {ADR_STATUS}"
        assert status["display"] == "inline-block", (
            f"{context}: expected an inline-block stamp; observed {status['display']!r}"
        )
        assert_rgb_close(
            status["backgroundColor"], SIGNAL_SAGE_SOLID, f"{context} fill"
        )
        assert_rgb_close(status["color"], PAPER, f"{context} type colour")
        assert status["textTransform"] == "uppercase"
        observed = contrast_ratio(
            parse_css_color(status["color"])[:3], status["contentGround"]
        )
        assert observed >= TEXT_CONTRAST_FLOOR, (
            f"{context}: paper on sage measures {observed:.2f}:1, under "
            f"{TEXT_CONTRAST_FLOOR}:1"
        )

    def test_provisional_adr_status_is_the_ochre_variant(
        self, probed: dict[str, typ.Any]
    ) -> None:
        """The provisional stamp swaps to ink type on the ochre fill."""
        prov = _element(probed, "desktop-design", ADR_STATUS_PROV)
        context = f"/stilyagi/design/ {ADR_STATUS_PROV}"
        assert_rgb_close(prov["backgroundColor"], JAZZ_OCHRE, f"{context} fill")
        assert_rgb_close(prov["color"], INK, f"{context} type colour")
        observed = contrast_ratio(
            parse_css_color(prov["color"])[:3], prov["contentGround"]
        )
        assert observed >= TEXT_CONTRAST_FLOOR, (
            f"{context}: ink on ochre measures {observed:.2f}:1, under "
            f"{TEXT_CONTRAST_FLOOR}:1"
        )

    def test_syntax_tabs_are_the_intended_tab_controls(
        self, probed: dict[str, typ.Any]
    ) -> None:
        """The tab row underlines in ink; the active tab carries the red."""
        tabs = _element(probed, "desktop-docs", SYNTAX_TABS)
        context = f"/stilyagi/docs/ {SYNTAX_TABS}"
        assert tabs["display"] == "flex", (
            f"{context}: expected the flex tab row; observed {tabs['display']!r}"
        )
        assert tabs["borderBottomWidth"] == "4px", (
            f"{context}: expected the 4px baseline rule; observed "
            f"{tabs['borderBottomWidth']!r}"
        )
        assert_rgb_close(tabs["borderBottomColor"], INK, f"{context} baseline colour")

        active = _element(probed, "desktop-docs", SYNTAX_TAB_ACTIVE)
        context = f"/stilyagi/docs/ {SYNTAX_TAB_ACTIVE}"
        assert_rgb_close(active["color"], PRESS_RED_TEXT, f"{context} type colour")
        assert_rgb_close(
            active["borderBottomColor"], PRESS_RED, f"{context} underline colour"
        )
        assert_rgb_close(active["backgroundColor"], PAPER_SHADE, f"{context} fill")

        idle = _element(probed, "desktop-docs", SYNTAX_TAB_IDLE)
        assert_rgb_close(
            idle["color"], INK_SOFT, f"/stilyagi/docs/ {SYNTAX_TAB_IDLE} type colour"
        )

    def test_tenet_card_is_the_intended_card(self, probed: dict[str, typ.Any]) -> None:
        """A 2px ink frame around paper, positioned for its own children."""
        card = _element(probed, "desktop-why", TENET_CARD)
        context = f"/stilyagi/why/ {TENET_CARD}"
        assert card["position"] == "relative", (
            f"{context}: expected position relative (the number is anchored to "
            f"it); observed {card['position']!r}"
        )
        assert card["borderTopWidth"] == "2px", (
            f"{context}: expected the 2px rule-weight frame; observed "
            f"{card['borderTopWidth']!r}"
        )
        assert_rgb_close(card["backgroundColor"], PAPER, f"{context} fill")
        assert_rgb_close(card["borderTopColor"], INK, f"{context} frame colour")

    def test_no_probed_element_carries_a_bare_daisyui_token(
        self, probed: dict[str, typ.Any]
    ) -> None:
        """The renamed classes must not regress to the colliding names."""
        for job, result in probed.items():
            for selector, element in result["elements"].items():
                if not element.get("found"):
                    continue
                collisions = class_tokens(element["className"]) & BARE_DAISYUI_TOKENS
                assert not collisions, (
                    f"{job} {selector}: the element carries the daisyUI-colliding "
                    f"class token(s) {sorted(collisions)}"
                )


@pytest.mark.playwright
@pytest.mark.timeout(300)
class TestMobileViewport:
    """Every renamed component stays visible and inside the 390px viewport."""

    @pytest.mark.parametrize(
        ("job", "selector"),
        [
            pytest.param(f"mobile-{name}", selector, id=f"{name}-{selector}")
            for name, (_, selectors) in MOBILE_JOBS.items()
            for selector in selectors
        ],
    )
    def test_component_is_visible_and_fits(
        self, probed: dict[str, typ.Any], job: str, selector: str
    ) -> None:
        """Shown, painted, and no wider than the viewport at 390px."""
        element = _element(probed, job, selector)
        page = job.removeprefix("mobile-")
        context = f"/stilyagi/{page}/ {selector} at {MOBILE_VIEWPORT[0]}px"
        assert element["display"] != "none", f"{context}: display is none"
        assert element["visibility"] == "visible", (
            f"{context}: visibility is {element['visibility']!r}"
        )
        assert element["width"] > 0, f"{context}: the element has no width"
        assert element["width"] <= MOBILE_VIEWPORT[0], (
            f"{context}: the element is {element['width']:.0f}px wide, past the "
            f"viewport"
        )

    @pytest.mark.parametrize("name", sorted(MOBILE_JOBS))
    def test_page_has_no_horizontal_overflow(
        self, probed: dict[str, typ.Any], name: str
    ) -> None:
        """The page itself lays out inside the mobile viewport.

        A page in ``PREEXISTING_OVERFLOW`` is asserted to still overflow
        instead, the way the Weaver suites keep their axe waivers honest:
        the waiver cannot outlive the defect, and whoever fixes the layout
        is pointed at the entry to delete.
        """
        page = probed[f"mobile-{name}"]["page"]
        if name in PREEXISTING_OVERFLOW:
            assert page["scrollWidth"] > page["innerWidth"], (
                f"/stilyagi/{MOBILE_JOBS[name][0]} no longer overflows at "
                f"{MOBILE_VIEWPORT[0]}px — the pre-existing defect is fixed, so "
                f"delete its PREEXISTING_OVERFLOW entry"
            )
            return
        assert page["scrollWidth"] <= page["innerWidth"], (
            f"/stilyagi/{MOBILE_JOBS[name][0]} at {MOBILE_VIEWPORT[0]}px scrolls "
            f"horizontally: content is {page['scrollWidth']}px wide in a "
            f"{page['innerWidth']}px viewport"
        )


@pytest.mark.playwright
@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    ("job", "selector"),
    [
        pytest.param(f"desktop-{name}", selector, id=f"{name}-{selector}")
        for name, (_, selectors) in DESKTOP_JOBS.items()
        for selector in selectors
    ],
)
def test_component_paint_snapshot(
    probed: dict[str, typ.Any],
    snapshot: SnapshotAssertion,
    job: str,
    selector: str,
) -> None:
    """Each probed element's paint and typography, pinned as a snapshot.

    Geometry and grounds are excluded — box sizes move with font loading
    and viewport, and the layout contracts are asserted directly above.
    ``normalize_style`` rounds pixel lengths and masks any URL, so the
    serialization carries no served origin and no sub-pixel noise.
    """
    element = _element(probed, job, selector)
    subset = {key: element[key] for key in SNAPSHOT_PROPERTIES}
    assert normalize_style(subset) == snapshot


class TestSupportHelpers:
    """The colour arithmetic and normalization the contracts lean on."""

    def test_parse_css_color_reads_rgb_and_rgba(self) -> None:
        """The two forms Chromium reports most computed colours in."""
        assert parse_css_color("rgb(239, 228, 206)") == (239, 228, 206, 1.0)
        assert parse_css_color("rgba(15, 15, 15, 0.5)") == (15, 15, 15, 0.5)

    def test_parse_css_color_scales_srgb_channels(self) -> None:
        """``color(srgb ...)`` carries 0-1 channels and scales to 0-255."""
        expected_alpha = 0.25
        red, green, blue, alpha = parse_css_color("color(srgb 1 0.5 0 / 0.25)")
        assert (round(red), round(green), round(blue)) == (255, 128, 0)
        assert alpha == expected_alpha

    def test_parse_css_color_rejects_a_non_colour(self) -> None:
        """A keyword the browser should never report fails loudly."""
        with pytest.raises(ValueError, match="cannot read"):
            parse_css_color("transparent")

    def test_relative_luminance_bounds(self) -> None:
        """Black is 0 and white is 1, per the WCAG definition."""
        assert relative_luminance((0, 0, 0)) == 0.0
        assert relative_luminance((255, 255, 255)) == pytest.approx(1.0)

    def test_contrast_ratio_is_symmetric_and_maximal_for_black_on_white(
        self,
    ) -> None:
        """Order must not matter, and the maximum is 21:1."""
        assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
        assert contrast_ratio((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0)

    def test_assert_rgb_close_tolerates_rounding_but_not_regression(self) -> None:
        """One channel step passes; a wrong colour fails."""
        assert_rgb_close("rgb(240, 227, 205)", PAPER, "tolerance case")
        with pytest.raises(AssertionError, match="expected rgb"):
            assert_rgb_close("rgb(255, 255, 255)", PAPER, "regression case")

    def test_assert_rgb_close_rejects_translucent_colours(self) -> None:
        """A translucent answer means the probe read the wrong layer."""
        with pytest.raises(AssertionError, match="opaque"):
            assert_rgb_close("rgba(239, 228, 206, 0.5)", PAPER, "alpha case")

    def test_normalize_style_rounds_and_redacts(self) -> None:
        """Sub-pixel lengths round; served-origin URLs are masked."""
        noisy = {
            "borderTopWidth": "1.3333333px",
            "backgroundImage": 'url("http://127.0.0.1:5391/x.png"), url(a.svg)',
            "width": 123.456789,
            "display": "block",
        }
        assert normalize_style(noisy) == {
            "backgroundImage": "url([redacted]), url([redacted])",
            "borderTopWidth": "1.3px",
            "display": "block",
            "width": 123.5,
        }

    def test_normalize_style_orders_keys(self) -> None:
        """Deterministic key order keeps the serialization stable."""
        assert list(normalize_style({"b": "x", "a": "y"})) == ["a", "b"]

    def test_class_tokens_splits_whole_tokens(self) -> None:
        """Membership is by whole token, never by substring."""
        assert class_tokens("syntax-tab active") == {"syntax-tab", "active"}
        assert "tab" not in class_tokens("syntax-tab")
