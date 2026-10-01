"""Run the first record example against the documented femtologging source."""

import sys

from femtologging import (
    basicConfig,
    get_logger,
)

basicConfig(level="INFO", stream=sys.stdout)
logger = get_logger("survey.transport")
root = get_logger("root")

try:
    logger.info("record received", extra={"specimen": 42})
    if not logger.flush_handlers() or not root.flush_handlers():
        message = "Logging did not flush"
        raise RuntimeError(message)
finally:
    root.clear_handlers()
