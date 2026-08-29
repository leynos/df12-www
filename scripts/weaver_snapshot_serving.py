"""Serving the published tree on a loopback port, and knowing it came up.

Getting a port, refusing one somebody else holds, starting the server, waiting
for it, and stopping it again — including when the start fails, since a child
left holding a port is what stops the next run.
"""

from __future__ import annotations

import collections.abc as cabc
import contextlib
import socket
import typing as typ

from weaver_snapshot_locking import _startup_lock
from weaver_snapshot_ownership import _confirm_ownership, _ownership_marker
from weaver_snapshot_paths import HTTP_SERVER
from weaver_snapshot_process import Launcher, _await_server, _launch, _stop

if typ.TYPE_CHECKING:
    import subprocess


def _refuse_occupied_port(port: int) -> None:
    """Exit rather than serve on a port somebody else already holds.

    ``http-server`` exits 1 when it cannot bind, but the readiness poll would
    then connect to the *pre-existing* server and take it for the one just
    spawned. Probing first makes that deterministic for a foreign server;
    :func:`_startup_lock` makes it deterministic for another run of this
    script, which the probe alone cannot do.

    Parameters
    ----------
    port
        TCP port to test.

    Raises
    ------
    SystemExit
        If the port cannot be bound.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        # `http-server` sets SO_REUSEADDR, so it will bind a port left in
        # TIME_WAIT by the previous run. Without it here the probe is stricter
        # than the thing it is standing in for, and a capture refuses to start
        # for a minute after the last one on a port nothing is actually using.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            message = (
                f"port {port} is already in use, so the snapshot would capture "
                f"whatever is being served there rather than this worktree's "
                f"public/ ({exc}). Stop that server, or pass --port."
            )
            raise SystemExit(message) from exc


def _server_argv(port: int) -> list[str]:
    """Build the command that serves ``public/`` on one port.

    ``-a 127.0.0.1`` is the part worth stating outright. ``http-server``
    defaults its address to ``0.0.0.0``, so without it the published tree —
    an unreleased sub-site, mid-migration — is offered to every host that can
    reach this machine, for as long as a capture runs. Nothing in this script
    needs that: every request it makes is to loopback.

    Parameters
    ----------
    port
        TCP port to listen on.

    Returns
    -------
    list of str
        The full argv, fixed apart from the port.
    """
    return [
        str(HTTP_SERVER),
        "public",
        "-a",
        "127.0.0.1",
        "-p",
        str(port),
        "-c-1",
        "--silent",
    ]


# How a port is obtained when none was named. Injected rather than called
# directly so the decision about *which* port to serve on can be exercised
# without binding one, and so the one function that touches the network stays
# at the edge where the command composes its dependencies.
type PortAllocator = cabc.Callable[[], int]


def _allocate_port() -> int:
    """Ask the kernel for a loopback port nothing is listening on.

    This is the environmental half, and the only part of port selection that
    can fail for reasons outside this process.

    Returns
    -------
    int
        A port that was free a moment ago. The bind probe and the startup lock
        in :func:`_start_server` handle the gap between then and now.

    Raises
    ------
    SystemExit
        If a port cannot be obtained at all, which means the machine has no
        ephemeral ports left or loopback is unavailable.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])
    except OSError as exc:
        message = (
            f"no loopback port could be obtained ({exc}); pass --port to name "
            f"one explicitly"
        )
        raise SystemExit(message) from exc


def _resolve_port(port: int, allocate: PortAllocator = _allocate_port) -> int:
    """Turn a requested port into the one to serve on.

    Zero means "whatever the kernel has spare", which is the default and the
    reason two concurrent runs normally have nothing to contend over at all.
    A fixed port is honoured as given, since reaching the served tree from a
    browser by hand needs a number known in advance.

    Parameters
    ----------
    port
        The requested port, or ``0``.
    allocate
        How to obtain a port when none was named. Injected so the decision can
        be tested without a socket.

    Returns
    -------
    int
        A port to serve on.
    """
    return port or allocate()


def _start_server(
    port: int,
    marker: str,
    *,
    named: bool = True,
    launch: Launcher = _launch,
) -> subprocess.Popen[bytes]:
    """Acquire the port and return a server already answering on it, as itself.

    Parameters
    ----------
    port
        TCP port to listen on.
    marker
        The ownership marker to fetch back once it answers.
    named
        Whether the caller asked for this port by number. A kernel-assigned
        one needs no startup lock, and keying a lock file on it would leave
        one behind per run.
    launch
        How to start the server process. Injected so the argv a start would
        use can be checked without a child process.

    Returns
    -------
    subprocess.Popen
        The running server. The caller owns stopping it.

    Raises
    ------
    SystemExit
        If the startup lock cannot be taken, the port is occupied, or the
        server does not come up as itself.
    """
    # The lock serializes two runs contending for one *named* port. A port the
    # kernel just handed out is not contended — nothing else can have been
    # given it — so locking it buys nothing and leaves a file behind in the
    # shared temp directory for every run ever made.
    with _startup_lock(port) if named else contextlib.nullcontext():
        _refuse_occupied_port(port)
        server = launch(_server_argv(port))
        try:
            base = f"http://127.0.0.1:{port}"
            _await_server(server, base, port)
            _confirm_ownership(base, marker, port, "on starting")
        except BaseException:
            # Otherwise a failed start leaves a child holding the port, and
            # the next run's probe refuses to start because of it.
            _stop(server)
            raise
        return server


@contextlib.contextmanager
def _served(port: int, allocate: PortAllocator = _allocate_port) -> cabc.Iterator[str]:
    """Serve ``public/`` locally for the duration of the context.

    Parameters
    ----------
    port
        TCP port to listen on, or ``0`` to be given a free one.
    allocate
        How to obtain that free one. The default binds a loopback socket; a
        caller with its own port source can pass one instead.

    Yields
    ------
    str
        The base URL of the running server, without a trailing slash.

    Raises
    ------
    SystemExit
        If the server binary is absent, if another run holds the startup lock,
        if the port is already occupied, if the server exits while starting,
        if it does not accept connections within roughly ten seconds, or if
        the server answering on the port turns out not to be this run's —
        either when it comes up or once the capture is finished.
    """
    if not HTTP_SERVER.is_file():
        message = "node_modules/.bin/http-server is missing; run 'bun install'"
        raise SystemExit(message)

    resolved = _resolve_port(port, allocate)
    base = f"http://127.0.0.1:{resolved}"
    with _ownership_marker() as marker:
        server = _start_server(resolved, marker, named=bool(port))
        try:
            yield base
            # Ownership is checked again on the way out, so a capture is only
            # accepted if the same server answered throughout it. Nothing
            # stops a stopped-and-replaced server from taking the port
            # mid-run, and the pages captured after that point would be its.
            _confirm_ownership(base, marker, resolved, "after the capture")
        finally:
            _stop(server)
