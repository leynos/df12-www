"""The shared atomic writer, exercised directly and over generated inputs.

The callers' suites — the icon generator's, the roadmap projector's — check
that *their* publication fails safely. These check the writer itself: that
whatever payload it is given arrives whole or not at all, wherever the write
or the rename chooses to fail.
"""

from __future__ import annotations

import tempfile
import typing as typ
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.support.weaver_harness import load

writer = load("atomic_write")

# Deterministic and quiet: these run in the commit gate, so a flaky example or
# a slow-data health check would be a gate failure rather than a finding. The
# function-scoped `tmp_path` is safe to reuse because every example makes its
# own directory beneath it.
SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
    ],
)

# Text arrives UTF-8 encoded and bytes arrive as they are, so the two must be
# interchangeable at the destination.
payloads = st.one_of(st.text(max_size=256), st.binary(max_size=256))


def _scratch(tmp_path: Path) -> Path:
    """Return a directory of this example's own, so examples cannot collide."""
    return Path(tempfile.mkdtemp(dir=tmp_path))


def _leftovers(directory: Path) -> list[str]:
    """Name any temporary file left beside the output."""
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.name.endswith(".tmp"))


def test_an_existing_file_is_wholly_replaced(tmp_path: Path) -> None:
    """Replaced, not appended to, and nothing left beside it."""
    output = tmp_path / "out.txt"
    output.write_text("the previous contents, which must go", encoding="utf-8")

    writer.atomic_write(output, "the new contents")

    assert output.read_text(encoding="utf-8") == "the new contents"
    assert _leftovers(tmp_path) == []


@SETTINGS
@given(payload=payloads)
def test_whatever_is_given_arrives_whole(tmp_path: Path, payload: str | bytes) -> None:
    """Any text or bytes payload lands exactly, parents made on demand."""
    output = _scratch(tmp_path) / "nested" / "deeper" / "out.bin"

    writer.atomic_write(output, payload)

    expected = payload.encode("utf-8") if isinstance(payload, str) else payload
    assert output.read_bytes() == expected, "the destination does not hold the payload"
    assert _leftovers(output.parent) == [], "a temporary file survived success"


@SETTINGS
@given(
    payload=payloads,
    prior=st.binary(max_size=64),
    failure=st.sampled_from(["write", "close", "replace"]),
)
def test_a_failure_anywhere_leaves_the_destination_untouched(
    tmp_path: Path, payload: str | bytes, prior: bytes, failure: str
) -> None:
    """Wherever the writer fails, the previous contents survive exactly.

    The write, the close, and the rename are the three operations that touch
    the filesystem after the temporary file exists; each is made to fail in
    turn, and the destination must hold the prior bytes with no temporary
    file left beside it.
    """
    scratch = _scratch(tmp_path)
    output = scratch / "out.bin"
    output.write_bytes(prior)

    real_temporary_file = writer.tempfile.NamedTemporaryFile
    original_replace = Path.replace

    class _FailsOnDemand:
        """Delegate to the real handle, failing the chosen operation."""

        def __init__(self, handle: typ.IO[bytes]) -> None:
            """Wrap the real handle."""
            self.handle = handle

        @property
        def name(self) -> str:
            """Name the real temporary file."""
            return str(self.handle.name)

        def __enter__(self) -> typ.Self:
            """Hand the wrapper back, as the real handle would itself."""
            return self

        def __exit__(self, *_: object) -> None:
            """Close the real handle, failing first if the close should."""
            self.handle.close()
            if failure == "close":
                message = "the close was refused"
                raise OSError(message)

        def write(self, data: bytes) -> int:
            """Write through, unless the write is the chosen failure."""
            if failure == "write":
                message = "no space left on device"
                raise OSError(message)
            return self.handle.write(data)

    def wrapped(*args: typ.Any, **kwargs: typ.Any) -> object:  # noqa: ANN401 - forwarded verbatim to the real factory
        """Hand back a wrapper around the real temporary file."""
        return _FailsOnDemand(real_temporary_file(*args, **kwargs))

    def refusing_replace(path: Path, target: object) -> Path:
        """Refuse only the temporary file's rename, when so scripted."""
        if failure == "replace" and path.name.endswith(".tmp"):
            message = "the rename was refused"
            raise OSError(message)
        return original_replace(path, typ.cast("Path", target))

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(writer.tempfile, "NamedTemporaryFile", wrapped)
        patch.setattr(Path, "replace", refusing_replace)
        with pytest.raises(OSError, match=r"refused|no space"):
            writer.atomic_write(output, payload)

    assert output.read_bytes() == prior, "a failed write changed the destination"
    assert _leftovers(scratch) == [], "a failed write left its temporary file"
