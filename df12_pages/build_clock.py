"""The generator's one reading of the time.

Pages stamp the build date into their copy, so a build's output depends on the
day it runs. Reading the time here, and nowhere else, lets a caller fix that
date through the ``SOURCE_DATE_EPOCH`` convention
(https://reproducible-builds.org/specs/source-date-epoch/) and get the same
tree from the same sources on any day.
"""

from __future__ import annotations

import datetime as dt
import os

SOURCE_DATE_EPOCH = "SOURCE_DATE_EPOCH"


def build_time() -> dt.datetime:
    """Return the moment this build claims to have happened.

    Returns
    -------
    datetime.datetime
        The timezone-aware UTC time in ``SOURCE_DATE_EPOCH``, or the current
        time when the variable is unset or empty.

    Raises
    ------
    ValueError
        If ``SOURCE_DATE_EPOCH`` is set to anything other than a whole number
        of seconds that a date can represent. A malformed value stops the
        build, as the convention requires, rather than silently stamping
        today's date into a build that asked for another.

    Examples
    --------
    >>> import os
    >>> os.environ["SOURCE_DATE_EPOCH"] = "0"
    >>> build_time().isoformat()
    '1970-01-01T00:00:00+00:00'
    >>> del os.environ["SOURCE_DATE_EPOCH"]
    """
    raw = os.environ.get(SOURCE_DATE_EPOCH, "")
    if not raw:
        return dt.datetime.now(dt.UTC)
    message = f"{SOURCE_DATE_EPOCH} must be whole seconds since 1970, got {raw!r}"
    if not (raw.isascii() and raw.isdigit()):
        raise ValueError(message)
    try:
        return dt.datetime.fromtimestamp(int(raw), dt.UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise ValueError(message) from error
