"""Holding a lock in a directory anyone can write to.

The lock's path has to be predictable, because two runs find each other by
computing it — which is exactly what makes the file at that path
untrustworthy. These cover both halves: that the lock excludes, and that what
is opened to hold it is checked rather than assumed.
"""

from __future__ import annotations

import errno
import os
import tempfile
import typing as typ
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

if typ.TYPE_CHECKING:
    import collections.abc as cabc

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


class _MustNotWait:
    """A clock the lock must not consult: no deadline, no retries."""

    def monotonic(self) -> float:
        """Refuse: a non-contention failure has no timeout to measure."""
        message = "the clock was consulted for a failure retrying cannot cure"
        raise AssertionError(message)

    def sleep(self, seconds: float) -> None:
        """Refuse: there is nothing to wait for."""
        message = f"slept {seconds}s over a failure retrying cannot cure"
        raise AssertionError(message)


class _Sequenced:
    """A clock that reports a scripted sequence of times and records sleeps."""

    def __init__(self, times: cabc.Iterable[float]) -> None:
        """Store the scripted times and start with no sleeps recorded."""
        self._times = iter(times)
        self.slept: list[float] = []

    def monotonic(self) -> float:
        """Report the next scripted time."""
        return next(self._times)

    def sleep(self, seconds: float) -> None:
        """Record the wait rather than taking it."""
        self.slept.append(seconds)


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

    def _no_locks_left(_handle: object, flags: int) -> None:
        """Refuse with ENOLCK, recording the attempt."""
        attempts.append(flags)
        raise OSError(errno.ENOLCK, "no locks available")

    monkeypatch.setattr(locking.fcntl, "flock", _no_locks_left)

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


# Deterministic and quiet, as in `test_weaver_snapshot_properties.py`; the
# function-scoped `tmp_path` is safe to reuse because every example makes a
# lock file in a directory of its own.
SETTINGS = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
    ],
)

# A spread of failures `flock(2)` can report that do not mean "held by
# somebody else". None will be cured by another run finishing.
_NON_CONTENTION = sorted({errno.ENOLCK, errno.EINVAL, errno.EBADF, errno.EIO})


@SETTINGS
@given(code=st.sampled_from(_NON_CONTENTION))
def test_every_non_contention_errno_is_raised_at_once(
    tmp_path: Path, code: int
) -> None:
    """Whatever the non-contention errno, one attempt and no clock at all."""
    lock = Path(tempfile.mkdtemp(dir=tmp_path)) / "port.lock"
    attempts: list[int] = []

    def broken(_handle: object, flags: int) -> None:
        """Refuse with the generated errno, recording the attempt."""
        attempts.append(flags)
        raise OSError(code, os.strerror(code))

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(locking.fcntl, "flock", broken)
        with (
            pytest.raises(OSError) as caught,  # noqa: PT011 - checked by errno below
            locking._exclusive(lock, "the test lock", _MustNotWait()),
        ):
            pass  # pragma: no cover - the lock must not be granted

    assert not isinstance(caught.value, SystemExit), (
        f"errno {code} was dressed up as the timeout message"
    )
    assert caught.value.errno == code
    assert len(attempts) == 1, f"flock was retried for errno {code}: {attempts}"


@SETTINGS
@given(code=st.sampled_from([errno.EACCES, errno.EAGAIN]))
def test_every_contention_errno_is_waited_out(tmp_path: Path, code: int) -> None:
    """Both contention errnos retry, then give up with the timeout message."""
    lock = Path(tempfile.mkdtemp(dir=tmp_path)) / "port.lock"
    attempts: list[int] = []

    def held(_handle: object, flags: int) -> None:
        """Refuse as contended, recording the attempt."""
        attempts.append(flags)
        raise OSError(code, os.strerror(code))

    # First contention sets the deadline at 0s; 10s is within it, so the lock
    # sleeps and retries; 31s is past it, so the second attempt gives up.
    clock = _Sequenced([0.0, 10.0, 31.0])

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(locking.fcntl, "flock", held)
        with (
            pytest.raises(SystemExit, match="another run has held") as caught,
            locking._exclusive(lock, "the test lock", clock),
        ):
            pass  # pragma: no cover - the lock must not be granted

    match caught.value.__cause__:
        case OSError():
            pass
        case unexpected:
            pytest.fail(
                f"the timeout message should chain from the last contention; "
                f"got {unexpected!r}"
            )
    attempts_before_giving_up = 2
    assert len(attempts) == attempts_before_giving_up, (
        f"expected one retry before giving up; got {attempts}"
    )
    assert clock.slept == [locking.LOCK_POLL_SECONDS], (
        f"expected one poll interval between attempts; slept {clock.slept}"
    )


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
