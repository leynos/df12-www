"""Publishing the generated icon macro, or leaving the old one alone.

Writing straight into the committed file is not failure-atomic, and a
truncated macro that still parses is worse than one that does not. These cover
each way the publication can fail, and what the output holds afterwards.
"""

from __future__ import annotations

import re
import typing as typ
from pathlib import Path

import pytest

from tests.support.weaver_harness import load
from tests.support.weaver_icons import _minimal_inputs

if typ.TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_WEAVER = REPO_ROOT / "public" / "weaver"
WEAVER_TEMPLATES = REPO_ROOT / "templates" / "weaver"
WEAVER_STYLES = REPO_ROOT / "src" / "styles"
COMPILED_STYLESHEET = PUBLIC_WEAVER / "assets" / "styles" / "weaver.css"


# `{{ icon('name') }}` as the templates write it, in either quote form.
ICON_CALL = re.compile(r"""icon\(\s*(?:'([^']+)'|"([^"]+)")""")


# What the output holds before a run starts: not a macro at all, just a marker
# distinctive enough to tell "still there" from "replaced" without comparing
# against whatever the generator would produce.
STALE = "a previous macro, which must survive a failed publication"


def _published(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Return the output path, seeded with content the run will replace."""
    output = tmp_path / "_icons.jinja"
    output.write_text(STALE, encoding="utf-8")
    monkeypatch.setattr(generator, "OUTPUT", output)
    return output


def _leftovers(directory: Path) -> list[str]:
    """Name any temporary file the publication left beside the output."""
    return sorted(
        path.name
        for path in directory.iterdir()
        if path.name.startswith(".") and path.name.endswith(".tmp")
    )


def test_a_failure_writing_the_temporary_file_leaves_the_previous_macro(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The committed macro is what the next build renders, so a partial one is fatal.

    A write that stops partway would leave a truncated macro where a valid one
    was, and a truncated macro that still parses is worse than one that does
    not. Nothing is written to the real path until the whole thing is on disk.
    """
    _minimal_inputs(generator, monkeypatch, tmp_path)
    output = _published(generator, monkeypatch, tmp_path)

    # The temporary file is opened by the shared writer, not the generator,
    # so the failure is provoked where the write now happens.
    writer = load("atomic_write")
    real = writer.tempfile.NamedTemporaryFile

    def fails_midway(*args: object, **kwargs: object) -> object:
        """Hand back a real handle whose write refuses."""
        handle = real(*args, **kwargs)

        def refuse(_data: object) -> int:
            """Refuse the write, the way a full disk would."""
            message = "No space left on device"
            raise OSError(message)

        handle.write = refuse
        return handle

    monkeypatch.setattr(writer.tempfile, "NamedTemporaryFile", fails_midway)

    with pytest.raises(SystemExit) as caught:
        generator.main()

    message = str(caught.value.code)
    assert str(output) in message, (
        f"the message should name the output; got {message!r}"
    )
    assert output.read_text(encoding="utf-8") == STALE, (
        "a failed write replaced or truncated the previous macro"
    )
    assert _leftovers(tmp_path) == [], (
        f"a partial macro was left beside the real one: {_leftovers(tmp_path)}"
    )


def test_a_failure_replacing_the_output_leaves_the_previous_macro(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The rename is the moment of publication, and it can fail too."""
    _minimal_inputs(generator, monkeypatch, tmp_path)
    output = _published(generator, monkeypatch, tmp_path)

    def refuse(_self: Path, _target: object) -> Path:
        """Refuse the rename, the way a permissions change would."""
        message = "Permission denied"
        raise PermissionError(message)

    monkeypatch.setattr(Path, "replace", refuse)

    with pytest.raises(SystemExit) as caught:
        generator.main()

    message = str(caught.value.code)
    assert str(output) in message, (
        f"the message should name the output; got {message!r}"
    )
    assert "could not be written" in message, (
        f"the publication handler should be the one that fired; got {message!r}"
    )
    monkeypatch.undo()
    assert output.read_text(encoding="utf-8") == STALE, (
        "a failed rename left the previous macro changed"
    )
    assert _leftovers(tmp_path) == [], (
        f"the temporary file outlived the failed rename: {_leftovers(tmp_path)}"
    )


def test_a_successful_publication_replaces_the_whole_file(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Wholly replaced, not appended to, and nothing left behind."""
    _minimal_inputs(generator, monkeypatch, tmp_path)
    output = _published(generator, monkeypatch, tmp_path)

    assert generator.main() == 0, "a successful run should report success"

    published = output.read_text(encoding="utf-8")
    assert STALE not in published, (
        "the previous macro survived inside the new one, so the file was not "
        f"replaced but added to; it now reads {published[:120]!r}"
    )
    assert published == generator.build_macro(), (
        "the published file should be exactly what the generator produced"
    )
    assert _leftovers(tmp_path) == [], (
        f"a temporary file outlived a successful publication: {_leftovers(tmp_path)}"
    )


def test_an_unreadable_output_is_reported_separately(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The read and the write are distinct failures and say so distinctly."""
    _minimal_inputs(generator, monkeypatch, tmp_path)

    # A directory exists and cannot be read as text, which is the read handler's
    # case and not the write handler's.
    output = tmp_path / "_icons.jinja"
    output.mkdir()
    monkeypatch.setattr(generator, "OUTPUT", output)

    with pytest.raises(SystemExit) as caught:
        generator.main()

    message = str(caught.value.code)
    assert str(output) in message, (
        f"the message should name the output; got {message!r}"
    )
    assert "could not be read" in message, (
        f"the read handler should be the one that fired; got {message!r}"
    )
