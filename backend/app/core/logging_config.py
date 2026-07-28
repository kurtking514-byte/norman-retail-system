import json
import logging
import sys
from typing import Any

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    """Emit log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging() -> None:
    level = logging.DEBUG if settings.ENVIRONMENT != "production" else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    # Clear existing handlers and apply our own
    logging.basicConfig(level=level, handlers=[handler], force=True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
