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
)
def test_publication_always_ends_in_a_recoverable_state(
    tmp_path: Path,
    previous: set[str],
    fresh: set[str],
    fail_at: frozenset[int],
    interrupt: bool,  # noqa: FBT001 - a generated boolean, not an API flag
) -> None:
    """Wherever a failure lands, no file is lost and no half-state survives."""
    destination = Path(tempfile.mkdtemp(dir=tmp_path)) / "out"
    destination.mkdir()
    for stem in previous:
        (destination / f"{stem}.json").write_text(f"prev:{stem}", encoding="utf-8")

    calls = {"n": 0}

    def mover(source: Path, target: Path) -> object:
        """Move for real, failing at each generated position."""
        calls["n"] += 1
        if calls["n"] in fail_at:
            if interrupt:
                raise KeyboardInterrupt
            message = "provoked"
            raise OSError(message)
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
                    # The second link matters as much as the first: dropping
                    # either `from` in the production code would keep the
                    # wrapper type while losing the diagnostic cause.
                    match inconsistent.__cause__:
                        case KeyboardInterrupt() if interrupt:
                            pass
                        case OSError() if not interrupt:
                            pass
                        case unexpected:
                            pytest.fail(
                                f"the inconsistent-destination report should "
                                f"chain from the provoked "
                                f"{'interrupt' if interrupt else 'OSError'}; "
                                f"got {unexpected!r}"
                            )
                case unexpected:
                    pytest.fail(
                        f"the report should chain from the rollback's own "
                        f"failure; got {unexpected!r}"
                    )
        case _:
            # Any other failure: the rollback ran, so the destination holds
            # wholly the previous run's results and staging is swept.
            assert published == {stem: f"prev:{stem}" for stem in previous}, (
                f"a rolled-back publication should restore the previous run "
                f"exactly; got {published}"
            )
            assert kept == [], f"staging survived a rolled-back failure: {kept}"
