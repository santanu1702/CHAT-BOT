"""
utils/logger.py — Centralized logging configuration
Logs to both console and logs/bot.log with rotation.
"""

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging() -> None:
    """
    Configure the root logger.
    - Console: INFO level, clean format
    - File: DEBUG level, detailed format, rotated at 5MB, keeps 3 backups
    """
    from bot.config import LOG_DIR

    log_file = os.path.join(LOG_DIR, "bot.log")

    # Root logger — capture everything from our code + libraries
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Silence noisy third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)

    # ── Console Handler ────────────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    ))

    # ── File Handler ───────────────────────────────────────────────────────────
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Attach handlers (avoid duplicates on re-import)
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    logging.info(f"Logging initialised. Log file: {log_file}")
