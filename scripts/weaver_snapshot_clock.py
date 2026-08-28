"""The passage of time, as something a caller can supply.

Two of this harness's waits — the lock's timeout and the server's readiness
poll — are loops over the clock, and both are the kind of thing a test either
cannot exercise or must sit through in real seconds. Neither loop's logic is
about the clock, so the clock is passed in and the loops become ordinary code
to check: how many attempts, how long between them, what the deadline does.

The default is the real one, bound at each function's definition, so callers
that do not care never see this module.
"""

from __future__ import annotations

import time
import typing as typ


class Clock(typ.Protocol):
    """What the waits in this harness need from time itself."""

    def monotonic(self) -> float:
        """Return a monotonically increasing time in seconds."""
        ...  # pragma: no cover - a protocol has no body

    def sleep(self, seconds: float, /) -> None:
        """Pause for roughly ``seconds``."""
        ...  # pragma: no cover - a protocol has no body


class _SystemClock:
    """The real clock, which is what production always uses."""

    def monotonic(self) -> float:
        """Return `time.monotonic`."""
        return time.monotonic()

    def sleep(self, seconds: float, /) -> None:
        """Sleep through `time.sleep`."""
        time.sleep(seconds)


SYSTEM_CLOCK: typ.Final[Clock] = _SystemClock()
