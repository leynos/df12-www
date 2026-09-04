"""The argv the harness hands css-view and agent-browser.

Built by pure functions, so what a command would run can be asserted without
starting a browser — which is the only way to catch a flag in the wrong place
or a session two runs would share.
"""

from __future__ import annotations

import json
import os
import subprocess
import typing as typ
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from tests.support.weaver_harness import load

paths = load("weaver_snapshot_paths")
tools = load("weaver_snapshot_tools")


def test_the_walker_expression_carries_its_parameters() -> None:
    """The evaluator is a template; every placeholder has to be filled in."""
    expression = tools._walker_expression(max_nodes=123, text_clip=45)

    assert "__" not in expression.replace("__snapshotSettle", ""), (
        "a placeholder left unfilled would be a syntax error in the page"
    )
    assert expression.rstrip().endswith("123, 45);"), (
        f"the parameters are the final call's arguments; got {expression[-60:]!r}"
    )
    assert '"line-height"' in expression, (
        "the inherited-property list is what makes a child's value a diff "
        "against its parent rather than the user-agent default"
    )
    assert '"margin-bottom"' in expression, (
        "margins are reported whatever they equal, or a paragraph's default "
        "16px below would go unrecorded and the gap folding would read it as 0"
    )


def test_the_snapshot_document_puts_the_tree_where_readers_look() -> None:
    """`payload.tree` is the contract every reader of a snapshot relies on."""
    tree = {"tag": "html", "classes": [], "styleDiff": {}, "children": []}
    # agent-browser prints the expression's string result JSON-encoded once
    # more, so the walker's JSON arrives double-encoded.
    evaluated = json.dumps(json.dumps({"tree": tree, "visited": 1}))

    document = tools._snapshot_document("http://x/netsuke/", evaluated)

    assert document["payload"]["tree"] == tree
    assert document["payload"]["meta"]["visited"] == 1
    assert document["meta"]["url"] == "http://x/netsuke/"
    assert document["meta"]["viewport"] == {
        "width": tools.CAPTURE_WIDTH,
        "height": tools.CAPTURE_HEIGHT,
    }


def test_the_browser_session_is_named_for_the_site_and_the_job() -> None:
    """Two sites, or a capture and a screenshot run, must not share a session."""
    assert tools._session_name("netsuke").startswith("netsuke-shots"), (
        f"got {tools._session_name('netsuke')!r}"
    )
    assert tools._session_name("netsuke", "capture").startswith("netsuke-capture"), (
        "the session is named for the site and the purpose, so two sites' runs "
        "cannot share a browser"
    )
    assert tools._session_name("netsuke") != tools._session_name("weaver"), (
        "a session is one viewport and one page; two sites need two"
    )


def test_the_screenshot_path_precedes_its_flags() -> None:
    """Order is load-bearing here, and getting it wrong still reports success.

    Passing ``--full`` first makes agent-browser read the path as a selector
    and write the image somewhere else, exiting zero either way. Only the
    argument order distinguishes the two.
    """
    argv = tools._screenshot_argv(Path("/out/home@360.png"))

    assert argv[0] == "screenshot", f"the subcommand comes first; got {argv!r}"
    assert argv[1] == "/out/home@360.png", (
        f"the path is positional and must precede any flag; got {argv!r}"
    )
    assert Path(argv[1]).is_absolute(), (
        "agent-browser runs as a daemon with its own working directory, so a "
        f"relative path would land somewhere unexpected; got {argv[1]!r}"
    )


def test_concurrent_runs_do_not_share_a_browser_session() -> None:
    """A shared session name would let two runs interleave.

    agent-browser sessions are named globally and hold one viewport and one
    current page between calls, so two runs sharing a name would resize each
    other's viewport mid-capture and report success for both.
    """
    name = tools._session_name()

    assert str(os.getpid()) in name, (
        f"the session name must distinguish this process; got {name!r}"
    )
    assert name.startswith("weaver-shots"), (
        f"the name should still say what the session is for; got {name!r}"
    )


def _recording_browser(
    tmp_path: Path,
    *,
    settle_fails: bool = False,
    unrendered: int = 0,
) -> tuple[list[list[str]], typ.Any, typ.Any]:
    """Stand in for agent-browser, recording each call and answering `eval`."""
    calls: list[list[str]] = []

    def run(argv: cabc.Sequence[str]) -> None:
        calls.append(list(argv))
        if settle_fails and argv[1] == "wait" and "--fn" in argv:
            raise subprocess.CalledProcessError(1, list(argv))

    def read(argv: cabc.Sequence[str]) -> str:
        calls.append(list(argv))
        spans = [
            {"tag": "span", "classes": ["iconify"], "styleDiff": {}, "children": []}
            for _ in range(unrendered)
        ]
        tree = {"tag": "html", "classes": [], "styleDiff": {}, "children": spans}
        return json.dumps(json.dumps({"tree": tree, "visited": 1 + unrendered}))

    return calls, run, read


def test_capture_settles_each_page_before_walking_it(tmp_path: Path) -> None:
    """Open, wait for the network, wait for the icons, then walk — in that order.

    A walk taken before Iconify has drawn its glyphs records placeholders
    where the icons will be, which moves every line below them: a layout
    change that is not a style change. The order is the whole point.
    """
    calls, run, read = _recording_browser(tmp_path)
    pages = ["", "install/"]
    tools._capture_pages(
        pages,
        tmp_path,
        "http://127.0.0.1:8099",
        "/usr/bin/agent-browser",
        run,
        read,
        "netsuke",
    )

    assert calls[0][1:5] == ["set", "viewport", "1280", "720"], (
        f"the viewport should be pinned before any page loads; got {calls[0]}"
    )
    per_page = [argv[1] for argv in calls[1:-1]]
    assert per_page == ["open", "wait", "wait", "eval"] * len(pages), (
        f"each page should be opened, settled twice over, then walked; got {per_page}"
    )
    opened = [argv[2] for argv in calls if argv[1] == "open"]
    assert opened == [
        "http://127.0.0.1:8099/netsuke/",
        "http://127.0.0.1:8099/netsuke/install/",
    ], f"every page should be opened under the site; got {opened}"
    settles = [argv for argv in calls if argv[1] == "wait" and "--fn" in argv]
    assert all("Iconify" in argv[argv.index("--fn") + 1] for argv in settles), (
        "the settle wait should ask Iconify whether its icons have arrived"
    )
    assert calls[-1][1] == "close", "the session should be closed on the way out"
    for page in pages:
        written = json.loads((tmp_path / f"{paths._slug(page)}.json").read_text())
        assert written["payload"]["tree"]["tag"] == "html", (
            f"the walk should be written under payload.tree; got {written}"
        )


def test_a_page_that_never_settles_is_still_captured(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An icon the set lacks keeps its placeholder; the page is captured and said so."""
    calls, run, read = _recording_browser(tmp_path, settle_fails=True, unrendered=1)
    tools._capture_pages(
        ["docs/"], tmp_path, "http://x", "/usr/bin/agent-browser", run, read, "netsuke"
    )

    assert [argv[1] for argv in calls].count("eval") == 1, (
        "the walk should still be taken once the settle wait gives up"
    )
    assert (tmp_path / "docs.json").is_file()
    report = capsys.readouterr().out
    assert "did not settle" in report, f"the report should say so; got {report!r}"
    assert "1 icons the set does not have" in report, (
        f"the report should count the placeholders left; got {report!r}"
    )


def test_a_snapshot_that_cannot_be_read_is_an_error_not_a_count(
    tmp_path: Path,
) -> None:
    """The harness has just written the file, so failing to read it is a bug."""
    with pytest.raises(FileNotFoundError):
        tools._unrendered_icons(tmp_path / "absent.json")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Expecting"):
        tools._unrendered_icons(tmp_path / "broken.json")
    (tmp_path / "shapeless.json").write_text('{"payload": {}}', encoding="utf-8")
    with pytest.raises(KeyError):
        tools._unrendered_icons(tmp_path / "shapeless.json")


def test_a_failing_capture_stops_the_run_rather_than_reporting_success() -> None:
    """A tool that exits non-zero must not leave a partial snapshot passing.

    Raising is half of it. The other half is stopping: a loop that swallowed
    the first failure and carried on would produce a directory missing one
    page, which compares clean against a baseline that has it.
    """
    attempted: list[list[str]] = []

    def explode(argv: cabc.Sequence[str]) -> None:
        attempted.append(list(argv))
        if argv[1] in {"set", "close"}:
            return
        raise subprocess.CalledProcessError(1, list(argv))

    with pytest.raises(subprocess.CalledProcessError):
        tools._capture_pages(
            ["", "install/"],
            Path("/out"),
            "http://x",
            "/usr/bin/agent-browser",
            explode,
            lambda _argv: "",
        )

    opened = [argv for argv in attempted if argv[1] == "open"]
    assert len(opened) == 1, (
        f"the run should stop at the first failure, but it opened "
        f"{len(opened)} pages: {opened}"
    )


def test_shots_closes_its_session_even_when_a_page_fails() -> None:
    """An interrupted run must not strand a daemon holding the viewport."""
    calls: list[list[str]] = []

    def fail_on_screenshot(argv: cabc.Sequence[str]) -> None:
        calls.append(list(argv))
        if "screenshot" in argv:
            raise subprocess.CalledProcessError(1, list(argv))

    with pytest.raises(subprocess.CalledProcessError):
        tools._shoot_pages(
            [""], Path("/out"), "http://x", "/usr/bin/agent-browser", fail_on_screenshot
        )

    assert calls[-1][1] == "close", (
        f"the session should be closed on the way out; last call was {calls[-1]!r}"
    )


def test_a_failure_to_close_the_session_does_not_mask_the_real_error() -> None:
    """The page failure is what the reader needs, not the cleanup's complaint."""

    def fail_everything(argv: cabc.Sequence[str]) -> None:
        raise subprocess.CalledProcessError(2, list(argv))

    with pytest.raises(subprocess.CalledProcessError) as caught:
        tools._shoot_pages(
            [""], Path("/out"), "http://x", "/usr/bin/agent-browser", fail_everything
        )

    assert "close" not in caught.value.cmd, (
        f"the surfaced error should be the page's, not the cleanup's; got "
        f"{caught.value.cmd!r}"
    )


def test_every_page_is_shot_at_every_width() -> None:
    """A width that quietly captured nothing would look like a clean run."""
    calls: list[list[str]] = []
    tools._shoot_pages(
        ["", "install/"],
        Path("/out"),
        "http://x",
        "/usr/bin/agent-browser",
        lambda argv: calls.append(list(argv)),
    )

    shots = [argv[2] for argv in calls if argv[1] == "screenshot"]
    out_dir = Path("/out")
    expected = [
        str(out_dir / f"{slug}@{width}.png")
        for width in tools.SCREENSHOT_WIDTHS
        for slug in (paths._slug(""), paths._slug("install/"))
    ]
    assert shots == expected, f"expected {expected!r}, got {shots!r}"


def test_a_missing_tool_names_itself_rather_than_failing_obscurely() -> None:
    """`FileNotFoundError` from deep inside subprocess helps nobody."""
    with pytest.raises(SystemExit) as caught:
        tools._tool("definitely-not-a-real-tool-name")
    assert "definitely-not-a-real-tool-name" in str(caught.value.code), (
        f"the message should name the missing tool; got {caught.value.code!r}"
    )


def test_capture_lays_pages_out_at_the_viewport_it_was_given(tmp_path: Path) -> None:
    """A phone width proves the narrow media queries; the default is the desktop."""
    calls, run, read = _recording_browser(tmp_path)
    tools._capture_pages(
        [""],
        tmp_path,
        "http://x",
        "/usr/bin/agent-browser",
        run,
        read,
        "netsuke",
        (360, 800),
    )
    assert calls[0][1:5] == ["set", "viewport", "360", "800"], calls[0]
    written = json.loads((tmp_path / "__home.json").read_text())
    assert written["meta"]["viewport"] == {"width": 360, "height": 800}
