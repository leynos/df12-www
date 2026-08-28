"""The commands themselves, and `diff`'s report.

The helpers are covered one by one elsewhere. These check that a command wires
them together: the right tool, the right port, the right staging suffix, and
one output per page.
"""

from __future__ import annotations

import contextlib
import subprocess
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
from pathlib import Path

import pytest

from tests.support.weaver_harness import load, write_snapshot

REPO_ROOT = Path(__file__).resolve().parents[1]

# Stands in for whatever goes wrong between taking a lock and the work
# finishing. Named so a `pytest.raises` block stays one statement.
_MID_START_FAILURE = "the port was occupied"

# A port number for the messages these tests read back. Nothing binds it.
PORT = 8099

commands = load("weaver_snapshot")
paths = load("weaver_snapshot_paths")
tools = load("weaver_snapshot_tools")


def test_diff_reports_no_differences_and_exits_cleanly(tmp_path: Path) -> None:
    """Two identical captures are not a change, so nothing should be raised."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    write_snapshot(before, "home", color="rgb(1, 2, 3)")
    write_snapshot(after, "home", color="rgb(1, 2, 3)")

    commands.diff(before, after)


def test_diff_exits_non_zero_when_a_page_changed(tmp_path: Path) -> None:
    """The exit status is what lets this gate a milestone."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    write_snapshot(before, "home", color="rgb(1, 2, 3)")
    write_snapshot(after, "home", color="rgb(9, 9, 9)")

    with pytest.raises(SystemExit) as caught:
        commands.diff(before, after)
    assert caught.value.code == 1, (
        f"a changed page should exit 1, not {caught.value.code!r}"
    )


def test_diff_ignores_a_change_the_normalization_calls_incidental(
    tmp_path: Path,
) -> None:
    """The same colour in two notations is not a difference worth reporting."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    write_snapshot(before, "home", color="rgb(1, 2, 3)")
    write_snapshot(after, "home", color="rgba(1, 2, 3, 1)")

    commands.diff(before, after)


def test_a_page_missing_from_the_candidate_counts_as_a_difference(
    tmp_path: Path,
) -> None:
    """A page that stopped being published is a change, not an absence."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    write_snapshot(before, "home", color="rgb(1, 2, 3)")
    write_snapshot(before, "install", color="rgb(1, 2, 3)")
    write_snapshot(after, "home", color="rgb(1, 2, 3)")

    with pytest.raises(SystemExit) as caught:
        commands.diff(before, after)
    assert caught.value.code == 1, "a missing page should fail the comparison"


def test_a_page_only_in_the_candidate_counts_as_a_difference(
    tmp_path: Path,
) -> None:
    """A new page is as much a change as an altered one."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    write_snapshot(before, "home", color="rgb(1, 2, 3)")
    write_snapshot(after, "home", color="rgb(1, 2, 3)")
    write_snapshot(after, "install", color="rgb(1, 2, 3)")

    with pytest.raises(SystemExit) as caught:
        commands.diff(before, after)
    assert caught.value.code == 1, "a new page should fail the comparison"


def test_diff_says_so_rather_than_passing_on_an_empty_baseline(
    tmp_path: Path,
) -> None:
    """An empty baseline would otherwise compare zero pages and report success."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()

    with pytest.raises(SystemExit) as caught:
        commands.diff(before, after)
    assert "no snapshots" in str(caught.value.code), (
        f"expected a message naming the empty directory; got {caught.value.code!r}"
    )


def test_two_readers_take_a_pair_of_directories_the_same_way_round(
    tmp_path: Path,
) -> None:
    """Opposite orders would let two diffs each hold what the other wants."""
    first = tmp_path / "aaa"
    second = tmp_path / "zzz"
    for directory in (first, second):
        directory.mkdir()

    assert commands._reading_order(first, second) == commands._reading_order(
        second, first
    ), "the order must not depend on which argument the directory arrived as"


def test_one_directory_named_twice_is_locked_once(tmp_path: Path) -> None:
    """`flock` on the same file twice from one process would block forever."""
    same = tmp_path / "snapshots"
    same.mkdir()

    assert commands._reading_order(same, same) == [same.resolve()], (
        f"got {commands._reading_order(same, same)!r}"
    )


@contextlib.contextmanager
def _driven(
    monkeypatch: pytest.MonkeyPatch, pages: list[str], tools: dict[str, str]
) -> cabc.Iterator[dict[str, typ.Any]]:
    """Run a command with every outward seam replaced, and record what it did.

    The commands are the part nobody had exercised: their helpers are covered
    one by one, and `capture` end to end through a real browser, but nothing
    checked that a command wires its helpers together in the right order with
    the right arguments. A command that resolved the wrong tool, served the
    wrong port, or staged the wrong suffix would pass every existing test.

    Yields
    ------
    dict
        ``argv`` — every command the run would have executed; ``served`` — the
        ports the server was asked for, and whether it was stopped; ``staged``
        — the (directory, suffix) pairs staged.
    """
    record: dict[str, typ.Any] = {"argv": [], "served": [], "staged": [], "closed": []}

    @contextlib.contextmanager
    def served(port: int, *_args: object, **_kwargs: object) -> cabc.Iterator[str]:
        record["served"].append(port)
        try:
            yield "http://127.0.0.1:9999"
        finally:
            record["closed"].append(port)

    @contextlib.contextmanager
    def staged(out_dir: Path, suffix: str) -> cabc.Iterator[Path]:
        record["staged"].append((out_dir, suffix))
        staging = out_dir / ".staging"
        staging.mkdir(parents=True, exist_ok=True)
        yield staging

    monkeypatch.setattr(commands, "_served", served)
    monkeypatch.setattr(commands, "_staged", staged)
    monkeypatch.setattr(commands, "_page_paths", lambda: list(pages))
    monkeypatch.setattr(commands, "_tool", lambda name: tools[name])
    monkeypatch.setattr(
        commands, "_run_tool", lambda argv: record["argv"].append(list(argv))
    )
    yield record


def test_the_shots_command_wires_its_helpers_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`shots` is a public command and had no test of its own at all."""
    pages = ["", "install/"]
    with _driven(
        monkeypatch, pages, {"agent-browser": "/usr/bin/agent-browser"}
    ) as run:
        commands.shots(tmp_path / "out", port=8123)

    assert run["served"] == [8123], (
        f"the port the caller named should reach the server; got {run['served']}"
    )
    assert run["closed"] == [8123], "the server should be stopped on the way out"
    assert run["staged"] == [(tmp_path / "out", ".png")], (
        f"screenshots should stage as .png; got {run['staged']}"
    )

    executables = {argv[0] for argv in run["argv"]}
    assert executables == {"/usr/bin/agent-browser"}, (
        f"every command should be the resolved browser; got {executables}"
    )

    shots = [argv[2] for argv in run["argv"] if argv[1] == "screenshot"]
    expected = [
        f"{tmp_path / 'out' / '.staging'}/{paths._slug(page)}@{width}.png"
        for width in tools.SCREENSHOT_WIDTHS
        for page in pages
    ]
    assert shots == expected, (
        f"expected one screenshot per page at every width, into the staging "
        f"directory; got {shots}"
    )


def test_the_capture_command_wires_its_helpers_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same for `capture`, whose only other coverage needs a real browser."""
    pages = ["", "commands/act/"]
    with _driven(monkeypatch, pages, {"bun": "/usr/bin/bun"}) as run:
        commands.capture(tmp_path / "out", port=8124)

    assert run["served"] == [8124], f"the named port should be served; got {run}"
    assert run["closed"] == [8124], f"and then stopped; got {run}"
    assert run["staged"] == [(tmp_path / "out", ".json")], (
        f"captures should stage as .json; got {run['staged']}"
    )

    outputs = [argv[argv.index("--output") + 1] for argv in run["argv"]]
    expected = [
        f"{tmp_path / 'out' / '.staging'}/{paths._slug(page)}.json" for page in pages
    ]
    assert outputs == expected, (
        f"expected one snapshot per page, into the staging directory; got {outputs}"
    )
    assert all(argv[0] == "/usr/bin/bun" for argv in run["argv"]), (
        f"every command should run through the resolved bun; got {run['argv']}"
    )


def test_a_command_stops_its_server_even_when_a_page_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A browser that fails on page two must not strand the server on port one."""
    with _driven(monkeypatch, ["", "install/"], {"bun": "/usr/bin/bun"}) as run:

        def refuse(_argv: cabc.Sequence[str]) -> None:
            raise subprocess.CalledProcessError(1, "bun")

        monkeypatch.setattr(commands, "_run_tool", refuse)
        with pytest.raises(subprocess.CalledProcessError):
            commands.capture(tmp_path / "out", port=8125)

    assert run["closed"] == [8125], (
        f"the server should be stopped however the run ends; got {run['closed']}"
    )
