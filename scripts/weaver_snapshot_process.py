"""Starting a server process, waiting for it, and stopping it again.

The half of serving that is about a child process rather than a port: what
argv it is launched with, how the wait for readiness is paced, and the
escalation from `terminate` to `kill` when it will not stand down.

Every outward dependency here is a parameter with a production default —
the clock, the HTTP probe, the launcher — so the retry counts, the timing and
the argv can be checked without a socket, a sleep or a child process.
"""

from __future__ import annotations

import contextlib
import subprocess
import typing as typ
import urllib.request

from weaver_snapshot_clock import SYSTEM_CLOCK, Clock
from weaver_snapshot_paths import REPO_ROOT

if typ.TYPE_CHECKING:
    import collections.abc as cabc


# How the readiness poll asks whether the server is answering yet. Raises when
# it is not, which is the only outcome the poll acts on.
type Probe = cabc.Callable[[str], None]


# How a server process is started. Returns something that can be polled,
# terminated and waited on — a `subprocess.Popen` in production.
type Launcher = cabc.Callable[[cabc.Sequence[str]], "subprocess.Popen[bytes]"]


# How many times the readiness poll asks before giving up, and how long it
# waits between attempts. Fifty attempts at 0.2s is roughly ten seconds.
READINESS_ATTEMPTS = 50


READINESS_POLL_SECONDS = 0.2


# How long to give a server to stand down, at each of the two attempts.
STOP_TIMEOUT_SECONDS = 10


def _probe_url(url: str) -> None:
    """Ask a URL for a response, raising if it does not give one.

    Parameters
    ----------
    url
        A loopback URL to request.

    Raises
    ------
    OSError
        If the request fails, which the readiness poll reads as "not yet".
    """
    with urllib.request.urlopen(url, timeout=1):  # noqa: S310 - literal loopback URL
        return


def _launch(argv: cabc.Sequence[str]) -> subprocess.Popen[bytes]:
    """Start a server process from a fixed argv.

    Parameters
    ----------
    argv
        The command, already resolved to an absolute executable.

    Returns
    -------
    subprocess.Popen
        The running process.
    """
    return subprocess.Popen(  # noqa: S603 - fixed argv, no shell, no user input
        list(argv),
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class _Stoppable(typ.Protocol):
    """What stopping a server needs from the process running it.

    Three methods, not the whole of `subprocess.Popen`. Stating that is what
    lets `_stop` be checked against a stand-in whose `wait` times out on
    demand, rather than against a real child that has to be made to hang.
    """

    def terminate(self) -> None:
        """Ask the process to stop."""
        ...  # pragma: no cover - a protocol has no body

    def kill(self) -> None:
        """Insist."""
        ...  # pragma: no cover - a protocol has no body

    def wait(self, timeout: int | None = None) -> int:
        """Wait for it to go, raising `TimeoutExpired` if it does not."""
        ...  # pragma: no cover - a protocol has no body


class _Pollable(typ.Protocol):
    """The one thing waiting on a server needs from the process running it.

    Annotating the parameter as ``subprocess.Popen[bytes]`` overstated it: the
    wait asks whether the child is still running and nothing else. Narrowing
    the contract to that is what lets it be checked against a stand-in that
    reports a chosen sequence of exits, rather than against a real process
    whose timing a test cannot control.
    """

    def poll(self) -> int | None:
        """Return the exit status, or ``None`` while the process runs."""
        ...  # pragma: no cover - a protocol has no body


def _await_server(
    server: _Pollable,
    base: str,
    port: int,
    clock: Clock = SYSTEM_CLOCK,
    probe: Probe = _probe_url,
) -> None:
    """Wait until the spawned server answers, and confirm it is the one that did.

    Parameters
    ----------
    server
        The freshly spawned ``http-server`` process, or anything that reports
        whether it is still running.
    base
        The origin it should be listening on.
    port
        The port, for the messages.
    clock
        How to wait between attempts. Injected so the retry behaviour can be
        checked without waiting through it.
    probe
        How to ask whether the server is answering. Injected so readiness can
        be checked without an HTTP request.

    Raises
    ------
    SystemExit
        If the child exits while starting, if it does not answer within
        roughly ten seconds, or if it is no longer running once something on
        its port has answered — in which case the answer came from something
        else, and this run must not snapshot it.
    """
    # Poll rather than sleeping a fixed interval, so a slow start does not
    # silently yield a directory full of failed captures.
    for _ in range(READINESS_ATTEMPTS):
        # A server that has already exited will never answer, and anything
        # that does answer on its port is not it.
        if (status := server.poll()) is not None:
            message = (
                f"http-server exited with status {status} while starting on "
                f"port {port}; it may have lost a race to bind it"
            )
            raise SystemExit(message)
        try:
            probe(f"{base}/weaver/")
        except OSError:
            clock.sleep(READINESS_POLL_SECONDS)
        else:
            break
    else:
        message = f"http-server did not come up on port {port}"
        raise SystemExit(message)

    # The request succeeded, but that alone does not say who answered it. If
    # the child has exited by now, something else on the port did, and the
    # capture would silently be of that.
    if (status := server.poll()) is not None:
        message = (
            f"port {port} answered, but this run's http-server had already "
            f"exited with status {status}; the reply came from another server"
        )
        raise SystemExit(message)


def _stop(server: _Stoppable) -> None:
    """Stop a served process, escalating if it will not stand down.

    Parameters
    ----------
    server
        The process to stop. Anything that can be terminated, killed and
        waited on; a `subprocess.Popen` in production.
    """
    server.terminate()
    try:
        server.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        # A server that will not stand down still holds the port, and the
        # next run's bind probe would refuse to start because of it.
        server.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            server.wait(timeout=STOP_TIMEOUT_SECONDS)
