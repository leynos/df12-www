"""The generator reads the time in one place, and a caller can fix it."""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

from df12_pages.build_clock import SOURCE_DATE_EPOCH, build_time

PACKAGE = Path(__file__).resolve().parents[1] / "df12_pages"
CLOCK_READS = frozenset({"now", "utcnow", "today"})


def test_an_unset_epoch_reads_the_current_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the variable, a build is stamped with the moment it runs."""
    monkeypatch.delenv(SOURCE_DATE_EPOCH, raising=False)
    before = dt.datetime.now(dt.UTC)
    assert before <= build_time() <= dt.datetime.now(dt.UTC)


def test_an_empty_epoch_reads_the_current_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty variable is treated as unset, as a CI default often leaves it."""
    monkeypatch.setenv(SOURCE_DATE_EPOCH, "")
    before = dt.datetime.now(dt.UTC)
    assert before <= build_time() <= dt.datetime.now(dt.UTC)


def test_an_epoch_fixes_the_time_in_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    """The variable names one UTC instant, whatever the local timezone is."""
    monkeypatch.setenv(SOURCE_DATE_EPOCH, "1791028800")
    assert build_time() == dt.datetime(2026, 10, 3, 12, tzinfo=dt.UTC)
    assert build_time().utcoffset() == dt.timedelta(0)


@pytest.mark.parametrize(
    "value",
    ["yesterday", "-1", "1.5", " 1", "٣", "9" * 40],
    ids=["word", "negative", "fraction", "padded", "non-ascii-digit", "overflow"],
)
def test_a_malformed_epoch_stops_the_build(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """A date that was asked for and cannot be honoured is an error, not today."""
    monkeypatch.setenv(SOURCE_DATE_EPOCH, value)
    with pytest.raises(ValueError, match=SOURCE_DATE_EPOCH):
        build_time()


def _clock_reads(source: Path) -> list[str]:
    """List each ``.now()``-style call in a module as ``path:line``."""
    return [
        f"{source.name}:{node.lineno}"
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in CLOCK_READS
    ]


def test_the_generator_has_one_clock() -> None:
    """A page stamped from another clock would ignore ``SOURCE_DATE_EPOCH``."""
    reads = [
        read
        for source in sorted(PACKAGE.rglob("*.py"))
        if source.name != "build_clock.py"
        for read in _clock_reads(source)
    ]
    assert not reads, f"read the time through build_clock.build_time: {reads}"
