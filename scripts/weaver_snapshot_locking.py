"""Advisory locks, and opening a lock file in a directory anyone can write to.

Two runs of this harness find each other by computing the same lock path, so
the path has to be predictable — which is exactly what makes the file at it
untrustworthy. Everything here exists to hold a lock without trusting what is
already there.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import stat
import tempfile
import time
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    import collections.abc as cabc

# How long to wait for another run to finish starting its server. A healthy
# start takes under a second, so anything near this means the holder was
# killed mid-start rather than that it is merely slow.
LOCK_TIMEOUT_SECONDS = 30


def _lock_path(port: int) -> Path:
    """Name the lock file guarding one port's startup.

    It sits in the system temp directory rather than in the repository,
    because the runs that contend are typically in different worktrees. The
    port is what they share, so the port is what the name is keyed on — and
    the user id too, since a shared ``/tmp`` is sticky and another user's file
    could not be opened for writing. Two users racing for one port are left to
    the bind probe, which catches them whoever owns the lock file.

    Parameters
    ----------
    port
        TCP port the lock guards.

    Returns
    -------
    Path
        The lock file's path. It is created on demand and left behind; the
        lock is the ``flock`` on it, not the file's existence.
    """
    return Path(tempfile.gettempdir()) / f"weaver-snapshot-{os.getuid()}-{port}.lock"


@contextlib.contextmanager
def _startup_lock(port: int) -> cabc.Iterator[None]:
    """Hold an exclusive lock on a port's startup for the duration.

    Probing a port and then spawning a server on it is check-then-act: two
    runs can both find the port free, both spawn, and one then answer the
    other's readiness poll. The loser would snapshot the winner's ``public/``
    and report the diff as its own work.

    The default port is ephemeral, so two runs normally have nothing to
    contend over; this covers the case where a port was named explicitly, and
    two runs in two worktrees were given the same number.

    Serializing probe and spawn behind one lock removes the interleaving
    rather than narrowing it: the second run reaches the probe only once the
    first is already serving, and is then refused with the ordinary
    port-in-use message rather than racing. The lock is released as soon as
    the server answers, so it covers startup and not the capture, which takes
    minutes.

    ``flock`` is advisory and POSIX-only, which suits both facts here: the
    only processes that need to co-operate are other runs of this script, and
    the repository's tooling is POSIX throughout. It is keyed on the user id
    as well as the port, because a shared ``/tmp`` is sticky and another
    user's lock file could not be opened for writing. That deliberately leaves
    two *users* unserialized, which is what :func:`_confirm_ownership` is for:
    a lock cannot prove whose server answered, and a marker can.

    Parameters
    ----------
    port
        TCP port whose startup is being serialized.

    Yields
    ------
    None
        With the lock held.

    Raises
    ------
    SystemExit
        If the lock is still held after :data:`LOCK_TIMEOUT_SECONDS`,
        which means another run has been starting for far longer than a
        healthy start takes.
    """
    with _exclusive(_lock_path(port), f"the startup lock for port {port}"):
        yield


@contextlib.contextmanager
def _lock_file(path: Path) -> cabc.Iterator[typ.IO[bytes]]:
    """Open a lock file in a shared temp directory without trusting it.

    The lock's path is predictable — it has to be, since two runs find each
    other by computing the same name — and the system temp directory is
    writable by everyone. So the file at that path may not be the one this
    process expects: another user can create it first, or leave a symlink
    there pointing at something of ours. Opening it with ``open("w")`` would
    follow that link and truncate whatever it found.

    ``O_NOFOLLOW`` refuses a symlink outright, ``O_CREAT`` without ``O_TRUNC``
    leaves an existing file's contents alone, and the mode denies everyone but
    the owner. What is opened is then checked to be a regular file this user
    owns, because winning the race is not the same as being handed the right
    file.

    Parameters
    ----------
    path
        The lock file to open, creating it if absent.

    Yields
    ------
    IO
        The open file, for :func:`fcntl.flock`. Nothing is written to it; the
        lock is the ``flock``, not the contents.

    Raises
    ------
    SystemExit
        If the path is a symlink, is not a regular file, belongs to another
        user, or cannot be opened.
    """
    try:
        descriptor = os.open(
            path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
        )
    except OSError as exc:
        message = (
            f"the lock file {path} could not be opened ({exc}). If it is a "
            f"symlink or belongs to another user, remove it; nothing but this "
            f"script should be writing there."
        )
        raise SystemExit(message) from exc

    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            message = f"the lock file {path} is not a regular file; remove it"
            raise SystemExit(message)
        if status.st_uid != os.getuid():
            message = (
                f"the lock file {path} belongs to uid {status.st_uid} rather "
                f"than this user; remove it, or pass --port to use another"
            )
            raise SystemExit(message)
        with os.fdopen(descriptor, "rb+") as handle:
            descriptor = -1
            yield handle
    finally:
        if descriptor != -1:
            os.close(descriptor)


@contextlib.contextmanager
def _exclusive(path: Path, contended: str) -> cabc.Iterator[None]:
    """Hold an exclusive advisory lock on ``path`` for the duration.

    Parameters
    ----------
    path
        The lock file. Created on demand and left behind; the lock is the
        ``flock`` on it, not the file's existence.
    contended
        What is being locked, for the message a waiting run eventually gives up
        with.

    Yields
    ------
    None
        With the lock held.

    Raises
    ------
    SystemExit
        If the lock is still held after :data:`LOCK_TIMEOUT_SECONDS`.
    """
    with _lock_file(path) as handle:
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    message = (
                        f"another run has held {contended} ({path}) for over "
                        f"{LOCK_TIMEOUT_SECONDS}s; it may have been killed "
                        f"partway. Remove the lock file if no run is active."
                    )
                    raise SystemExit(message) from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _output_lock_path(out_dir: Path) -> Path:
    """Name the lock file guarding one output directory's publication.

    Keyed on the resolved path, so two runs writing the same directory contend
    however they spelled it, and two writing different directories do not.

    Parameters
    ----------
    out_dir
        The directory the run will publish into.

    Returns
    -------
    Path
        The lock file's path.
    """
    digest = hashlib.sha256(str(out_dir).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"weaver-snapshot-{os.getuid()}-{digest}.lock"
