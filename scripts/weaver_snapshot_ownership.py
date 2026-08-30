"""Proving that the server answering on a port is this run's.

A reply says something is listening, not whose it is. An unrelated server can
claim the port between the bind probe and the spawn, and one in another
worktree answers a readiness poll just as readily — its pages would then be
captured and reported as this branch's work. So each run leaves a file only it
knows the name of, and fetches it back.
"""

from __future__ import annotations

import contextlib
import secrets
import typing as typ

from weaver_snapshot_paths import REPO_ROOT
from weaver_snapshot_process import _NO_REDIRECTS, _probe_failure_category

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@contextlib.contextmanager
def _ownership_marker() -> cabc.Iterator[str]:
    """Put a file under ``public/`` that only this run knows the name of.

    Fetching it back is what turns "something is listening" into "the thing
    listening is serving *this* worktree's tree". Liveness of the child cannot
    establish that: an unrelated server can claim the port in the moment
    between the bind probe and the spawn, and a run in another worktree — or
    another user's, which the startup lock deliberately does not serialize —
    answers requests just as readily.

    Yields
    ------
    str
        The marker's name, relative to the served root.
    """
    name = f"weaver-snapshot-{secrets.token_hex(8)}.txt"
    marker = REPO_ROOT / "public" / name
    marker.write_text(name, encoding="utf-8")
    try:
        yield name
    finally:
        marker.unlink(missing_ok=True)


# How the ownership check reads the marker back. Takes the URL and a byte
# ceiling, and returns what was served.
type Fetch = cabc.Callable[[str, int], str]


def _fetch(url: str, limit: int) -> str:
    """Read at most ``limit`` bytes from a URL, as text.

    Parameters
    ----------
    url
        A loopback URL to request.
    limit
        How much to read. Whatever is on the port is not necessarily ours, so
        its response is not necessarily small.

    Returns
    -------
    str
        The decoded body, undecodable bytes replaced.

    Raises
    ------
    OSError
        If the request fails — including by answering with a redirect. A
        marker is proof of ownership only if this exact URL served it, so a
        server that points somewhere else has already failed the check.
    """
    with _NO_REDIRECTS.open(url, timeout=5) as response:
        return response.read(limit).decode("utf-8", "replace")


def _confirm_ownership(
    base: str, marker: str, port: int, when: str, fetch: Fetch = _fetch
) -> None:
    """Check that the server on this port is serving this run's ``public/``.

    Parameters
    ----------
    base
        The origin to ask.
    marker
        The name :func:`_ownership_marker` chose, which is also its contents.
    port
        The port, for the message.
    when
        What was happening, for the message: the check runs once before the
        capture and once after, and the two failures mean different things.
    fetch
        How to read the marker back. Injected so a server that is not this
        run's can be simulated without one.

    Raises
    ------
    SystemExit
        If the marker cannot be fetched or does not come back intact, in which
        case whatever is on the port is not this run's server.
    """
    try:
        # One byte past the marker is enough to tell a match from anything
        # longer, and whatever is on that port may serve a great deal more.
        served = fetch(f"{base}/{marker}", len(marker) + 1).strip()
    except OSError as exc:
        # The category rather than the exception's text: whatever is on the
        # port is untrusted, and a redirect's reason or target is its to
        # choose. The chained exception keeps the detail for a traceback.
        message = (
            f"the server on port {port} did not serve this run's marker "
            f"{when} (the fetch failed as {_probe_failure_category(exc)}), "
            f"so it is serving some other tree; the snapshot would be of "
            f"that. Pass --port, or leave it unset to be given a free one."
        )
        raise SystemExit(message) from exc
    if served != marker:
        message = (
            f"port {port} returned {served!r} for this run's marker {when}; "
            f"another server has it"
        )
        raise SystemExit(message)
