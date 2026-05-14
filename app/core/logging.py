"""
Structured logging with structlog.
Outputs JSON in production, colored console in development.
"""
import logging
import sys

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def add_app_context(logger: logging.Logger, method: str, event_dict: EventDict) -> EventDict:
    """Inject app-level metadata into every log record."""
    event_dict["app"] = settings.app_name
    event_dict["env"] = settings.app_env
    event_dict["version"] = settings.app_version
    return event_dict


def setup_logging() -> None:
    """Configure structlog + stdlib logging."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        add_app_context,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # JSON for log aggregators (Datadog, Loki, CloudWatch…)
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Pretty console for local development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    return structlog.get_logger(name)
