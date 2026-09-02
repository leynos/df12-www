"""Getting a port, serving the tree on it, and stopping again.

The port has to be one nothing else holds, the server has to come up as
itself, and a start that fails must not leave a child holding the port for the
next run to trip over.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import socket
import typing as typ

import pytest

from tests.support.weaver_harness import load

if typ.TYPE_CHECKING:
    from pathlib import Path

# Stands in for whatever goes wrong between taking a lock and the work
# finishing. Named so a `pytest.raises` block stays one statement.
_MID_START_FAILURE = "the port was occupied"

# A port number for the messages these tests read back. Nothing binds it.
PORT = 8099

locking = load("weaver_snapshot_locking")
paths = load("weaver_snapshot_paths")
process = load("weaver_snapshot_process")
serving = load("weaver_snapshot_serving")


@pytest.mark.parametrize(
    ("page", "slug"),
    [
        ("", "__home"),
        ("/", "__home"),
        ("install/", "install"),
        ("commands/act/", "commands__act"),
        # A page whose directory carries an underscore must not flatten onto
        # the stem a nested page would produce.
        ("what_next/", "what_unext"),
        ("what/next/", "what__next"),
    ],
)
def test_a_page_path_becomes_a_flat_filename_stem(page: str, slug: str) -> None:
    """Snapshots sit in one directory, so the slug carries the whole path."""
    assert paths._slug(page) == slug, (
        f"{page!r} should slug to {slug!r}, got {paths._slug(page)!r}"
    )


def test_the_snapshot_port_refuses_to_borrow_someone_else_s_server() -> None:
    """Polling a port someone else holds would snapshot their pages, not ours."""
    # `_served` checks for the server binary before it looks at the port, so
    # without `bun install` this would pass on the wrong SystemExit: the
    # message would name the missing binary and the port assertion below would
    # fail for a reason that has nothing to do with the behaviour under test.
    if not paths.HTTP_SERVER.is_file():  # pragma: no cover - env guard
        pytest.skip(
            f"{paths.HTTP_SERVER} is missing; run 'bun install' to "
            "exercise the port guard"
        )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as squatter:
        squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        squatter.bind(("127.0.0.1", 0))
        squatter.listen(1)
        port = squatter.getsockname()[1]

        with pytest.raises(SystemExit) as caught, serving._served(port):
            pass  # pragma: no cover - the context must not be entered

    assert str(port) in str(caught.value.code), (
        f"the message should name the occupied port; got {caught.value.code!r}"
    )


def test_the_port_is_probed_with_the_startup_lock_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Probing outside the lock is the check-then-act the lock exists to remove.

    If the probe ran before the lock were taken, two runs could still both
    find the port free and both go on to spawn — the ordering is the whole
    mechanism, so it is asserted rather than assumed.
    """
    lock = tmp_path / "port.lock"
    monkeypatch.setattr(locking, "_lock_path", lambda _port: lock)

    held: list[bool] = []

    def probe(_port: int) -> None:
        """Observe whether the lock is held, then stop the start."""
        # An exclusive lock cannot be taken twice, so failing to take it here
        # is how holding it is observed.
        with lock.open("r+", encoding="utf-8") as rival:
            try:
                fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                # Only contention proves the lock is held; anything else —
                # ENOLCK, a bad descriptor — is a broken observation, not
                # evidence, and must fail the test rather than pass it.
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                held.append(True)
            else:
                fcntl.flock(rival, fcntl.LOCK_UN)
                held.append(False)
        message = "stop before spawning anything"
        raise SystemExit(message)

    monkeypatch.setattr(serving, "_refuse_occupied_port", probe)

    with pytest.raises(SystemExit):
        serving._start_server(8099, "weaver-snapshot-deadbeef.txt")

    assert held == [True], (
        "the port must be probed while the startup lock is held, or two runs "
        f"can still interleave; observed {held!r}"
    )


class _Stoppably:
    """A launched child that records whether it was told to stand down."""

    def __init__(self) -> None:
        """Start not yet stopped."""
        self.stopped = False

    def poll(self) -> int | None:
        """Report still running."""
        return None

    def terminate(self) -> None:
        """Record the request to stop."""
        self.stopped = True

    def kill(self) -> None:
        """Record the insistence, the same way."""
        self.stopped = True

    def wait(self, timeout: int | None = None) -> int:
        """Stand down immediately."""
        del timeout
        return 0


def test_the_whole_startup_sequence_runs_with_the_lock_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Probe, spawn, and readiness wait are the check-then-act; all under lock.

    Asserting only the probe would let the spawn or the readiness wait drift
    outside the lock unnoticed, and either would reopen the interleaving the
    lock exists to remove: two runs both finding the port free, or one run's
    readiness poll answered by the other's server.
    """
    lock = tmp_path / "port.lock"
    monkeypatch.setattr(locking, "_lock_path", lambda _port: lock)

    held: dict[str, bool] = {}

    def observed(stage: str) -> None:
        """Record whether the startup lock is held at this stage."""
        # An exclusive lock cannot be taken twice, so failing to take it here
        # is how holding it is observed.
        with lock.open("r+", encoding="utf-8") as rival:
            try:
                fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                # Only contention proves the lock is held; anything else is a
                # broken observation and must fail the test.
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                held[stage] = True
            else:
                fcntl.flock(rival, fcntl.LOCK_UN)
                held[stage] = False

    child = _Stoppably()

    def launch(_argv: object) -> _Stoppably:
        """Observe the lock at the spawn, then hand back the stand-in."""
        observed("launch")
        return child

    monkeypatch.setattr(
        serving, "_refuse_occupied_port", lambda _port: observed("probe")
    )
    monkeypatch.setattr(
        serving, "_await_server", lambda *_a, **_k: observed("readiness")
    )
    monkeypatch.setattr(
        serving, "_confirm_ownership", lambda *_a, **_k: observed("confirm")
    )

    server = serving._start_server(8099, "weaver-snapshot-deadbeef.txt", launch=launch)

    assert server is child, "the started server should be handed back as-is"
    assert held == {
        "probe": True,
        "launch": True,
        "readiness": True,
        "confirm": False,
    }, (
        "the probe, the spawn, and the readiness wait must all run under the "
        "startup lock, and only the ownership fetch after its release; "
        f"observed {held!r}"
    )
    assert not child.stopped, "a clean start should not stop its own server"


def test_ownership_is_confirmed_after_the_startup_lock_is_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lock covers the check-then-act, not the blocking ownership fetch.

    Once this run's server is answering, a contender reaching the probe is
    refused whether the lock is held or not — so holding it through a
    blocking HTTP request only makes the loser of the race wait longer for
    the same refusal.
    """
    lock = tmp_path / "port.lock"
    monkeypatch.setattr(locking, "_lock_path", lambda _port: lock)

    held: list[bool] = []

    def confirm(_base: str, _marker: str, _port: int, _when: str) -> None:
        """Observe whether the lock is still held at confirmation."""
        # An exclusive lock cannot be taken twice, so taking it here is how
        # its release is observed.
        with lock.open("r+", encoding="utf-8") as rival:
            try:
                fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                # Only contention proves the lock is held; anything else —
                # ENOLCK, a bad descriptor — is a broken observation, not
                # evidence, and must fail the test rather than pass it.
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                held.append(True)
            else:
                fcntl.flock(rival, fcntl.LOCK_UN)
                held.append(False)

    monkeypatch.setattr(serving, "_refuse_occupied_port", lambda _port: None)
    monkeypatch.setattr(serving, "_await_server", lambda *_a, **_k: None)
    monkeypatch.setattr(serving, "_confirm_ownership", confirm)

    child = _Stoppably()
    server = serving._start_server(
        8099, "weaver-snapshot-deadbeef.txt", launch=lambda _argv: child
    )

    assert server is child, "the started server should be handed back as-is"
    assert held == [False], (
        "ownership should be confirmed after the startup lock is released; "
        f"observed {held!r}"
    )
    assert not child.stopped, "a server that confirmed as ours was stopped"


def test_a_server_that_fails_the_ownership_check_is_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A child that answered as somebody else must not be left on the port."""

    def refuse(_base: str, _marker: str, _port: int, _when: str) -> None:
        """Refuse the way a foreign server on the port is refused."""
        message = "another server has it"
        raise SystemExit(message)

    monkeypatch.setattr(serving, "_refuse_occupied_port", lambda _port: None)
    monkeypatch.setattr(serving, "_await_server", lambda *_a, **_k: None)
    monkeypatch.setattr(serving, "_confirm_ownership", refuse)

    child = _Stoppably()
    with pytest.raises(SystemExit, match="another server"):
        serving._start_server(
            8099,
            "weaver-snapshot-deadbeef.txt",
            named=False,
            launch=lambda _argv: child,
        )

    assert child.stopped, (
        "a failed ownership check should stop the child, or the next run's "
        "probe refuses to start because of it"
    )


def test_an_unnamed_port_is_asked_for_rather_than_assumed() -> None:
    """Two runs cannot contend over a port the kernel picked for each of them."""
    first = serving._resolve_port(0)
    second = serving._resolve_port(0)

    for port in (first, second):
        assert port > 0, f"the kernel should have named a port; got {port!r}"
    named = 8099
    assert serving._resolve_port(named) == named, (
        "a port named explicitly should be honoured as given"
    )


def test_choosing_a_port_is_separable_from_obtaining_one() -> None:
    """The decision is pure; only the allocator touches the network.

    Splitting them is what lets the decision be checked without a socket — and
    what keeps the one function that can fail for reasons outside this process
    at the edge, where the command composes it.
    """
    allocated = 4321
    asked: list[int] = []

    def allocator() -> int:
        """Hand out the fixed port, recording the ask."""
        asked.append(allocated)
        return allocated

    assert serving._resolve_port(0, allocator) == allocated, (
        "an unnamed port should come from the allocator it was given"
    )
    assert asked == [allocated], (
        f"the allocator should be called exactly once; got {asked}"
    )

    asked.clear()
    assert serving._resolve_port(PORT, allocator) == PORT, (
        "a named port should be honoured without allocating anything"
    )
    assert asked == [], (
        "a named port should not have asked the allocator for one at all"
    )


def test_a_machine_with_no_free_port_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one environmental failure in port selection should not be a traceback."""

    class _Refusing:
        """A socket that cannot be bound, as an exhausted machine's would be."""

        def __enter__(self) -> _Refusing:
            """Hand the socket stand-in back."""
            return self

        def __exit__(self, *_exc: object) -> None:
            """Have nothing to close."""
            return

        def bind(self, _address: tuple[str, int]) -> None:
            """Refuse the bind, as a machine out of ports would."""
            message = "Address family not supported"
            raise OSError(message)

    monkeypatch.setattr(serving.socket, "socket", lambda *_a, **_k: _Refusing())

    with pytest.raises(SystemExit) as caught:
        serving._allocate_port()

    assert "--port" in str(caught.value.code), (
        f"the message should name the way out; got {caught.value.code!r}"
    )


def test_the_server_is_offered_only_to_this_machine() -> None:
    """`http-server` defaults to 0.0.0.0, which publishes the tree to the LAN.

    The tree being served is an unreleased sub-site mid-migration, and every
    request this script makes is to loopback, so there is nothing to gain from
    the default and a disclosure to lose. Verified against the packaged
    binary's own help text, which documents `-a` as defaulting to `0.0.0.0`.
    """
    argv = serving._server_argv(8099)

    assert "-a" in argv, f"no address was pinned, so the default applies: {argv}"
    assert argv[argv.index("-a") + 1] == "127.0.0.1", (
        f"the address should be loopback; got {argv}"
    )


def test_the_server_argv_still_names_the_port_and_the_tree() -> None:
    """Pinning the address must not have displaced anything else."""
    argv = serving._server_argv(9123)

    assert argv[0] == str(paths.HTTP_SERVER), f"wrong executable: {argv}"
    assert "public" in argv, f"the published tree should be served: {argv}"
    assert argv[argv.index("-p") + 1] == "9123", f"the port should be passed: {argv}"


def test_a_page_list_is_taken_from_the_tree_it_is_given(tmp_path: Path) -> None:
    """The traversal is passed its root, so it can be exercised on a real one."""
    for page in ("", "install", "commands/act"):
        directory = tmp_path / page if page else tmp_path
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.html").write_text("<html></html>", encoding="utf-8")

    assert paths._page_paths(tmp_path) == ["", "commands/act/", "install/"], (
        f"got {paths._page_paths(tmp_path)!r}"
    )


def test_an_unreadable_corner_of_the_tree_stops_the_capture(tmp_path: Path) -> None:
    """A short page list is worse than a failure: it compares clean.

    `rglob` swallows an `OSError` on a descendant and yields nothing further
    beneath it, so a directory this process cannot read would quietly shorten
    the list. The pages under it would be absent from the capture and absent
    from the diff, which reads as "no differences" rather than "not looked at".
    """
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    closed = tmp_path / "closed"
    closed.mkdir()
    (closed / "index.html").write_text("<html></html>", encoding="utf-8")
    closed.chmod(0o000)
    try:
        if os.getuid() == 0:  # pragma: no cover - root ignores the mode
            pytest.skip("running as root, which can read the directory anyway")
        with pytest.raises(SystemExit) as caught:
            paths._page_paths(tmp_path)
    finally:
        closed.chmod(0o755)

    assert "could not be read" in str(caught.value.code), (
        f"the message should say what failed; got {caught.value.code!r}"
    )


def test_the_port_probe_binds_the_way_the_server_will() -> None:
    """A stricter probe refuses a port the server would have taken.

    `http-server` sets SO_REUSEADDR, so it binds a port whose last connection
    is still in TIME_WAIT. Without the same option the probe fails where the
    server would succeed, and a capture is refused for a minute after the last
    one on a port nothing is really using.

    The state has to be produced rather than assumed: closing a listening
    socket that never accepted anything does not enter TIME_WAIT. A connection
    has to be made and closed from the listening side first.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    accepted, _peer = listener.accept()
    accepted.close()  # the listening side closes first, so its end waits
    client.close()
    listener.close()

    # Precondition: this is the state the probe has to tolerate. Without it
    # the test would pass on a port that is simply free.
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as bare,
        # `OSError` unqualified, because the assertion below is on the
        # errno rather than the message, which the C library localizes.
        pytest.raises(OSError) as refused,  # noqa: PT011 - checked by errno below
    ):
        bare.bind(("127.0.0.1", port))

    # `EADDRINUSE` rather than the message, which the C library localizes.
    assert refused.value.errno == errno.EADDRINUSE, (
        f"expected the port to be refused as in use; got errno "
        f"{refused.value.errno} ({refused.value})"
    )

    serving._refuse_occupied_port(port)


def test_a_kernel_assigned_port_leaves_no_lock_file_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lock keyed on an ephemeral port is one file per run, for ever.

    The lock exists to serialize two runs contending for a port somebody named.
    A port the kernel just handed out cannot be contended — nothing else was
    given it — so locking it buys nothing and leaves a file in the shared temp
    directory that no later run will ever look at again.
    """
    locks: list[int] = []

    def record(port: int) -> contextlib.AbstractContextManager[None]:
        """Record the port the lock was asked for."""
        locks.append(port)
        return contextlib.nullcontext()

    monkeypatch.setattr(serving, "_startup_lock", record)

    def stop_before_spawning(_port: int) -> None:
        """Stop the start before anything is spawned."""
        raise SystemExit(_MID_START_FAILURE)

    monkeypatch.setattr(serving, "_refuse_occupied_port", stop_before_spawning)

    with pytest.raises(SystemExit):
        serving._start_server(54321, "marker.txt", named=False)
    assert locks == [], f"an unnamed port should not be locked; locked {locks}"

    with pytest.raises(SystemExit):
        serving._start_server(8099, "marker.txt", named=True)
    assert locks == [8099], f"a named port should still be locked; locked {locks}"


def test_the_default_port_is_treated_as_unnamed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_served` decides from what the caller asked for, not what it resolved to."""
    seen: dict[str, object] = {}

    def start(_port: int, _marker: str, *, named: bool) -> object:
        """Record how the port was classified and stop there."""
        seen["named"] = named
        message = "far enough"
        raise SystemExit(message)

    monkeypatch.setattr(serving, "_start_server", start)
    monkeypatch.setattr(serving, "_resolve_port", lambda port, *_a: port or 54321)

    for requested, expected in ((0, False), (8099, True)):
        with pytest.raises(SystemExit), serving._served(requested):
            pass  # pragma: no cover - the server never starts
        assert seen["named"] is expected, (
            f"--port {requested} should be treated as named={expected}"
        )
