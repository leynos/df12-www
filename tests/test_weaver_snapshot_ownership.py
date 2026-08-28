"""Knowing whose server answered.

A reply on a port says something is listening, not that it is this run's. An
unrelated server — another worktree's, another user's — answers a readiness
poll just as readily, and its pages would be captured and reported as this
branch's work.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import threading
import typing as typ
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from tests.support.weaver_harness import load

REPO_ROOT = Path(__file__).resolve().parents[1]

# Stands in for whatever goes wrong between taking a lock and the work
# finishing. Named so a `pytest.raises` block stays one statement.
_MID_START_FAILURE = "the port was occupied"

# A port number for the messages these tests read back. Nothing binds it.
PORT = 8099

serving = load("weaver_snapshot_serving")
ownership = load("weaver_snapshot_ownership")


def test_the_ownership_marker_is_served_and_then_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The marker has to be reachable while serving and gone afterwards."""
    public = tmp_path / "public"
    public.mkdir()
    monkeypatch.setattr(ownership, "REPO_ROOT", tmp_path)

    with ownership._ownership_marker() as marker:
        placed = public / marker
        assert placed.is_file(), f"expected the marker at {placed}"
        assert placed.read_text(encoding="utf-8") == marker, (
            "the marker's contents name it, so a server that truncates or "
            "rewrites files cannot pass the check by accident"
        )

    assert not placed.exists(), f"{placed} was left behind in the served tree"


def test_two_runs_are_given_different_ownership_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shared name would let either run's server satisfy the other's check."""
    public = tmp_path / "public"
    public.mkdir()
    monkeypatch.setattr(ownership, "REPO_ROOT", tmp_path)

    with (
        ownership._ownership_marker() as first,
        ownership._ownership_marker() as second,
    ):
        assert first != second, f"both runs were given {first!r}"


@contextlib.contextmanager
def _serving(directory: Path) -> cabc.Iterator[str]:
    """Serve ``directory`` on a throwaway port for the duration of the context.

    `shutdown` stops `serve_forever`'s loop but leaves the listening socket
    open; only `server_close` releases it. Without both, each of these tests
    leaks a socket, and the next one can be handed a port the previous
    server's thread has not finished letting go of. Joining the thread is what
    makes "finished" true rather than probable.

    Yields
    ------
    str
        The origin it is listening on, without a trailing slash.
    """
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(directory)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        serving.join(timeout=10)


def test_another_worktree_s_server_on_the_port_is_refused(tmp_path: Path) -> None:
    """Refuse a server that answers on the port but serves another tree.

    The startup lock is keyed on the user id, so two users racing for one port
    are not serialized by it — deliberately, since a sticky `/tmp` would make
    another user's lock file unopenable. And a running child says only that
    *something* of ours is alive, not that it is what answered. A server
    belonging to another worktree answers a readiness poll perfectly well and
    would have its pages captured as this branch's work.

    A lock cannot catch this and liveness cannot detect it; fetching a marker
    only this run knows the name of settles it.
    """
    theirs = tmp_path / "their-public"
    theirs.mkdir()
    (theirs / "index.html").write_text("<html>not ours</html>", encoding="utf-8")
    with _serving(theirs) as base, pytest.raises(SystemExit) as caught:
        ownership._confirm_ownership(
            base, "weaver-snapshot-deadbeef.txt", PORT, "on starting"
        )

    message = str(caught.value.code)
    assert "8099" in message, f"the message should name the port; got {message!r}"
    assert "other tree" in message, (
        f"the message should say whose tree is being served; got {message!r}"
    )


def test_our_own_server_passes_the_ownership_check(tmp_path: Path) -> None:
    """The check must not refuse the server it was meant to accept."""
    ours = tmp_path / "public"
    ours.mkdir()
    marker = "weaver-snapshot-0123456789abcdef.txt"
    (ours / marker).write_text(marker, encoding="utf-8")
    with _serving(ours) as base:
        ownership._confirm_ownership(base, marker, PORT, "on starting")


def test_a_server_that_returns_the_wrong_marker_is_refused(tmp_path: Path) -> None:
    """A tree that happens to hold that name is still not this run's tree."""
    theirs = tmp_path / "public"
    theirs.mkdir()
    marker = "weaver-snapshot-0123456789abcdef.txt"
    (theirs / marker).write_text("something else entirely", encoding="utf-8")
    with _serving(theirs) as base, pytest.raises(SystemExit) as caught:
        ownership._confirm_ownership(base, marker, PORT, "on starting")

    assert "another server" in str(caught.value.code), (
        f"expected the mismatch to be reported; got {caught.value.code!r}"
    )
