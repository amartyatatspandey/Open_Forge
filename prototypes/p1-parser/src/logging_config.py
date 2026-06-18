"""Centralized logging configuration for all modules."""

import logging
import logging.handlers

from src.config import get_config


def setup_logging() -> None:
    """Configure logging once at startup.

    Logs go to both file and console. Call this once in main().
    """
    config = get_config()

    log_dir = config.pipeline.log_file.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        config.pipeline.log_file,
        maxBytes=10_000_000,
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.pipeline.log_level))
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger = logging.getLogger(__name__)
    logger.info("Logging initialized")
