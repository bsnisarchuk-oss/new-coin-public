from __future__ import annotations

import asyncio
import logging
import os


class _IgnoreCancelledError(logging.Filter):
    """Suppress CancelledError tracebacks from APScheduler executor on shutdown."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type is not None and issubclass(exc_type, asyncio.CancelledError):
                return False
        return True


def setup_logging() -> None:
    log_format = os.getenv("LOG_FORMAT", "text").strip().lower()

    if log_format == "json":
        # Structured JSON logs for production (parseable by Loki / Datadog / etc.)
        try:
            from pythonjsonlogger.json import JsonFormatter  # type: ignore[import-untyped]
        except ImportError:
            # Older versions of python-json-logger use a different import path
            from pythonjsonlogger import jsonlogger as _jl  # type: ignore[import-untyped]
            JsonFormatter = _jl.JsonFormatter  # type: ignore[assignment]

        handler = logging.StreamHandler()
        handler.setFormatter(
            JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
            )
        )
        logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    else:
        # Human-readable logs for local development
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )

    # APScheduler catches BaseException in running jobs during shutdown and logs
    # CancelledError as an error — suppress it since it's expected on Ctrl+C.
    logging.getLogger("apscheduler.executors.default").addFilter(_IgnoreCancelledError())
