"""Holding a lock in a directory anyone can write to.

The lock's path has to be predictable, because two runs find each other by
computing it — which is exactly what makes the file at that path
untrustworthy. These cover both halves: that the lock excludes, and that what
is opened to hold it is checked rather than assumed.
"""

from __future__ import annotations

import errno
import os
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    from pathlib import Path

from tests.support.weaver_harness import load

# Stands in for whatever goes wrong between taking a lock and the work
# finishing. Named so a `pytest.raises` block stays one statement.
_MID_START_FAILURE = "the port was occupied"


commands = load("weaver_snapshot")
locking = load("weaver_snapshot_locking")
output = load("weaver_snapshot_output")


def _lock_on(
    monkeypatch: pytest.MonkeyPatch, lock: Path, *, timeout: float = 0.2
) -> None:
    """Point the startup lock at a scratch file and shorten its wait."""
    monkeypatch.setattr(locking, "_lock_path", lambda _port: lock)
    monkeypatch.setattr(locking, "LOCK_TIMEOUT_SECONDS", timeout)


def test_the_startup_lock_is_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs must not both get past the probe and both spawn a server."""
    lock = tmp_path / "port.lock"
    _lock_on(monkeypatch, lock)

    # A second open file description on the same file is what a concurrent run
    # would have, so `flock` treats it as one.
    with (
        locking._startup_lock(8099),
        pytest.raises(SystemExit) as caught,
        locking._startup_lock(8099),
    ):
        pass  # pragma: no cover - the lock must not be granted twice

    message = str(caught.value.code)
    assert "8099" in message, f"the message should name the port; got {message!r}"
    assert str(lock) in message, f"the message should name the lock; got {message!r}"


def test_the_startup_lock_is_released_when_the_run_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that exits mid-start must not leave the next one waiting it out."""
    lock = tmp_path / "port.lock"
    _lock_on(monkeypatch, lock)

    with pytest.raises(RuntimeError), locking._startup_lock(8099):
        raise RuntimeError(_MID_START_FAILURE)

    # The lock must be free now, or a failed run would poison the port until
    # its file was removed by hand.
    with locking._startup_lock(8099):
        pass


def test_a_non_contention_flock_failure_is_raised_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only contention is worth waiting out.

    A kernel with no lock table left (ENOLCK) will not grow one because
    another run finished, so retrying turns a hard failure into a
    thirty-second stall that ends in the wrong message.
    """
    lock = tmp_path / "port.lock"
    attempts: list[int] = []

    def _no_locks_left(handle: object, flags: int) -> None:
        attempts.append(flags)
        raise OSError(errno.ENOLCK, "no locks available")

    monkeypatch.setattr(locking.fcntl, "flock", _no_locks_left)

    class _MustNotWait:
        """A clock the lock must not consult: no retries, no timeout."""

        def monotonic(self) -> float:
            return 0.0

        def sleep(self, seconds: float) -> None:
            message = f"slept {seconds}s over a failure retrying cannot cure"
            raise AssertionError(message)

    with (
        pytest.raises(OSError, match="no locks available") as caught,
        locking._exclusive(lock, "the test lock", _MustNotWait()),
    ):
        pass  # pragma: no cover - the lock must not be granted

    assert not isinstance(caught.value, SystemExit), (
        "a non-contention failure was dressed up as the timeout message"
    )
    assert caught.value.errno == errno.ENOLCK
    assert len(attempts) == 1, f"flock was retried: {len(attempts)} attempts"


def test_the_lock_file_is_named_for_the_port_and_the_user() -> None:
    """Two ports must not serialize against each other, nor two users contend."""
    first = locking._lock_path(8099)
    second = locking._lock_path(8100)

    assert first != second, f"both ports would serialize on {first}"
    assert str(os.getuid()) in first.name, (
        f"a shared /tmp is sticky, so the name needs the uid; got {first.name!r}"
    )


def test_a_symlink_where_the_lock_belongs_is_refused(tmp_path: Path) -> None:
    """The lock's path is predictable and its directory is world-writable.

    Another user can put a symlink there first. `open("w")` would follow it and
    truncate whatever it pointed at — something of ours, chosen by them.
    """
    victim = tmp_path / "something-of-ours.txt"
    victim.write_text("must survive", encoding="utf-8")
    lock = tmp_path / "port.lock"
    lock.symlink_to(victim)

    with pytest.raises(SystemExit) as caught, locking._lock_file(lock):
        pass  # pragma: no cover - the open must not succeed

    assert str(lock) in str(caught.value.code), (
        f"the message should name the lock; got {caught.value.code!r}"
    )
    assert victim.read_text(encoding="utf-8") == "must survive", (
        "the symlink was followed and its target truncated"
    )


def test_a_lock_path_that_is_not_a_regular_file_is_refused(tmp_path: Path) -> None:
    """Winning the race is not the same as being handed the right file.

    A FIFO rather than a directory, because `os.open` refuses a directory
    itself and the check under test is the one after the open succeeds.
    """
    lock = tmp_path / "port.lock"
    os.mkfifo(lock)

    with pytest.raises(SystemExit) as caught, locking._lock_file(lock):
        pass  # pragma: no cover - the open must not succeed

    assert "regular file" in str(caught.value.code), (
        f"the message should say what is wrong with it; got {caught.value.code!r}"
    )


def test_a_lock_belonging_to_another_user_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file another user got there first with is not this run's lock."""
    lock = tmp_path / "port.lock"
    lock.write_text("", encoding="utf-8")
    somebody_else = os.getuid() + 1
    monkeypatch.setattr(locking.os, "getuid", lambda: somebody_else)

    with pytest.raises(SystemExit) as caught, locking._lock_file(lock):
        pass  # pragma: no cover - the open must not succeed

    assert "belongs to uid" in str(caught.value.code), (
        f"the message should say whose it is; got {caught.value.code!r}"
    )


def test_an_existing_lock_file_is_not_truncated(tmp_path: Path) -> None:
    """Opening for writing would empty a file this process did not create."""
    lock = tmp_path / "port.lock"
    lock.write_text("a previous run left this", encoding="utf-8")

    with locking._lock_file(lock):
        pass

    assert lock.read_text(encoding="utf-8") == "a previous run left this", (
        "the lock file was truncated; the lock is the flock, not the contents"
    )
