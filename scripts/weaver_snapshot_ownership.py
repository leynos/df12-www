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
import urllib.error
import urllib.request

from weaver_snapshot_paths import REPO_ROOT

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


def _confirm_ownership(base: str, marker: str, port: int, when: str) -> None:
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

    Raises
    ------
    SystemExit
        If the marker cannot be fetched or does not come back intact, in which
        case whatever is on the port is not this run's server.
    """
    try:
        with urllib.request.urlopen(f"{base}/{marker}", timeout=5) as response:  # noqa: S310 - literal loopback URL
            # Whatever is on that port is not necessarily ours, so its
            # response is not necessarily small. One byte past the marker is
            # enough to tell a match from anything longer.
            served = response.read(len(marker) + 1).decode("utf-8", "replace").strip()
    except (urllib.error.URLError, OSError) as exc:
        message = (
            f"the server on port {port} did not serve this run's marker "
            f"{when} ({exc}), so it is serving some other tree; the snapshot "
            f"would be of that. Pass --port, or leave it unset to be given a "
            f"free one."
        )
        raise SystemExit(message) from exc
    if served != marker:
        message = (
            f"port {port} returned {served!r} for this run's marker {when}; "
            f"another server has it"
        )
        raise SystemExit(message)
