"""Replacing one file's contents atomically, or leaving it exactly as it was.

Writing straight into a destination is not failure-atomic: a write that stops
partway — a full disk, a signal — leaves a half-written file where a valid one
was. So the new contents go to a unique temporary file beside the target and
are moved into place with a rename, which is atomic within one filesystem.
Until that rename the old contents are untouched; after it they are wholly
replaced. The temporary file is removed on every path that does not end in a
successful rename.

Shared by the generators that publish a single committed file — the Weaver
icon macro, the Episodic roadmap projection, the typos dictionary cache —
which each hand-rolled this dance before it was extracted here.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def atomic_write(output: Path, payload: str | bytes) -> None:
    """Write ``payload`` to ``output`` through a same-directory rename.

    Parameters
    ----------
    output
        The file to replace. Its parent holds the temporary file, so the two
        are on one filesystem and the rename cannot become a copy. Missing
        parents are created.
    payload
        The complete contents to publish. Text is encoded as UTF-8.

    Raises
    ------
    OSError
        If the temporary file cannot be created, written, closed, or moved
        into place. The destination is unchanged, and callers with a friendlier
        story to tell — a generator naming its output — wrap this themselves.

    Examples
    --------
    >>> from pathlib import Path
    >>> atomic_write(Path("out.txt"), "whole, or not at all")
    """
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - closed by the `with` below, before the rename
        delete=False, dir=output.parent, prefix=f".{output.name}-", suffix=".tmp"
    )
    temporary = Path(handle.name)
    try:
        # Closed before the rename rather than after: a rename that beat the
        # flush would publish a file the buffer had not finished filling.
        with handle:
            handle.write(data)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
