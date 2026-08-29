"""Process logging for discovery and replay troubleshooting.

Messages are extra-based (institution, run_id, locators, coverage). A filter
scrubs email, phone, and long digit runs if they slip into the message text.
"""

from __future__ import annotations

import logging
from typing import Any

from interfaces_ai.redact import redact_text

_CONFIGURED = False
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _scrub_arg(v) for k, v in record.args.items()}
            else:
                record.args = tuple(_scrub_arg(arg) for arg in record.args)
        return True


def _scrub_arg(value: Any) -> Any:
    return redact_text(value) if isinstance(value, str) else value


def configure_logging(level: str = "INFO") -> None:
    """Idempotent. Call from create_app and the CLI."""
    global _CONFIGURED
    root = logging.getLogger("interfaces_ai")
    numeric = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric)
    if not _CONFIGURED:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        handler.addFilter(RedactFilter())
        root.addHandler(handler)
        root.propagate = False
        _CONFIGURED = True
    for handler in root.handlers:
        handler.setLevel(numeric)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
