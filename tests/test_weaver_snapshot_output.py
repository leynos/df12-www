"""Locks, staging, and publishing a capture without losing the last one.

The lock's path is predictable, so the file at it cannot be trusted; and
publication has to leave the destination either wholly replaced or wholly
untouched, because a directory holding half of each run still looks like a
directory of snapshots.
"""

from __future__ import annotations

import contextlib
import json
import os
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

from tests.support.weaver_harness import load

# Stands in for whatever goes wrong between taking a lock and the work
# finishing. Named so a `pytest.raises` block stays one statement.
_MID_START_FAILURE = "the port was occupied"


commands = load("weaver_snapshot")
locking = load("weaver_snapshot_locking")
output = load("weaver_snapshot_output")


def test_publishing_clears_only_the_extension_being_written(tmp_path: Path) -> None:
    """A capture and a screenshot run share a directory, so each clears its own.

    Clearing happens at publication rather than before the capture: emptying
    the destination up front destroys the previous run's results in exchange
    for nothing, and leaves nothing behind if this run then fails.
    """
    out = tmp_path / "shots"
    out.mkdir()
    (out / "gone.json").write_text("{}", encoding="utf-8")
    (out / "kept.png").write_text("x", encoding="utf-8")

    with output._staged(out, ".json") as stage:
        assert (out / "gone.json").exists(), (
            "the previous run's results should survive until this one succeeds"
        )
        (stage / "fresh.json").write_text("{}", encoding="utf-8")

    assert not (out / "gone.json").exists(), "the previous run's JSON should be cleared"
    assert (out / "fresh.json").exists(), "this run's snapshot should be published"
    assert (out / "kept.png").exists(), (
        "only the extension being written should be cleared, so a capture and "
        "a screenshot run can share a directory"
    )


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


def test_the_lock_file_is_named_for_the_port_and_the_user() -> None:
    """Two ports must not serialize against each other, nor two users contend."""
    first = locking._lock_path(8099)
    second = locking._lock_path(8100)

    assert first != second, f"both ports would serialize on {first}"
    assert str(os.getuid()) in first.name, (
        f"a shared /tmp is sticky, so the name needs the uid; got {first.name!r}"
    )


def test_a_capture_is_published_only_once_it_is_whole(tmp_path: Path) -> None:
    """A run that fails partway must not leave half a capture to be compared."""
    out_dir = tmp_path / "snapshots"
    out_dir.mkdir()
    (out_dir / "__home.json").write_text("previous run", encoding="utf-8")

    def half_a_capture() -> None:
        """Write one page, then fail the way an interrupted run does."""
        with output._staged(out_dir, ".json") as stage:
            (stage / "__home.json").write_text("this run", encoding="utf-8")
            raise RuntimeError(_MID_START_FAILURE)

    with pytest.raises(RuntimeError):
        half_a_capture()

    assert (out_dir / "__home.json").read_text(encoding="utf-8") == "previous run", (
        "a failed run replaced the previous capture with its own partial one"
    )
    assert not list(tmp_path.glob(".snapshots-*")), (
        f"the staging directory was left behind: {list(tmp_path.iterdir())}"
    )


def test_a_finished_capture_replaces_the_previous_one(tmp_path: Path) -> None:
    """Publication clears what was there, so a dropped page cannot linger."""
    out_dir = tmp_path / "snapshots"
    out_dir.mkdir()
    (out_dir / "__home.json").write_text("previous run", encoding="utf-8")
    (out_dir / "gone.json").write_text("a page that no longer exists", encoding="utf-8")

    with output._staged(out_dir, ".json") as stage:
        (stage / "__home.json").write_text("this run", encoding="utf-8")

    assert (out_dir / "__home.json").read_text(encoding="utf-8") == "this run", (
        "a capture that finished did not replace the previous run's snapshot, "
        "so the diff would compare the baseline against itself"
    )
    assert not (out_dir / "gone.json").exists(), (
        "a snapshot from a previous run survived, and would be compared as "
        "though this run had written it"
    )
    assert not list(tmp_path.glob(".snapshots-*")), "the staging directory was left"


def test_two_runs_publishing_the_same_directory_contend(tmp_path: Path) -> None:
    """Publication is the moment two runs would interleave, so it is serialized."""
    out_dir = tmp_path / "snapshots"
    out_dir.mkdir()
    first = locking._output_lock_path(out_dir.resolve())
    second = locking._output_lock_path((tmp_path / "other").resolve())

    assert first == locking._output_lock_path(out_dir.resolve()), (
        "one directory should map to one lock, however often it is asked for"
    )
    assert first != second, f"two directories both locked on {first}"


def test_a_diff_takes_the_same_lock_publication_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reader that started midway would compare two runs against each other.

    Publication replaces file by file. Each replacement is atomic, the
    sequence of them is not, and a diff running through that sequence would
    take some pages from this run and some from the last — then report the
    difference as the branch's work. The reader taking the writer's lock is
    what closes it.
    """
    before = tmp_path / "baseline"
    after = tmp_path / "current"
    for directory in (before, after):
        directory.mkdir()
        (directory / "__home.json").write_text(
            json.dumps({"payload": {"tree": {"tag": "html", "children": []}}}),
            encoding="utf-8",
        )

    taken: list[Path] = []
    real = locking._exclusive

    @contextlib.contextmanager
    def watched(path: Path, contended: str) -> cabc.Iterator[None]:
        taken.append(path)
        with real(path, contended):
            yield

    monkeypatch.setattr(commands, "_exclusive", watched)
    commands.diff(before, after)

    expected = [
        locking._output_lock_path(directory.resolve())
        for directory in sorted((before.resolve(), after.resolve()))
    ]
    assert taken == expected, (
        f"the diff should lock both directories, in a stable order; it took "
        f"{taken} rather than {expected}"
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


def test_a_failed_publication_leaves_the_destination_as_it_was(
    tmp_path: Path,
) -> None:
    """Deleting then moving is not atomic: a failure halfway loses both runs.

    The previous files are moved aside rather than deleted, so a rename that
    fails partway can be undone. Without that the destination ends up holding
    some of each with the originals already gone — the worst state, because it
    still looks like a directory of snapshots.
    """
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / "one.json").write_text("previous one", encoding="utf-8")
    (destination / "two.json").write_text("previous two", encoding="utf-8")
    (destination / "kept.png").write_text("a screenshot run's", encoding="utf-8")

    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "one.json").write_text("this one", encoding="utf-8")
    (staging / "two.json").write_text("this two", encoding="utf-8")

    moves = {"n": 0}
    # Two rescues, then one publication, then the disk fills.
    breaks_on = 4

    def failing(source: Path, target: Path) -> object:
        moves["n"] += 1
        # Exactly one operation fails. A rename back into the directory the
        # file just left needs no new space, so a real ENOSPC would not block
        # the rollback either, and a mover that failed forever would test the
        # fake rather than the code.
        if moves["n"] == breaks_on:
            message = "no space left on device"
            raise OSError(message)
        return source.replace(target)

    with pytest.raises(OSError, match="no space left"):
        output._publish(staging, destination, ".json", failing)

    assert (destination / "one.json").read_text(encoding="utf-8") == "previous one", (
        "a failed publication left this run's file in place of the previous one"
    )
    assert (destination / "two.json").read_text(encoding="utf-8") == "previous two", (
        "a failed publication lost the previous run's snapshot"
    )
    assert (destination / "kept.png").exists(), (
        "the other extension should not have been touched at all"
    )


def test_a_publication_that_succeeds_replaces_everything(tmp_path: Path) -> None:
    """The rollback path must not have cost the ordinary one its job."""
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / "one.json").write_text("previous", encoding="utf-8")
    (destination / "gone.json").write_text(
        "a page that no longer exists", encoding="utf-8"
    )
    (destination / "kept.png").write_text("a screenshot run's", encoding="utf-8")

    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "one.json").write_text("this run", encoding="utf-8")

    output._publish(staging, destination, ".json")

    assert (destination / "one.json").read_text(encoding="utf-8") == "this run", (
        "a publication that succeeded did not replace the previous snapshot"
    )
    assert not (destination / "gone.json").exists(), (
        "a snapshot from a previous run survived this one"
    )
    assert (destination / "kept.png").exists(), "the other extension was touched"


def test_a_cancelled_publication_still_restores_the_destination(
    tmp_path: Path,
) -> None:
    """Ctrl-C between two renames leaves the same mess a full disk would.

    Rolling back only `OSError` meant an interrupted publication left the
    destination holding some files from each run, with the originals already
    moved aside — and the operator who pressed Ctrl-C has no more reason to
    expect that than one who ran out of space.
    """
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / "one.json").write_text("previous one", encoding="utf-8")
    (destination / "two.json").write_text("previous two", encoding="utf-8")

    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "one.json").write_text("this one", encoding="utf-8")
    (staging / "two.json").write_text("this two", encoding="utf-8")

    moves = {"n": 0}
    interrupt_on = 4

    def interrupted(source: Path, target: Path) -> object:
        moves["n"] += 1
        if moves["n"] == interrupt_on:
            raise KeyboardInterrupt
        return source.replace(target)

    with pytest.raises(KeyboardInterrupt):
        output._publish(staging, destination, ".json", interrupted)

    assert (destination / "one.json").read_text(encoding="utf-8") == "previous one", (
        "an interrupted publication left this run's file in place of the last"
    )
    assert (destination / "two.json").read_text(encoding="utf-8") == "previous two", (
        "an interrupted publication lost the previous run's snapshot"
    )


def _seeded(tmp_path: Path) -> Path:
    """Return a destination holding one snapshot from a previous run."""
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / "one.json").write_text("previous one", encoding="utf-8")
    return destination


def _staged_run(destination: Path, move: cabc.Callable[[Path, Path], object]) -> Path:
    """Capture one page and publish it with `move`, returning the staging path.

    `_staged` chooses the staging directory itself, so a test that looks
    inside it afterwards has to capture the path on the way through.
    """
    seen: list[Path] = []
    with output._staged(destination, ".json", move) as staging:
        seen.append(staging)
        (staging / "one.json").write_text("this run", encoding="utf-8")
    return seen[0]


def test_a_rollback_that_cannot_finish_keeps_the_only_copy(tmp_path: Path) -> None:
    """When the rollback fails too, staging holds the only previous results.

    The destination then holds neither run in full, and the previous run's
    files are in the staging directory's `replaced/`. Sweeping that up with
    the rest of the staging directory — which is what happens to every other
    failure — would turn a recoverable mess into an unrecoverable one.
    """
    destination = _seeded(tmp_path)
    moves = {"n": 0}

    def hopeless(source: Path, target: Path) -> object:
        moves["n"] += 1
        # The rescue succeeds; the publication and then the rollback do not.
        if moves["n"] == 1:
            return source.replace(target)
        message = "the filesystem went away"
        raise OSError(message)

    staging: list[Path] = []
    with pytest.raises(SystemExit) as caught:
        staging.append(_staged_run(destination, hopeless))

    message = str(caught.value.code)
    assert "inconsistent state" in message, f"got {message!r}"
    kept = next(tmp_path.glob(".out-*"))
    assert kept.is_dir(), (
        "the staging directory was swept away, taking the previous run's only "
        "surviving copy with it"
    )
    assert (kept / "replaced" / "one.json").read_text(encoding="utf-8") == (
        "previous one"
    ), f"the previous run's file is not recoverable from {kept}"


def test_an_ordinary_publication_failure_still_cleans_up(tmp_path: Path) -> None:
    """A rollback that worked leaves nothing to keep, so staging goes."""
    destination = _seeded(tmp_path)
    moves = {"n": 0}
    # Rescue, then a failed publication, then a rollback that works.
    publication = 2

    def fails_once(source: Path, target: Path) -> object:
        moves["n"] += 1
        if moves["n"] == publication:
            message = "no space left on device"
            raise OSError(message)
        return source.replace(target)

    with pytest.raises(SystemExit) as caught:
        _staged_run(destination, fails_once)

    assert "could not be published" in str(caught.value.code), (
        f"expected the ordinary publication message; got {caught.value.code!r}"
    )
    assert (destination / "one.json").read_text(encoding="utf-8") == "previous one", (
        "the rollback should have restored the previous run"
    )
    assert not list(tmp_path.glob(".out-*")), (
        "a recoverable failure should not leave a staging directory behind"
    )
