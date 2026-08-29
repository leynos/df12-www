"""Publishing a capture, or leaving the destination exactly as it was.

A run captures into a directory of its own and moves the result into place at
the end, under a lock. The previous run's files are moved aside rather than
deleted, so a failure partway can be undone: a destination holding half of
each run is the worst outcome, because it still looks like a directory of
snapshots.
"""

from __future__ import annotations

import collections.abc as cabc
import contextlib
import shutil
import tempfile
from pathlib import Path

from weaver_snapshot_locking import _exclusive, _output_lock_path
from weaver_snapshot_paths import _ensure_output_dir

type Mover = cabc.Callable[[Path, Path], object]


class _InconsistentDestinationError(OSError):
    """Publication failed and the rollback could not put the old files back.

    Raised only when the destination is left holding neither run's results in
    full. It is an ``OSError`` so an ordinary caller still sees a filesystem
    failure, and distinct so :func:`_staged` can tell that the staging
    directory now holds the only copy of the previous run's files and must not
    be swept away with the rest.
    """


def _publish(
    staging: Path, destination: Path, suffix: str, move: Mover = Path.replace
) -> None:
    """Move a finished capture into place, or leave the destination as it was.

    Deleting the previous run's files and then moving this run's in is not
    failure-atomic: a rename that fails partway leaves the destination holding
    some of each, with the originals already gone. That is the worst state to
    be in, because it still looks like a directory of snapshots.

    So the previous files are moved aside rather than deleted, and put back if
    anything goes wrong. Every step is a rename within one filesystem, which
    is atomic per file, and the rollback is the same operation in reverse.
    Only the extension being written is touched, so a ``capture`` and a
    ``shots`` run can share a directory.

    Parameters
    ----------
    staging
        The directory this run captured into.
    destination
        Where the results belong.
    suffix
        File extension being published, including the leading dot.
    move
        How to move one file onto another, atomically. Injected so a failure
        partway through can be provoked without a full disk.

    Raises
    ------
    OSError
        If publication fails, after the destination has been put back as it
        was. The caller turns this into a ``SystemExit`` naming the directory.
    """
    aside = staging / "replaced"
    aside.mkdir(exist_ok=True)

    rescued: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for stale in sorted(destination.glob(f"*{suffix}")):
            moved = aside / stale.name
            move(stale, moved)
            rescued.append((moved, stale))
        for captured in sorted(staging.glob(f"*{suffix}")):
            landed = destination / captured.name
            move(captured, landed)
            published.append(landed)
    except BaseException as cause:
        # `BaseException`, not `OSError`: a Ctrl-C between two renames leaves
        # the destination holding half of each run just as a full disk does,
        # and the operator who pressed it has no more reason to expect that
        # than one who ran out of space.
        #
        # Undo this run's half-publication first, so putting the previous
        # files back cannot be blocked by a file this run had just landed.
        failures: list[str] = []
        for landed in published:
            try:
                landed.unlink()
            except OSError as exc:
                failures.append(f"{landed} could not be removed ({exc})")
        for moved, original in rescued:
            try:
                move(moved, original)
            except OSError as exc:
                failures.append(f"{original} could not be restored ({exc})")
        if failures:
            # The rollback itself failed, so the destination holds neither
            # run's results in full and the previous run's files are still in
            # the staging directory. Raising a distinct type is what stops
            # `_staged` deleting them along with everything else.
            message = (
                f"{destination} is in an inconsistent state after a failed "
                f"publication, and the previous run's files are in {aside}. "
                + "; ".join(failures)
            )
            # Chained from the failure that interrupted publication, because
            # the message describes the rollback and the operator also needs
            # to see what went wrong in the first place.
            raise _InconsistentDestinationError(message) from cause
        raise


@contextlib.contextmanager
def _staged(
    out_dir: Path, suffix: str, move: Mover = Path.replace
) -> cabc.Iterator[Path]:
    """Capture into a private directory, and publish it only if everything worked.

    Writing straight into ``out_dir`` gives a run no exclusive claim on it. Two
    runs sharing one would interleave: the second clears the directory the
    first is still filling, and the pages captured before that point are gone
    while the ones after remain, so the result looks like a complete capture of
    a site half of whose pages were never visited. A run that fails partway
    leaves the same thing behind.

    So each run captures into a directory of its own and publishes at the end,
    under a lock keyed on the destination. Publication replaces file by file
    with :func:`os.replace`, which is atomic per file, and the lock makes the
    sequence of replacements atomic against another run of this script.

    Parameters
    ----------
    out_dir
        Where the results should end up.
    suffix
        File extension being written, including the leading dot.
    move
        How to move one file onto another. Forwarded to :func:`_publish`, so
        a publication failure can be provoked without a full disk.

    Yields
    ------
    Path
        The staging directory to write into.

    Raises
    ------
    SystemExit
        If the staging directory cannot be made, or publication fails.
    """
    destination = _ensure_output_dir(out_dir)
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
        )
    except OSError as exc:
        message = f"a staging directory beside {destination} could not be made ({exc})"
        raise SystemExit(message) from exc

    try:
        yield staging
    except BaseException:
        # A half-finished capture is worse than none: it would be compared as
        # though it were whole.
        shutil.rmtree(staging, ignore_errors=True)
        raise

    try:
        with _exclusive(_output_lock_path(destination), f"the output {destination}"):
            _publish(staging, destination, suffix, move)
    except _InconsistentDestinationError as exc:
        # The staging directory holds the only copy of the previous run's
        # files, so it is deliberately left where it is. Sweeping it up here
        # would turn a recoverable mess into an unrecoverable one.
        message = (
            f"{exc} The staging directory has been kept; its `replaced/` "
            f"holds the previous run's files."
        )
        raise SystemExit(message) from exc
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        message = f"{destination} could not be published to ({exc})"
        raise SystemExit(message) from exc
    except BaseException:
        # Publication can fail without an OSError: `_exclusive` gives up on a
        # held lock with SystemExit, and a Ctrl-C can land between renames.
        # The rollback has already run by the time either arrives here, so
        # the staging directory holds nothing worth keeping — sweep it up
        # rather than leave a half-capture that looks like a published one.
        shutil.rmtree(staging, ignore_errors=True)
        raise
    else:
        shutil.rmtree(staging, ignore_errors=True)
