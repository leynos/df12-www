"""Run the stdlib handler example against the documented femtologging source."""

import io
import logging
from threading import Event

from femtologging import (
    StdlibHandlerAdapter,
    get_logger,
)

delivered = Event()


class _ObservedHandler(logging.StreamHandler):
    """Acknowledge delivery to the in-memory output."""

    def emit(self, record: logging.LogRecord) -> None:
        """Write the record and acknowledge its arrival."""
        super().emit(record)
        delivered.set()


output = io.StringIO()
stdlib_handler = _ObservedHandler(output)
stdlib_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
adapter = StdlibHandlerAdapter(stdlib_handler)
logger = get_logger("survey.adapter")
logger.set_level("INFO")
logger.set_propagate(False)
logger.add_handler(adapter)
try:
    logger.info("interface inspection complete")
    if not delivered.wait(timeout=2):
        message = "Record did not reach the adapter"
        raise RuntimeError(message)
    if not logger.flush_handlers():
        message = "Logging did not flush"
        raise RuntimeError(message)
    if output.getvalue() != "INFO: interface inspection complete\n":
        message = "Adapter output does not match the expected record"
        raise RuntimeError(message)
    print(output.getvalue(), end="")
finally:
    logger.remove_handler(adapter)
    adapter.close()
