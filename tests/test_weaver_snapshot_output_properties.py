"""Publication invariants, held over generated file sets and failure points.

The example suite in ``tests/test_weaver_snapshot_output.py`` provokes the
failures someone thought of — a full disk at the publication move, a Ctrl-C
mid-rollback. This asserts what must hold wherever the failure lands: the
destination is either wholly the previous run's results or wholly this run's,
and when even the rollback is denied, every previous file survives somewhere
recoverable and the staging directory is kept rather than swept.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.support.weaver_harness import load

output = load("weaver_snapshot_output")

# Deterministic and quiet, as elsewhere in the property suites; the
# function-scoped `tmp_path` is safe to reuse because every example works in
# a directory of its own.
SETTINGS = settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
    ],
)

# Small alphabets keep the example space dense: what varies usefully is the
# overlap between the two sets and where the failures land, not the names.
STEMS = st.sets(st.sampled_from(["a", "b", "c", "d"]), max_size=3)

# Which move calls fail. Publication of up to seven files makes at most ten
# calls including the rollback, so positions beyond that mean "no failure".
POSITIONS = st.frozensets(st.integers(min_value=1, max_value=10), max_size=3)


@SETTINGS
@given(
    previous=STEMS,
    fresh=STEMS,
    fail_at=POSITIONS,
    interrupt=st.booleans(),
    late=st.booleans(),
)
def test_publication_always_ends_in_a_recoverable_state(  # noqa: PLR0913 - each parameter is a generated dimension, not an API
    tmp_path: Path,
    previous: set[str],
    fresh: set[str],
    fail_at: frozenset[int],
    interrupt: bool,  # noqa: FBT001 - a generated boolean, not an API flag
    late: bool,  # noqa: FBT001 - a generated boolean, not an API flag
) -> None:
    """Wherever a failure lands, no file is lost and no half-state survives.

    `late` decides whether an injected failure fires before the rename or
    just after it has completed — the window a real interrupt has between a
    returned syscall and the caller's next statement.
    """
    destination = Path(tempfile.mkdtemp(dir=tmp_path)) / "out"
    destination.mkdir()
    for stem in previous:
        (destination / f"{stem}.json").write_text(f"prev:{stem}", encoding="utf-8")

    calls = {"n": 0}
    raised: list[BaseException] = []

    def mover(source: Path, target: Path) -> object:
        """Move for real, failing at each generated position."""
        calls["n"] += 1
        if calls["n"] in fail_at:
            # The text names the call so the message assertions below can
            # tell one injected failure from another.
            failure: BaseException = (
                KeyboardInterrupt()
                if interrupt
                else OSError(f"provoked at move {calls['n']}")
            )
            # Retained so the chain assertions below can demand the exact
            # objects, not merely their types.
            raised.append(failure)
            if late:
                source.replace(target)
            raise failure
        return source.replace(target)

    outcome: BaseException | None = None
    try:
        with output._staged(destination, ".json", mover) as staging:
            for stem in fresh:
                (staging / f"{stem}.json").write_text(f"new:{stem}", encoding="utf-8")
    except (SystemExit, KeyboardInterrupt, OSError) as exc:
        outcome = exc

    published = {
        path.stem: path.read_text(encoding="utf-8")
        for path in destination.glob("*.json")
    }
    kept = list(destination.parent.glob(f".{destination.name}-*"))

    match outcome:
        case None:
            # Success: wholly this run's results, staging swept.
            assert published == {stem: f"new:{stem}" for stem in fresh}, (
                f"a clean publication should land exactly the capture; got {published}"
            )
            assert kept == [], f"staging survived a clean publication: {kept}"
        case SystemExit() as stop if "inconsistent state" in str(stop.code):
            # The rollback itself was denied: staging must be kept, and every
            # previous file must survive in the destination or its `replaced/`.
            assert len(kept) == 1, f"expected the staging directory kept; got {kept}"
            for stem in previous:
                content = f"prev:{stem}"
                in_place = published.get(stem) == content
                aside = kept[0] / "replaced" / f"{stem}.json"
                rescued = aside.is_file() and (
                    aside.read_text(encoding="utf-8") == content
                )
                assert in_place or rescued, (
                    f"{stem} from the previous run is unrecoverable: "
                    f"destination holds {published}, replaced/ holds "
                    f"{sorted(p.name for p in (kept[0] / 'replaced').glob('*'))}"
                )
            match stop.__cause__:
                case output._InconsistentDestinationError() as inconsistent:
                    # The second link matters as much as the first, and it is
                    # asserted by identity: an interrupted rollback chains
                    # from the interruption that landed *inside* the rollback
                    # (the second exception raised), while a rollback whose
                    # restores merely failed chains from the publication
                    # failure that forced it (the first). Dropping either
                    # `from` in the production code fails this.
                    expected = raised[1] if interrupt else raised[0]
                    origin = (
                        "rollback interruption" if interrupt else "publication failure"
                    )
                    assert inconsistent.__cause__ is expected, (
                        f"the report should chain from the exact {origin}; got "
                        f"{inconsistent.__cause__!r} rather than {expected!r}"
                    )
                    if not interrupt:
                        # The chain carries the publication failure, so the
                        # failures that stopped the rollback must each be
                        # reported in the message instead.
                        for rollback_failure in raised[1:]:
                            assert str(rollback_failure) in str(stop.code), (
                                f"the report should name the rollback failure "
                                f"{rollback_failure!r}; got {stop.code!r}"
                            )
                case unexpected:
                    pytest.fail(
                        f"the SystemExit should chain through the "
                        f"inconsistent-destination report; got {unexpected!r}"
                    )
        case _:
            # Any other failure: the rollback ran, so the destination holds
            # wholly the previous run's results and staging is swept.
            assert published == {stem: f"prev:{stem}" for stem in previous}, (
                f"a rolled-back publication should restore the previous run "
                f"exactly; got {published}"
            )
            assert kept == [], f"staging survived a rolled-back failure: {kept}"
