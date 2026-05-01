"""Centralised structured JSON logger for the Contract Risk Analyzer.

All application code imports from here — never use ``print()`` or configure
``logging`` directly in module files.

Usage
-----
    from src.utils.logger import get_logger

    logger = get_logger(__name__)

    logger.info("node_started", node="extractor", document_id=state["document_id"])
    logger.error("node_failed", node="extractor", error=str(e))

Design
------
We use ``structlog`` to emit structured JSON events.  Each log record
automatically includes ``timestamp``, ``level``, and ``logger`` fields.
Additional keyword arguments become top-level JSON keys — easy to parse
in CloudWatch Logs Insights or Datadog.

If ``structlog`` is not installed (edge case in tests) we fall back gracefully
to the standard library ``logging`` module.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

try:
    import structlog

    _STRUCTLOG_AVAILABLE = True
except ImportError:
    _STRUCTLOG_AVAILABLE = False


def _configure_structlog() -> None:
    """One-time structlog configuration called on first import."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(os.getenv("LOG_LEVEL", "INFO"))
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


_structlog_configured = False


def get_logger(name: str) -> Any:
    """Return a structured logger bound to *name*.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module.

    Returns
    -------
    structlog.BoundLogger or logging.Logger
        A logger that accepts keyword arguments as structured fields.
    """
    global _structlog_configured  # noqa: PLW0603

    if _STRUCTLOG_AVAILABLE:
        if not _structlog_configured:
            _configure_structlog()
            _structlog_configured = True
        return structlog.get_logger(name)

    # Fallback: plain logging
    _logger = logging.getLogger(name)
    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt='{"timestamp":"%(asctime)s","level":"%(levelname)s",'
                '"logger":"%(name)s","event":"%(message)s"}',
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        _logger.addHandler(handler)
        _logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    return _logger
