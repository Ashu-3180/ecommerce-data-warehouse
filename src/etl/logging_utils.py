"""Logging helpers for the ETL pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.config import LOG_DIR, LOG_LEVEL


def setup_etl_logging(log_name: str = "etl") -> logging.Logger:
    """Configure console + file logging under logs/."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("shopsphere.etl")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = logging.FileHandler(Path(LOG_DIR) / f"{log_name}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger
