"""
Structured logging configuration using structlog.

This module provides JSON-formatted logs with correlation IDs,
timestamps, and context information for better observability.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from structlog.types import FilteringBoundLogger


def setup_logging(level: str = "INFO", log_file: str | None = None, json_logs: bool = True) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for file logging
        json_logs: If True, use JSON formatting (recommended for production)
    """
    if log_file:
        Path("logs").mkdir(exist_ok=True)
        log_file_path = f"logs/{log_file}"
    else:
        log_file_path = None  # noqa: F841

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Structured logger instance with context binding support

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("user_created", user_id=123, email="user@example.com")
    """
    return structlog.get_logger(name or __name__)


def bind_context(**kwargs: Any) -> None:
    """
    Bind context variables that will be included in all subsequent log entries.

    This is useful for adding correlation IDs, user IDs, or request IDs
    that should appear in all logs within a request context.

    Args:
        **kwargs: Context key-value pairs to bind

    Example:
        >>> bind_context(request_id="abc-123", user_id=456)
        >>> logger.info("processing_request")  # Will include request_id and user_id
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()