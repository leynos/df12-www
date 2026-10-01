"""Run the console and file example against the documented femtologging source."""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from femtologging import (
    FemtoFileHandler,
    FemtoStreamHandler,
    get_logger,
)

delivered = Event()


class _DeliverySignal:
    """Acknowledge that dispatch reached the handler set."""

    def handle(self, logger: str, level: str, message: str) -> None:
        """Signal delivery without altering the record."""
        delivered.set()


signal = _DeliverySignal()


logger = get_logger("survey.output")
logger.set_level("INFO")
logger.set_propagate(False)
console = FemtoStreamHandler.stdout()

with TemporaryDirectory() as directory:
    path = Path(directory) / "survey.log"
    file_handler = FemtoFileHandler(str(path))
    for handler in (console, file_handler):
        logger.add_handler(handler)
    logger.add_handler(signal)
    try:
        logger.info("sample prepared")
        if not delivered.wait(timeout=2):
            message = "Record did not reach the handlers"
            raise RuntimeError(message)
        if not logger.flush_handlers():
            message = "Logging did not flush"
            raise RuntimeError(message)
        if "sample prepared" not in path.read_text():
            message = "File output is missing the expected record"
            raise RuntimeError(message)
    finally:
        logger.remove_handler(signal)
        for handler in (console, file_handler):
            logger.remove_handler(handler)
            handler.close()
