"""Knowing whose server answered.

A reply on a port says something is listening, not that it is this run's. An
unrelated server — another worktree's, another user's — answers a readiness
poll just as readily, and its pages would be captured and reported as this
branch's work.
"""

from __future__ import annotations

import contextlib
import email.message
import functools
import http.server
import threading
import typing as typ
import urllib.error
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from tests.support.weaver_harness import load

REPO_ROOT = Path(__file__).resolve().parents[1]


# A port number for the messages these tests read back. Nothing binds it.
PORT = 8099

ownership = load("weaver_snapshot_ownership")
process = load("weaver_snapshot_process")


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
def _running(
    handler: cabc.Callable[..., http.server.BaseHTTPRequestHandler],
) -> cabc.Iterator[str]:
    """Answer requests with ``handler`` on a throwaway port for the duration.

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
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        loop.join(timeout=10)
        # `join` returns on timeout as readily as on success, so the thread
        # has to be asked whether it actually stopped. A live one still holds
        # the port the next test will be handed.
        assert not loop.is_alive(), (
            "the serving thread did not stop, so its port is still held"
        )


@contextlib.contextmanager
def _serving(directory: Path) -> cabc.Iterator[str]:
    """Serve ``directory`` on a throwaway port for the duration of the context.

    Yields
    ------
    str
        The origin it is listening on, without a trailing slash.
    """
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(directory)
    )
    with _running(handler) as base:
        yield base


class _Quiet(http.server.BaseHTTPRequestHandler):
    """A request handler that does not narrate itself to stderr."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - the base class named it
        """Say nothing; the assertions speak for these servers."""


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


def test_an_ownership_check_reads_only_as_far_as_the_comparison_needs() -> None:
    """Whatever is on that port may serve a great deal; this reads a marker."""
    asked: list[tuple[str, int]] = []
    marker = "weaver-snapshot-0123456789abcdef.txt"

    def fetch(url: str, limit: int) -> str:
        """Record the ask and answer with the marker."""
        asked.append((url, limit))
        return marker

    ownership._confirm_ownership(
        "http://127.0.0.1:9999", marker, PORT, "on starting", fetch
    )

    assert asked == [(f"http://127.0.0.1:9999/{marker}", len(marker) + 1)], (
        f"expected one bounded read of the marker's own URL; got {asked}"
    )


def test_a_server_that_answers_with_something_else_is_refused() -> None:
    """A tree that happens to serve that path is still not this run's."""
    marker = "weaver-snapshot-0123456789abcdef.txt"

    def fetch(_url: str, _limit: int) -> str:
        """Answer with somebody else's page."""
        return "<!doctype html><title>somebody else</title>"

    with pytest.raises(SystemExit) as caught:
        ownership._confirm_ownership(
            "http://127.0.0.1:9999", marker, PORT, "on starting", fetch
        )

    assert "another server" in str(caught.value.code), (
        f"expected the mismatch to be reported; got {caught.value.code!r}"
    )


def test_a_server_that_does_not_answer_at_all_is_refused() -> None:
    """Nothing on the port is as disqualifying as the wrong thing on it."""

    def refuse(_url: str, _limit: int) -> str:
        """Refuse the connection outright."""
        message = "connection refused"
        raise OSError(message)

    with pytest.raises(SystemExit) as caught:
        ownership._confirm_ownership(
            "http://127.0.0.1:9999",
            "marker.txt",
            PORT,
            "after the capture",
            fetch=refuse,
        )

    message = str(caught.value.code)
    assert str(PORT) in message, f"the message should name the port; got {message!r}"
    assert "after the capture" in message, (
        f"the message should say when the check ran, since the two failures "
        f"mean different things; got {message!r}"
    )


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (OSError("D" * 4096), "connection_failed"),
        (
            urllib.error.HTTPError(
                "http://127.0.0.1:9999/marker.txt",
                302,
                "E" * 4096,
                email.message.Message(),
                None,
            ),
            "redirect_refused",
        ),
    ],
)
def test_an_ownership_failure_reports_its_category_and_nothing_it_was_told(
    failure: OSError, category: str
) -> None:
    """The message classifies the fetch failure without repeating its text.

    Whatever answered the marker's URL is untrusted — the check exists
    because of that — so its reason phrases have no place in the message;
    the chained exception keeps the detail for a traceback.
    """

    def hostile(_url: str, _limit: int) -> str:
        """Fail the way the untrusted responder chose to."""
        raise failure

    with pytest.raises(SystemExit) as caught:
        ownership._confirm_ownership(
            "http://127.0.0.1:9999", "marker.txt", PORT, "on starting", hostile
        )

    message = str(caught.value.code)
    assert category in message, (
        f"the message should classify the failure; got {message!r}"
    )
    assert "D" * 64 not in message, (
        "the message repeated text the untrusted responder chose"
    )
    assert "E" * 64 not in message, (
        "the message repeated the reason phrase the responder chose"
    )
    assert caught.value.__cause__ is failure, (
        "the refusal should chain from the fetch failure it classifies"
    )


def test_a_server_that_redirects_the_marker_is_refused_unfollowed() -> None:
    """A redirect must fail the check without the foreign server being asked.

    Whatever holds the port can answer the marker's URL with a ``Location``
    pointing at a server of its choosing — one happy to serve the right
    marker back. The default opener would follow it and the check would pass
    on that server's say-so; the run would then capture foreign content and
    report it as this branch's work.
    """
    marker = "weaver-snapshot-0123456789abcdef.txt"
    foreign_hits: list[str] = []

    class _ObligingForeigner(_Quiet):
        """Serves the correct marker, as an attacker's server would."""

        def do_GET(self) -> None:
            """Serve the marker, recording that the request arrived."""
            foreign_hits.append(self.path)
            body = marker.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _running(_ObligingForeigner) as foreign:

        class _Redirecting(_Quiet):
            def do_GET(self) -> None:
                """Answer with a redirect to the foreign server."""
                self.send_response(302)
                self.send_header("Location", f"{foreign}{self.path}")
                self.end_headers()

        with _running(_Redirecting) as base, pytest.raises(SystemExit) as caught:
            ownership._confirm_ownership(base, marker, PORT, "on starting")

    assert "other tree" in str(caught.value.code), (
        f"a redirect should fail the ownership check; got {caught.value.code!r}"
    )
    assert foreign_hits == [], (
        f"the redirect was followed and the foreign server consulted: {foreign_hits}"
    )


def test_the_readiness_probe_refuses_a_redirect() -> None:
    """The probe, too, only means anything if the asked URL itself answered.

    Belongs beside the ownership redirect test because it is the same
    property: no request this harness makes may be sent onward to a server
    the redirecting one chose.
    """

    class _Redirecting(_Quiet):
        def do_GET(self) -> None:
            """Answer with a redirect off the loopback."""
            self.send_response(302)
            self.send_header("Location", "http://192.0.2.1/weaver/")
            self.end_headers()

    with (
        _running(_Redirecting) as base,
        pytest.raises(OSError, match="not the server being checked") as caught,
    ):
        process._probe_url(f"{base}/weaver/")

    assert getattr(caught.value, "code", None) == http.HTTPStatus.FOUND, (
        f"the probe should fail on the redirect itself, not on what lies "
        f"beyond it; got {caught.value!r}"
    )
