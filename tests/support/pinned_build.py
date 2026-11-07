"""The date the site-build suites build under.

Ten Netsuke pages stamp the build date into a heading, and the width of that
text reaches the bounding boxes the committed render baseline hashes. A suite
that built under today's date would pass or fail by the calendar, so
``tests/conftest.py`` fixes it for the whole session. The date is the one
``tests/support/netsuke_baseline.json`` was recorded under; nothing else about
it matters, and it never needs to move.
"""

from __future__ import annotations

import datetime as dt

PINNED_BUILD_TIME = dt.datetime(2026, 10, 2, 12, tzinfo=dt.UTC)
PINNED_SOURCE_DATE_EPOCH = str(int(PINNED_BUILD_TIME.timestamp()))
PINNED_STATUS_LINE = "Status on 2 October 2026"
