"""Run the request context example against the documented femtologging source."""

import json
import typing as typ
from threading import Event

from femtologging import (
    StreamHandlerBuilder,
    get_logger,
)

delivered = Event()


def _json_record(record: dict[str, object]) -> str:
    """Format the message and fields, acknowledging formatter delivery."""
    result = json.dumps(
        {
            "message": record["message"],
            "fields": typ.cast("dict[str, object]", record["metadata"])["key_values"],
        },
        sort_keys=True,
    )
    delivered.set()
    return result


logger = get_logger("service.request")
logger.set_level("INFO")
logger.set_propagate(False)
handler = StreamHandlerBuilder.stdout().with_formatter(_json_record).build()
logger.add_handler(handler)
try:
    # Per-call fields also suit concurrent asyncio tasks.
    logger.info("request accepted", extra={"request_id": 42})
    if not delivered.wait(timeout=2):
        message = "Record did not reach the formatter"
        raise RuntimeError(message)
    if not logger.flush_handlers():
        message = "Logging did not flush"
        raise RuntimeError(message)
finally:
    logger.remove_handler(handler)
    handler.close()
